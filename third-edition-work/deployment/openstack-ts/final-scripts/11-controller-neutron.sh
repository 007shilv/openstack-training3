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

# Install and initialize Neutron services on the controller node.
# This layout uses ML2 + Linux bridge + VXLAN tenant networks.
# The provider network maps to ens34, which must stay free of any IP config.

DB_PASS="${OPENSTACK_DEPLOY_PASSWORD}"
SERVICE_PASS="${OPENSTACK_DEPLOY_PASSWORD}"

cat > /etc/sysctl.d/99-openstack-neutron.conf <<'EOF'
net.bridge.bridge-nf-call-iptables = 1
net.bridge.bridge-nf-call-ip6tables = 1
EOF
modprobe br_netfilter || true
sysctl --system >/dev/null

mysql -uroot <<EOF
CREATE DATABASE IF NOT EXISTS neutron;
GRANT ALL PRIVILEGES ON neutron.* TO 'neutron'@'localhost' IDENTIFIED BY '${DB_PASS}';
GRANT ALL PRIVILEGES ON neutron.* TO 'neutron'@'127.0.0.1' IDENTIFIED BY '${DB_PASS}';
GRANT ALL PRIVILEGES ON neutron.* TO 'neutron'@'%' IDENTIFIED BY '${DB_PASS}';
FLUSH PRIVILEGES;
EOF

source /root/admin-openrc
openstack user show neutron >/dev/null 2>&1 || openstack user create --domain default --password "${SERVICE_PASS}" neutron
openstack role add --project service --user neutron admin || true
openstack service show neutron >/dev/null 2>&1 || openstack service create --name neutron --description "OpenStack Networking" network
openstack endpoint create --region RegionOne network public http://controller:9696 || true
openstack endpoint create --region RegionOne network internal http://controller:9696 || true
openstack endpoint create --region RegionOne network admin http://controller:9696 || true

if ! dnf_install_prefer_local openstack-neutron openstack-neutron-ml2 openstack-neutron-linuxbridge ebtables ipset; then
  dnf -y install openstack-neutron openstack-neutron-ml2 openstack-neutron-linuxbridge ebtables ipset
fi
ln -sf /etc/neutron/plugins/ml2/ml2_conf.ini /etc/neutron/plugin.ini

# Enable the experimental Linux bridge feature flag required by this package set.
python3 - <<'PY'
import configparser
import os
from urllib.parse import quote
password_urlencoded = quote(os.environ["OPENSTACK_DEPLOY_PASSWORD"], safe="")

path = "/etc/neutron/neutron.conf"
cfg = configparser.RawConfigParser()
cfg.read(path)
for sec in ("DEFAULT", "database", "keystone_authtoken", "nova", "oslo_concurrency", "experimental"):
    if sec != "DEFAULT" and not cfg.has_section(sec):
        cfg.add_section(sec)
cfg.set("database", "connection", f"mysql+pymysql://neutron:{password_urlencoded}@127.0.0.1/neutron")
cfg.set("DEFAULT", "core_plugin", "ml2")
cfg.set("DEFAULT", "service_plugins", "router")
cfg.set("DEFAULT", "transport_url", f"rabbit://openstack:{password_urlencoded}@controller")
cfg.set("DEFAULT", "auth_strategy", "keystone")
cfg.set("DEFAULT", "notify_nova_on_port_status_changes", "true")
cfg.set("DEFAULT", "notify_nova_on_port_data_changes", "true")
cfg.set("keystone_authtoken", "www_authenticate_uri", "http://controller:5000")
cfg.set("keystone_authtoken", "auth_url", "http://controller:5000")
cfg.set("keystone_authtoken", "memcached_servers", "controller:11211")
cfg.set("keystone_authtoken", "auth_type", "password")
cfg.set("keystone_authtoken", "project_domain_name", "Default")
cfg.set("keystone_authtoken", "user_domain_name", "Default")
cfg.set("keystone_authtoken", "project_name", "service")
cfg.set("keystone_authtoken", "username", "neutron")
cfg.set("keystone_authtoken", "password", os.environ["OPENSTACK_DEPLOY_PASSWORD"])
cfg.set("nova", "auth_url", "http://controller:5000")
cfg.set("nova", "auth_type", "password")
cfg.set("nova", "project_domain_name", "Default")
cfg.set("nova", "user_domain_name", "Default")
cfg.set("nova", "region_name", "RegionOne")
cfg.set("nova", "project_name", "service")
cfg.set("nova", "username", "nova")
cfg.set("nova", "password", os.environ["OPENSTACK_DEPLOY_PASSWORD"])
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

path = "/etc/neutron/plugins/ml2/ml2_conf.ini"
cfg = configparser.RawConfigParser()
cfg.read(path)
for sec in ("ml2", "ml2_type_flat", "ml2_type_vxlan", "securitygroup"):
    if not cfg.has_section(sec):
        cfg.add_section(sec)
cfg.set("ml2", "type_drivers", "flat,vxlan")
cfg.set("ml2", "tenant_network_types", "vxlan")
cfg.set("ml2", "mechanism_drivers", "linuxbridge,l2population")
cfg.set("ml2", "extension_drivers", "port_security")
cfg.set("ml2_type_flat", "flat_networks", "provider")
cfg.set("ml2_type_vxlan", "vni_ranges", "1:1000")
cfg.set("securitygroup", "enable_ipset", "true")
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
cfg.set("vxlan", "local_ip", "192.168.234.151")
cfg.set("vxlan", "l2_population", "true")
cfg.set("securitygroup", "enable_security_group", "true")
cfg.set("securitygroup", "firewall_driver", "neutron.agent.linux.iptables_firewall.IptablesFirewallDriver")
with open(path, "w") as f:
    cfg.write(f)
PY

python3 - <<'PY'
import configparser
import os
from urllib.parse import quote
password_urlencoded = quote(os.environ["OPENSTACK_DEPLOY_PASSWORD"], safe="")

for path, sec, values in [
    ("/etc/neutron/l3_agent.ini", "DEFAULT", {"interface_driver": "linuxbridge"}),
    ("/etc/neutron/dhcp_agent.ini", "DEFAULT", {"interface_driver": "linuxbridge", "dhcp_driver": "neutron.agent.linux.dhcp.Dnsmasq", "enable_isolated_metadata": "true"}),
    ("/etc/neutron/metadata_agent.ini", "DEFAULT", {"nova_metadata_host": "controller", "metadata_proxy_shared_secret": os.environ["OPENSTACK_DEPLOY_PASSWORD"]}),
]:
    cfg = configparser.RawConfigParser()
    cfg.read(path)
    if sec != "DEFAULT" and not cfg.has_section(sec):
        cfg.add_section(sec)
    for key, value in values.items():
        cfg.set(sec, key, value)
    with open(path, "w") as f:
        cfg.write(f)
PY

su -s /bin/sh -c "neutron-db-manage --config-file /etc/neutron/neutron.conf --config-file /etc/neutron/plugins/ml2/ml2_conf.ini upgrade head" neutron
systemctl restart openstack-nova-api
systemctl enable --now neutron-server neutron-linuxbridge-agent neutron-dhcp-agent neutron-metadata-agent neutron-l3-agent

source /root/admin-openrc
openstack network agent list
