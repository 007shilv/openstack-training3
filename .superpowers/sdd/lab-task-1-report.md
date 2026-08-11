# Lab Validation Task 1 Report — Controlled Workspace and Baseline Inventory

Date: 2026-08-11
Branch: `third-edition`

## Scope and safety

- The immutable inputs under `D:/codex/云计算教材更新/` were not modified.
- A recursive working copy of `openstack-ts` was created at `third-edition-work/deployment/openstack-ts/` (21 files). Its safe deployment settings are intentionally aligned to the verified lab addresses and data disks below.
- The VM work was read-only. The only attempted remote command sequence was:

  ```sh
  cat /etc/os-release
  uname -r
  ip -br addr
  lsblk -o NAME,PATH,SIZE,TYPE,FSTYPE,MOUNTPOINTS
  rpm -qa | sort
  ```

- The requested clean VMware snapshots are recorded as `controller-sp3-clean` and `compute-sp3-clean`. The task context states that both are confirmed created. They remain a hard gate for any later remote mutation.
- No credential is recorded in this report. The controlled deployment copy is scanned before each commit for known credential literals and uses runtime-only password inputs.

## Immutable-input checkpoint

`third-edition-work/checkpoints/original-inputs.sha256` contains 23 SHA-256 entries, sorted by input path:

- the second-edition DOCX;
- `openstack_repo.zip`; and
- every file in the original `openstack-ts` tree (21 files).

Each stored digest was recomputed against its original source during verification.

## Baseline findings

### Controller — 192.168.234.151

Collection completed and is stored in `third-edition-work/validation/baseline/controller.txt`.

- OS: openEuler 24.03 (LTS-SP3)
- Kernel: `6.6.0-132.0.0.111.oe2403sp3.x86_64`
- Management address: `192.168.234.151/24` on `ens33`
- Root filesystem: `/dev/sda2` (96G ext4 mounted at `/`)
- The full installed RPM inventory is included in the baseline file.

### Compute — 192.168.234.150

Collection completed and is stored in `third-edition-work/validation/baseline/compute.txt`.

- OS: openEuler 24.03 (LTS-SP3)
- Kernel: `6.6.0-132.0.0.111.oe2403sp3.x86_64`
- Management address: `192.168.234.150/24` on `ens33`
- Root filesystem: `/dev/sda2` (192G ext4 mounted at `/`)
- `/dev/sdb` and `/dev/sdc` are each 50G disks with no filesystem or mountpoint reported; they are suitable as the empty Cinder and Swift lab data disks, respectively.

## Verification

The initial verification check passed for:

1. all 23 checkpoint entries: structure, path order, and recomputed hashes;
2. exact 21-file parity between the original `openstack-ts` tree and the newly created controlled working copy; and
3. controller OS, address, and root-device facts, plus the explicit compute collection-failure record at that time.

## Baseline refresh and safe-copy alignment

After the lab addresses were fixed, the same read-only command sequence was successfully rerun on both controller and compute. The refreshed baseline files contain the full OS, network, block-device, and sorted RPM inventories.

The controlled deployment copy was then aligned without executing any deployment script:

- controller address remains `192.168.234.151/24`;
- compute references now use `192.168.234.150/24`;
- gateway and DNS remain `192.168.234.2`;
- Cinder uses `compute:/dev/sdb`; and
- Swift uses `compute:/dev/sdc`.

No disk was formatted and no OpenStack service was deployed during this task.

## Security and fail-closed remediation

The controlled copy is intentionally no longer byte-identical to the immutable source tree. The immutable checkpoint remains the evidence for the original 21-file inventory; the safe copy has controlled changes in these categories:

- all root/SSH, database, RabbitMQ, admin, and service credential defaults were removed from the copied Markdown, shell, and Python files;
- deployment shell scripts require `OPENSTACK_DEPLOY_PASSWORD` at runtime with no default value, and embedded Python reads it from the process environment instead of containing a literal;
- `remote_exec.py` now requires a fixed `--role` (`controller` or `compute`), resolves the only allowed lab addresses internally, restricts stdin scripts to `final-scripts/`, and reads SSH credentials from a protected environment variable or an interactive prompt;
- documentation uses placeholders and role-based SSH examples, never password command-line examples;
- Cinder is restricted to `/dev/sdb` and Swift to `/dev/sdc`; all Cinder `/dev/sda` references were removed; and
- the Cinder and Swift compute scripts now reject a wrong compute address, a non-whole-disk target, the root device/root parent, mounted or partitioned targets, unexpected signatures, and first initialization without `ALLOW_DISK_INITIALIZATION=YES`.

The initial baseline outputs were normalized to remove trailing whitespace. This does not alter any recorded field value.

## Remediation verification

- `git diff --check` passes after baseline normalization.
- Recursive scans find no legacy compute address, no Cinder `/dev/sda` target, and no known credential literal in `deployment/openstack-ts`.
- All copied deployment shell scripts pass `bash -n`; `remote_exec.py` passes `py_compile` and exposes the fixed-role help interface.
- Static guard checks confirm that both data-disk scripts contain the compute-address, exact-device, root-parent, mount/partition/signature, and explicit-confirmation rejection paths. A local mocked Cinder-guard harness verified that wrong-host, root-device, and absent-confirmation paths each exit nonzero. No deployment script was connected to a VM or executed.

## Second review remediation

- The disk guidance now treats `sda`/`sda2` only as the compute system disk/root partition. Cinder is exclusively `sdb`; Swift is exclusively `sdc`.
- Both disk guards resolve the complete root ancestry with `lsblk -s` and canonicalized paths, so a target that appears anywhere in the root chain is rejected.
- Swift initial formatting creates the stable XFS label `openstack-swift-data`. An existing Swift disk is accepted only when both its filesystem type and label match; its source and target mountpoint are rechecked before ownership changes.
- Deployment shell files are UTF-8 without a BOM, enabling a literal `#!` first byte and direct Git Bash syntax checks.
- SSH now uses system plus reviewed `known_hosts` keys with `RejectPolicy`; the documentation requires `ssh-keyscan` collection followed by manual fingerprint verification before use.
- Earlier task commits containing copied legacy credential defaults were never pushed. Before handoff, the branch history from the designated base is rewritten into one final sanitized commit so those intermediate commits are no longer reachable from this branch. No VM password was changed.
