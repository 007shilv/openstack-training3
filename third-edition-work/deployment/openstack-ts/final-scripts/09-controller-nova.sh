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

# Install and initialize Nova control-plane services on the controller node.

DB_PASS="${OPENSTACK_DEPLOY_PASSWORD}"
SERVICE_PASS="${OPENSTACK_DEPLOY_PASSWORD}"

mysql -uroot <<EOF
CREATE DATABASE IF NOT EXISTS nova_api;
CREATE DATABASE IF NOT EXISTS nova;
CREATE DATABASE IF NOT EXISTS nova_cell0;
GRANT ALL PRIVILEGES ON nova_api.* TO 'nova'@'localhost' IDENTIFIED BY '${DB_PASS}';
GRANT ALL PRIVILEGES ON nova_api.* TO 'nova'@'127.0.0.1' IDENTIFIED BY '${DB_PASS}';
GRANT ALL PRIVILEGES ON nova_api.* TO 'nova'@'%' IDENTIFIED BY '${DB_PASS}';
GRANT ALL PRIVILEGES ON nova.* TO 'nova'@'localhost' IDENTIFIED BY '${DB_PASS}';
GRANT ALL PRIVILEGES ON nova.* TO 'nova'@'127.0.0.1' IDENTIFIED BY '${DB_PASS}';
GRANT ALL PRIVILEGES ON nova.* TO 'nova'@'%' IDENTIFIED BY '${DB_PASS}';
GRANT ALL PRIVILEGES ON nova_cell0.* TO 'nova'@'localhost' IDENTIFIED BY '${DB_PASS}';
GRANT ALL PRIVILEGES ON nova_cell0.* TO 'nova'@'127.0.0.1' IDENTIFIED BY '${DB_PASS}';
GRANT ALL PRIVILEGES ON nova_cell0.* TO 'nova'@'%' IDENTIFIED BY '${DB_PASS}';
FLUSH PRIVILEGES;
EOF

source /root/admin-openrc
openstack user show nova >/dev/null 2>&1 || openstack user create --domain default --password "${SERVICE_PASS}" nova
openstack role add --project service --user nova admin || true
openstack service show nova >/dev/null 2>&1 || openstack service create --name nova --description "OpenStack Compute" compute
openstack endpoint create --region RegionOne compute public http://controller:8774/v2.1 || true
openstack endpoint create --region RegionOne compute internal http://controller:8774/v2.1 || true
openstack endpoint create --region RegionOne compute admin http://controller:8774/v2.1 || true

if ! dnf_install_prefer_local openstack-nova-api openstack-nova-conductor openstack-nova-novncproxy openstack-nova-scheduler; then
  dnf -y install openstack-nova-api openstack-nova-conductor openstack-nova-novncproxy openstack-nova-scheduler
fi

# Configure the control-plane services and integrate them with Placement and Neutron.
python3 - <<'PY'
import configparser
import os
from urllib.parse import quote
password_urlencoded = quote(os.environ["OPENSTACK_DEPLOY_PASSWORD"], safe="")

path = "/etc/nova/nova.conf"
cfg = configparser.RawConfigParser()
cfg.read(path)
for sec in ("DEFAULT", "api_database", "database", "api", "keystone_authtoken", "service_user", "vnc", "glance", "oslo_concurrency", "placement", "neutron", "scheduler", "cinder"):
    if sec != "DEFAULT" and not cfg.has_section(sec):
        cfg.add_section(sec)
cfg.set("DEFAULT", "enabled_apis", "osapi_compute,metadata")
cfg.set("DEFAULT", "transport_url", f"rabbit://openstack:{password_urlencoded}@controller")
cfg.set("DEFAULT", "my_ip", "192.168.234.151")
cfg.set("DEFAULT", "use_neutron", "true")
cfg.set("DEFAULT", "firewall_driver", "nova.virt.firewall.NoopFirewallDriver")
cfg.set("api_database", "connection", f"mysql+pymysql://nova:{password_urlencoded}@127.0.0.1/nova_api")
cfg.set("database", "connection", f"mysql+pymysql://nova:{password_urlencoded}@127.0.0.1/nova")
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
cfg.set("vnc", "server_listen", "$my_ip")
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
cfg.set("neutron", "service_metadata_proxy", "true")
cfg.set("neutron", "metadata_proxy_shared_secret", os.environ["OPENSTACK_DEPLOY_PASSWORD"])
cfg.set("scheduler", "discover_hosts_in_cells_interval", "300")
cfg.set("cinder", "os_region_name", "RegionOne")
with open(path, "w") as f:
    cfg.write(f)
PY

su -s /bin/sh -c "nova-manage api_db sync" nova
nova-manage cell_v2 map_cell0 || true
nova-manage cell_v2 list_cells | grep -q cell1 || nova-manage cell_v2 create_cell --name=cell1 --verbose
su -s /bin/sh -c "nova-manage db sync" nova

systemctl enable --now openstack-nova-api openstack-nova-scheduler openstack-nova-conductor openstack-nova-novncproxy

source /root/admin-openrc
openstack compute service list
