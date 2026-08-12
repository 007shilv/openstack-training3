# 13 Swift 计算节点手工部署、磁盘安全门与最终边界

`16-compute-swift.sh` 只作参数和顺序参考，**严禁执行**。Swift 只能使用 compute `192.168.234.150` 的 50 GiB 整盘 `/dev/sdc`；不得对系统盘 `/dev/sda` 或 Cinder PV `/dev/sdb` 执行格式化、分区、LVM 或挂载写入。

## 仅从本地源安装

```bash
set -Eeuo pipefail
dnf repoquery --available --disablerepo='*' --enablerepo=openstack-local \
  openstack-swift openstack-swift-common openstack-swift-account \
  openstack-swift-container openstack-swift-object rsync xfsprogs >/dev/null
dnf -y --disablerepo='*' --enablerepo=openstack-local \
  --setopt=install_weak_deps=False install \
  openstack-swift openstack-swift-common openstack-swift-account \
  openstack-swift-container openstack-swift-object rsync xfsprogs
rpm -V openstack-swift openstack-swift-common openstack-swift-account \
  openstack-swift-container openstack-swift-object rsync xfsprogs
umask 077
stamp=$(date -u +%Y%m%dT%H%M%SZ)
backup=/root/openstack-lab-backups/task-5h-compute-$stamp
install -d -m 700 "$backup"
for file in /etc/swift/swift.conf /etc/swift/account-server.conf \
  /etc/swift/container-server.conf /etc/swift/object-server.conf \
  /etc/rsyncd.conf /etc/fstab; do
  [[ ! -e $file ]] || cp -a "$file" "$backup"/
done
```

不得使用外部软件源、`--allowerasing` 或 `--skip-broken`。安装结束后、任何磁盘写入前，必须立即执行下一节完整安全门。

## `/dev/sdc` 失效即停的空白/已初始化两态分类门

本机 XFS 标签最多 12 个字符；原计划的 20 字符标签在写入前被 XFS 拒绝，因此本实验统一使用精确标签 `swift-data`。下面代码必须作为**同一个 shell 会话**逐条执行；它不使用会吞掉失败状态的否定管道。

```bash
set -Eeuo pipefail

die() { echo "ERROR: $*" >&2; exit 1; }

SWIFT_DEVICE=/dev/sdc
SWIFT_MOUNT=/srv/node/sdc
SWIFT_LABEL=swift-data

[[ $(hostnamectl --static) == compute ]] || die 'host is not compute'
ip -4 -o addr show ens33 | grep -Fq '192.168.234.150/24' || \
  die 'ens33 is not 192.168.234.150/24'
[[ $SWIFT_DEVICE == /dev/sdc ]] || die 'Swift target must be exactly /dev/sdc'
[[ $SWIFT_DEVICE != /dev/sda && $SWIFT_DEVICE != /dev/sdb ]] || \
  die 'refusing system or Cinder disk'
[[ -b $SWIFT_DEVICE ]] || die 'missing /dev/sdc block device'
canonical_target=$(readlink -f "$SWIFT_DEVICE") || die 'cannot canonicalize /dev/sdc'
[[ $canonical_target == /dev/sdc ]] || die 'unexpected /dev/sdc canonical path'
device_type=$(lsblk -dnro TYPE "$SWIFT_DEVICE") || die 'cannot read /dev/sdc type'
[[ $device_type == disk ]] || die '/dev/sdc is not a whole disk'
size_bytes=$(blockdev --getsize64 "$SWIFT_DEVICE") || die 'cannot read /dev/sdc size'
[[ $size_bytes == 53687091200 ]] || die '/dev/sdc is not exactly 50 GiB'

root_source=$(findmnt -nro SOURCE /) || die 'cannot determine root source'
[[ -n $root_source ]] || die 'root source is empty'
canonical_root=$(readlink -f "$root_source") || die 'cannot canonicalize root source'
[[ -n $canonical_root ]] || die 'canonical root source is empty'
root_chain=$(lsblk -s -nrpo NAME "$canonical_root") || die 'cannot resolve root ancestry'
[[ -n $root_chain ]] || die 'root ancestry is empty'
while IFS= read -r node; do
  [[ -n $node ]] || die 'empty node in root ancestry'
  canonical_node=$(readlink -f "$node") || die "cannot canonicalize root ancestor $node"
  [[ $canonical_node != "$canonical_target" ]] || die '/dev/sdc is a root ancestor'
done <<< "$root_chain"

device_tree=$(lsblk -nrpo NAME,TYPE,MOUNTPOINT "$SWIFT_DEVICE") || \
  die 'cannot inspect /dev/sdc tree'
[[ -n $device_tree ]] || die '/dev/sdc tree is empty'
[[ $(awk 'NF {count++} END {print count+0}' <<< "$device_tree") -eq 1 ]] || \
  die '/dev/sdc has children or partitions'
[[ -z $(awk '$2 == "part" {print}' <<< "$device_tree") ]] || \
  die '/dev/sdc contains a partition'
mount_rows=$(awk 'NF >= 3 {print $1 "|" $3}' <<< "$device_tree")

command -v pvs >/dev/null 2>&1 || die 'pvs is unavailable'
pv_rows=$(pvs --noheadings --readonly --separator '|' -o pv_name,vg_name 2>/dev/null) || \
  die 'cannot inspect LVM PV ownership'
sdb_rows=0
sdc_rows=0
while IFS='|' read -r pv_name vg_name; do
  pv_name=${pv_name//[[:space:]]/}
  vg_name=${vg_name//[[:space:]]/}
  [[ -n $pv_name ]] || continue
  case "$pv_name" in
    /dev/sdb)
      ((sdb_rows+=1))
      [[ $vg_name == cinder-volumes ]] || die '/dev/sdb is not owned by cinder-volumes'
      ;;
    /dev/sdc)
      ((sdc_rows+=1))
      ;;
  esac
done <<< "$pv_rows"
[[ $sdb_rows -eq 1 ]] || die '/dev/sdb must be the unique cinder-volumes PV row'
[[ $sdc_rows -eq 0 ]] || die '/dev/sdc must never be an LVM PV'

signature_rows=$(wipefs --no-act --noheadings --output TYPE "$SWIFT_DEVICE") || \
  die 'wipefs signature probe failed'
signature_types=$(sed '/^[[:space:]]*$/d; s/[[:space:]]//g' <<< "$signature_rows") || \
  die 'cannot normalize signature probe output'
blkid_info=
if blkid_info=$(blkid -p -o export "$SWIFT_DEVICE" 2>/dev/null); then
  blkid_rc=0
else
  blkid_rc=$?
fi
[[ $blkid_rc -eq 0 || $blkid_rc -eq 2 ]] || die 'blkid probe failed'
fstype=$(sed -n 's/^TYPE=//p' <<< "$blkid_info")
label=$(sed -n 's/^LABEL=//p' <<< "$blkid_info")

if [[ -z $mount_rows && -z $signature_types && $blkid_rc -eq 2 && \
      -z $fstype && -z $label ]]; then
  SWIFT_DISK_STATE=blank
elif [[ $signature_types == xfs && $blkid_rc -eq 0 && \
        $fstype == xfs && $label == "$SWIFT_LABEL" ]]; then
  uuid=$(sed -n 's/^UUID=//p' <<< "$blkid_info")
  [[ -n $uuid ]] || die 'initialized /dev/sdc has no UUID'
  active_mount_entries=$(awk -v mount="$SWIFT_MOUNT" \
    '$1 !~ /^#/ && $2 == mount {count++} END {print count+0}' /etc/fstab) || \
    die 'cannot inspect fstab mount entries'
  exact_fstab_entries=$(awk -v source="UUID=$uuid" -v mount="$SWIFT_MOUNT" \
    '$1 == source && $2 == mount && $3 == "xfs" && \
     $4 == "defaults,noatime,nodiratime" && $5 == "0" && $6 == "0" \
     {count++} END {print count+0}' /etc/fstab) || die 'cannot validate fstab'
  [[ $active_mount_entries -eq 1 && $exact_fstab_entries -eq 1 ]] || \
    die 'initialized /dev/sdc lacks the exact unique UUID fstab entry'
  mounted_source=$(findmnt -nro SOURCE --target "$SWIFT_MOUNT") || \
    die 'initialized Swift mount is absent'
  mounted_target=$(findmnt -nro TARGET --target "$SWIFT_MOUNT") || \
    die 'cannot resolve Swift mount target'
  canonical_mounted_source=$(readlink -f "$mounted_source") || \
    die 'cannot canonicalize Swift mount source'
  [[ $canonical_mounted_source == "$canonical_target" && \
     $mounted_target == "$SWIFT_MOUNT" && \
     $mount_rows == "$SWIFT_DEVICE|$SWIFT_MOUNT" ]] || \
    die 'initialized Swift mount source or target mismatch'
  SWIFT_DISK_STATE=initialized
else
  die 'refusing third Swift disk state'
fi

if [[ $SWIFT_DISK_STATE == blank ]]; then
  read -r -p '确认 compute /dev/sdc 是空白 50 GiB 教学整盘；输入 YES 初始化：' confirmation
  [[ $confirmation == YES ]] || die 'no explicit /dev/sdc initialization confirmation'
  mkfs.xfs -f -L "$SWIFT_LABEL" "$SWIFT_DEVICE"
  [[ $(blkid -o value -s TYPE "$SWIFT_DEVICE") == xfs ]] || die 'XFS verification failed'
  [[ $(blkid -o value -s LABEL "$SWIFT_DEVICE") == "$SWIFT_LABEL" ]] || \
    die 'XFS label verification failed'
  uuid=$(blkid -o value -s UUID "$SWIFT_DEVICE") || die 'cannot read Swift UUID'
  [[ -n $uuid ]] || die 'Swift UUID is empty'
  install -d -m 0755 "$SWIFT_MOUNT"
  vi /etc/fstab
  # 在 vi 中只增加：UUID=<上一步运行时UUID> /srv/node/sdc xfs defaults,noatime,nodiratime 0 0
  exact_fstab_entries=$(awk -v source="UUID=$uuid" -v mount="$SWIFT_MOUNT" \
    '$1 == source && $2 == mount && $3 == "xfs" && \
     $4 == "defaults,noatime,nodiratime" && $5 == "0" && $6 == "0" \
     {count++} END {print count+0}' /etc/fstab) || die 'cannot validate new fstab entry'
  [[ $exact_fstab_entries -eq 1 ]] || die 'exact UUID fstab entry is missing or duplicated'
  mount "$SWIFT_MOUNT"
elif [[ $SWIFT_DISK_STATE == initialized ]]; then
  echo 'verified exact initialized Swift state; skipping mkfs.xfs'
else
  die 'unexpected classifier result'
fi

mounted_source=$(findmnt -nro SOURCE --target "$SWIFT_MOUNT") || die 'Swift mount missing'
canonical_mounted_source=$(readlink -f "$mounted_source") || die 'cannot canonicalize mount source'
[[ $canonical_mounted_source == "$canonical_target" ]] || die 'Swift mount is backed by another device'
[[ $(findmnt -nro TARGET --target "$SWIFT_MOUNT") == "$SWIFT_MOUNT" ]] || \
  die 'Swift mount target mismatch'
chown -R swift:swift /srv/node /var/cache/swift
```

该分类器只接受两种状态：完全空白，或已按精确 UUID fstab 条目挂载的 XFS `swift-data`。探针失败、孤立/外来 PV、其他签名、错误标签、未挂载或错误来源全部退出。只有空白分支在读取精确 `YES` 后运行 `mkfs.xfs`；已初始化分支明确跳过格式化。

## 核对 Swift 配置与 rings

第 12 节复制后，`vi /etc/swift/swift.conf` 核对下列完整结构；两个运行时随机值必须与 controller 完全相同：

```ini
[swift-hash]
swift_hash_path_prefix = <与CONTROLLER相同的运行时值>
swift_hash_path_suffix = <与CONTROLLER相同的运行时值>

[storage-policy:0]
name = Policy-0
default = yes
```

```bash
cd /etc/swift
sha256sum account.ring.gz container.ring.gz object.ring.gz
ls -l swift.conf account.ring.gz container.ring.gz object.ring.gz
```

三份 ring 摘要必须与 controller 对应行相同；`swift.conf` 已在 controller 侧用 `cmp` 做字节相等验证，不得计算含真实 salt 配置的摘要。每份 ring 只能包含 `.150/sdc` 的单副本成员，不得在 compute 重新生成另一套 ring。

## 手工编辑 rsync 与三个存储服务配置

执行 `vi /etc/rsyncd.conf`：

```ini
uid = swift
gid = swift
log file = /var/log/rsyncd.log
pid file = /run/rsyncd.pid
address = 192.168.234.150

[account]
max connections = 2
path = /srv/node/
read only = false
lock file = /var/lock/account.lock

[container]
max connections = 2
path = /srv/node/
read only = false
lock file = /var/lock/container.lock

[object]
max connections = 2
path = /srv/node/
read only = false
lock file = /var/lock/object.lock
```

执行 `vi /etc/swift/account-server.conf`：

```ini
[DEFAULT]
bind_ip = 192.168.234.150
bind_port = 6202
user = swift
swift_dir = /etc/swift
devices = /srv/node
mount_check = true

[pipeline:main]
pipeline = healthcheck recon account-server

[app:account-server]
use = egg:swift#account

[filter:healthcheck]
use = egg:swift#healthcheck

[filter:recon]
use = egg:swift#recon
recon_cache_path = /var/cache/swift

[account-replicator]
[account-auditor]
[account-reaper]
```

执行 `vi /etc/swift/container-server.conf`：

```ini
[DEFAULT]
bind_ip = 192.168.234.150
bind_port = 6201
user = swift
swift_dir = /etc/swift
devices = /srv/node
mount_check = true

[pipeline:main]
pipeline = healthcheck recon container-server

[app:container-server]
use = egg:swift#container

[filter:healthcheck]
use = egg:swift#healthcheck

[filter:recon]
use = egg:swift#recon
recon_cache_path = /var/cache/swift

[container-replicator]
[container-updater]
[container-auditor]
```

执行 `vi /etc/swift/object-server.conf`：

```ini
[DEFAULT]
bind_ip = 192.168.234.150
bind_port = 6200
user = swift
swift_dir = /etc/swift
devices = /srv/node
mount_check = true

[pipeline:main]
pipeline = healthcheck recon object-server

[app:object-server]
use = egg:swift#object

[filter:healthcheck]
use = egg:swift#healthcheck

[filter:recon]
use = egg:swift#recon
recon_cache_path = /var/cache/swift

[object-replicator]
[object-updater]
[object-auditor]
```

```bash
chown -R swift:swift /etc/swift /srv/node /var/cache/swift
chmod 0640 /etc/swift/*.conf
```

## 逐项启用、启动和核验

```bash
systemctl enable rsyncd
systemctl start rsyncd
systemctl enable openstack-swift-account
systemctl start openstack-swift-account
systemctl enable openstack-swift-container
systemctl start openstack-swift-container
systemctl enable openstack-swift-object
systemctl start openstack-swift-object
for service in rsyncd openstack-swift-account openstack-swift-container openstack-swift-object; do
  systemctl is-active --quiet "$service"
  systemctl is-enabled --quiet "$service"
done
for port in 873 6200 6201 6202; do
  ss -ltn | grep -Eq "(^|[[:space:]])[^[:space:]]*:${port}[[:space:]]"
done
```

## 最终 Cinder/Swift 边界

在 compute 执行以下只读终验，确保 Cinder 状态未变且 Swift 仍精确使用 `/dev/sdc`：

```bash
set -Eeuo pipefail
[[ $(blkid -o value -s TYPE /dev/sdc) == xfs ]]
[[ $(blkid -o value -s LABEL /dev/sdc) == swift-data ]]
[[ $(readlink -f "$(findmnt -nro SOURCE --target /srv/node/sdc)") == /dev/sdc ]]
[[ $(findmnt -nro TARGET --target /srv/node/sdc) == /srv/node/sdc ]]
pv_rows=$(pvs --noheadings --readonly --separator '|' -o pv_name,vg_name)
sdb_rows=$(awk -F '|' '{gsub(/[[:space:]]/, "", $1); gsub(/[[:space:]]/, "", $2); if ($1 == "/dev/sdb" && $2 == "cinder-volumes") count++} END {print count+0}' <<< "$pv_rows")
sdc_rows=$(awk -F '|' '{gsub(/[[:space:]]/, "", $1); if ($1 == "/dev/sdc") count++} END {print count+0}' <<< "$pv_rows")
[[ $sdb_rows -eq 1 && $sdc_rows -eq 0 ]]
for service in targetclid openstack-cinder-volume rsyncd \
  openstack-swift-account openstack-swift-container openstack-swift-object; do
  systemctl is-active --quiet "$service"
  systemctl is-enabled --quiet "$service"
done
```

在 controller 执行：

```bash
set -Eeuo pipefail
for service in openstack-cinder-api openstack-cinder-scheduler openstack-swift-proxy; do
  systemctl is-active --quiet "$service"
  systemctl is-enabled --quiet "$service"
done
source /root/admin-openrc
openstack volume service list
openstack endpoint list --service swift --region RegionOne --long
curl --noproxy '*' -fsS http://controller:8080/healthcheck
```

对象生命周期验收使用第 12 节的唯一容器和小对象命令；完成后必须没有任务容器或对象残留。不得创建或恢复快照，不得重配 Cinder。

## Focused Swift contract（只用于验收，不是安装入口）

```python
def validate_swift_lightweight_evidence(evidence: dict[str, object]) -> None:
    expected = {
        "controller": {"openstack-swift-proxy"},
        "compute": {"rsyncd", "openstack-swift-account", "openstack-swift-container", "openstack-swift-object"},
    }
    if evidence.get("services") != expected:
        raise ValueError("Swift service evidence mismatch")
    if evidence.get("rings") != {"replicas": 1, "ip": "192.168.234.150", "device": "sdc"}:
        raise ValueError("Swift ring evidence mismatch")
    if evidence.get("disk") != {"device": "/dev/sdc", "filesystem": "xfs", "label": "swift-data", "mounted": True, "cinder_untouched": True}:
        raise ValueError("Swift disk evidence mismatch")
    if evidence.get("lifecycle") != {"api": True, "authenticated_cli": True, "one_object": True, "digest_matches": True, "deleted_exactly": True, "no_residue": True}:
        raise ValueError("Swift lifecycle evidence mismatch")
```
