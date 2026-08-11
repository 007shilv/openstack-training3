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

# Install controller-side infrastructure services:
# - MariaDB
# - RabbitMQ
# - Memcached
# - OpenStack client packages

RABBIT_USER="openstack"
RABBIT_PASS="${OPENSTACK_DEPLOY_PASSWORD}"
MEMCACHED_IP="192.168.234.151"

# openEuler may already ship mysql-config, which conflicts with mariadb-config.
dnf -y remove mysql-config || true
if ! dnf_install_prefer_local \
  mariadb-config \
  mariadb \
  mariadb-server \
  python3-PyMySQL \
  rabbitmq-server \
  memcached \
  python3-memcached \
  python3-openstackclient; then
  dnf -y --disablerepo='debuginfo,source,update-source' install \
    mariadb-config \
    mariadb \
    mariadb-server \
    python3-PyMySQL \
    rabbitmq-server \
    memcached \
    python3-memcached \
    python3-openstackclient
fi

cat > /etc/my.cnf.d/openstack.cnf <<'EOF'
[mysqld]
bind-address = 0.0.0.0
default-storage-engine = innodb
innodb_file_per_table = on
max_connections = 4096
collation-server = utf8_general_ci
character-set-server = utf8
EOF

systemctl enable --now mariadb
mysql -uroot -e "SELECT 1;"

systemctl enable --now rabbitmq-server
rabbitmqctl list_users | grep -q "^${RABBIT_USER}[[:space:]]" || rabbitmqctl add_user "${RABBIT_USER}" "${RABBIT_PASS}"
rabbitmqctl change_password "${RABBIT_USER}" "${RABBIT_PASS}"

# Grant permissions on the default vhost explicitly.
rabbitmqctl set_permissions -p / "${RABBIT_USER}" ".*" ".*" ".*"

cat > /etc/sysconfig/memcached <<EOF
PORT="11211"
USER="memcached"
MAXCONN="1024"
CACHESIZE="64"
OPTIONS="-l 127.0.0.1,::1,${MEMCACHED_IP}"
EOF

systemctl enable --now memcached

echo "=== services ==="
systemctl is-active mariadb rabbitmq-server memcached
