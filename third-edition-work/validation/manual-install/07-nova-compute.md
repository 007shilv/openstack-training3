# 07 Nova 计算节点手工部署记录

本节只在《06 Nova 控制节点手工部署记录》的全部门禁通过后执行。实际环境为 openEuler 24.03 LTS SP3，实验 OpenStack 软件为 Antelope 27.3.0。没有运行 `10-compute-nova.sh`，没有创建或恢复快照，也没有进入 Neutron 或后续组件。

严格顺序为：计算节点本地源软件包 → 计算节点原子配置 → 稳定 compute_id → libvirt 先于 nova-compute → 主机发现 → 最终双节点审计。任何中止都保持已经验证的前序状态，不允许用依赖跳过参数继续。

## 计算节点本地源软件包

计算节点写前门再次通过后，使用 `qemu libvirt openstack-nova-compute` 作为根请求。openEuler 的实体 RPM 名为 `qemu`，它提供 `qemu-kvm` capability；不存在名为 `qemu-kvm` 的独立 RPM。第一次计划曾因缺少同版本 `systemd-cryptsetup` 严格停止；经独立复审的离线仓库闭包加入官方签名的 255-58 RPM 后，重新计划得到精确 403 行：398 Install、5 Upgrade，403/403 均来自 `openstack-local`，Removing/Erasing/Obsoleting/Replacing/Downgrading 均为 0。

```bash
set -Eeuo pipefail
work=$(mktemp -d /root/.task5e-package.XXXXXX)
EXACT_COMPUTE_TRANSACTION_NEVRAS=(
  libvirt-9.10.0-27.oe2403sp3.x86_64
  openstack-nova-compute-27.3.0-1.oe2403sp2.noarch
  qemu-11:8.2.0-73.oe2403sp3.x86_64
)
trap 'rm -f -- "$work"/*; rmdir -- "$work" 2>/dev/null || :' EXIT
rpm -qa --qf '%{NAME}|%{EPOCHNUM}:%{VERSION}-%{RELEASE}.%{ARCH}\n' | sort -u >"$work/before"
set +e
LC_ALL=C dnf --color=never --assumeno --setopt=install_weak_deps=False --disablerepo='*' --enablerepo='openstack-local' install qemu libvirt openstack-nova-compute >"$work/plan" 2>&1
rc=$?
set -e
[[ $rc -eq 1 ]] && grep -Fq 'Operation aborted' "$work/plan"
! grep -Eiq '(^|[[:space:]])(Removing|Erasing|Obsoleting|Replacing|Downgrading)([[:space:]:]|$)' "$work/plan"
[[ $(sed -nE 's/^[[:space:]]*Install[[:space:]]+([0-9]+)[[:space:]]+Packages?.*/\1/p' "$work/plan" | tail -n1) == 398 ]]
[[ $(sed -nE 's/^[[:space:]]*Upgrade[[:space:]]+([0-9]+)[[:space:]]+Packages?.*/\1/p' "$work/plan" | tail -n1) == 5 ]]
[[ $(grep -Ec '[[:space:]]openstack-local[[:space:]]' "$work/plan") -eq 403 ]]
LC_ALL=C dnf -y --setopt=install_weak_deps=False --disablerepo='*' --enablerepo='openstack-local' install qemu libvirt openstack-nova-compute
history=$(LC_ALL=C dnf history info 3)
grep -Fq 'Return-Code    : Success' <<<"$history"
[[ $(grep -Ec '^[[:space:]]+Install .*@openstack-local$' <<<"$history") -eq 398 ]]
[[ $(grep -Ec '^[[:space:]]+Upgrade .*@openstack-local$' <<<"$history") -eq 5 ]]
! grep -Eiq '^[[:space:]]+(Erase|Removed|Obsolet|Replac|Downgrad)' <<<"$history"
rpm -qa --qf '%{NAME}|%{EPOCHNUM}:%{VERSION}-%{RELEASE}.%{ARCH}\n' | sort -u >"$work/after"
comm -13 "$work/before" "$work/after" >"$work/added"
comm -23 "$work/before" "$work/after" >"$work/old-upgraded"
[[ $(wc -l <"$work/added") -eq 403 && $(wc -l <"$work/old-upgraded") -eq 5 ]]
rm -f -- "$work"/*; rmdir -- "$work"; trap - EXIT
```

`EXACT_COMPUTE_TRANSACTION_NEVRAS` 的三个根是 `libvirt-9.10.0-27.oe2403sp3.x86_64`、`openstack-nova-compute-27.3.0-1.oe2403sp2.noarch`、`qemu-11:8.2.0-73.oe2403sp3.x86_64`。五个新升级 NEVRA 精确为：

- `gnutls-3.8.2-14.oe2403sp3.x86_64`；
- `systemd-255-58.oe2403sp3.x86_64`；
- `systemd-cryptsetup-255-58.oe2403sp3.x86_64`；
- `systemd-libs-255-58.oe2403sp3.x86_64`；
- `systemd-udev-255-58.oe2403sp3.x86_64`。

依赖闭包的 403 行审核计划保存在 `third-edition-work/validation/repository/systemd-dependency-transaction-compute.txt`；真实事务凭据另存为 `transaction-evidence/nova-compute-transaction.txt`。后者完整保存 398 条 Install、5 条 Upgrade 新 NEVRA、5 条 Upgraded 旧 NEVRA及其一一替换关系，并逐条保存 403 条当前 RPM 和 403 条 `openstack-local` repo metadata，不能只依赖安装前 assumeno 计划。升级只替换上述五个同名旧 NEVRA，不是包删除或依赖替换。真实事务号为 3；boot ID 未变化，sshd、chronyd 均 active/enabled，失败单元集合前后相同，安装脚本没有提前启动 libvirt 或 nova-compute，`/dev/sdb`、`/dev/sdc` 仍为空白盘。

禁止使用 `--allowerasing`、`--nodeps`、`--skip-broken` 或外部仓库。教学环境的离线仓库仍为 `gpgcheck=0`，完整性依赖不可变原始 ZIP、官方签名 overlay、SHA-256 manifest 与复审后的仓库门禁；生产环境应启用仓库签名校验和独立供应链策略。

## 计算节点原子配置

`rpm -V openstack-nova-common` 通过后，将 202457 字节软件包默认配置备份到 `/root/openstack-lab-backups/task-5e-20260811T122341Z/nova.conf.package-default`。计算节点不配置 Nova 数据库连接；消息队列、Keystone/service-user、VNC、Glance 和 Placement 与 controller 对齐。`[neutron]`、`[cinder]` 是 future inactive dependencies，只有各自后续切片通过后才进入业务路径。

课堂安装必须先备份，再手工使用 `vi` 编辑；不要运行后面的测试写入器代替本步骤。把 `<SERVICE_PASSWORD>` 换成服务口令，把 `<URL_ENCODED_PASSWORD>` 换成 URL 编码后的消息队列口令，逐节核对后保存。

```bash
cp -a /etc/nova/nova.conf /etc/nova/nova.conf.package-default
vi /etc/nova/nova.conf
```

```ini
[DEFAULT]
state_path = /var/lib/nova
transport_url = rabbit://openstack:<URL_ENCODED_PASSWORD>@controller
my_ip = 192.168.234.150
compute_driver = libvirt.LibvirtDriver
use_neutron = true
firewall_driver = nova.virt.firewall.NoopFirewallDriver

[api]
auth_strategy = keystone

[keystone_authtoken]
www_authenticate_uri = http://controller:5000/
auth_url = http://controller:5000/
memcached_servers = controller:11211
auth_type = password
project_domain_name = Default
user_domain_name = Default
project_name = service
username = nova
password = <SERVICE_PASSWORD>

[service_user]
send_service_user_token = true
auth_url = http://controller:5000/v3
auth_strategy = keystone
auth_type = password
project_domain_name = Default
project_name = service
user_domain_name = Default
username = nova
password = <SERVICE_PASSWORD>

[vnc]
enabled = true
server_listen = 0.0.0.0
server_proxyclient_address = $my_ip
novncproxy_base_url = http://controller:6080/vnc_auto.html

[glance]
api_servers = http://controller:9292

[oslo_concurrency]
lock_path = /var/lib/nova/tmp

[placement]
region_name = RegionOne
project_domain_name = Default
project_name = service
auth_type = password
user_domain_name = Default
auth_url = http://controller:5000/v3
username = placement
password = <SERVICE_PASSWORD>

[libvirt]
virt_type = qemu

[neutron]
auth_url = http://controller:5000
auth_type = password
project_domain_name = Default
user_domain_name = Default
region_name = RegionOne
project_name = service
username = neutron
password = <SERVICE_PASSWORD>

[cinder]
os_region_name = RegionOne
```

```bash
chown root:nova /etc/nova/nova.conf
chmod 0640 /etc/nova/nova.conf
```

下面的原子写入器只用于教材 focused tests 验证参数、失败清理和脱敏快照，不是学生安装命令。

```python
from __future__ import annotations

import configparser
from io import StringIO
import os
from pathlib import Path
import stat
import uuid
from urllib.parse import quote


def build_compute_nova_config(password: str) -> str:
    encoded = quote(password, safe="")
    values = {
        "DEFAULT": {"state_path": "/var/lib/nova", "transport_url": f"rabbit://openstack:{encoded}@controller", "my_ip": "192.168.234.150", "compute_driver": "libvirt.LibvirtDriver", "use_neutron": "true", "firewall_driver": "nova.virt.firewall.NoopFirewallDriver"},
        "api": {"auth_strategy": "keystone"},
        "keystone_authtoken": {"www_authenticate_uri": "http://controller:5000/", "auth_url": "http://controller:5000/", "memcached_servers": "controller:11211", "auth_type": "password", "project_domain_name": "Default", "user_domain_name": "Default", "project_name": "service", "username": "nova", "password": password},
        "service_user": {"send_service_user_token": "true", "auth_url": "http://controller:5000/v3", "auth_strategy": "keystone", "auth_type": "password", "project_domain_name": "Default", "project_name": "service", "user_domain_name": "Default", "username": "nova", "password": password},
        "vnc": {"enabled": "true", "server_listen": "0.0.0.0", "server_proxyclient_address": "$my_ip", "novncproxy_base_url": "http://controller:6080/vnc_auto.html"},
        "glance": {"api_servers": "http://controller:9292"}, "oslo_concurrency": {"lock_path": "/var/lib/nova/tmp"},
        "placement": {"region_name": "RegionOne", "project_domain_name": "Default", "project_name": "service", "auth_type": "password", "user_domain_name": "Default", "auth_url": "http://controller:5000/v3", "username": "placement", "password": password},
        "neutron": {"auth_url": "http://controller:5000", "auth_type": "password", "project_domain_name": "Default", "user_domain_name": "Default", "region_name": "RegionOne", "project_name": "service", "username": "neutron", "password": password},
        "libvirt": {"virt_type": "qemu"}, "cinder": {"os_region_name": "RegionOne"},
    }
    parser = configparser.RawConfigParser(strict=True, interpolation=None)
    for section, options in values.items():
        if section != "DEFAULT": parser.add_section(section)
        for name, value in options.items(): parser.set(section, name, value)
    stream = StringIO(); parser.write(stream); return stream.getvalue()


def write_compute_nova_config(target: Path, password: str, uid: int, gid: int, ops: object = os, nonce: str | None = None) -> None:
    temporary = target.parent / f".nova.conf.task5e.{nonce or uuid.uuid4().hex}"
    flags = ops.O_WRONLY | ops.O_CREAT | ops.O_EXCL | getattr(ops, "O_NOFOLLOW", 0)
    descriptor = None; created = False; identity = None
    try:
        descriptor = ops.open(str(temporary), flags, 0o640); created = True
        metadata = ops.fstat(descriptor); identity = (metadata.st_dev, metadata.st_ino)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1: raise RuntimeError("unsafe compute config temporary")
        ops.fchmod(descriptor, 0o640); ops.fchown(descriptor, uid, gid)
        payload = build_compute_nova_config(password).encode(); offset = 0
        while offset < len(payload):
            written = ops.write(descriptor, payload[offset:])
            if written <= 0: raise OSError("short compute config write")
            offset += written
        ops.fsync(descriptor); ops.close(descriptor); descriptor = None
        ops.replace(str(temporary), str(target)); created = False
        directory = ops.open(str(target.parent), ops.O_RDONLY | getattr(ops, "O_DIRECTORY", 0))
        try: ops.fsync(directory)
        finally: ops.close(directory)
    finally:
        if descriptor is not None: ops.close(descriptor)
        if created and identity is not None:
            try: current = ops.lstat(temporary)
            except FileNotFoundError: current = None
            if current is not None and (current.st_dev, current.st_ino) == identity and stat.S_ISREG(current.st_mode) and current.st_nlink == 1:
                ops.unlink(temporary)


def validate_written_compute_nova_config(target: Path, password: str, uid: int, gid: int, ops: object = os) -> None:
    metadata = ops.lstat(target)
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1 or metadata.st_uid != uid \
            or metadata.st_gid != gid or stat.S_IMODE(metadata.st_mode) != 0o640:
        raise ValueError("compute nova.conf metadata mismatch")
    try:
        payload = target.read_bytes()
    except OSError as error:
        raise RuntimeError("compute nova.conf read failed") from error
    if payload != build_compute_nova_config(password).encode("utf-8"):
        raise ValueError("compute nova.conf exact content mismatch")
```

真实配置为 root:nova、0640、单硬链接。快照用 `<URL_ENCODED_DB_PASSWORD>` 和 `<SERVICE_PASSWORD>` 替换真实口令。`virt_type=qemu` 是有意选择：本教学虚拟机没有 vmx/svm 标志，也没有 `/dev/kvm`；软件 QEMU 不依赖嵌套硬件虚拟化，可在更多学生终端上稳定复现。它的性能低于 KVM，因此生产环境应启用并验证硬件加速。

## 稳定 compute_id

Antelope 使用 `/etc/nova/compute_id` 保存计算节点稳定身份。目标不存在时必须直接用 `O_CREAT|O_EXCL|O_NOFOLLOW` 排他创建；失败清理只删除本次创建且 inode 未变化的普通文件。目标已存在时只验证，不得静默旋转（never rotate）。教材和快照只显示 `<COMPUTE_ID>`。

```python
from __future__ import annotations

import os
from pathlib import Path
import stat
import uuid


def _validate_compute_id_descriptor(descriptor: int, uid: int, gid: int, ops: object) -> uuid.UUID:
    before = ops.fstat(descriptor)
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
        raise RuntimeError("compute_id is not a regular single-link file")
    if before.st_uid != uid or before.st_gid != gid or stat.S_IMODE(before.st_mode) != 0o644:
        raise RuntimeError("compute_id ownership or mode mismatch")
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = ops.read(descriptor, 128)
        if not chunk:
            break
        total += len(chunk)
        if total > 128:
            raise RuntimeError("compute_id content is too long")
        chunks.append(chunk)
    after = ops.fstat(descriptor)
    before_identity = (before.st_dev, before.st_ino, before.st_mode, before.st_uid, before.st_gid, before.st_nlink)
    after_identity = (after.st_dev, after.st_ino, after.st_mode, after.st_uid, after.st_gid, after.st_nlink)
    if after_identity != before_identity:
        raise RuntimeError("compute_id descriptor identity changed during validation")
    try:
        payload = b"".join(chunks).decode("ascii")
    except UnicodeDecodeError as error:
        raise ValueError("compute_id is not ASCII") from error
    if not payload.endswith("\n") or payload.count("\n") != 1:
        raise RuntimeError("compute_id line format mismatch")
    value = payload[:-1]
    try:
        parsed = uuid.UUID(value)
    except ValueError as error:
        raise ValueError("compute_id UUID malformed") from error
    if parsed.int == 0 or str(parsed) != value:
        raise RuntimeError("compute_id UUID is not canonical and nonzero")
    return parsed


def validate_compute_id_fd(path: Path, uid: int, gid: int, ops: object = os) -> uuid.UUID:
    flags = ops.O_RDONLY | getattr(ops, "O_NOFOLLOW", 0)
    descriptor = ops.open(str(path), flags)
    try:
        return _validate_compute_id_descriptor(descriptor, uid, gid, ops)
    finally:
        ops.close(descriptor)


def ensure_compute_id(
    path: Path = Path("/etc/nova/compute_id"),
    account: object | None = None,
    ops: object = os,
    value_factory: object = uuid.uuid4,
) -> tuple[str, uuid.UUID]:
    if account is None:
        import pwd
        account = pwd.getpwnam("nova")
    flags = getattr(ops, "O_RDWR", ops.O_WRONLY) | ops.O_CREAT | ops.O_EXCL | getattr(ops, "O_NOFOLLOW", 0)
    descriptor = None; created = False; identity = None
    try:
        try:
            descriptor = ops.open(str(path), flags, 0o644)
        except FileExistsError:
            return "existing-stable", validate_compute_id_fd(
                path, account.pw_uid, account.pw_gid, ops=ops
            )
        created = True
        metadata = ops.fstat(descriptor); identity = (metadata.st_dev, metadata.st_ino)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1: raise RuntimeError("unsafe compute_id")
        ops.fchmod(descriptor, 0o644); ops.fchown(descriptor, account.pw_uid, account.pw_gid)
        value = value_factory()
        if not isinstance(value, uuid.UUID) or value.int == 0: raise ValueError("new compute_id UUID invalid")
        payload = f"{value}\n".encode("ascii"); offset = 0
        while offset < len(payload):
            written = ops.write(descriptor, payload[offset:])
            if written <= 0: raise OSError("short compute_id write")
            offset += written
        ops.fsync(descriptor)
        ops.lseek(descriptor, 0, os.SEEK_SET)
        parsed = _validate_compute_id_descriptor(
            descriptor, account.pw_uid, account.pw_gid, ops
        )
        if parsed != value: raise RuntimeError("created compute_id verification mismatch")
        ops.close(descriptor); descriptor = None
        directory = ops.open(str(path.parent), ops.O_RDONLY | getattr(ops, "O_DIRECTORY", 0))
        try: ops.fsync(directory)
        finally: ops.close(directory)
        created = False
        return "created", parsed
    finally:
        if descriptor is not None: ops.close(descriptor)
        if created and identity is not None:
            try: current = ops.lstat(path)
            except FileNotFoundError: current = None
            if current is not None and (current.st_dev, current.st_ino) == identity and stat.S_ISREG(current.st_mode) and current.st_nlink == 1:
                ops.unlink(path)
```

真实结果为 nova:nova、0644、单硬链接、规范非零 UUID。立即第二次调用得到 `existing-stable`，值保持不变且不输出。

## libvirt 先于 nova-compute

先启动 libvirt 并验证本地 URI，再启动 nova-compute。`virt-host-validate qemu` 在该嵌套教学环境因硬件加速缺席返回 RC 1；非硬件项目没有失败。该诊断不能被当作生产 KVM 合格证明。

```bash
set -Eeuo pipefail
systemctl enable --now libvirtd
systemctl is-active --quiet libvirtd && systemctl is-enabled --quiet libvirtd
[[ $(virsh -c qemu:///system uri) == 'qemu:///system' ]]
[[ -z $(virsh -c qemu:///system list --all --name | sed '/^[[:space:]]*$/d') ]]
systemctl enable --now openstack-nova-compute
systemctl is-active --quiet openstack-nova-compute && systemctl is-enabled --quiet openstack-nova-compute
```

启动后等待并复核服务仍 active，日志中 RabbitMQ、Keystone、Placement 和数据库认证错误均为 0。真实结果为 libvirt active/enabled、qemu:///system、domains=0、nova-compute active/enabled。

## 主机发现

nova-compute 已经 active 且控制端认证服务列表出现 `nova-compute/compute/up/enabled` 后，才允许发现主机。重复执行必须仍是 exactly one `compute` host mapping，并且绑定 cell1；不能显示 cell URL。

```bash
set -Eeuo pipefail
source /root/admin-openrc
openstack compute service list
nova-manage cell_v2 discover_hosts --by-service
[[ $(mysql -uroot -NBe "SELECT COUNT(*) FROM nova_api.host_mappings WHERE host='compute'") == 1 ]]
nova-manage cell_v2 discover_hosts --by-service
[[ $(mysql -uroot -NBe "SELECT COUNT(*) FROM nova_api.host_mappings") == 1 ]]
openstack hypervisor list --long
nova-status upgrade check
unset OS_PASSWORD
```

真实结果是 cell0/cell1 精确两条、compute→cell1 精确一条，第二次发现无重复。服务精确为 scheduler/controller、conductor/controller、compute/compute 三条且均 up/enabled；唯一 hypervisor 名称为 compute、类型 QEMU、state=up、status=enabled。

通过认证 Placement 1.39 REST 查询 `resource_providers`，Nova 自动创建唯一 provider `compute`，并自动上报 `VCPU`、`MEMORY_MB`、`DISK_GB` inventories；没有手工创建 provider 或 inventory。最终 `nova-status upgrade check` 七项均为 Success。

下面两个只读分类器消费由本节逐条命令保存的脱敏 JSON/数据库元数据。它们不依赖 `openstack ... show` 的人眼观察：查询失败、重复行、错误绑定、非法 inventory、非空资源、后续组件残留或磁盘漂移都会失败，且错误信息不拼接原始证据。

```python
from __future__ import annotations

import uuid


def _valid_inventory(row: object) -> bool:
    if not isinstance(row, dict) or set(row) != {
        "total", "reserved", "min_unit", "max_unit", "step_size", "allocation_ratio"
    }:
        return False
    numbers = (row["total"], row["reserved"], row["min_unit"], row["max_unit"], row["step_size"])
    if any(isinstance(value, bool) or not isinstance(value, int) for value in numbers):
        return False
    ratio = row["allocation_ratio"]
    return (
        row["total"] > 0 and 0 <= row["reserved"] < row["total"]
        and 0 < row["min_unit"] <= row["max_unit"] <= row["total"]
        and row["step_size"] > 0 and isinstance(ratio, (int, float))
        and not isinstance(ratio, bool) and ratio > 0
    )


def validate_nova_integration_evidence(evidence: dict[str, object]) -> None:
    if evidence.get("query_ok") is not True:
        raise RuntimeError("Nova integration query failed")
    services = evidence.get("compute_services")
    expected_services = {
        ("nova-scheduler", "controller", "up", "enabled"),
        ("nova-conductor", "controller", "up", "enabled"),
        ("nova-compute", "compute", "up", "enabled"),
    }
    if not isinstance(services, list) or len(services) != 3 or {
        (row.get("binary"), row.get("host"), row.get("state"), row.get("status"))
        for row in services if isinstance(row, dict)
    } != expected_services:
        raise ValueError("Nova compute-service exact state mismatch")

    cells = evidence.get("cells")
    if not isinstance(cells, list) or len(cells) != 2:
        raise ValueError("Nova cell cardinality mismatch")
    cell0 = [row for row in cells if row.get("name") == "cell0"]
    cell1 = [row for row in cells if row.get("name") == "cell1"]
    if len(cell0) != 1 or cell0[0] != {
        "name": "cell0", "uuid": "00000000-0000-0000-0000-000000000000", "disabled": False
    } or len(cell1) != 1 or cell1[0].get("disabled") is not False:
        raise ValueError("Nova cell exact state mismatch")
    try:
        cell1_uuid = uuid.UUID(str(cell1[0].get("uuid")))
    except ValueError as error:
        raise ValueError("cell1 UUID mismatch") from error
    if cell1_uuid.int == 0 or str(cell1_uuid) != cell1[0].get("uuid"):
        raise ValueError("cell1 UUID mismatch")
    mappings = evidence.get("host_mappings")
    if mappings != [{"host": "compute", "cell_uuid": str(cell1_uuid)}]:
        raise ValueError("compute host-to-cell1 mapping mismatch")

    hypervisors = evidence.get("hypervisors")
    if not isinstance(hypervisors, list) or len(hypervisors) != 1:
        raise ValueError("hypervisor cardinality mismatch")
    hypervisor = hypervisors[0]
    if not isinstance(hypervisor, dict) or not (
        hypervisor.get("name") == "compute" and hypervisor.get("type") == "QEMU"
        and hypervisor.get("state") == "up" and hypervisor.get("status") == "enabled"
    ):
        raise ValueError("hypervisor exact state mismatch")
    providers = evidence.get("providers")
    if not isinstance(providers, list) or len(providers) != 1:
        raise ValueError("Placement provider cardinality mismatch")
    provider = providers[0]
    if not isinstance(provider, dict) or provider.get("name") != "compute" or not provider.get("uuid"):
        raise ValueError("Placement provider exact state mismatch")
    if provider.get("uuid") != hypervisor.get("uuid"):
        raise ValueError("Placement provider and hypervisor UUID mismatch")
    inventories = evidence.get("inventories")
    if not isinstance(inventories, dict) or set(inventories) != {"VCPU", "MEMORY_MB", "DISK_GB"}:
        raise ValueError("required Placement inventory set mismatch")
    if not all(_valid_inventory(inventories[name]) for name in sorted(inventories)):
        raise ValueError("Placement inventory structure or totals invalid")

    identity = evidence.get("nova_identity")
    if not isinstance(identity, dict):
        raise ValueError("Nova identity evidence missing")
    service = identity.get("service")
    if not isinstance(service, dict) or not (
        service.get("id") and service.get("name") == "nova" and service.get("type") == "compute"
        and service.get("enabled") is True
    ):
        raise ValueError("Nova identity service mismatch")
    endpoints = identity.get("endpoints")
    if not isinstance(endpoints, list) or len(endpoints) != 3 or {
        row.get("interface") for row in endpoints if isinstance(row, dict)
    } != {"admin", "internal", "public"} or any(
        row.get("service_id") != service["id"] or row.get("region") != "RegionOne"
        or row.get("url") != "http://controller:8774/v2.1" or row.get("enabled") is not True
        for row in endpoints
    ):
        raise ValueError("Nova endpoint exact binding mismatch")
    if evidence.get("nova_api") != {"http": 200, "id": "v2.1", "status": "CURRENT", "authenticated": True}:
        raise ValueError("Nova current/authenticated API evidence mismatch")
    if evidence.get("resources") != {"images": [], "servers": [], "flavors": []}:
        raise ValueError("Nova slice must leave images, servers, and flavors empty")
    if evidence.get("database_grants") != {
        "hosts": ["%", "127.0.0.1", "localhost"],
        "schemas": ["nova", "nova_api", "nova_cell0"],
        "global_only_usage": True, "object_privileges": 0, "proxy": 0, "roles": 0,
    }:
        raise ValueError("Nova database-grant summary mismatch")

    compute_identity = evidence.get("compute_identity")
    if not isinstance(compute_identity, dict):
        raise ValueError("compute identity evidence missing")
    identifiers = [compute_identity.get(name) for name in ("file_uuid", "database_uuid", "hypervisor_uuid")]
    try:
        parsed_identifiers = [uuid.UUID(str(value)) for value in identifiers]
    except ValueError as error:
        raise ValueError("compute identity UUID malformed") from error
    if len(set(identifiers)) != 1 or any(value.int == 0 or str(value) != raw for value, raw in zip(parsed_identifiers, identifiers)):
        raise ValueError("compute identity internal UUID consistency mismatch")
    if identifiers[0] != hypervisor.get("uuid") or compute_identity.get("owner") != "nova:nova" \
            or compute_identity.get("mode") != "0644" or compute_identity.get("nlink") != 1:
        raise ValueError("compute identity metadata or hypervisor binding mismatch")
    if evidence.get("upgrade") != {"rc": 0, "successes": 7, "failures": 0, "warnings": 0}:
        raise ValueError("Nova upgrade-check evidence mismatch")
    if evidence.get("later") != {"packages": [], "databases": [], "db_users": [], "users": [],
                                 "services": [], "endpoints": [], "listeners": []}:
        raise ValueError("Neutron or later state is present")
    expected_disk = {"bytes": 53687091200, "type": "disk", "root_ancestor": False,
                     "children": 0, "filesystem": "", "mountpoint": "", "wipefs": [], "blkid_rc": 2}
    disks = evidence.get("disks")
    if not isinstance(disks, dict) or set(disks) != {"/dev/sdb", "/dev/sdc"} \
            or any(disks[name] != expected_disk for name in sorted(disks)):
        raise ValueError("compute disk boundary mismatch")
    if evidence.get("temporary") != []:
        raise ValueError("task temporary files remain")


def validate_nova_final_evidence(evidence: dict[str, object]) -> None:
    if evidence.get("query_ok") is not True:
        raise RuntimeError("final two-node query failed")
    integration = evidence.get("integration")
    if not isinstance(integration, dict):
        raise ValueError("final integration evidence missing")
    validate_nova_integration_evidence(integration)
    controller = evidence.get("controller")
    compute = evidence.get("compute")
    expected_controller_services = {
        "chronyd", "mariadb", "rabbitmq-server", "memcached", "httpd", "openstack-glance-api",
        "openstack-nova-api", "openstack-nova-scheduler", "openstack-nova-conductor", "openstack-nova-novncproxy",
    }
    if not isinstance(controller, dict) or set(controller.get("active_enabled", [])) != expected_controller_services \
            or len(controller.get("active_enabled", [])) != len(expected_controller_services):
        raise ValueError("final controller service audit mismatch")
    if controller.get("listeners") != [5000, 6080, 8774, 8778, 9292] or controller.get("databases") != [
        "glance", "keystone", "nova", "nova_api", "nova_cell0", "placement"
    ]:
        raise ValueError("final controller listeners or databases mismatch")
    if not isinstance(compute, dict) or set(compute.get("active_enabled", [])) != {
        "chronyd", "sshd", "libvirtd", "openstack-nova-compute"
    } or len(compute.get("active_enabled", [])) != 4:
        raise ValueError("final compute service audit mismatch")
    if compute.get("virt_type") != "qemu" or compute.get("domains") != [] or compute.get("boot_changed") is not False:
        raise ValueError("final compute virtualization or boot audit mismatch")
```

## 附录：验证用顺序模型（禁止用于学生安装）

下列函数只供教材 focused tests 对“手工步骤的先后关系与失败短路”建模，**学生不得运行它来安装 OpenStack，也不能把它作为一键部署入口**。课堂正文的唯一安装路径仍是前后各小节：先通过只读门禁，再由学生手工创建数据库与授权、手工创建用户/服务/端点、手工编辑并核对配置参数、逐条执行 `nova-manage`、逐条启动服务和发现主机。`runtime` 的每个方法仅代表相应手工命令块，以便测试删除或交换任一块时失败；它不提供也不允许自动化替代这些正文步骤。

```python
from __future__ import annotations


def run_guarded_nova_deployment(password: str, runtime: object) -> dict[str, object]:
    runtime.run_strict_gate("controller", password)
    runtime.run_strict_gate("compute", password)

    controller_transaction = runtime.install_controller_packages()
    validate_nova_transaction_evidence("controller", controller_transaction)
    secret = runtime.load_secret()
    runtime.create_controller_databases_and_grants(secret)
    grant_evidence = collect_nova_grant_evidence(runtime.grant_cursor())
    validate_nova_grant_evidence(grant_evidence)

    identity_adapter = runtime.identity_adapter(secret)
    identity_evidence = ensure_nova_identity_objects(
        secret, identity_adapter.query, identity_adapter.mutate
    )
    validate_nova_identity_evidence(identity_evidence)
    write_nova_config(*runtime.controller_config_args)
    validate_written_nova_config(*runtime.controller_config_args)

    runtime.sync_api_database()
    cell_evidence = runtime.collect_and_ensure_cells()
    classify_cell_state(cell_evidence)
    runtime.sync_main_database()
    controller_schema = runtime.collect_controller_schema()
    validate_nova_controller_schema(controller_schema)
    runtime.start_controller_services()

    runtime.run_strict_gate("compute", password)
    compute_transaction = runtime.install_compute_packages()
    validate_nova_transaction_evidence("compute", compute_transaction)
    write_compute_nova_config(*runtime.compute_config_args)
    validate_written_compute_nova_config(*runtime.compute_config_args)
    _identity_state, expected_compute_id = ensure_compute_id(*runtime.compute_id_args)
    actual_compute_id = validate_compute_id_fd(*runtime.compute_id_args)
    if actual_compute_id != expected_compute_id:
        raise RuntimeError("compute_id changed between ensure and same-FD validation")

    runtime.start_libvirt()
    runtime.start_nova_compute()
    runtime.discover_hosts()
    integration_evidence = runtime.collect_integration_evidence()
    validate_nova_integration_evidence(integration_evidence)
    final_evidence = runtime.collect_final_evidence()
    validate_nova_final_evidence(final_evidence)
    runtime.run_final_node_audits(password)
    return {"integration": integration_evidence, "final": final_evidence}
```

测试映射严格为：`run_strict_gate`→本章双节点 `RejectPolicy` 门禁；`install_*_packages`→对应本地源事务；数据库和授权方法→控制节点三库/九授权手工小节；身份适配器→正文逐条 OpenStack CLI；配置参数→正文手工编辑后的只读复核；同步、cell、服务、libvirt、nova-compute、发现方法→各同名手工命令段；两个证据收集器→下节的严格集成分类器和最终双节点审计。本顺序模型不得出现在学生操作命令中，也不得替代 `vi`、`openstack`、`nova-manage` 或 `systemctl` 的逐步教学。

## 最终双节点审计

最终审计再次读取两个节点。Controller 要求四种 OpenStack 服务、12 个精确端点、六个数据库、两个 cell、一条 host mapping、三条 Nova 服务、一台 hypervisor、一个 provider 和三类必要 inventory；image/server/flavor 仍为空。Compute 要求事务 3 的 398 Install+5 Upgrade、QEMU/libvirt/nova-compute、稳定 identity、空 domain 与两块空白数据盘。Neutron and later 必须全部缺席，no task temporary files 必须成立。

```python
from __future__ import annotations

from pathlib import Path
from typing import Callable

import paramiko


HOSTS = {
    "controller": ("192.168.234.151", Path(".superpowers/sdd/known_hosts.controller")),
    "compute": ("192.168.234.150", Path(".superpowers/sdd/known_hosts.compute")),
}

FINAL_CONTROLLER_AUDIT = r'''set -Eeuo pipefail
for s in chronyd mariadb rabbitmq-server memcached httpd openstack-glance-api openstack-nova-api openstack-nova-scheduler openstack-nova-conductor openstack-nova-novncproxy; do systemctl is-active --quiet "$s" && systemctl is-enabled --quiet "$s"; done
[[ $(mysql -uroot -NBe "SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA='nova_api'") == 32 ]]
[[ $(mysql -uroot -NBe "SELECT version_num FROM nova_api.alembic_version") == b30f573d3377 ]]
[[ $(mysql -uroot -NBe "SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA='nova'") == 110 ]]
[[ $(mysql -uroot -NBe "SELECT version_num FROM nova.alembic_version") == 960aac0e09ea ]]
[[ $(mysql -uroot -NBe "SELECT COUNT(*) FROM nova_api.cell_mappings") == 2 ]]
[[ $(mysql -uroot -NBe "SELECT COUNT(*) FROM nova_api.host_mappings WHERE host='compute'") == 1 ]]
for p in openstack-nova-compute openstack-neutron-common openstack-cinder-common openstack-swift-common python3-horizon; do rpm -q "$p" >/dev/null 2>&1 && exit 1 || [[ $? -eq 1 ]]; done
for port in 9696 8776 8080; do [[ -z $(ss -H -lnt "( sport = :$port )") ]]; done
[[ -z $(find /root -maxdepth 1 -name '.task5e-*' -print -quit) ]]
printf 'FINAL_CONTROLLER_AUDIT=PASS\n'
'''

FINAL_COMPUTE_AUDIT = r'''set -Eeuo pipefail
for s in chronyd sshd libvirtd openstack-nova-compute; do systemctl is-active --quiet "$s" && systemctl is-enabled --quiet "$s"; done
for p in qemu libvirt openstack-nova-compute; do rpm -q "$p" >/dev/null; done
for p in openstack-nova-api openstack-neutron-common openstack-cinder-common openstack-swift-common python3-horizon; do rpm -q "$p" >/dev/null 2>&1 && exit 1 || [[ $? -eq 1 ]]; done
[[ $(stat -c '%U:%G %a %h' /etc/nova/compute_id) == 'nova:nova 644 1' ]]
[[ -z $(virsh -c qemu:///system list --all --name | sed '/^[[:space:]]*$/d') ]]
for d in /dev/sdb /dev/sdc; do [[ -b $d && $(blockdev --getsize64 "$d") == 53687091200 && $(lsblk -dnro TYPE "$d") == disk ]]; [[ $(lsblk -nrpo NAME "$d" | sed '/^$/d' | wc -l) -eq 1 ]]; [[ -z $(wipefs --no-act --noheadings --output TYPE "$d") ]]; blkid -p "$d" >/dev/null 2>&1 && exit 1 || [[ $? -eq 2 ]]; done
[[ -z $(find /root -maxdepth 1 -name '.task5e-*' -print -quit) ]]
printf 'FINAL_COMPUTE_AUDIT=PASS\n'
'''


def connect_node(name: str, password: str) -> paramiko.SSHClient:
    host, known_hosts = HOSTS[name]
    client = paramiko.SSHClient(); client.load_host_keys(str(known_hosts))
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    client.connect(host, username="root", password=password, look_for_keys=False, allow_agent=False,
                   timeout=10, auth_timeout=10, banner_timeout=10)
    return client


def run_remote(client: paramiko.SSHClient, script: str) -> None:
    stdin, stdout, stderr = client.exec_command("bash -s")
    stdin.write(script); stdin.channel.shutdown_write()
    rc = stdout.channel.recv_exit_status()
    if rc: raise RuntimeError(stderr.read().decode("utf-8", "replace"))


def run_nova_final_audits(
    password: str,
    connector: Callable[[str, str], paramiko.SSHClient] = connect_node,
    runner: Callable[[paramiko.SSHClient, str], None] = run_remote,
) -> None:
    for name, script in (("controller", FINAL_CONTROLLER_AUDIT), ("compute", FINAL_COMPUTE_AUDIT)):
        client = connector(name, password)
        try: runner(client, script)
        finally: client.close()
    print("FINAL_NOVA_AUDIT=PASS")
```

真实总审计结果：controller `SERVICES=4 ENDPOINTS=12 DBS=6 CELLS=2 HOSTS=1 COMPUTE_SERVICES=3 HYPERVISORS=1 PROVIDERS=1 INVENTORIES=3 IMAGES=0 SERVERS=0 FLAVORS=0 LATER=0 TEMP=0`；compute `TX=3 INSTALLS=398 UPGRADES=5 SERVICES=libvirt,nova-compute VIRT=qemu DOMAINS=0 COMPUTE_ID=stable-redacted LATER=0 SDB=blank50G SDC=blank50G TEMP=0`。

本节不创建实例、不创建网络、不创建规格、不上传镜像；不部署 `openstack-neutron-common`、`openstack-cinder-common`、`openstack-swift-common`、`python3-horizon`，也不格式化、分区、初始化 LVM 或写入 `/dev/sdb`、`/dev/sdc`。下一步必须等待本切片独立复审通过，不能直接进入 Neutron。
