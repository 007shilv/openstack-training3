# 11 Cinder 计算节点手工部署与轻量验收

在第 10 节完成后执行。`14-compute-cinder.sh` 只作参数/顺序参考，**严禁执行**；验证函数不参与安装。禁止附加卷、快照、Swift 和 Horizon。

## 再次只读门禁与明确确认

任何写入前，必须确认 compute `.150`，仅以 `/dev/sdb` 为目标；它必须是 50 GiB 整盘、不是根盘祖先、无挂载/分区/签名/PV。`/dev/sda` 是系统盘，`/dev/sdc` 留给 Swift，绝不触碰。若已有 PV，只接受 `/dev/sdb` **精确**属于唯一 `cinder-volumes` 的幂等状态；孤立或外来 PV 均停止。

```bash
set -Eeuo pipefail
[[ $(hostnamectl --static) == compute ]]
ip -4 -o addr show ens33 | grep -Fq '192.168.234.150/24'
target=/dev/sdb
[[ $target == /dev/sdb && -b $target && $(readlink -f "$target") == /dev/sdb ]]
[[ $(lsblk -dnro TYPE "$target") == disk && $(blockdev --getsize64 "$target") == 53687091200 ]]
root=$(readlink -f "$(findmnt -nro SOURCE /)")
! lsblk -s -nrpo NAME "$root" | while read -r node; do [[ $(readlink -f "$node") == /dev/sdb ]] && exit 1; done
[[ $(lsblk -nrpo NAME "$target" | sed '/^$/d' | wc -l) -eq 1 ]]
[[ -z $(lsblk -nrpo NAME,MOUNTPOINT "$target" | awk 'NF > 1 && $2 != "" {print}') ]]
[[ -z $(lsblk -nrpo TYPE "$target" | awk '$1 == "part" {print}') ]]
[[ -z $(wipefs --no-act --noheadings --output TYPE "$target") ]]
blkid -p "$target" >/dev/null 2>&1 && exit 1 || [[ $? -eq 2 ]]
pvs --noheadings --readonly -o pv_name,vg_name
```

上述只读命令出现两种且仅两种可继续状态：首次教学初始化时，`/dev/sdb` 没有任何签名或 PV；已经初始化时，`pvs` 必须只显示 `/dev/sdb cinder-volumes`，且不得有孤立 PV、其他 VG 或分区。后者是幂等续作状态，**不得**再次运行 `pvcreate` 或 `vgcreate`，也不得先执行 `wipefs`。任何第三种状态（包括外来签名、挂载、PV 无 VG、VG 名错误，或 `/dev/sda`/`/dev/sdc`）都停止处理。

首次初始化前，学生必须明确确认：“我确认 compute 的 `/dev/sdb` 是 50 GiB 空白教学盘，根盘祖先为 `/dev/sda2,/dev/sda`，允许初始化为 `cinder-volumes`。”只有确认且上述检查通过后，才可执行下面两条 LVM 命令。

## 本地源、备份、LVM 与服务

```bash
set -Eeuo pipefail
dnf repoquery --available --disablerepo='*' --enablerepo='openstack-local' lvm2 targetcli openstack-cinder-volume >/dev/null
dnf -y --disablerepo='*' --enablerepo='openstack-local' --setopt=install_weak_deps=False install lvm2 targetcli openstack-cinder-volume
dnf history info "$(dnf history | awk 'NR==3 {print $1}')"
rpm -V lvm2 targetcli openstack-cinder-volume
umask 077; backup=/root/openstack-lab-backups/task-5g-<UTC>; install -d -m 700 "$backup"
cp -a /etc/cinder/cinder.conf "$backup"/
# 仅首次初始化：
pvcreate /dev/sdb
vgcreate cinder-volumes /dev/sdb
```

DNF 不得使用外部源、`--allowerasing` 或 `--skip-broken`；事务中的移除/替换/降级均停止。

手工 `vi /etc/cinder/cinder.conf`：

```ini
[DEFAULT]
transport_url = rabbit://openstack:<URL_ENCODED_PASSWORD>@controller
auth_strategy = keystone
my_ip = 192.168.234.150
glance_api_servers = http://controller:9292
enabled_backends = lvm
default_volume_type = lvm
[database]
connection = mysql+pymysql://cinder:<URL_ENCODED_PASSWORD>@controller/cinder
[keystone_authtoken]
www_authenticate_uri = http://controller:5000
auth_url = http://controller:5000
memcached_servers = controller:11211
auth_type = password
project_domain_name = Default
user_domain_name = Default
project_name = service
username = cinder
password = <SERVICE_PASSWORD>
[oslo_concurrency]
lock_path = /var/lib/cinder/tmp
[lvm]
volume_driver = cinder.volume.drivers.lvm.LVMVolumeDriver
volume_group = cinder-volumes
target_protocol = iscsi
target_helper = lioadm
target_ip_address = 192.168.234.150
volume_backend_name = LVM-ISCSI
```

```bash
systemctl enable --now targetclid
systemctl enable --now openstack-cinder-volume
for s in targetclid openstack-cinder-volume; do systemctl is-active --quiet "$s" && systemctl is-enabled --quiet "$s"; done
```

## 轻量验收：唯一 1 GiB 卷

只在 controller 验证服务、API/认证 CLI、后端、一个任务卷生命周期。删除使用创建返回的精确 ID；不得附加。

```bash
set -Eeuo pipefail
source /root/admin-openrc
token=$(openstack token issue -f value -c id)
curl --noproxy '*' -fsS -H "X-Auth-Token: $token" http://controller:8776/ >/dev/null
unset token
openstack volume service list
openstack volume backend pool list
openstack volume type show lvm
name="task5g-volume-$(date -u +%Y%m%d%H%M%S)"
volume_id=$(openstack volume create --size 1 --type lvm "$name" -f value -c id)
[[ -n $volume_id ]]
until [[ $(openstack volume show "$volume_id" -f value -c status) == available ]]; do sleep 5; done
openstack volume delete "$volume_id"
for attempt in $(seq 1 36); do
  if ! openstack volume show "$volume_id" >/dev/null 2>&1; then break; fi
  sleep 5
done
if openstack volume show "$volume_id" >/dev/null 2>&1; then echo 'task-owned volume remains' >&2; exit 1; fi
openstack volume list --name "$name"
```

最后确认 `/dev/sdb` 只属于 `cinder-volumes`，`/dev/sdc` 仍是无签名 50 GiB 整盘。LVM 驱动可保留其后端 thin-pool；它不是任务卷。除了这一后端池以外，`lvs cinder-volumes` 不得显示任务卷逻辑卷。不要按名称模糊删除任何 LVM 对象。

## Focused Cinder contract（仅验收，不安装）

```python
from __future__ import annotations

def validate_cinder_lightweight_evidence(evidence: dict[str, object]) -> None:
    expected = {"controller": {"openstack-cinder-api", "openstack-cinder-scheduler"}, "compute": {"targetclid", "openstack-cinder-volume"}}
    services = evidence.get("services")
    if not isinstance(services, dict) or set(services) != set(expected) or any(set(services[node]) != value for node, value in expected.items()):
        raise ValueError("Cinder service active/enabled evidence mismatch")
    if evidence.get("api_cli") != {"api_reachable": True, "authenticated_cli": True}:
        raise ValueError("Cinder API/CLI evidence mismatch")
    if evidence.get("backend") != {"name": "compute@lvm#LVM-ISCSI", "up": True, "volume_type": "lvm"}:
        raise ValueError("Cinder backend mismatch")
    if evidence.get("volume_lifecycle") != {"size_gib": 1, "created": True, "available": True, "deleted_exact_id": True, "absent_after_delete": True}:
        raise ValueError("Cinder test-volume lifecycle mismatch")
    if evidence.get("disk") != {"device": "/dev/sdb", "vg": "cinder-volumes", "initialized": True, "sda_touched": False, "sdc_touched": False}:
        raise ValueError("Cinder disk guard mismatch")
    if evidence.get("boundaries") != {"attachments": [], "snapshots": [], "swift": False, "horizon": False}:
        raise ValueError("Cinder scope boundary mismatch")
```
