#!/usr/bin/env bash
set -euo pipefail

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

# Prepare the compute node:
# 1. Disable SELinux enforcement and firewalld for lab deployment.
# 2. Install the Antelope release package.
# 3. Rewrite the generated OpenStack repo from SP3 to SP2.
# 4. Install and enable chrony.

ANTELOPE_REPO_FILE="/etc/yum.repos.d/openstack-antelope.repo"
OPENEULER_REPO_FILE="/etc/yum.repos.d/openEuler.repo"

sed -ri 's/^SELINUX=.*/SELINUX=permissive/' /etc/selinux/config || true
setenforce 0 || true
systemctl disable --now firewalld || true

if ! dnf_install_prefer_local openstack-release-antelope; then
  dnf -y --disablerepo='OpenStack_Antelope*' install openstack-release-antelope
fi

if [ -f "${ANTELOPE_REPO_FILE}" ]; then
  sed -ri 's#openEuler-24.03-LTS-SP3#openEuler-24.03-LTS-SP2#g' "${ANTELOPE_REPO_FILE}"
fi

if [ -f "${OPENEULER_REPO_FILE}" ]; then
  sed -ri 's/^metalink=/# metalink=/' "${OPENEULER_REPO_FILE}"
  python3 - <<'PY'
import configparser
import os
from urllib.parse import quote
password_urlencoded = quote(os.environ["OPENSTACK_DEPLOY_PASSWORD"], safe="")

path = "/etc/yum.repos.d/openEuler.repo"
cfg = configparser.RawConfigParser()
cfg.read(path)
for section in ("debuginfo", "source", "update-source"):
    if cfg.has_section(section):
        cfg.set(section, "enabled", "0")
with open(path, "w") as f:
    cfg.write(f)
PY
fi

dnf clean all
if ! dnf_makecache_prefer_local; then
  dnf makecache --disablerepo='debuginfo,source,update-source'
fi

# Keep chrony on the default upstream sources for reliability.
if ! dnf_install_prefer_local chrony; then
  dnf -y install chrony
fi
systemctl enable --now chronyd

# Force an initial time step when the node has just been reset so service
# heartbeats do not start with a large clock skew.
chronyc -a makestep || true

echo "=== chrony ==="
chronyc tracking || true
chronyc sources || true
