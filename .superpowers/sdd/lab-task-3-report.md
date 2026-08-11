# Lab Task 3 Report

## Scope and implementation

- Rechecked all seven files named in the task brief and all 24 deployment-contract tests.
- Kept the already-approved fail-closed host-IP checks, full root-device ancestry checks, explicit `ALLOW_DISK_INITIALIZATION=YES` confirmation, strict Swift XFS-label idempotency, and strict `known_hosts` guidance.
- Added `assert_blank_data_disk DEVICE EXPECTED_SIZE_GIB` to Cinder and Swift.  It is invoked only after the pre-existing state classifier has established a blank target and immediately before the first destructive operation.  It rejects `/dev/sda`, a non-disk or wrong-size target, mounted devices, child partitions, filesystem signatures, and LVM physical volumes.
- Cinder remains limited to `/dev/sdb` and Swift remains limited to `/dev/sdc`; the pre-existing known-safe idempotent states remain separate from first initialization.

## Validation

- Git Bash `bash -n`: 17/17 final scripts passed.
- Deployment contract tests: `python -m pytest third-edition-work/tests/test_deployment_contract.py -v` — 24 passed.
- Hash manifest: `third-edition-work/checkpoints/safe-scripts.sha256` contains lower-case SHA-256 values, POSIX-relative paths, sorted by path, for 17 final scripts plus `build_controller_local_repo.sh` and `remote_exec.py`; recomputation passed 19/19.
- `git diff --check`: passed.

## Remote parser checkpoint

Remote `bash -n -s` parsing on controller `192.168.234.151` is deliberately not attempted until a pre-verified `known_hosts` entry or fingerprint is supplied.  The local known-hosts store has no entry for that address and the controlled documentation explicitly forbids treating `ssh-keyscan` output as identity verification.  No credential was written to this report, source code, command examples, or logs (`<REDACTED>`).

## Risk

The only outstanding risk is the unverified controller host key, which blocks the required remote read-only parser checkpoint.  No deployment command, storage operation, VM change, service change, or source-archive mutation was performed.
