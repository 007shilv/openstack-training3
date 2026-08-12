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
