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

# Install and initialize the Swift proxy service on the controller node.
# This lab uses a single storage node on compute with a single replica ring.

SWIFT_STORAGE_IP="192.168.234.150"
SWIFT_DEVICE="sdc"
SWIFT_HASH_PREFIX="${OPENSTACK_DEPLOY_PASSWORD}-swift-prefix"
SWIFT_HASH_SUFFIX="${OPENSTACK_DEPLOY_PASSWORD}-swift-suffix"
SERVICE_PASS="${OPENSTACK_DEPLOY_PASSWORD}"

source /root/admin-openrc
openstack user show swift >/dev/null 2>&1 || openstack user create --domain default --password "${SERVICE_PASS}" swift
openstack role add --project service --user swift admin || true
openstack service show swift >/dev/null 2>&1 || openstack service create --name swift --description "OpenStack Object Storage" object-store
openstack endpoint create --region RegionOne object-store public 'http://controller:8080/v1/AUTH_%(project_id)s' || true
openstack endpoint create --region RegionOne object-store internal 'http://controller:8080/v1/AUTH_%(project_id)s' || true
openstack endpoint create --region RegionOne object-store admin 'http://controller:8080/v1/AUTH_%(project_id)s' || true

if ! dnf_install_prefer_local openstack-swift openstack-swift-common openstack-swift-proxy; then
  dnf -y install openstack-swift openstack-swift-common openstack-swift-proxy
fi

mkdir -p /etc/swift /var/cache/swift
chown -R swift:swift /var/cache/swift

cat > /etc/swift/swift.conf <<EOF
[swift-hash]
swift_hash_path_prefix = ${SWIFT_HASH_PREFIX}
swift_hash_path_suffix = ${SWIFT_HASH_SUFFIX}

[storage-policy:0]
name = Policy-0
default = yes
EOF

# Build one-replica rings for the single storage node on compute.
cd /etc/swift
[ -f account.builder ] || swift-ring-builder account.builder create 10 1 1
[ -f container.builder ] || swift-ring-builder container.builder create 10 1 1
[ -f object.builder ] || swift-ring-builder object.builder create 10 1 1

swift-ring-builder account.builder search --ip "${SWIFT_STORAGE_IP}" --port 6202 --device "${SWIFT_DEVICE}" >/dev/null 2>&1 || \
  swift-ring-builder account.builder add --region 1 --zone 1 --ip "${SWIFT_STORAGE_IP}" --port 6202 --device "${SWIFT_DEVICE}" --weight 100
swift-ring-builder container.builder search --ip "${SWIFT_STORAGE_IP}" --port 6201 --device "${SWIFT_DEVICE}" >/dev/null 2>&1 || \
  swift-ring-builder container.builder add --region 1 --zone 1 --ip "${SWIFT_STORAGE_IP}" --port 6201 --device "${SWIFT_DEVICE}" --weight 100
swift-ring-builder object.builder search --ip "${SWIFT_STORAGE_IP}" --port 6200 --device "${SWIFT_DEVICE}" >/dev/null 2>&1 || \
  swift-ring-builder object.builder add --region 1 --zone 1 --ip "${SWIFT_STORAGE_IP}" --port 6200 --device "${SWIFT_DEVICE}" --weight 100

swift-ring-builder account.builder rebalance
swift-ring-builder container.builder rebalance
swift-ring-builder object.builder rebalance

cat > /etc/swift/proxy-server.conf <<'EOF'
[DEFAULT]
bind_ip = 0.0.0.0
bind_port = 8080
user = swift
swift_dir = /etc/swift

[pipeline:main]
pipeline = catch_errors gatekeeper healthcheck proxy-logging cache authtoken keystoneauth proxy-logging proxy-server

[app:proxy-server]
use = egg:swift#proxy
account_autocreate = true
allow_account_management = true

[filter:catch_errors]
use = egg:swift#catch_errors

[filter:gatekeeper]
use = egg:swift#gatekeeper

[filter:healthcheck]
use = egg:swift#healthcheck

[filter:proxy-logging]
use = egg:swift#proxy_logging

[filter:cache]
use = egg:swift#memcache
memcache_servers = controller:11211

[filter:authtoken]
paste.filter_factory = keystonemiddleware.auth_token:filter_factory
www_authenticate_uri = http://controller:5000
auth_url = http://controller:5000
memcached_servers = controller:11211
auth_type = password
project_domain_name = Default
user_domain_name = Default
project_name = service
username = swift
password = ${OPENSTACK_DEPLOY_PASSWORD}
delay_auth_decision = true

[filter:keystoneauth]
use = egg:swift#keystoneauth
operator_roles = admin,user
reseller_prefix = AUTH
EOF

systemctl enable --now openstack-swift-proxy

source /root/admin-openrc
openstack endpoint list --service swift
