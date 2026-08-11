# Glance 手工部署与验证记录

本记录对应 controller `192.168.234.151` 上的 OpenStack 2023.1 Antelope Glance。它承接已经复审的 Keystone 状态，compute `192.168.234.150` 在本阶段仍只做只读审计。没有创建或恢复虚拟机快照，没有运行复制的 `07-controller-glance.sh`，也没有部署 Placement、Nova、Neutron、Cinder、Swift 或 Horizon。

必须保持以下依赖顺序：双节点起始状态门禁 → 仅本地源的软件包预检与安装 → Glance 数据库及三主机授权 → Keystone 用户、角色、服务和端点 → 原包配置备份与原子写入 → 数据库同步 → API 启动 → 合成镜像上传/下载/删除 → 跨切片收口审计。任一查询失败、返回未知状态或出现重复对象，都必须停止，不能把“查询失败”当成“不存在”。

## 双节点只读起始状态门禁

在任何 DNF、SQL 或 Keystone 写操作之前，从 Windows 工作站依次检查 controller 和 compute。连接只加载已经复审的节点专用 `known_hosts`，未知或变化的主机密钥由 `RejectPolicy` 拒绝；SSH 登录密码只从内存读取。

```python
from __future__ import annotations

import getpass
from pathlib import Path

import paramiko


HOSTS = {
    "controller": ("192.168.234.151", Path(".superpowers/sdd/known_hosts.controller")),
    "compute": ("192.168.234.150", Path(".superpowers/sdd/known_hosts.compute")),
}


def connect_strict(node: str, password: str) -> paramiko.SSHClient:
    host, known_hosts = HOSTS[node]
    client = paramiko.SSHClient()
    client.load_host_keys(str(known_hosts))
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    client.connect(
        host,
        username="root",
        password=password,
        look_for_keys=False,
        allow_agent=False,
        timeout=10,
        auth_timeout=10,
        banner_timeout=10,
    )
    return client


def run_checked(client: paramiko.SSHClient, script: str) -> None:
    stdin, stdout, stderr = client.exec_command("bash -s")
    stdin.write(script)
    stdin.channel.shutdown_write()
    output = stdout.read()
    error = stderr.read()
    rc = stdout.channel.recv_exit_status()
    if rc != 0:
        raise RuntimeError(f"read-only gate failed (rc={rc}): {error.decode(errors='replace')}")
    print(output.decode(), end="")


def run_dual_node_starting_gate(
    password: str,
    connector=connect_strict,
    runner=run_checked,
    controller_gate: str = "",
    compute_gate: str = "",
) -> None:
    controller = connector("controller", password)
    try:
        runner(controller, controller_gate)
    finally:
        controller.close()
    compute = connector("compute", password)
    try:
        runner(compute, compute_gate)
    finally:
        compute.close()


run_dual_node_starting_gate(
    getpass.getpass("SSH password: "),
    controller_gate=CONTROLLER_GATE,
    compute_gate=COMPUTE_GATE,
)
```

controller 门禁检查固定地址、ens34 无 IPv4、时间同步、MariaDB/RabbitMQ/Memcached/HTTPD/Keystone、受保护 token、唯一 identity 服务及三个端点、唯一 `service` 项目；同时证明 Glance 数据库、用户、服务、端点、9292 监听、配置路径、Glance 及后续软件包均不存在。compute 门禁检查固定地址、时间、本地源、后续软件包，以及两块数据盘的只读状态。

```bash
set -Eeuo pipefail
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

assert_absent_package() {
  local package=$1 output rc
  if output=$(LC_ALL=C rpm -q "$package" 2>&1); then
    die "unexpected package installed: $package"
  else
    rc=$?
    [[ $rc -eq 1 && $output == "package $package is not installed" ]] ||
      die "RPM probe failed: $package"
  fi
}

assert_compute_data_disk() {
  local device=$1 expected_size=$2 root_source root_chain facts signatures rc
  [[ -b $device ]] || die "$device is not a block device"
  [[ $(blockdev --getsize64 "$device") == "$expected_size" ]] || die "$device size drift"
  [[ $(lsblk -dnro TYPE "$device") == disk ]] || die "$device is not a whole disk"
  root_source=$(findmnt -nro SOURCE /) || die "root source probe failed"
  root_source=$(readlink -f "$root_source") || die "root source canonicalization failed"
  root_chain=$(lsblk -s -nrpo NAME "$root_source") || die "root ancestry probe failed"
  grep -Fxq "$device" <<<"$root_chain" && die "$device belongs to the root ancestry"
  [[ $(lsblk -nrpo NAME "$device" | sed '/^[[:space:]]*$/d' | wc -l) -eq 1 ]] ||
    die "$device has child devices"
  facts=$(lsblk -dnro FSTYPE,MOUNTPOINT "$device") || die "$device fact probe failed"
  [[ -z ${facts//[[:space:]]/} ]] || die "$device has a filesystem or mount"
  signatures=$(wipefs --no-act --noheadings --output TYPE "$device") || die "wipefs read-only probe failed"
  [[ -z ${signatures//[[:space:]]/} ]] || die "$device has a visible signature"
  if blkid -p "$device" >/dev/null 2>&1; then
    die "$device contains a signature"
  else
    rc=$?
    [[ $rc -eq 2 ]] || die "$device signature probe failed"
  fi
}
```

本次实际结果为 `CONTROLLER_STARTING_GATE=PASS` 和 `COMPUTE_STARTING_GATE=PASS`。controller 上 Glance 相关状态为全空；compute 的 `/dev/sdb`、`/dev/sdc` 均为 53687091200 字节整盘，无子设备、文件系统、挂载和可见签名。这里仍不声称已经完成 PV 层证明，因为 compute 尚未安装 `lvm2`；Cinder/Swift 阶段要在写盘前补齐该门禁。

## 仅使用 openstack-local 的软件包事务

先递归解析直接包和依赖，要求每一项的 `repoid` 都是 `openstack-local`。再用 `--assumeno` 获取事务表；只接受正数安装项，事务表的本地源行数必须与安装数一致，并拒绝 Remove、Erase、Obsolete、Replace 或 Downgrade。预检成功后才执行实际安装。

```bash
validate_glance_preflight() {
  local candidate_file=$1 transaction_file=$2 install_count repo_rows
  [[ -s $candidate_file && -s $transaction_file ]] || return 1
  awk -F'|' 'NF != 2 || $2 != "openstack-local" {bad=1} END {exit bad}' "$candidate_file" || return 1
  grep -Fxq 'openstack-glance|openstack-local' "$candidate_file" || return 1
  grep -Fq 'Operation aborted' "$transaction_file" || return 1
  if grep -Eiq '(^|[[:space:]])(Removing|Erasing|Obsoleting|Replacing|Downgrading)([[:space:]:]|$)' "$transaction_file"; then
    return 1
  fi
  install_count=$(sed -nE 's/^[[:space:]]*Install[[:space:]]+([0-9]+)[[:space:]]+Packages?.*/\1/p' "$transaction_file" | tail -n1)
  [[ $install_count =~ ^[1-9][0-9]*$ ]] || return 1
  repo_rows=$(grep -Ec '[[:space:]]openstack-local[[:space:]]' "$transaction_file")
  [[ $repo_rows -eq $install_count ]]
}

candidate_file=$(mktemp)
transaction_file=$(mktemp)
trap 'rm -f -- "$candidate_file" "$transaction_file"' EXIT
dnf -q repoquery --disablerepo='*' --enablerepo='openstack-local' \
  --qf '%{name}|%{repoid}' openstack-glance >"$candidate_file"
dnf -q repoquery --disablerepo='*' --enablerepo='openstack-local' \
  --requires --resolve --recursive --qf '%{name}|%{repoid}' openstack-glance >>"$candidate_file"
sort -u -o "$candidate_file" "$candidate_file"
set +e
LC_ALL=C dnf --assumeno --setopt=install_weak_deps=False \
  --disablerepo='*' --enablerepo='openstack-local' install openstack-glance >"$transaction_file" 2>&1
preflight_rc=$?
set -e
[[ $preflight_rc -eq 1 ]] || die "unexpected assumeno status"
validate_glance_preflight "$candidate_file" "$transaction_file" || die "unsafe package transaction"
LC_ALL=C dnf -y --setopt=install_weak_deps=False \
  --disablerepo='*' --enablerepo='openstack-local' install openstack-glance
rm -f -- "$candidate_file" "$transaction_file"
trap - EXIT
```

实际预检计划安装 49 个 RPM，事务表有 49 个 `openstack-local` 行，移除、降级和替换均为 0。DNF 事务 6 实际净增 49 个 RPM；根包为 `openstack-glance-26.0.0-1.oe2403sp2.noarch`。Placement 及后续根包仍缺失。严禁添加 `--allowerasing`、`--nodeps`、`--skip-broken` 或外部源回退。

## 数据库、用户、角色、服务与端点

### 运行时秘密加载器

数据库授权、Keystone 用户口令、配置写入和配置复核都调用同一个失败关闭的加载器。它要求秘密文件是 `root:root 0600`、硬链接数 1、普通非符号链接，并且只有一行非空 `OPENSTACK_DEPLOY_PASSWORD=...`。加载器必须保留到所有需要真实值的内存核验结束，然后再删除函数；不能在第二次核验前执行 `unset -f load_runtime_secret`。

```bash
load_runtime_secret() {
  local output_name=$1 path=${2:-/root/.openstack-lab-secrets} metadata secret_value readlink_rc
  local -a lines=()
  [[ -e $path && -f $path && ! -L $path ]] || return 1
  if readlink -- "$path" >/dev/null 2>&1; then
    return 1
  else
    readlink_rc=$?
    [[ $readlink_rc -eq 1 ]] || return 1
  fi
  metadata=$(stat -c '%U:%G %a %h' -- "$path") || return 1
  [[ $metadata == 'root:root 600 1' ]] || return 1
  mapfile -t lines <"$path" || return 1
  [[ ${lines[0]+present} == present && ${lines[1]+present} != present ]] || return 1
  [[ ${lines[0]} =~ ^OPENSTACK_DEPLOY_PASSWORD=(.+)$ ]] || return 1
  secret_value=${BASH_REMATCH[1]}
  printf -v "$output_name" '%s' "$secret_value"
}
```

### 创建数据库和参数化授权

`%` 必须作为数据库参数传入，不能放进 PyMySQL 的格式字符串。只查询数据库名和 `User/Host`，绝不查询或记录 `authentication_string`、口令摘要或真实口令。

```bash
load_runtime_secret OPENSTACK_DEPLOY_PASSWORD || die "runtime secret failed closed"
MYSQL_SOCKET=$(mysql -uroot --batch --skip-column-names -e 'SELECT @@socket;')
[[ -S $MYSQL_SOCKET ]] || die "MariaDB socket path unsafe"
export OPENSTACK_DEPLOY_PASSWORD MYSQL_SOCKET
python3 - <<'PY'
import os
import pymysql

password = os.environ["OPENSTACK_DEPLOY_PASSWORD"]
connection = pymysql.connect(
    unix_socket=os.environ["MYSQL_SOCKET"], user="root", charset="utf8mb4", autocommit=True
)
hosts = ("localhost", "127.0.0.1", "%")
try:
    with connection.cursor() as cursor:
        cursor.execute("CREATE DATABASE IF NOT EXISTS glance")
        for host in hosts:
            cursor.execute("CREATE USER IF NOT EXISTS %s@%s IDENTIFIED BY %s", ("glance", host, password))
            cursor.execute("ALTER USER %s@%s IDENTIFIED BY %s", ("glance", host, password))
            cursor.execute("GRANT ALL PRIVILEGES ON glance.* TO %s@%s", ("glance", host))
        cursor.execute("FLUSH PRIVILEGES")
finally:
    connection.close()

probe = pymysql.connect(
    host="127.0.0.1", user="glance", password=password, database="glance", connect_timeout=5
)
try:
    with probe.cursor() as cursor:
        cursor.execute("SELECT 1")
        if cursor.fetchone() != (1,):
            raise RuntimeError("protected Glance database probe failed")
finally:
    probe.close()
PY
unset OPENSTACK_DEPLOY_PASSWORD MYSQL_SOCKET
```

实际结果：数据库 `glance` 唯一，账号主机集合精确为 `%,127.0.0.1,localhost`，受保护的 TCP 登录通过。

### 创建或验证 Keystone 对象

每个存在性查询都先区分查询成功与失败，再区分 0、1、重复。0 条时创建；1 条时必须逐字段验证并跳过；2 条及以上或查询错误时停止。端点总数还必须恰好为 3，而不只是“三种接口都能查到”。下面的生产分类器用于所有对象。

```python
def decide_exact_state(probe_ok: bool, rows: list[dict], label: str) -> str:
    if not probe_ok:
        raise RuntimeError(f"{label} probe failed")
    if len(rows) == 0:
        return "CREATE"
    if len(rows) == 1:
        return "VALIDATE"
    raise RuntimeError(f"{label} duplicate objects: {len(rows)}")


def validate_glance_identity(evidence: dict) -> None:
    user = evidence["user"]
    service = evidence["service"]
    assignment = evidence["assignments"]
    endpoints = evidence["endpoints"]
    if not (
        user.get("name") == "glance" and user.get("domain_id") == "default"
        and user.get("enabled") is True
    ):
        raise ValueError("Glance user mismatch")
    if not (
        service.get("name") == "glance" and service.get("type") == "image"
        and service.get("enabled") is True
    ):
        raise ValueError("Glance service mismatch")
    if len(assignment) != 1:
        raise ValueError("Glance assignment cardinality mismatch")
    row = assignment[0]
    if not (
        row.get("role") == evidence["admin_role_id"]
        and row.get("user") == user.get("id")
        and row.get("project") == evidence["service_project_id"]
        and not row.get("group") and not row.get("domain") and not row.get("system")
        and row.get("inherited") is False
    ):
        raise ValueError("Glance assignment binding mismatch")
    if len(endpoints) != 3 or {row.get("interface") for row in endpoints} != {"public", "internal", "admin"}:
        raise ValueError("Glance endpoint cardinality/interface mismatch")
    if any(
        row.get("region") != "RegionOne" or row.get("service_id") != service.get("id")
        or row.get("url") != "http://controller:9292"
        for row in endpoints
    ):
        raise ValueError("Glance endpoint binding mismatch")
```

实际执行的创建命令如下；`OS_PASSWORD` 来自受保护的 `admin-openrc`，没有显示在终端记录中。

```bash
source /root/admin-openrc || die "admin-openrc failed closed"
openstack token issue -f value -c expires >/dev/null
openstack user create --domain default --password "$OS_PASSWORD" glance >/dev/null
openstack role add --project service --user glance admin
openstack service create --name glance --description 'OpenStack Image' image >/dev/null
for interface in public internal admin; do
  openstack endpoint create --region RegionOne image "$interface" http://controller:9292 >/dev/null
done
unset OS_PASSWORD
```

最终证据为：Default 域中唯一且启用的 `glance` 用户；该用户只有一条全局 `admin` 角色到 `service` 项目的精确授权；唯一且启用的 `glance:image` 服务；RegionOne 中 public、internal、admin 端点各一个，全部指向 `http://controller:9292`。

## 原包备份与 Glance 配置

配置前运行 `rpm -V openstack-glance openstack-glance-api`，结果无输出且返回 0。包默认 `/etc/glance/glance-api.conf` 先用 `cp -a` 备份到 `/root/openstack-lab-backups/task-5c-20260811T084708Z/glance-api.conf.package-default`，并用 `cmp` 和元数据再次确认。配置使用与目标文件同目录的独占、非跟随临时文件，完成 `fchmod`、`fchown`、文件 `fsync`、原子替换及目录 `fsync`；失败清理只删除 inode 与创建时相同的任务临时文件。

数据库口令在内存中用 `urllib.parse.quote(value, safe="")` 编码；服务口令只写入远端 root 受控配置。Git 中仅保存带 `<DB_PASSWORD>`、`<SERVICE_PASSWORD>` 的脱敏快照。

```python
import configparser
import os
from pathlib import Path
import stat
import uuid
from urllib.parse import quote


def write_glance_config(target: Path, password: str, glance_gid: int, ops=os) -> None:
    parser = configparser.RawConfigParser(strict=True)
    with target.open("r", encoding="utf-8") as stream:
        parser.read_file(stream)
    parser["DEFAULT"]["enabled_backends"] = "file:file"
    values = {
        "database": {
            "connection": "mysql+pymysql://glance:" + quote(password, safe="") + "@127.0.0.1/glance"
        },
        "keystone_authtoken": {
            "www_authenticate_uri": "http://controller:5000",
            "auth_url": "http://controller:5000",
            "memcached_servers": "controller:11211",
            "auth_type": "password",
            "project_domain_name": "Default",
            "user_domain_name": "Default",
            "project_name": "service",
            "username": "glance",
            "password": password,
        },
        "paste_deploy": {"flavor": "keystone"},
        "glance_store": {"default_backend": "file"},
        "file": {"filesystem_store_datadir": "/var/lib/glance/images/"},
    }
    for section, options in values.items():
        if not parser.has_section(section):
            parser.add_section(section)
        for option, value in options.items():
            parser.set(section, option, value)

    temporary = target.parent / f".glance-api.conf.task5c.{uuid.uuid4().hex}"
    flags = ops.O_WRONLY | ops.O_CREAT | ops.O_EXCL | getattr(ops, "O_NOFOLLOW", 0)
    descriptor = None
    created = False
    identity = None
    try:
        descriptor = ops.open(str(temporary), flags, 0o640)
        created = True
        metadata = ops.fstat(descriptor)
        identity = (metadata.st_dev, metadata.st_ino)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise RuntimeError("unsafe Glance config temporary")
        ops.fchmod(descriptor, 0o640)
        ops.fchown(descriptor, 0, glance_gid)
        with os.fdopen(descriptor, "w", encoding="utf-8", closefd=False) as stream:
            parser.write(stream)
            stream.flush()
        ops.fsync(descriptor)
        ops.close(descriptor)
        descriptor = None
        ops.replace(str(temporary), str(target))
        created = False
        directory = ops.open(str(target.parent), ops.O_RDONLY | getattr(ops, "O_DIRECTORY", 0))
        try:
            ops.fsync(directory)
        finally:
            ops.close(directory)
    finally:
        if descriptor is not None:
            ops.close(descriptor)
        if created and identity is not None:
            try:
                current = ops.lstat(str(temporary))
            except FileNotFoundError:
                current = None
            if (
                current is not None and (current.st_dev, current.st_ino) == identity
                and stat.S_ISREG(current.st_mode) and current.st_nlink == 1
            ):
                ops.unlink(str(temporary))
```

正确的加载器生命周期如下：第一次读取用于写入，清空变量；第二次调用同一个仍存在的函数，在内存中逐项复核真实配置；全部通过后才删除函数。这样既不把口令写入证据，也不会跳过第二次核验。

```bash
load_runtime_secret OPENSTACK_DEPLOY_PASSWORD || die "secret load before write failed"
export OPENSTACK_DEPLOY_PASSWORD
python3 /root/task-owned-write-glance-config.py
unset OPENSTACK_DEPLOY_PASSWORD

load_runtime_secret OPENSTACK_DEPLOY_PASSWORD || die "secret load before validation failed"
export OPENSTACK_DEPLOY_PASSWORD
python3 /root/task-owned-validate-glance-config.py
unset OPENSTACK_DEPLOY_PASSWORD
unset -f load_runtime_secret
```

最终配置为 `root:glance 0640`，本地多后端标识为 `file:file`，默认后端为 `file`，镜像目录为 `/var/lib/glance/images/` 且属主为 `glance:glance`。

## 数据库同步

配置核验通过后，才以系统用户 `glance` 执行同步。必需表使用集合计数验证，不能依赖数据库返回的字符串排序。

```bash
pre_tables=$(mysql -uroot --batch --skip-column-names -D glance -e \
  'SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE();')
[[ $pre_tables -eq 0 ]] || die "unexpected pre-existing Glance schema"
su -s /bin/sh -c 'glance-manage db_sync' glance
required_count=$(mysql -uroot --batch --skip-column-names -D glance -e \
  "SELECT COUNT(DISTINCT TABLE_NAME) FROM information_schema.TABLES \
   WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME IN \
   ('alembic_version','images','image_locations','image_members','image_properties','image_tags','tasks','task_info');")
[[ $required_count -eq 8 ]] || die "required Glance schema mismatch"
version_rows=$(mysql -uroot --batch --skip-column-names -D glance -e \
  'SELECT COUNT(*) FROM alembic_version;')
[[ $version_rows -ge 1 ]] || die "Alembic version missing"
```

实际同步到 `2023_1_expand01` 与 `2023_1_contract01`，共 14 张表，8 张必需表全部存在，`alembic_version` 有 1 行。

## API 启动与认证验证

只有 schema 门禁通过后才启用 API。systemd 报告启动后还要轮询版本入口；本次首次连接发生一次短暂拒绝，随后服务就绪。最终必须只有一个 9292 TCP 监听，根版本发现返回 200 或 300，并包含当前或受支持的 v2；认证 CLI 在合成测试前必须为空。

```bash
systemctl enable --now openstack-glance-api
for attempt in $(seq 1 30); do
  if systemctl is-active --quiet openstack-glance-api && \
     curl --noproxy '*' -sS -o /dev/null http://controller:9292/; then
    break
  fi
  [[ $attempt -lt 30 ]] || die "Glance API readiness timeout"
  sleep 1
done
systemctl is-enabled --quiet openstack-glance-api
listener=$(ss -H -lnt '( sport = :9292 )')
[[ $(sed '/^[[:space:]]*$/d' <<<"$listener" | wc -l) -eq 1 ]] || die "9292 listener mismatch"
source /root/admin-openrc
openstack token issue -f value -c expires >/dev/null
openstack image list -f json | python3 -c 'import json,sys; assert json.load(sys.stdin) == []'
unset OS_PASSWORD
```

实际结果：`openstack-glance-api` active/enabled，9292 监听 1 个，版本入口 HTTP 300，v2 发现通过，认证镜像列表为空。

## 合成镜像数据路径闭环

测试不依赖互联网镜像。任务在 `/root/.task5c-image.XXXXXX` 创建 0700 临时目录，用固定的非秘密字节生成 4224 字节 raw 文件。对象名固定为 `task5c-synthetic-validation-v1`，并同时写入 `task_owner=lab-task-5c`、`task_artifact=synthetic-validation-v1`。重跑时，0 条表示可创建；1 条必须验证名称、ID 和两个属性后才允许清理；重复或属性不符立即停止，绝不按模糊名称删除。

```python
def classify_task_image(rows: list[dict], name: str, owner: str, artifact: str) -> str:
    matches = [row for row in rows if row.get("name") == name]
    if len(matches) == 0:
        return "ABSENT"
    if len(matches) > 1:
        raise RuntimeError("ambiguous duplicate task images")
    row = matches[0]
    properties = row.get("properties")
    if not isinstance(properties, dict):
        raise RuntimeError("image properties are not structured")
    if properties.get("task_owner") != owner or properties.get("task_artifact") != artifact:
        raise RuntimeError("image is not exactly task-owned")
    if not row.get("id"):
        raise RuntimeError("task image ID missing")
    return row["id"]
```

```bash
image_name=task5c-synthetic-validation-v1
task_owner=lab-task-5c
task_artifact=synthetic-validation-v1
workdir=$(mktemp -d /root/.task5c-image.XXXXXX)
chmod 700 "$workdir"
payload="$workdir/payload.raw"
download="$workdir/download.raw"
python3 - "$payload" <<'PY'
from pathlib import Path
import sys
Path(sys.argv[1]).write_bytes((b"OPENSTACK_TASK5C_SYNTHETIC_RAW\n" * 128) + bytes(range(256)))
PY
chmod 600 "$payload"
expected_size=$(stat -c '%s' "$payload")
expected_sha=$(sha256sum "$payload" | awk '{print $1}')
openstack image create "$image_name" --private --disk-format raw --container-format bare \
  --property task_owner="$task_owner" --property task_artifact="$task_artifact" \
  --file "$payload" -f json >"$workdir/create.json"
image_id=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["id"])' "$workdir/create.json")
openstack image show "$image_id" -f json >"$workdir/show.json"
python3 - "$workdir/show.json" "$expected_size" <<'PY'
import json, sys
row = json.load(open(sys.argv[1]))
assert row["status"] == "active"
assert row["visibility"] == "private"
assert row["disk_format"] == "raw" and row["container_format"] == "bare"
assert row["size"] == int(sys.argv[2])
assert row["properties"]["task_owner"] == "lab-task-5c"
assert row["properties"]["task_artifact"] == "synthetic-validation-v1"
PY
openstack image save --file "$download" "$image_id"
download_sha=$(sha256sum "$download" | awk '{print $1}')
[[ $(stat -c '%s' "$download") == "$expected_size" && $download_sha == "$expected_sha" ]]
cmp -s -- "$payload" "$download"
openstack image delete "$image_id"
openstack image list --private -f json | python3 -c \
  'import json,sys; assert all(r.get("Name") != "task5c-synthetic-validation-v1" for r in json.load(sys.stdin))'
rm -f -- "$payload" "$download" "$workdir/create.json" "$workdir/show.json"
rmdir -- "$workdir"
unset OS_PASSWORD
```

实际结果：镜像状态 active，格式 raw/bare、可见性 private、大小 4224 字节；上传源与下载文件的非秘密 SHA-256 和大小一致，`cmp` 通过。随后按精确 ID 删除，镜像列表、临时文件和 Glance 后端测试文件均为 0。

## 依赖顺序驱动器与跨切片收口

教材中的最终驱动器只表达已经逐步验证的顺序；它不替代每一步内部的失败关闭门禁。

```bash
stage_starting_state() { controller_and_compute_starting_gate; }
stage_package_transaction() { glance_repo_only_preflight_and_install; }
stage_database_and_grants() { create_and_validate_glance_database; }
stage_identity_objects() { create_and_validate_glance_identity; }
stage_configuration() { backup_and_configure_glance; }
stage_schema() { sync_and_validate_glance_schema; }
stage_api() { start_and_validate_glance_api; }
stage_image_lifecycle() { validate_synthetic_image_lifecycle; }
stage_cross_slice_audit() { validate_controller_then_compute; }

assert_packages_absent openstack-placement-api openstack-nova-common \
  openstack-neutron-common openstack-cinder-common openstack-swift-common python3-horizon

run_glance_sequence() {
  stage_starting_state
  stage_package_transaction
  stage_database_and_grants
  stage_identity_objects
  stage_configuration
  stage_schema
  stage_api
  stage_image_lifecycle
  stage_cross_slice_audit
}

run_glance_sequence
```

最终 controller 审计结果为 PASS：chronyd、MariaDB、RabbitMQ、Memcached、HTTPD、Glance API 均 active/enabled；Keystone token 正常；identity 与 image 服务各唯一且端点各 3 个；`service` 项目、`glance` 用户及其唯一角色绑定精确；Glance 数据库、配置、schema、9292、认证 CLI 正常；镜像和任务临时文件为 0；Placement 及后续软件包仍缺失。

最终 compute 审计结果为 PASS：地址、ens34、时间和 `openstack-local` 未漂移；Glance 及后续软件包均未安装；`/dev/sdb`、`/dev/sdc` 仍为 50 GiB 整盘，无子设备、文件系统、挂载或当前可见签名。整个 Glance 切片没有对数据盘、网络接口、LVM、分区或文件系统执行写操作。

## 中止、诊断、回退与教学安全说明

- 配置原子写入后，首次脚本误在第二次内存核验前删除了加载器函数，因 `command not found` 严格中止。只读恢复审计证明唯一原包备份存在、配置已精确完成、schema 为 0、API inactive/disabled、9292 无监听；因此没有覆盖配置，而是从 schema 继续。教材给出的上述生命周期已经修正，并由回归测试证明第二次核验发生在 `unset -f` 之前。
- `glance-manage db_sync` 成功后，首次验证器错误依赖 MySQL 返回表名的排序字符串而中止。只读审计证明 14 张表、8 张必需表和 1 行 Alembic 版本均存在，API 尚未启动。教材改用 `COUNT(DISTINCT TABLE_NAME)`，不再依赖排序，也没有为掩盖问题重跑同步。
- 包事务若出现外部 repo 或移除、降级、替换，停止并修复离线依赖闭包，不得使用依赖绕过选项。
- 数据库或 Keystone 阶段若中断，先只读盘点数据库、授权主机、用户、角色绑定、服务和端点。只有 0 条或逐字段证明的 1 条可以继续；PARTIAL、重复或查询失败不得自动删除或补齐。
- API 故障先检查 `systemctl status openstack-glance-api`、`journalctl -u openstack-glance-api` 和 `/var/log/glance/api.log`。不要在配置或 schema 状态不明时反复重启。
- 合成镜像清理只接受精确 ID、固定名称和两个任务属性共同证明的对象。不得按名称通配、不得删除无任务属性或用户创建的镜像。
- 回退配置时使用 `/root/openstack-lab-backups/task-5c-20260811T084708Z/glance-api.conf.package-default`，先停止 Glance API，再确认不会覆盖后续切片的新配置；数据库和 Keystone 对象应先审计关系后再决定是否回退，不能直接删库掩盖失败原因。
- 当前是隔离教学实验环境：SELinux Permissive、firewalld 关闭、服务端点为 HTTP、本地源 `gpgcheck=0`。生产环境必须恢复 Enforcing、最小端口开放、TLS、独立服务口令、签名软件源、集中秘密管理以及镜像签名/扫描/审计。
