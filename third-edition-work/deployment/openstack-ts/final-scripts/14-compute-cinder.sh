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

# Install and initialize the Cinder LVM backend on the compute node.
# This script uses /dev/sdb as the only block storage device for Cinder.

CINDER_DEVICE="/dev/sdb"
CINDER_VG="cinder-volumes"

die() {
  echo "ERROR: $*" >&2
  exit 1
}

is_block_device() {
  [[ -b "$1" ]]
}

require_compute_host() {
  ip -br addr show ens33 2>/dev/null | grep -Fq '192.168.234.150/24' || \
    die 'Refusing Cinder disk work: ens33 is not 192.168.234.150/24.'
}

assert_not_root_ancestor() {
  local device="$1" root_source canonical_target root_chain node canonical_node
  root_source="$(findmnt -nro SOURCE /)" || die 'Cannot determine the root filesystem source.'
  [[ -n "${root_source}" ]] || die 'Root filesystem source is empty.'
  root_source="$(readlink -f "${root_source}")" || die 'Cannot canonicalize the root filesystem source.'
  canonical_target="$(readlink -f "${device}")" || die "Cannot canonicalize disk target: ${device}"
  root_chain="$(lsblk -s -nrpo NAME "${root_source}" 2>/dev/null)" || \
    die "Cannot resolve the root-device ancestry for ${root_source}."
  [[ -n "${root_chain}" ]] || die "Cannot resolve the root-device ancestry for ${root_source}."
  while IFS= read -r node; do
    canonical_node="$(readlink -f "${node}")" || die "Cannot canonicalize root ancestor: ${node}"
    [[ "${canonical_node}" != "${canonical_target}" ]] || \
      die "Refusing root device or an ancestor of root: ${device}"
  done <<< "${root_chain}"
}

require_safe_cinder_disk() {
  local type mounted partitions pv_rows pv_uuid pv_name vg canonical_target canonical_pv
  [[ "${CINDER_DEVICE}" == '/dev/sdb' ]] || die 'Cinder device must be exactly /dev/sdb.'
  [[ -b "${CINDER_DEVICE}" ]] || die "Missing block device: ${CINDER_DEVICE}"
  type="$(lsblk -dn -o TYPE "${CINDER_DEVICE}")"
  [[ "${type}" == 'disk' ]] || die "${CINDER_DEVICE} is not a whole disk."
  assert_not_root_ancestor "${CINDER_DEVICE}"
  canonical_target="$(readlink -f "${CINDER_DEVICE}")" || die "Cannot canonicalize disk target: ${CINDER_DEVICE}"
  mounted="$(lsblk -nrpo NAME,MOUNTPOINT "${CINDER_DEVICE}" | awk 'NF > 1 && $2 != "" {print}')"
  [[ -z "${mounted}" ]] || die "Mounted target or child detected: ${mounted}"
  partitions="$(lsblk -nrpo TYPE "${CINDER_DEVICE}" | awk '$1 == "part" {print}')"
  [[ -z "${partitions}" ]] || die "Partitioned target is not allowed: ${CINDER_DEVICE}"
  command -v pvs >/dev/null 2>&1 || die 'pvs is required to inspect the Cinder data disk.'
  if ! pv_rows="$(pvs --noheadings --readonly -o pv_uuid,pv_name,vg_name 2>/dev/null)"; then
    die "Unable to inspect LVM physical volumes for ${CINDER_DEVICE}."
  fi
  while read -r pv_uuid pv_name vg; do
    [[ -n "${pv_uuid:-}" && -n "${pv_name:-}" ]] || continue
    canonical_pv="$(readlink -f "${pv_name}")" || die "Cannot canonicalize LVM PV: ${pv_name}"
    if [[ "${canonical_pv}" == "${canonical_target}" ]]; then
      [[ "${vg:-}" == "${CINDER_VG}" ]] || die "Unexpected LVM ownership on ${CINDER_DEVICE}: ${vg:-orphan PV}"
      CINDER_DISK_STATE='initialized'
      return
    fi
  done <<< "${pv_rows}"
  if blkid -p "${CINDER_DEVICE}" >/dev/null 2>&1; then
    die "Unexpected signature on uninitialized Cinder target: ${CINDER_DEVICE}"
  fi
  CINDER_DISK_STATE='blank'
}

assert_blank_data_disk() {
  local device="$1" expected_size_gib="$2" size_bytes expected_size_bytes mounted partitions fstype label pv_rows pv_uuid pv_name canonical_target canonical_pv
  [[ "${device}" != '/dev/sda' ]] || die 'Refusing to initialize the system disk /dev/sda.'
  is_block_device "${device}" || die "Missing block device: ${device}"
  [[ "$(lsblk -dn -o TYPE "${device}")" == 'disk' ]] || die "${device} is not a whole disk."
  assert_not_root_ancestor "${device}"
  canonical_target="$(readlink -f "${device}")" || die "Cannot canonicalize disk target: ${device}"
  size_bytes="$(lsblk -bdn -o SIZE "${device}")"
  expected_size_bytes=$((expected_size_gib * 1024 * 1024 * 1024))
  [[ "${size_bytes}" == "${expected_size_bytes}" ]] || \
    die "Unexpected disk size for ${device}: expected ${expected_size_gib} GiB, found ${size_bytes} bytes."
  mounted="$(lsblk -nrpo NAME,MOUNTPOINT "${device}" | awk 'NF > 1 && $2 != "" {print $1 " " $2}')"
  [[ -z "${mounted}" ]] || die "Mounted target or child detected: ${mounted}"
  partitions="$(lsblk -nrpo TYPE "${device}" | awk '$1 == "part" {print}')"
  [[ -z "${partitions}" ]] || die "Partitioned target is not allowed: ${device}"
  fstype="$(blkid -o value -s TYPE "${device}" 2>/dev/null || true)"
  label="$(blkid -o value -s LABEL "${device}" 2>/dev/null || true)"
  [[ -z "${fstype}" && -z "${label}" ]] || die "Existing filesystem signature on ${device}."
  command -v pvs >/dev/null 2>&1 || die 'pvs is required to inspect the Cinder data disk.'
  if ! pv_rows="$(pvs --noheadings --readonly -o pv_uuid,pv_name 2>/dev/null)"; then
    die "Unable to inspect LVM physical volumes for ${device}."
  fi
  while read -r pv_uuid pv_name; do
    [[ -n "${pv_uuid:-}" && -n "${pv_name:-}" ]] || continue
    canonical_pv="$(readlink -f "${pv_name}")" || die "Cannot canonicalize LVM PV: ${pv_name}"
    [[ "${canonical_pv}" != "${canonical_target}" ]] || die "Existing LVM physical volume on ${device}: ${pv_uuid}"
  done <<< "${pv_rows}"
}

require_initialization_confirmation() {
  [[ "${ALLOW_DISK_INITIALIZATION:-}" == 'YES' ]] || \
    die "Refusing first initialization of ${CINDER_DEVICE}; set ALLOW_DISK_INITIALIZATION=YES after verifying the target."
  echo "Initializing verified Cinder target: ${CINDER_DEVICE}" >&2
}

require_compute_host

if ! dnf_install_prefer_local lvm2 targetcli openstack-cinder-volume; then
  dnf -y install lvm2 targetcli openstack-cinder-volume
fi

# The guard accepts only the known idempotent LVM state or a blank /dev/sdb.
require_safe_cinder_disk
if [[ "${CINDER_DISK_STATE}" == 'blank' ]]; then
  assert_blank_data_disk "${CINDER_DEVICE}" 50
  require_initialization_confirmation
  pvcreate "${CINDER_DEVICE}"
  vgcreate "${CINDER_VG}" "${CINDER_DEVICE}"
fi

# Configure the cinder-volume service to export LVM volumes through LIO iSCSI.
python3 - <<'PY'
import configparser
import os
from urllib.parse import quote
password_urlencoded = quote(os.environ["OPENSTACK_DEPLOY_PASSWORD"], safe="")

path = "/etc/cinder/cinder.conf"
cfg = configparser.RawConfigParser()
cfg.read(path)
for sec in ("DEFAULT", "database", "keystone_authtoken", "oslo_concurrency", "lvm"):
    if sec != "DEFAULT" and not cfg.has_section(sec):
        cfg.add_section(sec)
cfg.set("DEFAULT", "transport_url", f"rabbit://openstack:{password_urlencoded}@controller")
cfg.set("DEFAULT", "auth_strategy", "keystone")
cfg.set("DEFAULT", "my_ip", "192.168.234.150")
cfg.set("DEFAULT", "glance_api_servers", "http://controller:9292")
cfg.set("DEFAULT", "enabled_backends", "lvm")
cfg.set("DEFAULT", "default_volume_type", "lvm")
cfg.set("database", "connection", f"mysql+pymysql://cinder:{password_urlencoded}@controller/cinder")
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
cfg.set("lvm", "volume_driver", "cinder.volume.drivers.lvm.LVMVolumeDriver")
cfg.set("lvm", "volume_group", "cinder-volumes")
cfg.set("lvm", "target_protocol", "iscsi")
cfg.set("lvm", "target_helper", "lioadm")
cfg.set("lvm", "target_ip_address", "192.168.234.150")
cfg.set("lvm", "volume_backend_name", "LVM-ISCSI")
with open(path, "w") as f:
    cfg.write(f)
PY

systemctl enable --now targetclid
systemctl enable --now openstack-cinder-volume

systemctl is-active targetclid openstack-cinder-volume
