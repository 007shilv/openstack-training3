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

require_compute_host() {
  ip -br addr show ens33 2>/dev/null | grep -Fq '192.168.234.150/24' || \
    die 'Refusing Cinder disk work: ens33 is not 192.168.234.150/24.'
}

require_safe_cinder_disk() {
  local root_source type mounted partitions vg canonical_target root_chain
  [[ "${CINDER_DEVICE}" == '/dev/sdb' ]] || die 'Cinder device must be exactly /dev/sdb.'
  [[ -b "${CINDER_DEVICE}" ]] || die "Missing block device: ${CINDER_DEVICE}"
  type="$(lsblk -dn -o TYPE "${CINDER_DEVICE}")"
  [[ "${type}" == 'disk' ]] || die "${CINDER_DEVICE} is not a whole disk."
  root_source="$(readlink -f "$(findmnt -nro SOURCE /)")"
  canonical_target="$(readlink -f "${CINDER_DEVICE}")"
  root_chain="$(lsblk -s -nrpo NAME "${root_source}" 2>/dev/null | while read -r node; do readlink -f "${node}"; done)"
  [[ -n "${root_chain}" ]] || die "Cannot resolve the root-device ancestry for ${root_source}."
  grep -Fxq "${canonical_target}" <<<"${root_chain}" && \
    die "Refusing root device or an ancestor of root: ${CINDER_DEVICE}"
  mounted="$(lsblk -nrpo NAME,MOUNTPOINT "${CINDER_DEVICE}" | awk 'NF > 1 && $2 != "" {print}')"
  [[ -z "${mounted}" ]] || die "Mounted target or child detected: ${mounted}"
  partitions="$(lsblk -nrpo TYPE "${CINDER_DEVICE}" | awk '$1 == "part" {print}')"
  [[ -z "${partitions}" ]] || die "Partitioned target is not allowed: ${CINDER_DEVICE}"
  vg="$(pvs --noheadings -o vg_name "${CINDER_DEVICE}" 2>/dev/null | xargs || true)"
  if [[ -n "${vg}" ]]; then
    [[ "${vg}" == "${CINDER_VG}" ]] || die "Unexpected LVM ownership on ${CINDER_DEVICE}: ${vg}"
    CINDER_DISK_STATE='initialized'
    return
  fi
  if blkid -p "${CINDER_DEVICE}" >/dev/null 2>&1; then
    die "Unexpected signature on uninitialized Cinder target: ${CINDER_DEVICE}"
  fi
  CINDER_DISK_STATE='blank'
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
