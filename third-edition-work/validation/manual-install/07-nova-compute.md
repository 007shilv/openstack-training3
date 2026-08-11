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

完整 403 行计划保存在 `third-edition-work/validation/repository/systemd-dependency-transaction-compute.txt`，实际 RPM after 集合与该列表的 name/epoch/version/release/arch 精确一致。升级只替换上述五个同名旧 NEVRA，不是包删除或替换依赖。真实事务号为 3；boot ID 未变化，sshd、chronyd 均 active/enabled，失败单元集合前后相同，安装脚本没有提前启动 libvirt 或 nova-compute，`/dev/sdb`、`/dev/sdc` 仍为空白盘。

禁止使用 `--allowerasing`、`--nodeps`、`--skip-broken` 或外部仓库。教学环境的离线仓库仍为 `gpgcheck=0`，完整性依赖不可变原始 ZIP、官方签名 overlay、SHA-256 manifest 与复审后的仓库门禁；生产环境应启用仓库签名校验和独立供应链策略。

## 计算节点原子配置

`rpm -V openstack-nova-common` 通过后，将 202457 字节软件包默认配置备份到 `/root/openstack-lab-backups/task-5e-20260811T122341Z/nova.conf.package-default`。计算节点不配置 Nova 数据库连接；消息队列、Keystone/service-user、VNC、Glance 和 Placement 与 controller 对齐。`[neutron]`、`[cinder]` 是 future inactive dependencies，只有各自后续切片通过后才进入业务路径。

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


def validate_compute_id(path: Path, uid: int, gid: int, ops: object = os) -> uuid.UUID:
    metadata = ops.lstat(path)
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        raise RuntimeError("compute_id is not a regular single-link file")
    if metadata.st_uid != uid or metadata.st_gid != gid or stat.S_IMODE(metadata.st_mode) != 0o644:
        raise RuntimeError("compute_id ownership or mode mismatch")
    lines = path.read_text(encoding="ascii").splitlines()
    if len(lines) != 1:
        raise RuntimeError("compute_id line count mismatch")
    parsed = uuid.UUID(lines[0])
    if str(parsed) != lines[0] or parsed.int == 0:
        raise RuntimeError("compute_id UUID mismatch")
    return parsed


def ensure_compute_id(
    path: Path = Path("/etc/nova/compute_id"),
    account: object | None = None,
    ops: object = os,
    value_factory: object = uuid.uuid4,
) -> tuple[str, uuid.UUID]:
    if account is None:
        import pwd
        account = pwd.getpwnam("nova")
    try: existing = ops.lstat(path)
    except FileNotFoundError: existing = None
    if existing is not None:
        return "existing-stable", validate_compute_id(path, account.pw_uid, account.pw_gid, ops=ops)
    flags = ops.O_WRONLY | ops.O_CREAT | ops.O_EXCL | getattr(ops, "O_NOFOLLOW", 0)
    descriptor = None; created = False; identity = None
    try:
        descriptor = ops.open(str(path), flags, 0o644); created = True
        metadata = ops.fstat(descriptor); identity = (metadata.st_dev, metadata.st_ino)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1: raise RuntimeError("unsafe compute_id")
        ops.fchmod(descriptor, 0o644); ops.fchown(descriptor, account.pw_uid, account.pw_gid)
        payload = f"{value_factory()}\n".encode("ascii")
        if ops.write(descriptor, payload) != len(payload): raise OSError("short compute_id write")
        ops.fsync(descriptor); ops.close(descriptor); descriptor = None
        directory = ops.open(str(path.parent), ops.O_RDONLY | getattr(ops, "O_DIRECTORY", 0))
        try: ops.fsync(directory)
        finally: ops.close(directory)
        value = validate_compute_id(path, account.pw_uid, account.pw_gid, ops=ops); created = False
        return "created", value
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
