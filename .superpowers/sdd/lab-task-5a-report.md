# Lab Task 5A Report — Manual Base and Infrastructure Deployment

## Outcome

DONE. The current reviewed VM state was retained; no VMware snapshot was restored or created. Both nodes completed the base gate, and the controller then completed the infrastructure gate in strict dependency order. No copied deployment script was executed. No Keystone or later OpenStack service package was installed, and no disk, partition, LVM object, filesystem, or mount was changed.

All remote access loaded the node-specific reviewed host-key file and used Paramiko `RejectPolicy`. The SSH login credential existed only in connection memory and is absent from files, examples, logs, artifacts, and Git.

## Strict execution order

The run used hard stop-on-failure gates:

1. controller and compute starting state, identity, IPs, `ens34`, RPM baseline, service absence, and compute disks;
2. persistent hostnames, preserved `/etc/hosts`, forward resolution, and cross-node ping;
3. isolated `openstack-local` access on both nodes;
4. teaching-lab SELinux/firewalld state;
5. Antelope release installation, SP3-host/SP2-Antelope compatibility rewrite, and openEuler repository adjustments;
6. chronyd enablement and time-state verification;
7. protected runtime-secret creation and two-node placement;
8. controller package preflight and installation;
9. MariaDB configuration, startup, SQL access, variables, and listener;
10. RabbitMQ startup, user/password update, permissions, and protected authentication;
11. Memcached configuration, startup, exact listeners, and client set/get/delete;
12. OpenStack CLI version and final cross-node audit.

No later component ran while an earlier gate was unresolved. The required order for subsequent slices is Keystone → Glance → Placement/Nova → Neutron → Cinder/Swift → Horizon. Each slice must finish database, service, endpoint, synchronization, and API/CLI checks before the next begins; they must not race in parallel.

## First-round review remediation

The independent first-round review reported no Critical finding. Every Important and Minor item was addressed without reconnecting to either VM and without changing the already verified remote state:

1. Both manual records now establish `set -Eeuo pipefail`, an inherited ERR trap, `die`, executable assertion functions, and ordered stage runners. Behavior tests inject a failure into a middle stage and prove that no later stage runs. MariaDB live values, chrony synchronization, RabbitMQ user/permission/authentication state, Memcached exact listeners and set/get/delete behavior are assertions rather than display-only probes. RabbitMQ authentication failure clears the transient variable inside the failure branch before terminating.
2. The compute disk guard accepts only `blkid -p` RC=2 as blank and rejects RC=0 plus every other exit class. It also asserts block-device identity, exact byte size, no child/partition, no filesystem, no mount, no LVM PV (including orphan PV), and exclusion from the canonical root-device ancestry. Later-service RPM absence now distinguishes installed, expected absent, RPM database/query failure, and misleading RC=1 output.
3. The base record now includes a complete executable workstation Paramiko transfer example. It loads only the two reviewed known-host files with `RejectPolicy`, obtains the SSH credential through `getpass`, creates a root-owned `0600` remote temporary file with `O_EXCL|O_NOFOLLOW`, streams in 64 KiB chunks without output or hashing, performs same-directory atomic promotion, always cleans the exact temporary path, and compares only safe metadata. RabbitMQ's user-present and user-absent rerun branches are executable and behavior-tested.
4. The `/etc/hosts` transformation removes only the two target aliases, preserves unrelated aliases and comments on the same line, and appends one canonical mapping for each node. A behavior test executes the extracted Python heredoc against mixed-alias/comment fixtures and compares the exact result.
5. Fourteen targeted contract-test cases now cover strict-session short-circuiting, disk-probe exit classes and safety dimensions, hosts preservation, later-package absence classes, transfer-program AST and syntax, unowned-temporary cleanup refusal, RabbitMQ idempotence/authentication and user-probe failure, live-service assertions, and the ban on `|| true` in protected manual checks. Together with the original 26 tests, the suite contains 40 passing tests.

## Second-round review remediation

The second review identified one Important and one Minor path; both were reproduced by new failing behavior tests before the documentation code was changed:

- RabbitMQ `list_users` is now an independent captured probe. Its true nonzero status is retained and reported, the transient password variable is cleared, and execution stops before `add_user`, `change_password`, `set_permissions`, or `authenticate_user`. The new RC=7 behavior case proves zero mutation/authentication actions; the existing absent-user, present-user, and authentication-failure paths continue to pass.
- Secret transfer now records ownership separately for controller and compute as exact path → `(st_dev, st_ino)` mappings. Registration occurs only after remote `O_EXCL|O_NOFOLLOW`, ownership/mode checks, and `fstat`/`lstat` inode equality return success. Streaming, promotion, and cleanup validate that identity; promotion removes the owned entry, and `finally` iterates only entries still owned. The new preexisting-path/O_EXCL-failure case proves that cleanup is not called for an unowned path.

## Starting-state proof

- Both nodes reported openEuler 24.03 LTS SP3 x86_64.
- controller `ens33` was `192.168.234.151/24`; compute `ens33` was `192.168.234.150/24`; neither `ens34` had an IPv4 address.
- controller RPMs were the Task 1 baseline plus only Task 4 `vsftpd`; compute matched its Task 1 RPM baseline exactly.
- Neither node had the Antelope release package, the Task 5A infrastructure targets, or any later OpenStack service package.
- controller `/dev/sda` remained its 100 GiB system disk. compute `/dev/sda` remained its 200 GiB system disk; `/dev/sdb` and `/dev/sdc` were each blank 50 GiB whole disks. Read-only `blkid -p` returned RC=2 for both data disks.
- Both existing `openstack-local` repositories passed isolated repolist and makecache checks before base mutation.

## Remote mutations and backups

The root-only backup directory on each node is:

```text
/root/openstack-lab-backups/task-5a-20260811T043901Z
```

It was created mode 0700. Before replacement, it received the original `/etc/hostname`, `/etc/hosts`, `/etc/selinux/config`, `/etc/yum.repos.d/openEuler.repo`, `/etc/yum.repos.d/openstack-local.repo`, and `/etc/chrony.conf`. After the release package generated its file, the original SP3 `/etc/yum.repos.d/openstack-antelope.repo` was saved there. The controller also retains the package-default `/etc/sysconfig/memcached` in this backup directory. `/etc/my.cnf.d/openstack.cnf` did not exist before Task 5A and therefore had no predecessor to back up.

Base mutations on both nodes:

- persistent hostname set to `controller` or `compute`;
- unique mappings `192.168.234.151 controller` and `192.168.234.150 compute` appended while unrelated hosts entries and comments were preserved;
- SELinux set to Permissive persistently and at runtime;
- firewalld stopped and disabled for the isolated teaching lab;
- `openstack-release-antelope-1.0.6-6.oe2403sp3.noarch` installed with only `openstack-local` enabled;
- generated Antelope URLs rewritten from openEuler 24.03 LTS SP3 to SP2, including repository and GPG-key URLs;
- active metalinks removed from `openEuler.repo`; `debuginfo`, `source`, and `update-source` disabled;
- chrony confirmed from only `openstack-local`; chronyd enabled and started.

Controller infrastructure mutations:

- 163 packages installed in DNF transaction 4, all from `openstack-local`, with weak dependencies disabled and no removal or downgrade action;
- `/etc/my.cnf.d/openstack.cnf` created with the reviewed OpenStack MariaDB settings;
- MariaDB enabled and started;
- RabbitMQ enabled and started; user `openstack` created/updated, authenticated, and granted `.*` configure/write/read permissions on `/`;
- `/etc/sysconfig/memcached` replaced with the reviewed three-address listener configuration; Memcached enabled and started;
- OpenStack CLI installed and verified.

## Runtime-secret handling

One cryptographically random value was generated on controller and stored only as `/root/.openstack-lab-secrets`. It was streamed directly into an exclusive root-only destination on compute and atomically promoted to the same path. No local secret file was created. The value was never inspected, printed, returned, hashed, logged, documented, or committed.

Only metadata was checked: both files are non-empty, equal length, root-owned, and mode 0600. RabbitMQ consumed the controller value through a transient non-interactive shell variable; its value did not appear in command text or output. Documentation uses `<RABBIT_PASS>`, `<SERVICE_PASSWORD>`, and `<DB_PASSWORD>` placeholders and never implies that production should reuse one credential.

## Package resolution and Task 4B dependency closure

The first isolated infrastructure transaction failed before installing any package because the immutable repository lacked `mysql-selinux` and `memcached-selinux`, which are conditional requirements while `selinux-policy-targeted` is installed. Execution stopped. No `--allowerasing`, `--nodeps`, `--skip-broken`, external repository, or policy-package removal was used.

Task 4B then independently verified and added the exact matching SP3 policy RPMs through a reviewed overlay. On resume, the controller `--assumeno` plan resolved 163 installs and zero removal-class sections. The actual command retained `--disablerepo='*' --enablerepo='openstack-local'` and `install_weak_deps=False`. `mysql-config` remained absent and `mariadb-config` declared no conflict, so no mysql configuration package was removed.

Direct package results:

```text
mariadb-config-10.5.29-4.oe2403sp3.x86_64
mariadb-10.5.29-4.oe2403sp3.x86_64
mariadb-server-10.5.29-4.oe2403sp3.x86_64
python3-PyMySQL-1.0.2-1.oe2403sp2.noarch
rabbitmq-server-3.9.23-2.oe2403sp3.x86_64
memcached-1.6.22-4.oe2403sp3.x86_64
python3-memcached-1.59-3.oe2403sp3.noarch
python3-openstackclient-6.2.0-1.oe2403sp2.noarch
mysql-selinux-1.0.10-1.oe2403sp3.noarch
memcached-selinux-1.6.22-4.oe2403sp3.x86_64
policycoreutils-python-utils-3.5-4.oe2403sp3.noarch
```

Final RPM counts are controller 680 and compute 516. The compute node did not receive any controller infrastructure package.

## Service and verification evidence

Base:

- exact hosts mappings: one each on both nodes;
- `getent ahostsv4`: controller `.151`, compute `.150`;
- cross-node ping: 2/2 packets each direction, 0% loss;
- SELinux: Permissive; firewalld: inactive/disabled;
- Antelope repository: 0 SP3 references and 4 SP2 references on both nodes;
- chronyd: active/enabled; controller Stratum 3 and compute Stratum 4; both Leap status Normal;
- secret files: mode/owner/non-empty/equal-length metadata PASS.

Infrastructure:

- MariaDB active/enabled; local `SELECT 1` returned 1; live variables matched `0.0.0.0`, InnoDB, file-per-table=1, 4096 connections, `utf8_general_ci`, and `utf8`; TCP 3306 listening on `0.0.0.0`;
- RabbitMQ active/enabled; protected authentication PASS; `openstack` user present with no administrator tag; `/` permissions exactly `.* / .* / .*`; AMQP TCP 5672 listening;
- Memcached active/enabled; TCP 11211 listening on only `127.0.0.1`, `::1`, and `192.168.234.151`; python3-memcached set/get/delete passed on all three;
- `openstack --version`: `openstack 6.2.0`;
- Keystone, Glance, Placement, Nova, Neutron, Cinder, Swift, and Horizon service packages absent;
- compute data disks remained blank and untouched after all work.

The first RabbitMQ display check used an unsupported `--formatter=tsv` option after the service, user, permissions, and authentication had already passed. Native `list_users` and `list_user_permissions` output then passed. The first Memcached client checks used unsupported IPv6 connection-string forms; source inspection showed that python3-memcached 1.59 requires `inet6:[::1]:11211`. That exact supported form passed without any service configuration change. These were verification-client compatibility issues, not service failures.

## Artifacts

- `third-edition-work/validation/manual-install/01-base.md`
- `third-edition-work/validation/manual-install/02-infrastructure.md`
- `third-edition-work/validation/manual-install/config-snapshots/controller-etc-hostname.txt`
- `third-edition-work/validation/manual-install/config-snapshots/compute-etc-hostname.txt`
- `third-edition-work/validation/manual-install/config-snapshots/controller-etc-hosts.txt`
- `third-edition-work/validation/manual-install/config-snapshots/compute-etc-hosts.txt`
- `third-edition-work/validation/manual-install/config-snapshots/controller-openstack-local.repo`
- `third-edition-work/validation/manual-install/config-snapshots/compute-openstack-local.repo`
- `third-edition-work/validation/manual-install/config-snapshots/controller-openstack-antelope.repo`
- `third-edition-work/validation/manual-install/config-snapshots/compute-openstack-antelope.repo`
- `third-edition-work/validation/manual-install/config-snapshots/controller-openEuler.repo`
- `third-edition-work/validation/manual-install/config-snapshots/compute-openEuler.repo`
- `third-edition-work/validation/manual-install/config-snapshots/controller-chrony.conf`
- `third-edition-work/validation/manual-install/config-snapshots/compute-chrony.conf`
- `third-edition-work/validation/manual-install/config-snapshots/controller-selinux-config`
- `third-edition-work/validation/manual-install/config-snapshots/compute-selinux-config`
- `third-edition-work/validation/manual-install/config-snapshots/controller-openstack.cnf`
- `third-edition-work/validation/manual-install/config-snapshots/controller-memcached`
- `.superpowers/sdd/lab-task-5a-report.md`

All snapshots were captured from final remote files after successful checks. None contains a credential.

## Required local gates

- TDD review-fix RED evidence: 12 first-round and 2 second-round Task 5A cases each failed against the corresponding pre-fix documents for the expected reason; after remediation, all 14 pass.
- `python -m pytest -q`: 40 passed (26 existing plus 14 targeted Task 5A cases).
- `git diff --check`: RC=0, no output.
- `git diff --cached --check`: RC=0, no output.
- Extracted Python transfer/hosts/Memcached snippets: parsed and compiled or executed by the targeted tests; extracted Bash gate functions: executed with command mocks under Git Bash.
- Canonical snapshot-to-remote comparison through host-key-pinned SFTP: controller 9/9 and compute 7/7 match. Only trailing whitespace and redundant final blank lines in remote text were normalized.
- Artifact requirement audit: PASS for the two manual records, strict order gates, placeholders, rollback/diagnostic sections, 16 snapshots, and absence of copied-script invocation.
- Targeted credential scan of the complete committed Task 5A artifact set and the remediation diff: PASS for the known login credential, literal long secret assignments, credential-bearing URLs, and private-key markers. Runtime-secret values were never read for scanning.
- Remediation staged-file audit: only the two manual records, their contract-test file, and this report changed; no binary or unrelated path.

## Residual risks

- SELinux Permissive and disabled firewalld are teaching-lab exceptions. Production requires Enforcing policy and least-privilege firewall rules.
- `gpgcheck=0` remains on the lab local repositories; integrity depends on the immutable ZIP and reviewed overlay provenance, signatures, manifest, and hashes.
- Anonymous read-only FTP remains available from Task 4. With firewalld disabled, exposure is broader than the earlier port-limited state.
- MariaDB listens on all IPv4 addresses, RabbitMQ listens on AMQP 5672, and Memcached exposes an unauthenticated listener on the management address. These are acceptable only on the isolated network; production requires network restriction, authentication/TLS where supported, and service-specific credentials.
- One runtime random value is reused by later lab slices. Production must use independent secrets, a secret manager, rotation, and audit. Delete both protected files after the lab is decommissioned.
- Root-only backups remain on both nodes and should be removed only after later slices pass and the exact rollback scope is no longer needed.
- Public chrony sources currently report Normal status, but later execution must recheck time before relying on token expiry or message heartbeats.
- The lab VMs and data disks are resettable, but this slice deliberately did not weaken any fail-closed disk guard or touch `/dev/sdb`/`/dev/sdc`. Later Cinder/Swift initialization must retain full root-ancestor, signature, partition, mount, and LVM checks.
