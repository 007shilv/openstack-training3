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

# Install and initialize the Cinder control plane on the controller node.
# The actual LVM backend runs on the compute node and uses /dev/sdb there.

DB_PASS="${OPENSTACK_DEPLOY_PASSWORD}"
SERVICE_PASS="${OPENSTACK_DEPLOY_PASSWORD}"

mysql -uroot <<EOF
CREATE DATABASE IF NOT EXISTS cinder;
GRANT ALL PRIVILEGES ON cinder.* TO 'cinder'@'localhost' IDENTIFIED BY '${DB_PASS}';
GRANT ALL PRIVILEGES ON cinder.* TO 'cinder'@'127.0.0.1' IDENTIFIED BY '${DB_PASS}';
GRANT ALL PRIVILEGES ON cinder.* TO 'cinder'@'%' IDENTIFIED BY '${DB_PASS}';
FLUSH PRIVILEGES;
EOF

source /root/admin-openrc
openstack user show cinder >/dev/null 2>&1 || openstack user create --domain default --password "${SERVICE_PASS}" cinder
openstack role add --project service --user cinder admin || true
openstack service show cinderv3 >/dev/null 2>&1 || openstack service create --name cinderv3 --description "OpenStack Block Storage" volumev3
openstack endpoint create --region RegionOne volumev3 public 'http://controller:8776/v3/%(project_id)s' || true
openstack endpoint create --region RegionOne volumev3 internal 'http://controller:8776/v3/%(project_id)s' || true
openstack endpoint create --region RegionOne volumev3 admin 'http://controller:8776/v3/%(project_id)s' || true

if ! dnf_install_prefer_local openstack-cinder openstack-cinder-api openstack-cinder-scheduler; then
  dnf -y install openstack-cinder openstack-cinder-api openstack-cinder-scheduler
fi

# Configure the API and scheduler services. The volume backend itself lives on compute.
python3 - <<'PY'
import configparser
import os
from urllib.parse import quote
password_urlencoded = quote(os.environ["OPENSTACK_DEPLOY_PASSWORD"], safe="")

path = "/etc/cinder/cinder.conf"
cfg = configparser.RawConfigParser()
cfg.read(path)
for sec in ("DEFAULT", "database", "keystone_authtoken", "oslo_concurrency", "nova"):
    if sec != "DEFAULT" and not cfg.has_section(sec):
        cfg.add_section(sec)
cfg.set("DEFAULT", "transport_url", f"rabbit://openstack:{password_urlencoded}@controller")
cfg.set("DEFAULT", "auth_strategy", "keystone")
cfg.set("DEFAULT", "my_ip", "192.168.234.151")
cfg.set("DEFAULT", "glance_api_servers", "http://controller:9292")
cfg.set("DEFAULT", "default_volume_type", "lvm")
cfg.set("database", "connection", f"mysql+pymysql://cinder:{password_urlencoded}@127.0.0.1/cinder")
cfg.set("keystone_authtoken", "www_authenticate_uri", "http://controller:5000")
cfg.set("keystone_authtoken", "auth_url", "http://controller:5000")
cfg.set("keystone_authtoken", "memcached_servers", "controller:11211")
cfg.set("keystone_authtoken", "auth_type", "password")
cfg.set("keystone_authtoken", "project_domain_name", "Default")
cfg.set("keystone_authtoken", "user_domain_name", "Default")
cfg.set("keystone_authtoken", "project_name", "service")
cfg.set("keystone_authtoken", "username", "cinder")
cfg.set("keystone_authtoken", "password", os.environ["OPENSTACK_DEPLOY_PASSWORD"])
cfg.set("oslo_concurrency", "lock_path", "/var/lib/cinder/tmp")
cfg.set("nova", "auth_url", "http://controller:5000")
cfg.set("nova", "auth_type", "password")
cfg.set("nova", "project_domain_name", "Default")
cfg.set("nova", "user_domain_name", "Default")
cfg.set("nova", "region_name", "RegionOne")
cfg.set("nova", "project_name", "service")
cfg.set("nova", "username", "nova")
cfg.set("nova", "password", os.environ["OPENSTACK_DEPLOY_PASSWORD"])
with open(path, "w") as f:
    cfg.write(f)
PY

su -s /bin/sh -c "cinder-manage db sync" cinder
systemctl enable --now openstack-cinder-api openstack-cinder-scheduler

# Let Nova discover the Block Storage endpoint in RegionOne.
python3 - <<'PY'
import configparser
import os
from urllib.parse import quote
password_urlencoded = quote(os.environ["OPENSTACK_DEPLOY_PASSWORD"], safe="")

path = "/etc/nova/nova.conf"
cfg = configparser.RawConfigParser()
cfg.read(path)
if not cfg.has_section("cinder"):
    cfg.add_section("cinder")
cfg.set("cinder", "os_region_name", "RegionOne")
with open(path, "w") as f:
    cfg.write(f)
PY

systemctl restart openstack-nova-api

source /root/admin-openrc
openstack volume type show lvm >/dev/null 2>&1 || openstack volume type create lvm
openstack volume type set --property volume_backend_name=LVM-ISCSI lvm || true
openstack volume service list || true
