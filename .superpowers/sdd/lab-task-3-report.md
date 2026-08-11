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

Remote parsing completed on controller `192.168.234.151`: all 17 scripts passed `bash -n -s`.  Each script was sent only through standard input to a separate remote syntax-parser process; none was saved, sourced, or executed.  The target reported `openEuler release 24.03 (LTS-SP3)`.

Before authentication, the controller VMX MAC address was matched to the Windows VMnet8 neighbour entry, and two unauthenticated handshakes returned the same ED25519 host key, fingerprint `SHA256:pDvchiPMwmZkhINk+30i1SZR7OjrZseDGUw4mKfLlVE`.  The reviewed `known_hosts` entry was loaded with Paramiko `RejectPolicy`.  The detailed, credential-free evidence is in `third-edition-work/validation/static/bash-syntax-openeuler.txt`; no credential was written to this report, source code, command examples, or logs (`<REDACTED>`).

## Risk

The remote syntax checkpoint validates parsing only; it cannot establish runtime package availability or deployment correctness.  No deployment command, storage operation, VM change, service change, or source-archive mutation was performed.
