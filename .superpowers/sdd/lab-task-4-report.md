# Lab Task 4 Report — Offline Repository Validation and Staging

## Outcome

DONE. The supplied offline repository ZIP was safety-scanned locally, staged atomically on the controller, exposed through a read-only anonymous FTP endpoint, and verified from both controller and compute with isolated `dnf repolist` queries. No OpenStack deployment script or OpenStack package installation was run.

## Local validation

- ZIP: `openstack_repo.zip`
- SHA256: `ddae4b9bd63b20e5ebb052e52d86afb8a98f6edfeefde799f8ccf966aae65978`
- Size: `726582890` bytes; 1,089 entries; 1,079 RPM files; 743,736,553 uncompressed bytes.
- Safety scan rejected none: there are no absolute paths, `..` traversal entries, symlinks, or special ZIP entries. Its only repository root is `openstack_repo`.
- `repodata/repomd.xml` SHA256 is `6ccbb9e00263dd9c35cb93c9c60d83a4e7ace3d9fd4c5c85abf9e5c722978fec`.
- The eight core RPM filename matches are each unique and match `version-matrix.json`: Keystone 23.0.1, Glance 26.0.0, Placement 9.0.0, Nova 27.3.0, Neutron 22.1.0, Cinder 22.1.2, Swift 2.31.1, and Horizon 23.1.0. The complete RPM inventory is in `third-edition-work/validation/repository/rpm-inventory.txt`.

## Controller changes

- Read-only preflight found `/opt/openstack_repo` absent and 93,647,896,576 bytes free under `/opt`.
- The ZIP was uploaded to the exact task-owned temporary path `/opt/.openstack_repo.zip.ddae4b9bd63b20e5ebb052e52d86afb8a98f6edfeefde799f8ccf966aae65978`; its remote size and SHA256 matched locally.
- It was extracted only to `/opt/.openstack_repo.staging.ddae4b9bd63b20e5ebb052e52d86afb8a98f6edfeefde799f8ccf966aae65978`. Before promotion, the repository layout, RPM count, `repomd.xml`, and hashes for all eight core RPMs were checked.
- The validated `openstack_repo` directory was atomically renamed to `/opt/openstack_repo`. The uploaded archive, atomic-write temporary files, and now-empty staging directory were removed; final exact-path absence checks passed.
- Atomically wrote `/etc/yum.repos.d/openstack-local.repo` with `openstack-local`, `file:///opt/openstack_repo`, `enabled=1`, and `gpgcheck=0`. Controller `dnf repolist --disablerepo='*' --enablerepo='openstack-local'` passed.
- Installed only `vsftpd-3.0.5-3.oe2403sp3.x86_64`, using only `openstack-local` with every other DNF source disabled.
- Backed up the package-provided configuration before replacement at `/root/openstack-repo-backups/vsftpd.conf.pre-openstack-repo-ddae4b9bd63b20e5ebb052e52d86afb8a98f6edfeefde799f8ccf966aae65978`.
- Atomically wrote `/etc/vsftpd/vsftpd.conf`: IPv4 listener, anonymous-only read access, `anon_root=/opt`, and passive ports 30000–30009. The service is enabled and active.
- The active firewalld configuration was minimally extended with the FTP service and TCP 30000–30009; both permanent and runtime checks passed. SELinux remained Enforcing and required no change because FTP access succeeded.

## Compute changes and verification

- Atomically wrote `/etc/yum.repos.d/openstack-local.repo` with `baseurl=ftp://192.168.234.151/openstack_repo`, `enabled=1`, and `gpgcheck=0`.
- `curl -fsSI ftp://192.168.234.151/openstack_repo/repodata/repomd.xml` succeeded from compute (Content-Length: 1569).
- `dnf repolist --disablerepo='*' --enablerepo='openstack-local'` succeeded from compute.
- No OpenStack package installation occurred on compute.

## Residual risks

- `gpgcheck=0` is deliberately required by the task; integrity is instead anchored by the documented ZIP, metadata, and core-RPM SHA256 checks. Treat the controller repository directory as protected from unauthorized local changes.
- Anonymous FTP is intentionally enabled but confined to read-only access rooted at `/opt`; firewall exposure consists only of FTP and the specified passive-port range.
- Credentials were used only in memory for host-key-pinned Paramiko sessions and are not present in repository files, the report, or validation records.
