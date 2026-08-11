#!/usr/bin/env bash
set -euo pipefail

: "${OPENSTACK_DEPLOY_PASSWORD:?Set OPENSTACK_DEPLOY_PASSWORD in the runtime environment.}"
export OPENSTACK_DEPLOY_PASSWORD

# Prefer the controller-hosted local repo when it is available. Fall back to
# the original remote repos only when the local repo is missing or incomplete.
OPENSTACK_LOCAL_REPO_ID="openstack-local"
OPENSTACK_LOCAL_REPO_FILE="/etc/yum.repos.d/${OPENSTACK_LOCAL_REPO_ID}.repo"
OPENSTACK_LOCAL_FILE_BASEURL="file:///opt/openstack_repo"
OPENSTACK_LOCAL_FTP_BASEURL="ftp://192.168.234.151/openstack_repo"

repo_url_reachable() {
  local url="$1"
  if command -v curl >/dev/null 2>&1; then
    curl -fsS --connect-timeout 5 "$url" >/dev/null 2>&1
  else
    python3 - "$url" <<'PY'
import sys
import urllib.request

try:
    with urllib.request.urlopen(sys.argv[1], timeout=5) as resp:
        sys.exit(0 if resp.status < 400 else 1)
except Exception:
    sys.exit(1)
PY
  fi
}

ensure_openstack_local_repo() {
  local baseurl=""
  if [ -f /opt/openstack_repo/repodata/repomd.xml ]; then
    baseurl="${OPENSTACK_LOCAL_FILE_BASEURL}"
  elif repo_url_reachable "${OPENSTACK_LOCAL_FTP_BASEURL}/repodata/repomd.xml"; then
    baseurl="${OPENSTACK_LOCAL_FTP_BASEURL}"
  else
    return 1
  fi

  cat > "${OPENSTACK_LOCAL_REPO_FILE}" <<EOF
[${OPENSTACK_LOCAL_REPO_ID}]
name=OpenStack Local Preferred Repo
baseurl=${baseurl}
enabled=1
gpgcheck=0
skip_if_unavailable=1
EOF
}

dnf_install_prefer_local() {
  if ensure_openstack_local_repo; then
    if dnf -y --disablerepo='*' --enablerepo="${OPENSTACK_LOCAL_REPO_ID}" install "$@"; then
      return 0
    fi
    echo "Local repo install failed, falling back to remote repos..." >&2
  fi
  return 1
}

dnf_makecache_prefer_local() {
  if ensure_openstack_local_repo; then
    if dnf makecache --disablerepo='*' --enablerepo="${OPENSTACK_LOCAL_REPO_ID}"; then
      return 0
    fi
    echo "Local repo makecache failed, falling back to remote repos..." >&2
  fi
  return 1
}

# Install and initialize the Linux bridge agent on the compute node.
# The provider network maps to ens34, which must stay free of any IP config.

cat > /etc/sysctl.d/99-openstack-neutron.conf <<'EOF'
net.bridge.bridge-nf-call-iptables = 1
net.bridge.bridge-nf-call-ip6tables = 1
EOF
modprobe br_netfilter || true
sysctl --system >/dev/null

if ! dnf_install_prefer_local openstack-neutron-linuxbridge ebtables ipset; then
  dnf -y install openstack-neutron-linuxbridge ebtables ipset
fi

# Enable the experimental Linux bridge feature flag required by this package set.
python3 - <<'PY'
import configparser
import os
from urllib.parse import quote
password_urlencoded = quote(os.environ["OPENSTACK_DEPLOY_PASSWORD"], safe="")

path = "/etc/neutron/neutron.conf"
cfg = configparser.RawConfigParser()
cfg.read(path)
for sec in ("DEFAULT", "oslo_concurrency", "experimental"):
    if sec != "DEFAULT" and not cfg.has_section(sec):
        cfg.add_section(sec)
cfg.set("DEFAULT", "transport_url", f"rabbit://openstack:{password_urlencoded}@controller")
cfg.set("DEFAULT", "auth_strategy", "keystone")
cfg.set("oslo_concurrency", "lock_path", "/var/lib/neutron/tmp")
cfg.set("experimental", "linuxbridge", "true")
with open(path, "w") as f:
    cfg.write(f)
PY

python3 - <<'PY'
import configparser
import os
from urllib.parse import quote
password_urlencoded = quote(os.environ["OPENSTACK_DEPLOY_PASSWORD"], safe="")

path = "/etc/neutron/plugins/ml2/linuxbridge_agent.ini"
cfg = configparser.RawConfigParser()
cfg.read(path)
for sec in ("linux_bridge", "vxlan", "securitygroup"):
    if not cfg.has_section(sec):
        cfg.add_section(sec)
cfg.set("linux_bridge", "physical_interface_mappings", "provider:ens34")
cfg.set("vxlan", "enable_vxlan", "true")
cfg.set("vxlan", "local_ip", "192.168.234.150")
cfg.set("vxlan", "l2_population", "true")
cfg.set("securitygroup", "enable_security_group", "true")
cfg.set("securitygroup", "firewall_driver", "neutron.agent.linux.iptables_firewall.IptablesFirewallDriver")
with open(path, "w") as f:
    cfg.write(f)
PY

systemctl enable --now neutron-linuxbridge-agent

# Restart nova-compute so it re-reads the Neutron integration settings cleanly.
systemctl restart openstack-nova-compute
systemctl status neutron-linuxbridge-agent --no-pager || true
