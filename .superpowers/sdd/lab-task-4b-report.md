# Lab Task 4B Report — SP3 SELinux-policy Dependency Closure

## Outcome

DONE. The immutable 1,079-RPM ZIP was not changed. Two exact, signed policy RPMs from the configured official openEuler 24.03 LTS SP3 `everything` repository were verified, saved to an ignored local cache, added to a privately staged repository candidate, and promoted through a recoverable exact-path swap. The final controller repository has 1,081 RPMs, both nodes see the same metadata and overlay hashes, and the isolated Task 5A package set now resolves with no removal of `selinux-policy*`. No infrastructure or OpenStack service was installed and no disk was modified.

## Overlay and provenance

- `memcached-selinux-1.6.22-4.oe2403sp3.x86_64.rpm`, 16,449 bytes, SHA256 `d19f42f77449b9f1d4c600d396d18baa09c959864ad39e8d01969ca62793ec77`.
- `mysql-selinux-1.0.10-1.oe2403sp3.noarch.rpm`, 31,617 bytes, SHA256 `079ab9c805f999c3c4c96ac0247a3150ea5e3d34c37330bdc056c471d28cbb95`.

Each exact NEVRA had one location in the configured official SP3 `everything` repository. An isolated rpmdb containing the configured openEuler key verified both Header V4 RSA/SHA256 signatures under key ID `b675600b` and both payload SHA256 digests. The newer update-repository memcached policy was deliberately rejected because it was not built from the immutable repository's `memcached-1.6.22-4` source EVR.

## Mutations and rollback points

The controller received one exclusive random-nonce staging directory and, immediately before promotion, one exclusive random-nonce rollback directory under the verified root-owned `/opt` parent. Both were root-owned mode 0700 and each had an exclusive root-only ownership marker. The original repository was copied into the candidate; only the two verified RPMs were added. `createrepo_c 1.0.1` was extracted from the reviewed repository into the private stage and run with `--update`; it was not installed.

Promotion moved `/opt/openstack_repo` to the marker-owned rollback child and then moved the validated candidate to `/opt/openstack_repo`. Until all checks passed, the exact reverse rename remained the rollback point. No rollback was needed. After validation, cleanup rechecked nonce, parent, ownership, mode, no-follow identity, marker content, exact child sets, old repository identity, and promoted repository identity before deleting only the two task-owned temporary objects. `/opt` again contains only `openstack_repo`.

## Validation

The pre-change `--assumeno` transaction failed before planning because `mariadb-server` required `mysql-selinux` and `memcached` required `memcached-selinux`. RPM queries before and after proved that the attempted Task 5A set installed nothing.

The candidate and promoted repository each had 1,081 RPMs. All eight reviewed core RPM hashes remained exact. The final `repomd.xml` SHA256 is `e5cecca736e5eee2477211225397d1f65d55ae03772ed5224f99634a50a5a3dc`. Controller file DNF, controller FTP, and compute FTP DNF all returned the two exact policy NEVRAs and matching overlay/metadata hashes.

The final isolated `openstack-local` transaction plan resolved 163 installs, including the two policy RPMs and the already-present original-repository dependency `policycoreutils-python-utils`. It contained zero Removing/Erasing entries and was aborted by `--assumeno`; no package was installed. Both nodes still have no target infrastructure or OpenStack service package.

Compute `/dev/sda` retained its GPT system/root/swap layout and UUIDs. `/dev/sdb` and `/dev/sdc` remain blank, unpartitioned 50 GiB whole disks with no filesystem, mount, child, label, UUID, or read-only `blkid` signature.

Detailed credential-free evidence is in `third-edition-work/validation/repository/dependency-closure.txt`. `repo-check.txt` has a separately labeled Task 4B addendum; it does not reinterpret the original ZIP inventory.

## Local cache and packaging contract

The ignored binary cache is `third-edition-work/environment-cache/repository-overlay/`. Its two RPMs are intentionally absent from Git. `third-edition-work/config/repository-overlay-manifest.json` is the tracked deterministic packaging contract and contains exact filenames, NEVRAs, official sources, sizes, signatures, and SHA256 values.

## Residual risks

- The deployed `openstack-local` repository retains the reviewed `gpgcheck=0` contract, so ongoing repository integrity still depends on the immutable ZIP evidence plus the overlay manifest and hashes. The two new RPMs were independently verified against the configured official key before promotion.
- The ignored binary cache must accompany the final environment build; a fresh Git checkout alone intentionally does not contain the RPM payloads. The manifest-to-cache check is therefore a hard packaging gate.
- Repository metadata was regenerated on the controller, not written back into the original ZIP. A future rebuild must start from the immutable ZIP, apply the manifest overlay, run `createrepo_c --update`, and verify the resulting package set rather than assuming the old ZIP metadata includes the overlay.
