# Lab Task 5E report: manual Nova controller and compute deployment

Status: DONE — pending independent review.

Resume closure (2026-08-12): no snapshot was created or restored, and neither node
was changed.  The two reviewed, per-node `known_hosts` files were used with
Paramiko `RejectPolicy` for fresh read-only acceptance.  Controller identity and
address were exact; the Nova API, scheduler, conductor and noVNC services were
active and enabled; `http://controller:8774/v2.1` returned 200; an authenticated
OpenStack CLI token, the exact three healthy compute-service rows and the one
healthy `compute` hypervisor were confirmed.  The Placement client subcommand
was unavailable in this client build, so the same authenticated token was used
against the documented Placement 1.39 REST resource-provider endpoint instead;
it returned exactly one provider named `compute`.  This is a client-command
availability deviation, not a Placement API failure.  On compute, libvirtd and
nova-compute were active and enabled.  Neutron was absent on both nodes, and
`/dev/sdb` and `/dev/sdc` remained blank 50 GiB disks with no children,
filesystem, mount, wipefs signature or blkid signature.  The previous
cross-node compute-identity verifier also passed again without disclosing the
identifier.

The existing controller transaction 8 and compute transaction 3 were collected
again through strict-host-key, read-only collectors.  Their complete sanitized
history/current-RPM/local-repository evidence is now tracked with this Task 5E
closure.  No package, database, identity, configuration, schema, cell mapping,
service, or Neutron mutation was repeated during the resume.

Last known remote state before the pause: Nova controller and compute were installed and healthy; controller services, compute service, libvirt, cells, host mapping, hypervisor, Placement provider/inventories and the no-workload boundaries had passed the last remote audit. The final read-only check before the pause proved nova:nova 0644 single-link compute identity and file/Nova DB/Placement provider UUID consistency without disclosing the UUID. No Neutron or later component was entered. The user may safely pause or power off the two lab VMs; this report makes no claim about their state after that action.

Review-remediation state at pause: work in progress. The focused `31 passed` and full `181 passed` results below were fresh when obtained, but the controller/compute gate text and manual presentation were edited afterward and have not been rerun. Final structured audit wiring, final fenced syntax, security scan, diff/scope audit, commit and independent review remain incomplete.

Base commit: `c247695f5b079249086f9fdcc74621b7a3071462`

Partial TDD checkpoint: `66fb5d558f1b22b44af06ab97a009bf48568f12b`

Dependency-closure prerequisite: `0bdd42479e57934102cf941a26d9875abe89d15b` (independently reviewed PASS before compute installation resumed)

Task 5E implementation commit: `276ddc7dfe51f92e1d7e60e1770741d68aa0004c`

Manual-procedure decision record in review base: `029bfa6` (not duplicated in the Task 5E remediation commit)

The first independent review of `276ddc7` returned FAIL with five Important findings and one Minor finding. This remediation changes only Task 5E documentation, tests, complete transaction evidence, and read-only verification helpers; it does not repeat the already healthy Nova deployment and does not enter Neutron.

## Required order and remote outcome

No VMware snapshot was created or restored. Both nodes were reached through their reviewed per-node known_hosts files with Paramiko RejectPolicy. Neither reference script 09 nor 10 was executed.

The exact order was controller+compute starting gate, controller package transaction, three databases/grants, staged identity, package-default backup/atomic controller config, API DB/cell0/cell1/main DB, upgrade check, API/scheduler/conductor/noVNC, rerun compute gate, compute plan/transaction, package-default backup/atomic compute config, compute identity, libvirt, nova-compute, host discovery twice, services/hypervisor/provider/inventory, upgrade check, and final two-node audit. No Neutron or later task was entered.

### Controller

- The two-node starting gate proved exact host/IP/ens34/time/local-repo state, complete Keystone/Glance/Placement dependencies and APIs/schemas/upgrades, authenticated `resource_providers=[]`, total Nova/later absence, and two blank compute data disks.
- The remediated production start gate now proves exact Default-domain service project and global admin role; exact enabled glance/placement service users and project-role bindings; exact identity/image/placement services and nine service-ID-bound endpoints; Keystone v3.14, Glance v2.15 CURRENT and Placement v1.0/CURRENT/max 1.39; exact 49/14/13 table counts and exact migration heads; three successful Placement upgrade checks; authenticated providers exactly empty; and all Nova/later packages, databases, DB users, identities, endpoints, listeners and temporary artifacts absent. Probe errors and partial state remain failures.
- DNF transaction 8 installed 40 RPMs, all from `openstack-local`, weak dependencies disabled, with zero removal/downgrade/replacement actions. `transaction-evidence/nova-controller-transaction.txt` stores all 40 history action/NEVRA/repo rows, all 40 current RPM rows and all 40 current repo-metadata rows; the three sets match exactly. The four requested roots and Nova common/python package are 27.3.0-1.oe2403sp2.
- Databases `nova_api`, `nova`, `nova_cell0` and only `nova` accounts at `%`, `127.0.0.1`, `localhost` were created with parameterized values. Exact non-credential evidence proved nine schema scopes, global USAGE only, the MariaDB complete schema-level ALL set only on those databases, and no table/column/routine/proxy/role extras. Two TCP login probes passed without logging credentials.
- The enabled Default-domain `nova` user, exact admin assignment on project service, enabled `nova`/`compute` service, and public/internal/admin RegionOne endpoints at `http://controller:8774/v2.1` passed staged requery and per-ID show validation.
- The student-facing path now shows the MariaDB SQL one statement at a time, the Nova user/role/service/three endpoint CLI commands one at a time, `vi /etc/nova/nova.conf` with every final parameter, all four `nova-manage` schema/cell commands, and controller `systemctl` commands in their required order. Python helpers are labeled validation-only and cannot replace those manual steps.
- Clean package-default `/etc/nova/nova.conf` was copied byte-for-byte with metadata to `/root/openstack-lab-backups/task-5e-20260811T113129Z/nova.conf.package-default`. Atomic configuration installed root:nova 0640 with URL-encoded connection values and raw service auth values only in process memory. Future Neutron/Cinder sections are documented inactive dependencies.
- Strict schema order passed. API DB has exactly 32 tables and head `b30f573d3377`; main and cell0 each have 110 tables and head `960aac0e09ea`. Cell mappings are exactly reserved cell0 and one enabled cell1; cell1 UUID and credential-bearing URLs were not printed.
- Precompute `nova-status upgrade check` returned RC 0 with seven Success results. Controller service order API, scheduler, conductor, noVNC passed. Ports 8774/v2.1 CURRENT and 6080 were unique; authenticated Compute API access succeeded; only scheduler and conductor existed before compute.

### Compute

- The compute pre-mutation gate was rerun immediately before planning and passed: packages/identity/later state absent, both disks blank.
- After reviewed Task 4C closure, the fresh no-install plan exactly matched the reviewed result: 403 machine rows, 398 Install and five Upgrade, all `openstack-local`, every removal class zero. RPM baseline, DNF history 2, and boot ID were unchanged; install count remained zero.
- Real DNF transaction 3 completed the same 398 Install and five Upgrade. History has 398 Install plus five Upgrade new rows from `@openstack-local`, zero unsafe actions. The new RPM set has 403 NEVRAs; only five old same-name NEVRAs left the installed set: gnutls 3.8.2-9 and systemd/systemd-cryptsetup/systemd-libs/systemd-udev 255-50. New values are gnutls 3.8.2-14 and those systemd components 255-58. QEMU 11:8.2.0-73 provides qemu-kvm.
- `transaction-evidence/nova-compute-transaction.txt` stores all 403 new history rows (398 Install plus five Upgrade), all five old Upgraded rows with exact new replacement NEVRA, all 403 current RPM rows, and all 403 current `openstack-local` repo-metadata rows. The three new-NEVRA sets and all five old/new pairs match; this proof does not rely on the Task 4C assumeno plan.
- Boot ID stayed unchanged; sshd/chronyd stayed active+enabled; failed-unit set was identical before/after; package scripts did not start libvirt or nova-compute. Disk guards passed again.
- Clean package-default Nova config was copied byte-for-byte to `/root/openstack-lab-backups/task-5e-20260811T122341Z/nova.conf.package-default`. Atomic compute config is root:nova 0640. No vmx/svm and no `/dev/kvm` were present, so `virt_type=qemu` is used for portable nested teaching; hardware-acceleration validation is explicitly not claimed.
- The compute chapter now presents `vi /etc/nova/nova.conf`, every exact final parameter, ownership/mode correction, libvirt then nova-compute service commands, and controller-side host discovery as explicit student steps. The atomic writer and deployment-order model are expressly validation-only appendices, not student installation entry points.
- `/etc/nova/compute_id` was created directly with exclusive/no-follow flags, nova:nova 0644, canonical nonzero UUID, file/directory fsync and inode-bound cleanup. The remediated implementation validates an existing path with one `O_RDONLY|O_NOFOLLOW` descriptor, fstat/read/fstat on that same descriptor and an invariant descriptor identity. Creation uses `O_EXCL|O_NOFOLLOW`, fchown/fchmod, complete write, fsync and same-FD content/metadata validation; failure cleanup unlinks only the inode created by that invocation. A strict-host-key read-only remote recheck proved file metadata and file/Nova DB/Placement provider UUID consistency without printing or tracking the UUID.
- libvirtd was enabled/started first, `qemu:///system` passed with zero domains, then nova-compute was enabled/started. It remained active; startup-window RabbitMQ/Keystone/Placement/database auth error classifiers were empty. `virt-host-validate qemu` RC 1 was limited to expected missing nested hardware acceleration.

### Integration and final audit

- First host discovery created exactly `compute` to cell1; repeated `nova-manage cell_v2 discover_hosts --by-service` kept one row with zero duplicates.
- Exact services are scheduler/controller, conductor/controller, compute/compute, all up+enabled. One QEMU hypervisor named compute is up+enabled.
- Authenticated Placement 1.39 reports exactly one provider named compute and required VCPU/MEMORY_MB/DISK_GB inventories with positive valid totals/units. No provider or inventory was manually created.
- Final `nova-status upgrade check` returned seven Success results.
- Final controller audit: `SERVICES=4 ENDPOINTS=12 DBS=6 CELLS=2 HOSTS=1 COMPUTE_SERVICES=3 HYPERVISORS=1 PROVIDERS=1 INVENTORIES=3 IMAGES=0 SERVERS=0 FLAVORS=0 LATER=0 TEMP=0`.
- Final compute audit: `TX=3 INSTALLS=398 UPGRADES=5 SERVICES=libvirt,nova-compute VIRT=qemu DOMAINS=0 COMPUTE_ID=stable-redacted LATER=0 SDB=blank50G SDC=blank50G TEMP=0`.
- The structured integration/final classifiers now reject query errors, duplicate or down/disabled service rows, wrong/missing cells or host mappings, duplicate/wrong hypervisors or providers, missing/invalid inventory structures and totals, Nova identity/API binding drift, retained image/server/flavor objects, grant drift, internal compute UUID mismatch, later-state presence, disk drift and temporary files. They are wired into the validation-only order model after discovery and before the final per-node audits.

## Transparent strict stops and recoveries

1. Database/grant creation completed, then the first validator stopped because this MariaDB build lacks `information_schema.ROUTINE_PRIVILEGES`. Identity had not begun. Safe resume accepted only the exact complete three-schema/three-host state, changed the non-credential probe to `mysql.procs_priv`, and passed the full gate.
2. Nova user creation completed, then the first role-add subprocess returned nonzero before service/endpoint creation. The original adapter discarded stderr and numeric RC to avoid accidental credential exposure; this is a retained evidence deficiency. A separate exact-ID diagnostic proved unique user, empty assignment, project and role, and the same exact role add returned RC 0. There was no automatic retry, unsafe flag, duplicate tolerance, or wrong-ID fallback. The production stage then re-queried all bindings.
3. Compute preflight first stopped because openEuler names the qemu-kvm provider RPM `qemu`. A read-only provider query established the mapping; installed count remained zero.
4. The next preflight stopped because libvirt's systemd-container 255-58 dependency conflicted with installed systemd-cryptsetup 255-50 and the local repo lacked 255-58. No unsafe flag or external install was used. Task 5E paused. Task 4C independently closed and reviewed the signed official overlay before Task 5E resumed.
5. Integration discovery passed, then a read-only hypervisor classifier stopped because this client's `hypervisor list --long` omits Status. `hypervisor show` proved status enabled; the classifier now requires State from list and enabled Status from show. Provider queries had not started at the stop; the complete integration path then passed.
6. During remediation, the first two read-only transaction-evidence collection attempts stopped locally while pairing the five compute Upgraded rows. No VM state changed. Evidence showed that prefix matching classified `systemd-cryptsetup`, `systemd-libs` and `systemd-udev` correctly on the old side but allowed the shorter `systemd` prefix to match four new rows. The collector was corrected to classify both old and new NEVRAs by the same longest exact package-name rule; the third read-only run produced the complete 403+5 evidence and the transaction validator passed.

## Artifacts

- `third-edition-work/validation/manual-install/06-nova-controller.md`
- `third-edition-work/validation/manual-install/07-nova-compute.md`
- `third-edition-work/validation/manual-install/config-snapshots/controller-nova.conf`
- `third-edition-work/validation/manual-install/config-snapshots/compute-nova.conf`
- `third-edition-work/validation/manual-install/config-snapshots/compute-identity.metadata`
- `third-edition-work/validation/manual-install/transaction-evidence/nova-controller-transaction.txt`
- `third-edition-work/validation/manual-install/transaction-evidence/nova-compute-transaction.txt`
- `third-edition-work/tests/test_deployment_contract.py`
- `.superpowers/sdd/collect_task5e_transactions.py`
- `.superpowers/sdd/verify_task5e_compute_identity.py`

No real deployment secret, OpenStack token, cell URL, compute UUID, cookie, authentication hash, private key, or credential-bearing URL is tracked.

## Verification

- Initial TDD RED: `1 failed, 150 deselected` because the Nova manual records did not yet exist.
- First documentation GREEN attempt: 12 passed, 5 failed; failures precisely identified history/EXACT markers, identity terminology, Windows pwd import, and provider terminology. These were documentation/test portability defects only; no VM state changed.
- First complete Nova focused GREEN: 17 passed, 150 deselected.
- Expanded meaningful mutation contracts: exact grant mutations, staged identity zero/exact/duplicate/partial states, both atomic config replacement failures, compute_id create/rerun/failure cleanup, and idempotent URL-safe cell state machine.
- Expanded Nova focused GREEN: 23 passed, 150 deselected.
- First-review remediation TDD used seven vertical RED→GREEN slices: complete start evidence, validation-only fixed order, cell state, integration/final classifiers, complete transactions, same-FD compute identity, and explicit manual student commands/real collectors. Each new public seam first failed because the production helper or artifact was missing, then passed after the minimal implementation.
- Remediated Nova focused result before the final documentation audit: `31 passed, 150 deselected`.
- Remediated complete pytest before the final documentation audit: `181 passed in 24.91s`.
- Resume focused Nova test result: `31 passed, 150 deselected` (three upstream Paramiko cryptography deprecation warnings only).
- Resume complete pytest result: `181 passed` (the same three upstream Paramiko cryptography deprecation warnings only).
- Resume Python fenced-block syntax result: all six controller and five compute Python fences compile successfully.  The Windows workspace exposes only an unconfigured WSL `bash.exe`; no local Bash parser is available, so Bash-fence parsing was not claimed or worked around by changing the environment.  This bounded local-tool limitation is for the independent reviewer to note.
- The staged `git diff --check` and exact five-file Task 5E scope audit pass.  The staged scanner found no literal authorized password, private-key block, credential-bearing URL, UUID literal, or token assignment; it is run again immediately before the remediation commit.
- Remote preflight, transactions, schema, services, integration, and final audits: PASS as detailed above.

### Resume record and closure steps

The pause instructions above were completed on 2026-08-12.  The resumed work
used only the strict-host-key read-only acceptance described at the top of this
report; it did not rerun host discovery or any installation/configuration
operation.  The remaining local closure is to run the focused and complete
tests, validate fenced code and tracked-artifact safety, commit precisely the
Task 5E evidence/collectors/report, and obtain independent review.  Neutron
remains out of scope even if that review passes.

## Residual risks

- `gpgcheck=0`, SELinux Permissive, firewalld disabled, clear-text HTTP and one reused lab secret are isolated teaching choices. Production requires signed repository enforcement, TLS, secret separation/rotation, firewall policy, SELinux enforcement and HA design.
- Software QEMU is portable but slow and is not evidence of production KVM readiness.
- Controller and compute are single nodes without HA or failure-domain redundancy.
- The offline repository has a large libvirt dependency closure and five base-component upgrades; the exact reviewed transaction must remain part of environment packaging and reproducibility checks.
- No workload object was created in this slice. Instance/flavor/network/image lifecycle belongs to the later intelligent-agent operations chapter, after Neutron and remaining services pass their own gates.
- The user requires the final textbook presentation for every infrastructure component—not only Nova—to use manual configuration editing, manual schema synchronization, manual user/service/endpoint creation and manual service start. Task 5E applies that rule in 06/07. Keystone, Glance and Placement are not modified during this remediation because they were already reviewed; their eventual formal-manuscript pass must apply the same rule. Automated code may validate order and state but must never be presented as the student installation method.
