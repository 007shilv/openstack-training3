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

# Install and initialize Glance on the controller node.

DB_PASS="${OPENSTACK_DEPLOY_PASSWORD}"
SERVICE_PASS="${OPENSTACK_DEPLOY_PASSWORD}"

mysql -uroot <<EOF
CREATE DATABASE IF NOT EXISTS glance;
GRANT ALL PRIVILEGES ON glance.* TO 'glance'@'localhost' IDENTIFIED BY '${DB_PASS}';
GRANT ALL PRIVILEGES ON glance.* TO 'glance'@'127.0.0.1' IDENTIFIED BY '${DB_PASS}';
GRANT ALL PRIVILEGES ON glance.* TO 'glance'@'%' IDENTIFIED BY '${DB_PASS}';
FLUSH PRIVILEGES;
EOF

source /root/admin-openrc
openstack user show glance >/dev/null 2>&1 || openstack user create --domain default --password "${SERVICE_PASS}" glance
openstack role add --project service --user glance admin || true
openstack service show glance >/dev/null 2>&1 || openstack service create --name glance --description "OpenStack Image" image
openstack endpoint create --region RegionOne image public http://controller:9292 || true
openstack endpoint create --region RegionOne image internal http://controller:9292 || true
openstack endpoint create --region RegionOne image admin http://controller:9292 || true

if ! dnf_install_prefer_local openstack-glance; then
  dnf -y install openstack-glance
fi

# Use the local filesystem store for a simple two-node lab deployment.
python3 - <<'PY'
import configparser
import os
from urllib.parse import quote
password_urlencoded = quote(os.environ["OPENSTACK_DEPLOY_PASSWORD"], safe="")

path = "/etc/glance/glance-api.conf"
cfg = configparser.RawConfigParser()
cfg.read(path)
for sec in ("database", "keystone_authtoken", "paste_deploy", "glance_store", "file"):
    if not cfg.has_section(sec):
        cfg.add_section(sec)
cfg.set("database", "connection", f"mysql+pymysql://glance:{password_urlencoded}@127.0.0.1/glance")
cfg.set("keystone_authtoken", "www_authenticate_uri", "http://controller:5000")
cfg.set("keystone_authtoken", "auth_url", "http://controller:5000")
cfg.set("keystone_authtoken", "memcached_servers", "controller:11211")
cfg.set("keystone_authtoken", "auth_type", "password")
cfg.set("keystone_authtoken", "project_domain_name", "Default")
cfg.set("keystone_authtoken", "user_domain_name", "Default")
cfg.set("keystone_authtoken", "project_name", "service")
cfg.set("keystone_authtoken", "username", "glance")
cfg.set("keystone_authtoken", "password", os.environ["OPENSTACK_DEPLOY_PASSWORD"])
cfg.set("paste_deploy", "flavor", "keystone")
cfg.set("glance_store", "default_backend", "file")
cfg.set("glance_store", "stores", "file,http")
cfg.set("file", "filesystem_store_datadir", "/var/lib/glance/images/")
with open(path, "w") as f:
    cfg.write(f)
PY

su -s /bin/sh -c "glance-manage db_sync" glance
systemctl enable --now openstack-glance-api

# The API can take a few seconds to finish binding after systemd reports
# success, so poll the root version endpoint before running the CLI check.
for _ in $(seq 1 15); do
  if curl -fsS http://controller:9292/ >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

source /root/admin-openrc
openstack image list
