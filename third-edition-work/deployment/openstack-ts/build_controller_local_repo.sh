#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="/opt/openstack_repo"
RPM_DIR="${REPO_ROOT}/Packages"
TOP_PKG_FILE="/tmp/openstack-top-packages.txt"

mkdir -p "${RPM_DIR}"
find "${RPM_DIR}" -maxdepth 1 -type f -name '*.rpm' -delete
rm -rf "${REPO_ROOT}/repodata"

cat > "${TOP_PKG_FILE}" <<'EOF'
chrony
createrepo_c
dnf-plugins-core
httpd
ipset
libvirt
lvm2
mariadb
mariadb-config
mariadb-server
memcached
mod_wsgi
openstack-cinder
openstack-cinder-api
openstack-cinder-scheduler
openstack-cinder-volume
openstack-dashboard
openstack-glance
openstack-keystone
openstack-neutron
openstack-neutron-linuxbridge
openstack-neutron-ml2
openstack-nova-api
openstack-nova-compute
openstack-nova-conductor
openstack-nova-novncproxy
openstack-nova-scheduler
openstack-placement-api
openstack-release-antelope
openstack-swift
openstack-swift-account
openstack-swift-common
openstack-swift-container
openstack-swift-object
openstack-swift-proxy
python3-PyMySQL
python3-memcached
python3-openstackclient
qemu-kvm
rabbitmq-server
rsync
targetcli
unzip
vsftpd
xfsprogs
zip
ebtables
EOF

sort -u -o "${TOP_PKG_FILE}" "${TOP_PKG_FILE}"

dnf -y install dnf-plugins-core createrepo_c vsftpd zip unzip

mapfile -t TOP_PACKAGES < "${TOP_PKG_FILE}"
dnf download \
  --resolve \
  --alldeps \
  --downloaddir "${RPM_DIR}" \
  "${TOP_PACKAGES[@]}"

createrepo_c "${REPO_ROOT}"

cat > "${REPO_ROOT}/openstack-local-file.repo" <<'EOF'
[openstack-local-file]
name=OpenStack Local File Repo
baseurl=file:///opt/openstack_repo
enabled=1
gpgcheck=0
EOF

cat > "${REPO_ROOT}/openstack-local-ftp.repo" <<'EOF'
[openstack-local-ftp]
name=OpenStack Local FTP Repo
baseurl=ftp://192.168.234.151/openstack_repo
enabled=1
gpgcheck=0
EOF

cp -f "${TOP_PKG_FILE}" "${REPO_ROOT}/top-packages.txt"

cat > /etc/vsftpd/vsftpd.conf <<'EOF'
listen=YES
listen_ipv6=NO
anonymous_enable=YES
local_enable=NO
write_enable=NO
anon_root=/opt
no_anon_password=YES
hide_ids=YES
dirmessage_enable=YES
use_localtime=YES
xferlog_enable=YES
connect_from_port_20=YES
ftpd_banner=OpenStack Local Repo FTP
pasv_enable=YES
pasv_min_port=30000
pasv_max_port=30009
EOF

systemctl enable --now vsftpd

cd /opt
rm -f /opt/openstack_repo.zip
zip -qr /opt/openstack_repo.zip openstack_repo

echo "=== repo summary ==="
find "${RPM_DIR}" -maxdepth 1 -type f -name '*.rpm' | wc -l
du -sh "${REPO_ROOT}"
echo "=== ftp test ==="
curl -sS ftp://127.0.0.1/openstack_repo/ | head -n 20 || true
