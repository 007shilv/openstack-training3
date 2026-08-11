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

# Install and initialize nova-compute on the compute node.
# This deployment uses qemu because nested virtualization may not be available.

if ! dnf_install_prefer_local qemu-kvm libvirt openstack-nova-compute; then
  dnf -y install qemu-kvm libvirt openstack-nova-compute
fi

python3 - <<'PY'
import configparser
import os
from urllib.parse import quote
password_urlencoded = quote(os.environ["OPENSTACK_DEPLOY_PASSWORD"], safe="")

path = "/etc/nova/nova.conf"
cfg = configparser.RawConfigParser()
cfg.read(path)
for sec in ("DEFAULT", "api", "keystone_authtoken", "service_user", "vnc", "glance", "oslo_concurrency", "placement", "neutron", "libvirt", "cinder"):
    if sec != "DEFAULT" and not cfg.has_section(sec):
        cfg.add_section(sec)
cfg.set("DEFAULT", "state_path", "/var/lib/nova")
cfg.set("DEFAULT", "transport_url", f"rabbit://openstack:{password_urlencoded}@controller")
cfg.set("DEFAULT", "my_ip", "192.168.234.150")
cfg.set("DEFAULT", "compute_driver", "libvirt.LibvirtDriver")
cfg.set("DEFAULT", "use_neutron", "true")
cfg.set("DEFAULT", "firewall_driver", "nova.virt.firewall.NoopFirewallDriver")
cfg.set("api", "auth_strategy", "keystone")
cfg.set("keystone_authtoken", "www_authenticate_uri", "http://controller:5000/")
cfg.set("keystone_authtoken", "auth_url", "http://controller:5000/")
cfg.set("keystone_authtoken", "memcached_servers", "controller:11211")
cfg.set("keystone_authtoken", "auth_type", "password")
cfg.set("keystone_authtoken", "project_domain_name", "Default")
cfg.set("keystone_authtoken", "user_domain_name", "Default")
cfg.set("keystone_authtoken", "project_name", "service")
cfg.set("keystone_authtoken", "username", "nova")
cfg.set("keystone_authtoken", "password", os.environ["OPENSTACK_DEPLOY_PASSWORD"])
cfg.set("service_user", "send_service_user_token", "true")
cfg.set("service_user", "auth_url", "http://controller:5000/v3")
cfg.set("service_user", "auth_strategy", "keystone")
cfg.set("service_user", "auth_type", "password")
cfg.set("service_user", "project_domain_name", "Default")
cfg.set("service_user", "project_name", "service")
cfg.set("service_user", "user_domain_name", "Default")
cfg.set("service_user", "username", "nova")
cfg.set("service_user", "password", os.environ["OPENSTACK_DEPLOY_PASSWORD"])
cfg.set("vnc", "enabled", "true")
cfg.set("vnc", "server_listen", "0.0.0.0")
cfg.set("vnc", "server_proxyclient_address", "$my_ip")
cfg.set("vnc", "novncproxy_base_url", "http://controller:6080/vnc_auto.html")
cfg.set("glance", "api_servers", "http://controller:9292")
cfg.set("oslo_concurrency", "lock_path", "/var/lib/nova/tmp")
cfg.set("placement", "region_name", "RegionOne")
cfg.set("placement", "project_domain_name", "Default")
cfg.set("placement", "project_name", "service")
cfg.set("placement", "auth_type", "password")
cfg.set("placement", "user_domain_name", "Default")
cfg.set("placement", "auth_url", "http://controller:5000/v3")
cfg.set("placement", "username", "placement")
cfg.set("placement", "password", os.environ["OPENSTACK_DEPLOY_PASSWORD"])
cfg.set("neutron", "auth_url", "http://controller:5000")
cfg.set("neutron", "auth_type", "password")
cfg.set("neutron", "project_domain_name", "Default")
cfg.set("neutron", "user_domain_name", "Default")
cfg.set("neutron", "region_name", "RegionOne")
cfg.set("neutron", "project_name", "service")
cfg.set("neutron", "username", "neutron")
cfg.set("neutron", "password", os.environ["OPENSTACK_DEPLOY_PASSWORD"])
cfg.set("libvirt", "virt_type", "qemu")
cfg.set("cinder", "os_region_name", "RegionOne")
with open(path, "w") as f:
    cfg.write(f)
PY

# Antelope persists compute node identity to disk; pre-create the stable file.
install -d -o nova -g nova /var/lib/nova
if [ ! -f /etc/nova/compute_id ]; then
  python3 - <<'PY'
from pathlib import Path
import uuid

Path("/etc/nova/compute_id").write_text(f"{uuid.uuid4()}\n", encoding="utf-8")
PY
  chmod 0644 /etc/nova/compute_id
fi

systemctl enable --now libvirtd
systemctl enable --now openstack-nova-compute
