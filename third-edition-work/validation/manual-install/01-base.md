# 01 基础环境：双节点身份、软件源与时间同步

## 执行结论与顺序门禁

本记录来自 2026-08-11 对两台 openEuler 24.03 LTS SP3 虚拟机的实际手工执行。所有 SSH 会话均加载各节点经复核的 `known_hosts`，并使用 `RejectPolicy` 拒绝未知或变化的主机密钥；未执行 `01`—`05` 中任何复制脚本。

本阶段严格按以下顺序完成，并在每一步检查通过后才继续：

1. 起始状态与 RPM 基线；
2. 主机名、`/etc/hosts`、正向解析和双向连通；
3. 两节点 `openstack-local` 隔离访问；
4. 实验室安全状态；
5. Antelope release 包与 SP3 主机/SP2 Antelope 仓库兼容改写；
6. chrony 服务与同步状态；
7. 运行时密钥文件的创建、保护和双节点放置；
8. 全部基础检查通过后，才允许进入 `02-infrastructure.md`。

任一检查失败均停止。实际执行中没有修改 `ens33` 的既有静态地址，没有给 `ens34` 配置地址，也没有访问磁盘写路径。

以下所有 `bash` 片段必须在同一个 root shell 中按文档顺序执行。先建立严格会话；不要逐行复制到会吞掉退出状态的外层工具中：

```bash
set -Eeuo pipefail

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

on_error() {
  local rc=$?
  local line=${1:-unknown}
  local command=${2:-unknown}
  trap - ERR
  printf 'ERROR: rc=%s line=%s command=%s\n' "$rc" "$line" "$command" >&2
  exit "$rc"
}

trap 'on_error "$LINENO" "$BASH_COMMAND"' ERR
```

`set -E` 让函数内错误继承 ERR trap，`-e` 在未处理失败时退出，`-u` 拒绝未定义变量，`pipefail` 防止流水线前段失败被末段成功掩盖。后文的 `die`、断言函数和阶段函数依赖这一会话合同。

## 实验拓扑与起始状态

| 节点 | 管理地址 | 管理接口 | 第二接口 | 用途 |
| --- | --- | --- | --- | --- |
| controller | `192.168.234.151/24` | `ens33` | `ens34`，无 IP | 控制节点与本地仓库 |
| compute | `192.168.234.150/24` | `ens33` | `ens34`，无 IP | 计算节点 |

在两节点分别执行以下只读核验。接口、RPM 数据库或磁盘探针本身异常时立即停止，不能把探针错误解释为“没有地址”“没有安装”或“空盘”：

```bash
assert_packages_absent_initial() {
  local package output rc
  LC_ALL=C rpm -q rpm >/dev/null 2>&1 || die "RPM database health probe failed"
  for package in "$@"; do
    if output=$(LC_ALL=C rpm -q "$package" 2>&1); then
      die "unexpected starting package: $package"
    else
      rc=$?
      [[ "$rc" -eq 1 ]] || die "RPM query failed for $package (rc=$rc)"
      [[ "$output" == "package $package is not installed" ]] || \
        die "unexpected RPM absence response for $package"
    fi
  done
}

cat /etc/os-release
hostnamectl --static
ip -4 -o addr show dev ens33
ens34_ipv4=$(ip -4 -o addr show dev ens34)
[[ -z "$ens34_ipv4" ]] || die "ens34 must not have an IPv4 address"
ip -4 route
findmnt -n -o SOURCE,FSTYPE,TARGET /
lsblk -b -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS
rpm -qa --qf '%{NAME}-%{VERSION}-%{RELEASE}.%{ARCH}\n' | sort
assert_packages_absent_initial openstack-release-antelope mariadb-server \
  rabbitmq-server memcached python3-openstackclient
```

compute 额外执行以下只读、fail-closed 空盘门禁。`blkid -p` 只有返回码 2 表示未发现签名；返回 0 表示有签名，其他返回码均表示探针故障。检查同时覆盖块设备身份、精确容量、子项/分区、文件系统、挂载、LVM/PV，以及根文件系统完整祖先链；任一项失败即退出，且不执行任何磁盘写命令：

```bash
is_block_device() {
  [[ -b "$1" ]]
}

assert_not_root_ancestor() {
  local device root_source root_chain
  device=$(readlink -f "$1") || die "cannot canonicalize data disk: $1"
  root_source=$(findmnt -nro SOURCE /) || die "cannot resolve root source"
  root_source=$(readlink -f "$root_source") || die "cannot canonicalize root source"
  root_chain=$(lsblk -s -nrpo NAME "$root_source") || die "cannot inspect root ancestry"
  if grep -Fxq "$device" <<<"$root_chain"; then
    die "$device belongs to the root-device ancestry"
  fi
}

assert_blank_data_disk() {
  local device=$1 expected_size=$2 actual_size nodes facts pv_output rc
  is_block_device "$device" || die "$device is not a block device"
  actual_size=$(blockdev --getsize64 "$device") || die "cannot read size for $device"
  [[ "$actual_size" == "$expected_size" ]] || die "unexpected size for $device: $actual_size"
  assert_not_root_ancestor "${device}"

  nodes=$(lsblk -nrpo NAME "$device") || die "cannot inspect children for $device"
  [[ $(printf '%s\n' "$nodes" | sed '/^[[:space:]]*$/d' | wc -l) -eq 1 ]] || \
    die "$device has a partition or another child"
  facts=$(lsblk -dnro FSTYPE,MOUNTPOINT "$device") || \
    die "cannot inspect filesystem or mount state for $device"
  [[ -z "${facts//[[:space:]]/}" ]] || die "$device has a filesystem or mount"

  command -v pvs >/dev/null 2>&1 || die "pvs is unavailable; refusing to classify $device"
  pv_output=$(pvs --noheadings --readonly -o pv_uuid,pv_name) || \
    die "LVM PV probe failed for $device"
  if awk -v device="$device" 'NF >= 2 && $2 == device { found=1 } END { exit !found }' \
      <<<"$pv_output"; then
    die "$device is an LVM physical volume"
  fi

  if blkid -p "$device" >/dev/null 2>&1; then
    die "$device contains a detectable signature"
  else
    rc=$?
    [[ "$rc" -eq 2 ]] || die "blkid probe failed for $device (rc=$rc)"
  fi
}

assert_blank_data_disk /dev/sdb 53687091200
assert_blank_data_disk /dev/sdc 53687091200
```

脱敏代表性结果：

```text
controller ens33: 192.168.234.151/24; ens34 IPv4: none
compute    ens33: 192.168.234.150/24; ens34 IPv4: none
controller RPM: baseline + vsftpd only
compute RPM: exact baseline
/dev/sdb: no-visible-signature, rc=2
/dev/sdc: no-visible-signature, rc=2
later OpenStack service packages: not installed
```

controller 的 `/dev/sda` 是系统盘；compute 的 `/dev/sda` 是 200 GiB 系统盘，`/dev/sdb`、`/dev/sdc` 各为 50 GiB 空白整盘。本阶段未运行分区、LVM、文件系统或挂载写命令。

## 主机名和 hosts 映射

修改前，两个节点的 `/etc/hostname` 均为空。先在每个节点建立 root-only 备份目录并保存原文件：

```bash
install -d -m 0700 /root/openstack-lab-backups
install -d -m 0700 /root/openstack-lab-backups/task-5a-20260811T043901Z
cp -a /etc/hostname /root/openstack-lab-backups/task-5a-20260811T043901Z/etc-hostname
cp -a /etc/hosts /root/openstack-lab-backups/task-5a-20260811T043901Z/etc-hosts
```

controller：

```bash
hostnamectl set-hostname controller
```

compute：

```bash
hostnamectl set-hostname compute
```

两节点均以同一保留式方法更新 `/etc/hosts`。该命令只从地址行的别名字段移除 `controller`/`compute`，不会因为同一行含目标别名而丢弃其他别名或行尾注释；再追加唯一的精确映射：

```bash
tmp=$(mktemp /etc/.hosts.task5a.XXXXXX)
python3 - /etc/hosts "$tmp" <<'PY'
from pathlib import Path
import sys

TARGET_ALIASES = {"controller", "compute"}
source = Path(sys.argv[1])
destination = Path(sys.argv[2])
result = []

for raw in source.read_text(encoding="utf-8").splitlines():
    if not raw.strip() or raw.lstrip().startswith("#"):
        result.append(raw)
        continue
    address_and_aliases, marker, comment_tail = raw.partition("#")
    fields = address_and_aliases.split()
    if len(fields) < 2:
        result.append(raw)
        continue
    aliases = [alias for alias in fields[1:] if alias not in TARGET_ALIASES]
    comment = marker + comment_tail.rstrip() if marker else ""
    if aliases:
        rewritten = " ".join([fields[0], *aliases])
        if comment:
            rewritten += "  " + comment
        result.append(rewritten)
    elif comment:
        result.append(comment)

result.extend((
    "192.168.234.151 controller",
    "192.168.234.150 compute",
))
destination.write_text("\n".join(result) + "\n", encoding="utf-8")
PY
chown root:root "$tmp"
chmod 0644 "$tmp"
if command -v restorecon >/dev/null 2>&1; then
  restorecon -F "$tmp" >/dev/null
fi
mv -f "$tmp" /etc/hosts
if command -v restorecon >/dev/null 2>&1; then
  restorecon -F /etc/hosts >/dev/null
fi
```

例如，`192.168.234.151 controller repo mirror # keep` 会保留为 `192.168.234.151 repo mirror  # keep`，而不是整行删除；纯注释行保持原样。

检查命令：

```bash
hostnamectl --static
getent ahostsv4 controller
getent ahostsv4 compute
grep -Ec '^192\.168\.234\.151[[:space:]]+controller([[:space:]]|$)' /etc/hosts
grep -Ec '^192\.168\.234\.150[[:space:]]+compute([[:space:]]|$)' /etc/hosts
```

controller 执行 `ping -c 2 -W 2 compute`，compute 执行 `ping -c 2 -W 2 controller`。实际结果均为 `2 transmitted, 2 received, 0% packet loss`。

## 隔离本地软件源

controller 的本地文件源和 compute 的 FTP 源已由前置任务建立。两节点均执行：

```bash
dnf -q repolist --disablerepo='*' --enablerepo='openstack-local'
dnf -q makecache --disablerepo='*' --enablerepo='openstack-local'
```

代表性结果：

```text
controller: openstack-local  Validated local OpenStack repository
compute:    openstack-local  Validated controller FTP OpenStack repository
```

最终源文件见 `config-snapshots/controller-openstack-local.repo` 和 `compute-openstack-local.repo`。其中 `gpgcheck=0` 是本实验既定合同，完整性依赖已记录的不可变 ZIP、overlay manifest、RPM 签名与哈希验证；生产环境不得照搬。

## 实验室安全状态

先备份 SELinux 和仓库配置：

```bash
cp -a /etc/selinux/config \
  /root/openstack-lab-backups/task-5a-20260811T043901Z/etc-selinux-config
cp -a /etc/yum.repos.d/openEuler.repo \
  /root/openstack-lab-backups/task-5a-20260811T043901Z/etc-yum.repos.d-openEuler.repo
cp -a /etc/yum.repos.d/openstack-local.repo \
  /root/openstack-lab-backups/task-5a-20260811T043901Z/etc-yum.repos.d-openstack-local.repo
cp -a /etc/chrony.conf \
  /root/openstack-lab-backups/task-5a-20260811T043901Z/etc-chrony.conf
```

两节点执行：

```bash
sed -ri 's/^SELINUX=.*/SELINUX=permissive/' /etc/selinux/config
setenforce 0
systemctl disable --now firewalld
```

检查：

```bash
[[ $(getenforce) == Permissive ]] || die "SELinux runtime mode is not Permissive"
grep -qx 'SELINUX=permissive' /etc/selinux/config || die "SELinux boot mode is not permissive"
if firewall_active=$(systemctl is-active firewalld 2>&1); then
  die "firewalld is unexpectedly active"
else
  rc=$?
  [[ "$rc" -eq 3 && "$firewall_active" == inactive ]] || \
    die "firewalld active-state probe failed (rc=$rc)"
fi
if firewall_enabled=$(systemctl is-enabled firewalld 2>&1); then
  die "firewalld is unexpectedly enabled"
else
  rc=$?
  [[ "$rc" -eq 1 && "$firewall_enabled" == disabled ]] || \
    die "firewalld enable-state probe failed (rc=$rc)"
fi
```

实际输出为 `Permissive`、`inactive`、`disabled`。

> 安全警告：这是隔离教学实验的简化设置。生产环境应保持 SELinux Enforcing，使用最小化防火墙规则，仅开放经认证、加密且确有需要的服务端口；不得直接禁用两项防护。

## Antelope release 与仓库兼容处理

两节点都只允许 `openstack-local` 安装 release 包：

```bash
dnf -y --disablerepo='*' --enablerepo='openstack-local' \
  install openstack-release-antelope
rpm -q openstack-release-antelope
```

实际安装版本：

```text
openstack-release-antelope-1.0.6-6.oe2403sp3.noarch
```

该 release 包在 SP3 主机上生成了不存在的 SP3 Antelope URL，因此先备份生成文件，再按已复核兼容方案改为 SP2：

```bash
cp -a /etc/yum.repos.d/openstack-antelope.repo \
  /root/openstack-lab-backups/task-5a-20260811T043901Z/etc-yum.repos.d-openstack-antelope.repo.generated
sed -ri 's#openEuler-24.03-LTS-SP3#openEuler-24.03-LTS-SP2#g' \
  /etc/yum.repos.d/openstack-antelope.repo
```

按基础脚本要求，openEuler 主源使用直接 `baseurl`，禁用调试和源码仓库：

```bash
sed -ri 's/^metalink=/# metalink=/' /etc/yum.repos.d/openEuler.repo
python3 - <<'PY'
import configparser

path = '/etc/yum.repos.d/openEuler.repo'
cfg = configparser.RawConfigParser()
with open(path, encoding='utf-8') as stream:
    cfg.read_file(stream)
for section in ('debuginfo', 'source', 'update-source'):
    if cfg.has_section(section):
        cfg.set(section, 'enabled', '0')
with open(path, 'w', encoding='utf-8') as stream:
    cfg.write(stream)
PY
if command -v restorecon >/dev/null 2>&1; then
  restorecon -F /etc/yum.repos.d/openEuler.repo \
    /etc/yum.repos.d/openstack-antelope.repo >/dev/null
fi
dnf clean all
dnf -q makecache --disablerepo='*' --enablerepo='openstack-local'
```

检查结果：Antelope 文件中有 4 处 SP2 引用、0 处 SP3 引用；openEuler 文件中无活动 metalink，`debuginfo`、`source`、`update-source` 均为 `enabled = 0`。最终内容见节点前缀的 `openstack-antelope.repo` 和 `openEuler.repo` 快照。

## chrony 安装与验证

两节点执行：

```bash
dnf -y --disablerepo='*' --enablerepo='openstack-local' install chrony
systemctl enable --now chronyd
chronyc -a makestep

assert_chrony() {
  local tracking sources stratum
  systemctl is-active --quiet chronyd || die "chronyd is not active"
  systemctl is-enabled --quiet chronyd || die "chronyd is not enabled"
  tracking=$(chronyc tracking) || die "chronyc tracking failed"
  grep -Eq '^Leap status[[:space:]]*:[[:space:]]*Normal$' <<<"$tracking" || \
    die "chrony Leap status is not Normal"
  stratum=$(awk -F: '/^Stratum[[:space:]]*:/ {gsub(/[[:space:]]/, "", $2); print $2}' <<<"$tracking")
  [[ "$stratum" =~ ^[0-9]+$ ]] && (( stratum > 0 )) || die "chrony stratum is invalid"
  sources=$(chronyc sources) || die "chronyc sources failed"
  grep -Eq '^\^\*' <<<"$sources" || die "chrony has no selected synchronized source"
}

assert_chrony
```

`chrony-4.3-4.oe2403sp3.x86_64` 在起始 RPM 基线中已存在，因此安装命令为本地源约束下的幂等确认。最终结果：controller Stratum 3、compute Stratum 4，二者 `Leap status: Normal`，服务均为 `active/enabled`。

## 运行时密钥文件

文档只使用 `<RABBIT_PASS>`、`<SERVICE_PASSWORD>` 和 `<DB_PASSWORD>` 等占位符，不记录、显示、哈希或提交实际值。controller 实际执行的生成命令如下；随机值只写入 root-only 文件：

```bash
test ! -e /root/.openstack-lab-secrets
umask 077
tmp=$(mktemp /root/.openstack-lab-secrets.XXXXXX)
trap 'rm -f -- "$tmp"' EXIT
{
  printf 'OPENSTACK_DEPLOY_PASSWORD='
  openssl rand -hex 32
} > "$tmp"
chown root:root "$tmp"
chmod 0600 "$tmp"
mv -f "$tmp" /root/.openstack-lab-secrets
trap - EXIT
```

随后在仓库根目录的工作站会话执行下面完整示例。它只加载已经人工复核并纳入本任务输入的两个 `known_hosts` 文件，使用 Paramiko `RejectPolicy`；登录密码通过 `getpass` 只进入进程内存。controller 文件以 64 KiB 块流经内存写入 compute 上由 `O_EXCL|O_NOFOLLOW` 建立的随机临时文件，不落工作站磁盘，不显示或哈希内容。临时文件在 `/root` 中固定为 `root:root`、`0600`，校验后同目录原子提升；`finally` 对精确临时路径做失败清理。最后只比较文件类型、非零大小、大小相等、UID/GID 与权限，不读取第二遍、更不输出内容：

```python
from getpass import getpass
from pathlib import Path
import os
import shlex
import stat
import uuid

import paramiko

CONTROLLER_HOST_KEYS = Path(".superpowers/sdd/known_hosts.controller")
COMPUTE_HOST_KEYS = Path(".superpowers/sdd/known_hosts.compute")
SECRET_PATH = "/root/.openstack-lab-secrets"
CHUNK_SIZE = 65536

CREATE_EXCLUSIVE_PROGRAM = r"""
import os
import sys

path = sys.argv[1]
flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
fd = os.open(path, flags, 0o600)
try:
    os.fchmod(fd, 0o600)
    os.fchown(fd, 0, 0)
    while True:
        chunk = sys.stdin.buffer.read(65536)
        if not chunk:
            break
        view = memoryview(chunk)
        while view:
            written = os.write(fd, view)
            view = view[written:]
    os.fsync(fd)
finally:
    os.close(fd)
"""

PROMOTE_PROGRAM = r"""
import os
import stat
import sys

temporary, target = sys.argv[1:3]
info = os.lstat(temporary)
if not stat.S_ISREG(info.st_mode):
    raise RuntimeError("temporary path is not a regular file")
if info.st_uid != 0 or info.st_gid != 0 or stat.S_IMODE(info.st_mode) != 0o600:
    raise RuntimeError("temporary metadata is unsafe")
if info.st_size <= 0:
    raise RuntimeError("temporary file is empty")
if os.path.lexists(target):
    raise FileExistsError(target)
os.replace(temporary, target)
directory = os.open(os.path.dirname(target), os.O_RDONLY | os.O_DIRECTORY)
try:
    os.fsync(directory)
finally:
    os.close(directory)
"""

CLEANUP_PROGRAM = r"""
import os
import sys

path = sys.argv[1]
try:
    os.unlink(path)
except FileNotFoundError:
    pass
"""


def connect_pinned(host, reviewed_host_keys, password):
    if not reviewed_host_keys.is_file():
        raise FileNotFoundError(reviewed_host_keys)
    client = paramiko.SSHClient()
    client.load_host_keys(str(reviewed_host_keys))
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    client.connect(
        hostname=host,
        username="root",
        password=password,
        look_for_keys=False,
        allow_agent=False,
        timeout=10,
        auth_timeout=10,
    )
    return client


def remote_command(client, program, *arguments):
    command = "python3 -c " + shlex.quote(program)
    command += " " + " ".join(shlex.quote(value) for value in arguments)
    remote_stdin, remote_stdout, remote_stderr = client.exec_command(command)
    return remote_stdin, remote_stdout, remote_stderr


def create_exclusive_temp(client, temporary):
    return remote_command(client, CREATE_EXCLUSIVE_PROGRAM, temporary)


def run_remote_python(client, program, *arguments):
    remote_stdin, remote_stdout, remote_stderr = remote_command(client, program, *arguments)
    remote_stdin.close()
    remote_stdout.read()
    remote_stderr.read()
    status = remote_stdout.channel.recv_exit_status()
    if status != 0:
        raise RuntimeError(f"remote metadata operation failed with rc={status}")


def promote_atomic(client, temporary, target):
    run_remote_python(client, PROMOTE_PROGRAM, temporary, target)


def cleanup_exact_temp(client, temporary):
    run_remote_python(client, CLEANUP_PROGRAM, temporary)


def checked_metadata(sftp, path):
    info = sftp.lstat(path)
    if not stat.S_ISREG(info.st_mode):
        raise RuntimeError("secret path is not a regular file")
    metadata = (info.st_size, info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode))
    if info.st_size <= 0 or metadata[1:] != (0, 0, 0o600):
        raise RuntimeError("secret metadata is unsafe")
    return metadata


def verify_metadata_equal(controller_sftp, compute_sftp):
    source = checked_metadata(controller_sftp, SECRET_PATH)
    target = checked_metadata(compute_sftp, SECRET_PATH)
    if source != target:
        raise RuntimeError("secret metadata differs between nodes")


def transfer_secret(controller, compute):
    temporary = SECRET_PATH + ".task5a-" + uuid.uuid4().hex
    controller_sftp = controller.open_sftp()
    compute_sftp = compute.open_sftp()
    try:
        source = controller_sftp.open(SECRET_PATH, "rb")
        remote_stdin, remote_stdout, remote_stderr = create_exclusive_temp(compute, temporary)
        try:
            while True:
                chunk = source.read(CHUNK_SIZE)
                if not chunk:
                    break
                remote_stdin.write(chunk)
            remote_stdin.flush()
            remote_stdin.close()
            remote_stdout.read()
            remote_stderr.read()
            status = remote_stdout.channel.recv_exit_status()
            if status != 0:
                raise RuntimeError(f"exclusive streaming transfer failed with rc={status}")
        finally:
            source.close()
        promote_atomic(compute, temporary, SECRET_PATH)
        verify_metadata_equal(controller_sftp, compute_sftp)
    finally:
        cleanup_exact_temp(compute, temporary)
        controller_sftp.close()
        compute_sftp.close()


password = getpass("SSH root password (memory only): ")
controller = connect_pinned("192.168.234.151", CONTROLLER_HOST_KEYS, password)
compute = connect_pinned("192.168.234.150", COMPUTE_HOST_KEYS, password)
try:
    transfer_secret(controller, compute)
finally:
    password = None
    controller.close()
    compute.close()
```

远端目标必须在执行前不存在；如果目标或临时路径已存在，程序拒绝覆盖。发生认证、主机密钥、读写、元数据或提升错误时，异常使该阶段非零退出，后续阶段不得继续。该流程没有 `AutoAddPolicy`，也不从 DNS、默认用户 known_hosts 或命令行参数静默采信密钥。

节点上只验证以下元数据条件；不得执行 `cat`、哈希或其他内容输出：

```bash
assert_secret_metadata() {
  local metadata
  metadata=$(stat -c '%a:%u:%g' /root/.openstack-lab-secrets) || \
    die "cannot stat runtime secret"
  [[ "$metadata" == 600:0:0 ]] || die "runtime secret metadata is unsafe"
  [[ -s /root/.openstack-lab-secrets ]] || die "runtime secret is empty"
}

assert_secret_metadata
```

代表性结果：

```text
controller: 600:root:root, non-empty
compute:    600:root:root, non-empty
metadata parity: PASS
```

## 收口检查

下面的阶段驱动器把本页关键不变量组成一个真实短路链。前述变更命令在同一严格 shell 中按章节执行；每完成一章立即执行对应 `stage_*`，页末再调用一次 `run_base_sequence` 做收口复验。任何函数非零返回时，`set -e` 与 ERR trap 终止会话，后续函数不会运行：

```bash
stage_starting_state() {
  local role expected_ip ens34_ipv4
  role=$(hostnamectl --static) || die "cannot read hostname"
  case "$role" in
    controller) expected_ip=192.168.234.151 ;;
    compute) expected_ip=192.168.234.150 ;;
    *) die "unexpected role hostname: $role" ;;
  esac
  ip -4 -o addr show dev ens33 | grep -q "[[:space:]]${expected_ip}/24[[:space:]]" || \
    die "ens33 address does not match $role"
  ens34_ipv4=$(ip -4 -o addr show dev ens34) || die "cannot inspect ens34"
  [[ -z "$ens34_ipv4" ]] || die "ens34 unexpectedly has an IPv4 address"
  findmnt -nro SOURCE,FSTYPE,TARGET / >/dev/null || die "root mount probe failed"
  if [[ "$role" == compute ]]; then
    assert_blank_data_disk /dev/sdb 53687091200
    assert_blank_data_disk /dev/sdc 53687091200
  fi
}

stage_identity_hosts() {
  local role peer expected_controller expected_compute
  role=$(hostnamectl --static) || die "cannot read hostname"
  [[ $(grep -Ec '^192\.168\.234\.151[[:space:]]+controller([[:space:]]|$)' /etc/hosts) -eq 1 ]] || \
    die "controller hosts mapping is not unique"
  [[ $(grep -Ec '^192\.168\.234\.150[[:space:]]+compute([[:space:]]|$)' /etc/hosts) -eq 1 ]] || \
    die "compute hosts mapping is not unique"
  expected_controller=$(getent ahostsv4 controller) || die "controller resolution failed"
  expected_compute=$(getent ahostsv4 compute) || die "compute resolution failed"
  grep -q '^192\.168\.234\.151[[:space:]]' <<<"$expected_controller" || \
    die "controller resolved to an unexpected address"
  grep -q '^192\.168\.234\.150[[:space:]]' <<<"$expected_compute" || \
    die "compute resolved to an unexpected address"
  [[ "$role" == controller ]] && peer=compute || peer=controller
  ping -c 2 -W 2 "$peer" >/dev/null || die "cross-node ping failed: $role -> $peer"
}

assert_lab_security() {
  local active_state enabled_state rc
  [[ $(getenforce) == Permissive ]] || die "SELinux is not Permissive"
  grep -qx 'SELINUX=permissive' /etc/selinux/config || die "SELinux boot mode differs"
  if active_state=$(systemctl is-active firewalld 2>&1); then
    die "firewalld is active"
  else
    rc=$?
    [[ "$rc" -eq 3 && "$active_state" == inactive ]] || die "firewalld active probe failed"
  fi
  if enabled_state=$(systemctl is-enabled firewalld 2>&1); then
    die "firewalld is enabled"
  else
    rc=$?
    [[ "$rc" -eq 1 && "$enabled_state" == disabled ]] || die "firewalld enabled probe failed"
  fi
}

stage_repository_security() {
  dnf -q repolist --disablerepo='*' --enablerepo='openstack-local' | \
    grep -q 'openstack-local' || die "isolated repository is unavailable"
  dnf -q makecache --disablerepo='*' --enablerepo='openstack-local'
  rpm -q openstack-release-antelope >/dev/null || die "Antelope release package is absent"
  grep -q 'openEuler-24.03-LTS-SP2' /etc/yum.repos.d/openstack-antelope.repo || \
    die "Antelope repository was not corrected to SP2"
  if grep -q 'openEuler-24.03-LTS-SP3' /etc/yum.repos.d/openstack-antelope.repo; then
    die "SP3 Antelope URL remains"
  fi
  assert_lab_security
}

stage_chrony() {
  assert_chrony
}

stage_secret_metadata() {
  assert_secret_metadata
}

run_base_sequence() {
  stage_starting_state
  stage_identity_hosts
  stage_repository_security
  stage_chrony
  stage_secret_metadata
}

run_base_sequence
```

```text
controller: identity/repo/security/time/secret-metadata/later-service-absence = PASS
compute:    identity/repo/security/time/secret-metadata/later-service-absence = PASS
controller RPM count after 02 infrastructure installation: 680
compute RPM count after base stage: 516
compute /dev/sdb and /dev/sdc: blank, 50 GiB each, blkid rc=2
```

只有上述基础门禁全部通过，才执行 controller 基础设施包预检和安装；不得把 MariaDB、RabbitMQ、Memcached 与本阶段并行抢跑。

## 回滚与诊断说明

- 本次实际备份目录为 `/root/openstack-lab-backups/task-5a-20260811T043901Z`，模式 0700。回滚命令未执行；如需回滚，只能逐个核对目标与备份后恢复对应文件，并重启受影响服务。
- 解析失败时依次检查 `/etc/hosts` 唯一映射、`getent ahostsv4` 和跨节点 ping，不要用临时 DNS 绕过错误。
- 本地源失败时坚持 `--disablerepo='*' --enablerepo='openstack-local'` 复现，先检查 repo 文件、FTP/文件路径和 repodata；禁止悄悄回退网络源。
- 时间异常时检查 `systemctl status chronyd`、`chronyc tracking` 和 `chronyc sources`；`Leap status` 非 Normal 时不得进入消息队列和数据库服务阶段。
- 若恢复 firewalld，必须先重新建立最小化的 FTP、数据库、消息队列和缓存服务规则；生产环境还应恢复 SELinux Enforcing 并验证策略。
