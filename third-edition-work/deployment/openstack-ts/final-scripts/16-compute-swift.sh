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

# Install and initialize the Swift storage services on the compute node.
# This script formats /dev/sdc as XFS and mounts it at /srv/node/sdc.

SWIFT_DEVICE="/dev/sdc"
SWIFT_MOUNT="/srv/node/sdc"
SWIFT_LABEL="openstack-swift-data"
SWIFT_STORAGE_IP="192.168.234.150"
SWIFT_DEVICE_NAME="sdc"
SWIFT_HASH_PREFIX="${OPENSTACK_DEPLOY_PASSWORD}-swift-prefix"
SWIFT_HASH_SUFFIX="${OPENSTACK_DEPLOY_PASSWORD}-swift-suffix"

die() {
  echo "ERROR: $*" >&2
  exit 1
}

require_compute_host() {
  ip -br addr show ens33 2>/dev/null | grep -Fq '192.168.234.150/24' || \
    die 'Refusing Swift disk work: ens33 is not 192.168.234.150/24.'
}

require_safe_swift_disk() {
  local root_source type mounted partitions fstype label canonical_target root_chain
  [[ "${SWIFT_DEVICE}" == '/dev/sdc' ]] || die 'Swift device must be exactly /dev/sdc.'
  [[ -b "${SWIFT_DEVICE}" ]] || die "Missing block device: ${SWIFT_DEVICE}"
  type="$(lsblk -dn -o TYPE "${SWIFT_DEVICE}")"
  [[ "${type}" == 'disk' ]] || die "${SWIFT_DEVICE} is not a whole disk."
  root_source="$(readlink -f "$(findmnt -nro SOURCE /)")"
  canonical_target="$(readlink -f "${SWIFT_DEVICE}")"
  root_chain="$(lsblk -s -nrpo NAME "${root_source}" 2>/dev/null | while read -r node; do readlink -f "${node}"; done)"
  [[ -n "${root_chain}" ]] || die "Cannot resolve the root-device ancestry for ${root_source}."
  grep -Fxq "${canonical_target}" <<<"${root_chain}" && \
    die "Refusing root device or an ancestor of root: ${SWIFT_DEVICE}"
  partitions="$(lsblk -nrpo TYPE "${SWIFT_DEVICE}" | awk '$1 == "part" {print}')"
  [[ -z "${partitions}" ]] || die "Partitioned target is not allowed: ${SWIFT_DEVICE}"
  mounted="$(lsblk -nrpo NAME,MOUNTPOINT "${SWIFT_DEVICE}" | awk 'NF > 1 && $2 != "" {print $1 " " $2}')"
  if [[ -n "${mounted}" && "${mounted}" != "${SWIFT_DEVICE} ${SWIFT_MOUNT}" ]]; then
    die "Unexpected mounted target or child: ${mounted}"
  fi
  fstype="$(blkid -o value -s TYPE "${SWIFT_DEVICE}" 2>/dev/null || true)"
  label="$(blkid -o value -s LABEL "${SWIFT_DEVICE}" 2>/dev/null || true)"
  if [[ -z "${fstype}" && -z "${label}" ]]; then
    SWIFT_DISK_STATE='blank'
    return
  fi
  [[ "${fstype}" == 'xfs' && "${label}" == "${SWIFT_LABEL}" ]] || \
    die "Swift target must be XFS with label ${SWIFT_LABEL}; found type=${fstype:-none}, label=${label:-none}"
  SWIFT_DISK_STATE='initialized'
}

require_initialization_confirmation() {
  [[ "${ALLOW_DISK_INITIALIZATION:-}" == 'YES' ]] || \
    die "Refusing first initialization of ${SWIFT_DEVICE}; set ALLOW_DISK_INITIALIZATION=YES after verifying the target."
  echo "Initializing verified Swift target: ${SWIFT_DEVICE}" >&2
}

require_compute_host

if ! dnf_install_prefer_local openstack-swift openstack-swift-common openstack-swift-account openstack-swift-container openstack-swift-object rsync xfsprogs; then
  dnf -y install openstack-swift openstack-swift-common openstack-swift-account openstack-swift-container openstack-swift-object rsync xfsprogs
fi

mkdir -p /etc/swift /srv/node /var/cache/swift

# The guard accepts only the known idempotent XFS state or a blank /dev/sdc.
require_safe_swift_disk
if [[ "${SWIFT_DISK_STATE}" == 'blank' ]]; then
  require_initialization_confirmation
  mkfs.xfs -f -L "${SWIFT_LABEL}" "${SWIFT_DEVICE}"
fi

UUID="$(blkid -s UUID -o value "${SWIFT_DEVICE}")"
[[ "$(blkid -s TYPE -o value "${SWIFT_DEVICE}")" == 'xfs' ]] || die "Swift target lost its XFS signature."
[[ "$(blkid -s LABEL -o value "${SWIFT_DEVICE}")" == "${SWIFT_LABEL}" ]] || die "Swift target label verification failed."
grep -q "UUID=${UUID} ${SWIFT_MOUNT} xfs" /etc/fstab || echo "UUID=${UUID} ${SWIFT_MOUNT} xfs defaults,noatime,nodiratime 0 0" >> /etc/fstab
mkdir -p "${SWIFT_MOUNT}"
mounted_source="$(findmnt -nro SOURCE --target "${SWIFT_MOUNT}" 2>/dev/null || true)"
if [[ -n "${mounted_source}" && "$(readlink -f "${mounted_source}")" != "$(readlink -f "${SWIFT_DEVICE}")" ]]; then
  die "Swift mountpoint is already backed by another device: ${mounted_source}"
fi
mountpoint -q "${SWIFT_MOUNT}" || mount "${SWIFT_MOUNT}"
[[ "$(readlink -f "$(findmnt -nro SOURCE --target "${SWIFT_MOUNT}")")" == "$(readlink -f "${SWIFT_DEVICE}")" ]] || \
  die "Swift mountpoint verification failed after mount."

chown -R swift:swift /srv/node /var/cache/swift

cat > /etc/swift/swift.conf <<EOF
[swift-hash]
swift_hash_path_prefix = ${SWIFT_HASH_PREFIX}
swift_hash_path_suffix = ${SWIFT_HASH_SUFFIX}

[storage-policy:0]
name = Policy-0
default = yes
EOF

# Keep the ring files identical to the controller by generating them with the same inputs.
cd /etc/swift
[ -f account.builder ] || swift-ring-builder account.builder create 10 1 1
[ -f container.builder ] || swift-ring-builder container.builder create 10 1 1
[ -f object.builder ] || swift-ring-builder object.builder create 10 1 1

swift-ring-builder account.builder search --ip "${SWIFT_STORAGE_IP}" --port 6202 --device "${SWIFT_DEVICE_NAME}" >/dev/null 2>&1 || \
  swift-ring-builder account.builder add --region 1 --zone 1 --ip "${SWIFT_STORAGE_IP}" --port 6202 --device "${SWIFT_DEVICE_NAME}" --weight 100
swift-ring-builder container.builder search --ip "${SWIFT_STORAGE_IP}" --port 6201 --device "${SWIFT_DEVICE_NAME}" >/dev/null 2>&1 || \
  swift-ring-builder container.builder add --region 1 --zone 1 --ip "${SWIFT_STORAGE_IP}" --port 6201 --device "${SWIFT_DEVICE_NAME}" --weight 100
swift-ring-builder object.builder search --ip "${SWIFT_STORAGE_IP}" --port 6200 --device "${SWIFT_DEVICE_NAME}" >/dev/null 2>&1 || \
  swift-ring-builder object.builder add --region 1 --zone 1 --ip "${SWIFT_STORAGE_IP}" --port 6200 --device "${SWIFT_DEVICE_NAME}" --weight 100

swift-ring-builder account.builder rebalance
swift-ring-builder container.builder rebalance
swift-ring-builder object.builder rebalance

cat > /etc/rsyncd.conf <<'EOF'
uid = swift
gid = swift
log file = /var/log/rsyncd.log
pid file = /var/run/rsyncd.pid
address = 192.168.234.150

[account]
max connections = 2
path = /srv/node/
read only = false
lock file = /var/lock/account.lock

[container]
max connections = 2
path = /srv/node/
read only = false
lock file = /var/lock/container.lock

[object]
max connections = 2
path = /srv/node/
read only = false
lock file = /var/lock/object.lock
EOF

cat > /etc/swift/account-server.conf <<'EOF'
[DEFAULT]
bind_ip = 0.0.0.0
bind_port = 6202
user = swift
swift_dir = /etc/swift
devices = /srv/node
mount_check = true

[pipeline:main]
pipeline = healthcheck recon account-server

[filter:healthcheck]
use = egg:swift#healthcheck

[filter:recon]
use = egg:swift#recon
recon_cache_path = /var/cache/swift

[app:account-server]
use = egg:swift#account
EOF

cat > /etc/swift/container-server.conf <<'EOF'
[DEFAULT]
bind_ip = 0.0.0.0
bind_port = 6201
user = swift
swift_dir = /etc/swift
devices = /srv/node
mount_check = true

[pipeline:main]
pipeline = healthcheck recon container-server

[filter:healthcheck]
use = egg:swift#healthcheck

[filter:recon]
use = egg:swift#recon
recon_cache_path = /var/cache/swift

[app:container-server]
use = egg:swift#container
EOF

cat > /etc/swift/object-server.conf <<'EOF'
[DEFAULT]
bind_ip = 0.0.0.0
bind_port = 6200
user = swift
swift_dir = /etc/swift
devices = /srv/node
mount_check = true

[pipeline:main]
pipeline = healthcheck recon object-server

[filter:healthcheck]
use = egg:swift#healthcheck

[filter:recon]
use = egg:swift#recon
recon_cache_path = /var/cache/swift

[app:object-server]
use = egg:swift#object
EOF

systemctl enable --now rsyncd
systemctl enable --now \
  openstack-swift-account \
  openstack-swift-account-auditor \
  openstack-swift-account-reaper \
  openstack-swift-account-replicator \
  openstack-swift-container \
  openstack-swift-container-auditor \
  openstack-swift-container-replicator \
  openstack-swift-container-updater \
  openstack-swift-object \
  openstack-swift-object-auditor \
  openstack-swift-object-replicator \
  openstack-swift-object-updater

systemctl is-active rsyncd openstack-swift-account openstack-swift-container openstack-swift-object
