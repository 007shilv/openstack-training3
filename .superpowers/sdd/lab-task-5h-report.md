# Lab Task 5H report: manual Swift deployment

Baseline/current Cinder PASS commit: `6de09a2466bec1e33515296c0be745a93f8d6d51`.

## Gates and remote changes

- Read-only two-node gate passed: controller `.151` and compute `.150` were exact; Cinder API/scheduler and targetclid/volume were active and enabled; `/dev/sdb` remained the sole `cinder-volumes` PV. Swift and Horizon were absent before this task.
- Controller installed Swift proxy packages only from `openstack-local`, backed up existing Swift configuration under restricted `/root/openstack-lab-backups/task-5h-controller-<UTC>`, created/verified the Default-domain `swift` service user, global service-project admin assignment, enabled `swift`/`object-store`, and the three exact RegionOne endpoints.
- Controller configured runtime-only hash salts and service password, created/rebalanced one-replica account/container/object rings for `.150/sdc`, and enabled the proxy.
- Compute was rechecked before mutation, installed storage packages only from `openstack-local`, and backed up its prior configuration under restricted `/root/openstack-lab-backups/task-5h-compute-<UTC>`.
- The first requested `mkfs.xfs -L openstack-swift-data` was rejected before any write because the installed XFS accepts at most 12 label characters. With explicit authorization, the exact initialized label is `swift-data`. The verified blank `/dev/sdc` alone was formatted, UUID-mounted at `/srv/node/sdc`, and entered in fstab; `/dev/sda` and `/dev/sdb` were not written.
- Swift configuration and binary rings were copied directly in memory over Paramiko with reviewed known_hosts and RejectPolicy, then byte-equality-checked; no binary rings, UUIDs, salts, passwords, tokens, or digest are tracked.

## Lightweight acceptance

- Proxy, rsync, account, container and object services are active and enabled; storage ports 6200/6201/6202 are listening and Swift proxy is operational on 8080.
- Authenticated Keystone-token API `/info` and authenticated OpenStack container/object CLI passed.
- One uniquely named task container and one small task object were uploaded and downloaded; content digests matched without outputting the digest. The exact object and exact container were deleted and absence was confirmed.
- Final check retained `/dev/sdb` as `cinder-volumes` and `/dev/sdc` as mounted XFS `swift-data` with no LVM PV.

## Scope and residual risk

The two reference scripts were never run; manual commands and `vi` records are the teaching path. No snapshots, Horizon, Cinder reconfiguration, `/dev/sda`/`/dev/sdb` writes, or persistent test objects occurred. One-replica rings are an intentional teaching simplification with no redundancy or fault tolerance; they are not production-safe. Bash parsing was unavailable locally and no parser was installed; remote live acceptance plus Python contract/static scope checks are recorded instead.

## Post-review local-only remediation

Independent review correctly found that the first records summarized disk safety and configuration but did not give students a complete executable fail-closed path. The remediation was local-only: no VM connection, deployment rerun, disk operation, service restart, or object lifecycle was performed.

- `13-swift-compute.md` now places one explicit two-state guard before the only real `mkfs.xfs` command. It checks compute identity and `.150`, exact `/dev/sdc`, whole-disk type and 50 GiB size, reliable root-source/ancestry return codes and non-empty values, canonicalizes every ancestor, rejects children/partitions, inspects mounts, fails closed on `pvs`/`wipefs`/`blkid`, proves `/dev/sdb` remains the unique `cinder-volumes` PV and `/dev/sdc` has no PV, and accepts only blank or exact mounted XFS `swift-data`. Blank requires an interactive exact `YES`; initialized requires a unique exact UUID fstab row and precise `/srv/node/sdc` source/target and skips formatting. Every third state exits.
- Both records now contain local-only DNF commands, create/show/list identity verification, full `swift.conf`, proxy, rsync and account/container/object configuration, ring create/add/rebalance/search checks, reviewed-fingerprint `scp` steps, ring byte-equality hashes, salt-bearing `swift.conf` byte comparison without hashing, UUID fstab/mount/ownership steps, individual enable/start/active/enabled/port checks, authenticated API/CLI and exact one-object cleanup, plus executable final Cinder/Swift boundary gates.
- The reference-only `16-compute-swift.sh` and the consolidated installation guide now use `swift-data`; `safe-scripts.sha256` was updated to the exact new script hash. The script remains prohibited as a student installation entry point.
- Sanitized snapshots were expanded for the full proxy, rsync, Swift storage services, compute Swift config and UUID fstab placeholder. No UUID, secret, salt, token, binary ring or object digest was introduced.
- Focused Swift/manual-document and full deployment contracts, the exact safe-script hash contract, Python syntax, diff/security/task-scope scans were rerun after these local-only changes. The post-review run found the existing Git Bash at its explicit installation path and used `bash -n` on all 17 manual Swift shell blocks plus the touched reference script; no additional parser was installed. This supersedes the earlier local-parser availability note for the remediation run.
