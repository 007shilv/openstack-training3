# OpenStack Lab Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a safe, reproducible Antelope deployment baseline and verified facts for the manual textbook procedures.

**Architecture:** Preserve the user's original scripts and create a controlled working copy. Static contract tests enforce addresses, disks, versions, and destructive-operation guards before any remote mutation; deployment then runs in staged manual and automated modes with sanitized logs.

**Tech Stack:** PowerShell, Python 3.14 + pytest + Paramiko, Bash, RPM/DNF, openEuler 24.03 LTS SP3, OpenStack Antelope.

## Global Constraints

- Never edit `openstack-ts/` or `openstack_repo.zip` in place.
- Never run `pvcreate`, `mkfs`, `wipefs`, or LVM commands against `/dev/sda`.
- Do not begin mutation until the user confirms clean snapshots for both VMs.
- Remote log files must replace the known lab password with `<REDACTED>`.
- All checkpoints use SHA-256 because the workspace has no Git repository.

---

### Task 1: Create the controlled deployment workspace and baseline inventory

**Files:**
- Create: `third-edition-work/deployment/openstack-ts/`
- Create: `third-edition-work/validation/baseline/controller.txt`
- Create: `third-edition-work/validation/baseline/compute.txt`
- Create: `third-edition-work/checkpoints/original-inputs.sha256`

**Interfaces:**
- Consumes: original scripts, repo ZIP, VM SSH access.
- Produces: immutable input hashes and safe working copy.

- [ ] Create the directories with `New-Item -ItemType Directory -Force`.
- [ ] Copy `openstack-ts/` recursively to `third-edition-work/deployment/openstack-ts/` with `Copy-Item`; do not move or delete the original.
- [ ] Hash the original DOCX, `openstack_repo.zip`, and every original script using `Get-FileHash -Algorithm SHA256`; save sorted output in `third-edition-work/checkpoints/original-inputs.sha256`.
- [ ] Record that VMware snapshots named `controller-sp3-clean` and `compute-sp3-clean` have been requested. Snapshot confirmation is not required for this read-only baseline task, but it is a hard gate before Task 5 performs any remote mutation.
- [ ] Run read-only commands on both VMs: `cat /etc/os-release`, `uname -r`, `ip -br addr`, `lsblk -o NAME,PATH,SIZE,TYPE,FSTYPE,MOUNTPOINTS`, and `rpm -qa | sort`.
- [ ] Verify expected facts: both hosts are SP3; controller has `192.168.234.151/24`; compute has `192.168.234.150/24`; compute root is `/dev/sda2`; `/dev/sdb` and `/dev/sdc` are blank 50 GB disks.

### Task 2: Write static deployment-contract tests

**Files:**
- Create: `third-edition-work/tests/test_deployment_contract.py`
- Create: `third-edition-work/config/version-matrix.json`

**Interfaces:**
- Consumes: safe script copy and RPM names from `openstack_repo.zip`.
- Produces: executable tests preventing address/disk/version regressions.

- [ ] Create `version-matrix.json` with exact values: Keystone 23.0.1, Glance 26.0.0, Placement 9.0.0, Nova 27.3.0, Neutron 22.1.0, Cinder 22.1.2, Swift 2.31.1, Horizon 23.1.0.
- [ ] Write pytest cases that assert: `.152` is absent from the working scripts; controller `.151` and compute `.150` are present; Cinder uses `/dev/sdb`; Swift uses `/dev/sdc`; no destructive command contains `/dev/sda`; all 17 final scripts exist; Antelope release configuration remains present.
- [ ] Add a test that opens `openstack_repo.zip`, matches the eight component RPM versions, and compares them with `version-matrix.json`.
- [ ] Run `python -m pytest third-edition-work/tests/test_deployment_contract.py -v`; expected initial result is FAIL because `.152` and Cinder `/dev/sda` still exist in the copied scripts.

### Task 3: Patch addresses, disks, and destructive-operation guards

**Files:**
- Modify: `third-edition-work/deployment/openstack-ts/final-scripts/02-compute-network.sh`
- Modify: `third-edition-work/deployment/openstack-ts/final-scripts/04-compute-base.sh`
- Modify: `third-edition-work/deployment/openstack-ts/final-scripts/10-compute-nova.sh`
- Modify: `third-edition-work/deployment/openstack-ts/final-scripts/12-compute-neutron.sh`
- Modify: `third-edition-work/deployment/openstack-ts/final-scripts/14-compute-cinder.sh`
- Modify: `third-edition-work/deployment/openstack-ts/final-scripts/16-compute-swift.sh`
- Modify: `third-edition-work/deployment/openstack-ts/openstack-antelope-openeuler-install.md`

**Interfaces:**
- Consumes: contract tests from Task 2.
- Produces: safe scripts accepted by tests.

- [ ] Replace every active compute management address `192.168.234.152` with `192.168.234.150` in the working copy.
- [ ] Change the Cinder data device from `/dev/sda` to `/dev/sdb` in code and documentation.
- [ ] Add a shared `assert_blank_data_disk DEVICE EXPECTED_SIZE_GIB` function to Cinder and Swift scripts. It must reject `/dev/sda`, any mounted device, any device with child partitions, any device with an existing filesystem, and any device reported by `pvs`.
- [ ] Call the guard with `/dev/sdb 50` before `pvcreate`, and with `/dev/sdc 50` before `mkfs.xfs`.
- [ ] Run `bash -n` against all 17 scripts through an openEuler VM without executing them; expected result is exit code 0 for every file.
- [ ] Run `python -m pytest third-edition-work/tests/test_deployment_contract.py -v`; expected result is all PASS.
- [ ] Save hashes of the working scripts in `third-edition-work/checkpoints/safe-scripts.sha256`.

### Task 4: Validate and stage the offline repository

**Files:**
- Create: `third-edition-work/validation/repository/rpm-inventory.txt`
- Create: `third-edition-work/validation/repository/repo-check.txt`

**Interfaces:**
- Consumes: `openstack_repo.zip` and version matrix.
- Produces: validated local repository available to controller and compute.

- [ ] List all ZIP entries and record the eight exact component RPM versions in `rpm-inventory.txt`.
- [ ] Extract the repository to `controller:/opt/openstack_repo` only after checking the target path is exactly `/opt/openstack_repo`.
- [ ] Verify `repodata/repomd.xml` exists and run `dnf repolist --disablerepo='*' --enablerepo='openstack-local'` on controller.
- [ ] Configure or verify the controller FTP repository and test `curl -I ftp://192.168.234.151/openstack_repo/repodata/repomd.xml` from compute.
- [ ] Record successful file and FTP repository access in `repo-check.txt`.

### Task 5: Execute and record the manual deployment path

**Files:**
- Create: `third-edition-work/validation/manual-install/01-base.md` through `10-dashboard.md`
- Create: `third-edition-work/validation/manual-install/config-snapshots/`

**Interfaces:**
- Consumes: safe scripts as reference, validated repository, clean snapshots.
- Produces: textbook-ready manual commands, configuration blocks, and sanitized outputs.

- [ ] Restore both clean snapshots before the manual run and reconfirm the three compute disks.
- [ ] For each component, read the corresponding script and execute its commands manually rather than invoking the script.
- [ ] Record package commands, SQL statements, OpenStack user/service/endpoint commands, exact edited INI sections, database-sync commands, systemd commands, and verification output.
- [ ] Copy the final relevant configuration files into `config-snapshots/`, replacing all passwords with `<SERVICE_PASSWORD>` or `<DB_PASSWORD>`.
- [ ] Complete components in order: networking/base, MariaDB/RabbitMQ/Memcached, Keystone, Glance, Placement, Nova controller/compute, Neutron controller/compute, Cinder controller/compute, Swift controller/compute, Horizon.
- [ ] After each component, run its API/CLI/service checks and do not continue until they pass.

### Task 6: Run end-to-end acceptance and preserve evidence

**Files:**
- Create: `third-edition-work/validation/openstack-install/end-to-end.md`
- Create: `third-edition-work/validation/openstack-install/service-output/`

**Interfaces:**
- Consumes: completed manual platform.
- Produces: evidence that later textbook and agent tasks can rely on.

- [ ] Run and save `openstack service list`, `endpoint list`, `compute service list`, `network agent list`, and `volume service list`.
- [ ] Confirm Swift `/healthcheck` returns HTTP 200 and record `swift stat`.
- [ ] Upload CirrOS, create a flavor, create networks/router/security rule, boot an instance, and verify console and network reachability.
- [ ] Create and attach a Cinder volume; verify inside the instance or via OpenStack attachment state.
- [ ] Create a Swift container, upload an object, download it, and compare SHA-256 hashes.
- [ ] Record PASS/FAIL and timestamps in `end-to-end.md`; all required checks must be PASS before this stream completes.
