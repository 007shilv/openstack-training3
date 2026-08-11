# Lab Task 4 Report — Offline Repository Validation and Staging

## Outcome

DONE. The supplied offline repository was safety-scanned locally, staged on the controller, exposed through a read-only anonymous FTP endpoint, and verified from both controller and compute. The review follow-up added a complete ZIP-versus-remote tree proof and removed the exact out-of-scope backup path identified in the contemporaneous first-execution record. No repository retransmission or re-extraction occurred during the follow-up, no OpenStack deployment script ran, and no OpenStack service package was installed.

## Local archive inventory

- ZIP: `openstack_repo.zip`; size `726582890` bytes; SHA256 `ddae4b9bd63b20e5ebb052e52d86afb8a98f6edfeefde799f8ccf966aae65978`.
- The normalized, unique inventory contains exactly 1,089 relative entries: 3 directories and 1,086 files. The files comprise 1,079 RPMs plus `top-packages.txt`, two repository files, and four repodata files.
- The safety scan found no absolute path, `..` traversal, symlink, special entry, or duplicate normalized path.
- The revised `third-edition-work/validation/repository/rpm-inventory.txt` lists all 1,089 sorted ZIP entries and separately preserves the complete 1,079-RPM list.
- Each core component record independently identifies its relative filename, exact version, uncompressed size, local ZIP-member content SHA256, and remote controller SHA256. All eight versions match `version-matrix.json`, and every local/remote SHA pair matches.

## Complete post-staging proof

A read-only recursive SFTP walk mapped `controller:/opt/openstack_repo` back to the normalized ZIP paths. It found 1,089 remote entries (3 directories and 1,086 regular files). Set and metadata comparison results were:

- missing entries: 0;
- extra entries: 0;
- type mismatches: 0;
- file-size mismatches across all 1,086 files: 0;
- `repodata/repomd.xml` SHA256 mismatches: 0; and
- eight core RPM SHA256 mismatches: 0.

This complete comparison includes all non-RPM entries and rules out stale files from any earlier staging directory. The verified `repomd.xml` SHA256 is `6ccbb9e00263dd9c35cb93c9c60d83a4e7ace3d9fd4c5c85abf9e5c722978fec`. A read-only `/opt` top-level listing showed only `openstack_repo/`; no `/opt/.openstack_repo.*` item remains.

## Staging evidence correction and reusable procedure

The initial report described a ZIP-hash-only staging name as task-unique. That description was too strong: the same archive can be retried or processed concurrently. The original execution checked that the target, upload path, and staging path did not exist, but it did not preserve durable pre-create lstat evidence in the validation artifacts. The exact post-staging tree proof above now excludes pre-existing or stale repository content.

For every future run:

1. `lstat` and canonicalize the parent first, requiring the exact non-symlink directory `/opt` with the expected root ownership. Reject any other resolved parent.
2. Generate a cryptographically random UUID/task nonce. Create `/opt/.openstack_repo.task-<uuid>` with one exclusive `mkdir` at mode 0700; `EEXIST` is a hard stop. Immediately `lstat` it and require a root-owned, non-symlink directory with mode 0700 and the expected initial link count.
3. Exclusively create a root-only ownership marker inside that directory. Its content binds the directory to the UUID/task nonce and expected ZIP SHA256 and later serves as the cleanup authorization token.
4. Exclusively create the upload file inside the verified task directory at mode 0600. Use SFTP `x` mode only when that implementation also guarantees no-follow semantics; otherwise use a server-side open with `O_CREAT|O_EXCL|O_NOFOLLOW`. Before writing any archive bytes, `lstat` the new inode and require a regular, non-symlink, root-owned file with `nlink=1` and mode 0600. Any exclusive-create or metadata check failure is a hard stop. A preceding `lstat` or `test ! -e` may be recorded for diagnosis but is not the security boundary and never substitutes for exclusive creation.
5. Write and close the upload, then `lstat` again and verify exact size and SHA256. Create the extraction child directory within the task directory using exclusive `mkdir`, and validate its type, owner, mode, and non-symlink state before extraction.
6. Compare the full normalized entry set, type of every entry, size of every regular file, `repomd.xml` SHA256, and the eight core RPM SHA256 values before atomic promotion.
7. Before cleanup, revalidate the exact task-directory parent, root ownership/mode, non-symlink state, and ownership-marker UUID/SHA256. Cleanup may address only exact children of that marker-verified nonce directory; remove the directory only after it is empty, and record final absence.

## Controller state and FTP exposure

- `/etc/yum.repos.d/openstack-local.repo` uses ID `openstack-local`, `baseurl=file:///opt/openstack_repo`, `enabled=1`, and `gpgcheck=0`; its isolated `dnf repolist` query passes.
- Only `vsftpd-3.0.5-3.oe2403sp3.x86_64` was added relative to the Task 1 controller RPM baseline. It was installed with every source disabled except the verified local source; no dependency or OpenStack service RPM was added.
- vsftpd is active with IPv4 listening, anonymous read access, local-user access disabled, every anonymous write setting disabled, `anon_world_readable_only=YES`, `anon_root=/opt`, and passive ports 30000–30009.
- Firewalld allows only the required FTP service and passive-port range for this task. SELinux remains Enforcing and needed no change.
- Because `/opt` has no top-level item other than `openstack_repo`, the current anonymous FTP root exposes only the repository tree. Controller and compute FTP header reads both return Content-Length 1569.

## Exact backup cleanup

The report path was parsed and constrained to a single basename directly below `/root/openstack-repo-backups/`. Before deletion, `/root/openstack-repo-backups/vsftpd.conf.pre-openstack-repo-ddae4b9bd63b20e5ebb052e52d86afb8a98f6edfeefde799f8ccf966aae65978` was verified as a 5,039-byte regular file with SHA256 `fa52b7c07f7499930bbd5fdd890b3828d55250bfa39361837944f6236408e0f6`. Its size and hash establish only that its content was identical to `etc/vsftpd/vsftpd.conf` streamed from the offline vsftpd RPM; they do not independently establish when or by whom it was created. The first execution report contemporaneously recorded creating this exact path immediately before replacing the package configuration. That record, combined with the content match, is consistent with the file being this task's backup and supported deletion of that exact path.

Only that exact file was deleted, and its post-delete absence was verified. The default is recoverable by reinstalling or extracting the same RPM. The now-empty `/root/openstack-repo-backups` directory was retained because no pre-create evidence proves that the directory itself belonged exclusively to this task; no other backup or file was touched.

## Task 1 baseline comparison

- Controller RPM delta: one addition (`vsftpd-3.0.5-3.oe2403sp3.x86_64`), zero removals, and zero added OpenStack service packages.
- Compute RPM delta: zero additions, zero removals, and zero added OpenStack service packages.
- Compute `/dev/sda` remains the 200 GiB system disk with the same partition/mount layout: 192 GiB ext4 root on `sda2` and swap on `sda3`.
- Compute `/dev/sdb` and `/dev/sdc` each remain unpartitioned 50 GiB whole disks with no filesystem, child, or mount. Read-only `blkid -p` probes returned no signature for either disk.
- These mappings, visible signatures, and mounts match the Task 1 `lsblk` baseline. No command modified a disk, partition, filesystem, LVM object, or mount.

## Compute access

`/etc/yum.repos.d/openstack-local.repo` points to `ftp://192.168.234.151/openstack_repo`, and both the FTP read and isolated `dnf repolist` query pass. No package was installed on compute.

## Residual risks

- `gpgcheck=0` is required by the task; integrity relies on the recorded archive, metadata, complete-tree, and core-RPM checks.
- Anonymous FTP is intentionally read-only. Its current `/opt` root exposes only the repository, but future additions under `/opt` require re-evaluating or narrowing `anon_root` before service continuation.
- The empty `/root/openstack-repo-backups` directory remains because its ownership could not be proven safely; deleting it would violate the exact-target cleanup rule.
- Credentials were used only in memory for host-key-pinned Paramiko sessions and do not appear in repository files or audit records.
