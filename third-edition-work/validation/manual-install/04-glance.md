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

CONTROLLER_GATE = r'''
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
[[ $(hostnamectl --static) == controller ]] || die "controller hostname drift"
ip -4 -o addr show dev ens33 | grep -Fq '192.168.234.151/24' || die "controller ens33 drift"
ens34_output=$(ip -4 -o addr show dev ens34) || die "controller ens34 probe failed"
[[ -z $ens34_output ]] || die "controller ens34 has IPv4"
[[ $(timedatectl show -p NTPSynchronized --value) == yes ]] || die "controller clock not synchronized"
for service in chronyd mariadb rabbitmq-server memcached httpd; do
  systemctl is-active --quiet "$service" || die "$service inactive"
  systemctl is-enabled --quiet "$service" || die "$service disabled"
done
[[ $(mysql -uroot --batch --skip-column-names -e 'SELECT 1;') == 1 ]] || die "MariaDB access failed"
repo=$(dnf -q repolist --disablerepo='*' --enablerepo='openstack-local') || die "local repo probe failed"
grep -Fq openstack-local <<<"$repo" || die "openstack-local missing"
[[ -f /root/.openstack-lab-secrets && ! -L /root/.openstack-lab-secrets ]] || die "runtime secret unsafe"
[[ $(stat -c '%U:%G %a %h' /root/.openstack-lab-secrets) == 'root:root 600 1' ]] || die "runtime secret metadata drift"
[[ $(awk 'END {print NR}' /root/.openstack-lab-secrets) -eq 1 ]] || die "runtime secret line count drift"
grep -Eq '^OPENSTACK_DEPLOY_PASSWORD=.+$' /root/.openstack-lab-secrets || die "runtime secret shape drift"
[[ -f /root/admin-openrc && ! -L /root/admin-openrc ]] || die "admin-openrc unsafe"
[[ $(stat -c '%U:%G %a %h' /root/admin-openrc) == 'root:root 600 1' ]] || die "admin-openrc metadata drift"
for package in openstack-glance openstack-placement-api openstack-nova-common \
  openstack-neutron-common openstack-cinder-common openstack-swift-common python3-horizon; do
  assert_absent_package "$package"
done
[[ $(mysql -uroot --batch --skip-column-names -e \
  "SELECT COUNT(*) FROM information_schema.SCHEMATA WHERE SCHEMA_NAME='glance';") == 0 ]] ||
  die "Glance database already exists"
glance_hosts=$(mysql -uroot --batch --skip-column-names -e \
  "SELECT Host FROM mysql.user WHERE User='glance';") || die "Glance DB-user probe failed"
[[ -z $glance_hosts ]] || die "Glance DB users already exist"
for path in /etc/glance/glance-api.conf /var/lib/glance/images /root/.glance-task5c-complete; do
  [[ ! -e $path && ! -L $path ]] || die "unexpected Glance path: $path"
done
listener=$(ss -H -lnt '( sport = :9292 )') || die "9292 probe failed"
[[ -z $listener ]] || die "9292 already listens"
source /root/admin-openrc || die "admin-openrc failed closed"
openstack token issue -f value -c expires >/dev/null || die "protected token issuance failed"
tmpdir=$(mktemp -d /root/.task5c-start-gate.XXXXXX)
trap 'rm -f -- "$tmpdir/projects.json" "$tmpdir/users.json" "$tmpdir/services.json" "$tmpdir/endpoints.json"; rmdir -- "$tmpdir" 2>/dev/null || :; unset OS_PASSWORD' EXIT
openstack project list --domain default -f json >"$tmpdir/projects.json" || die "project probe failed"
openstack user list --domain default -f json >"$tmpdir/users.json" || die "user probe failed"
openstack service list -f json >"$tmpdir/services.json" || die "service probe failed"
openstack endpoint list -f json >"$tmpdir/endpoints.json" || die "endpoint probe failed"
python3 - "$tmpdir" <<'PY'
import json, pathlib, sys
root = pathlib.Path(sys.argv[1])
projects = json.loads((root / "projects.json").read_text())
users = json.loads((root / "users.json").read_text())
services = json.loads((root / "services.json").read_text())
endpoints = json.loads((root / "endpoints.json").read_text())
service_projects = [row for row in projects if row.get("Name") == "service"]
if len(service_projects) != 1:
    raise SystemExit("service project cardinality mismatch")
if [row for row in users if row.get("Name") == "glance"]:
    raise SystemExit("Glance user already exists")
identity = [row for row in services if row.get("Type") == "identity"]
if len(identity) != 1 or identity[0].get("Name") != "keystone":
    raise SystemExit("identity service mismatch")
if [row for row in services if row.get("Type") == "image" or row.get("Name") == "glance"]:
    raise SystemExit("Glance service already exists")
identity_endpoints = [row for row in endpoints if row.get("Service Type") == "identity"]
if len(identity_endpoints) != 3 or {row.get("Interface") for row in identity_endpoints} != {"public", "internal", "admin"}:
    raise SystemExit("identity endpoint cardinality/interface mismatch")
if any(row.get("Region") != "RegionOne" or row.get("URL") != "http://controller:5000/v3/" for row in identity_endpoints):
    raise SystemExit("identity endpoint binding mismatch")
if [row for row in endpoints if row.get("Service Type") == "image" or row.get("URL") == "http://controller:9292"]:
    raise SystemExit("Glance endpoint already exists")
PY
rm -f -- "$tmpdir/projects.json" "$tmpdir/users.json" "$tmpdir/services.json" "$tmpdir/endpoints.json"
rmdir -- "$tmpdir"
trap - EXIT
unset OS_PASSWORD
printf '%s\n' CONTROLLER_STARTING_GATE=PASS
'''

COMPUTE_GATE = r'''
set -Eeuo pipefail
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
assert_absent_package() {
  local package=$1 output rc
  if output=$(LC_ALL=C rpm -q "$package" 2>&1); then
    die "unexpected package installed: $package"
  else
    rc=$?
    [[ $rc -eq 1 && $output == "package $package is not installed" ]] || die "RPM probe failed: $package"
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
  grep -Fxq "$device" <<<"$root_chain" && die "$device is a root ancestor"
  [[ $(lsblk -nrpo NAME "$device" | sed '/^[[:space:]]*$/d' | wc -l) -eq 1 ]] || die "$device has children"
  facts=$(lsblk -dnro FSTYPE,MOUNTPOINT "$device") || die "$device fact probe failed"
  [[ -z ${facts//[[:space:]]/} ]] || die "$device has filesystem or mount"
  signatures=$(wipefs --no-act --noheadings --output TYPE "$device") || die "$device wipefs probe failed"
  [[ -z ${signatures//[[:space:]]/} ]] || die "$device has a wipefs signature"
  if blkid -p "$device" >/dev/null 2>&1; then
    die "$device has a signature"
  else
    rc=$?
    [[ $rc -eq 2 ]] || die "$device blkid probe failed"
  fi
}
[[ $(hostnamectl --static) == compute ]] || die "compute hostname drift"
ip -4 -o addr show dev ens33 | grep -Fq '192.168.234.150/24' || die "compute ens33 drift"
ens34_output=$(ip -4 -o addr show dev ens34) || die "compute ens34 probe failed"
[[ -z $ens34_output ]] || die "compute ens34 has IPv4"
[[ $(timedatectl show -p NTPSynchronized --value) == yes ]] || die "compute clock not synchronized"
systemctl is-active --quiet chronyd || die "chronyd inactive"
systemctl is-enabled --quiet chronyd || die "chronyd disabled"
repo=$(dnf -q repolist --disablerepo='*' --enablerepo='openstack-local') || die "local repo probe failed"
grep -Fq openstack-local <<<"$repo" || die "openstack-local missing"
for package in openstack-glance openstack-placement-api openstack-nova-common \
  openstack-neutron-common openstack-cinder-common openstack-swift-common python3-horizon; do
  assert_absent_package "$package"
done
assert_compute_data_disk /dev/sdb 53687091200
assert_compute_data_disk /dev/sdc 53687091200
printf '%s\n' COMPUTE_STARTING_GATE=PASS
'''


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
    controller_gate: str = CONTROLLER_GATE,
    compute_gate: str = COMPUTE_GATE,
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


def run_after_both_gates(password: str, mutation, **gate_options) -> None:
    run_dual_node_starting_gate(password, **gate_options)
    mutation()


if __name__ == "__main__":
    run_dual_node_starting_gate(getpass.getpass("SSH password: "))
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

`%` 必须作为数据库参数传入，不能放进 PyMySQL 的格式字符串。验证过程查询数据库名、`User/Host` 及不含凭据的授权元数据，但绝不查询或记录 `authentication_string`、password hash、认证字符串、真实口令或其他凭据内容。

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

授权创建后立即运行结构化证明。它读取 `information_schema.USER_PRIVILEGES`、`SCHEMA_PRIVILEGES`、`TABLE_PRIVILEGES`、`COLUMN_PRIVILEGES`，并读取 `mysql.user` 的 `User/Host`、`mysql.procs_priv`、`mysql.proxies_priv`、`mysql.roles_mapping` 中不含凭据的授权元数据。它明确不读取 `mysql.user.authentication_string` 或任何口令摘要，也不执行可能返回摘要的 `SHOW GRANTS`。验证器要求全部探针成功、Host 集合精确、全局层只有无权的 `USAGE`、数据库层是当前 MariaDB 版本 `ALL PRIVILEGES` 展开的精确集合且全部只属于 `glance`，并且没有额外表级、列级、例程、代理或数据库角色授权。

```python
from __future__ import annotations

import pymysql


EXPECTED_GRANT_HOSTS = {"%", "127.0.0.1", "localhost"}
EXPECTED_SCHEMA_PRIVILEGES = {
    "ALTER", "ALTER ROUTINE", "CREATE", "CREATE ROUTINE", "CREATE TEMPORARY TABLES",
    "CREATE VIEW", "DELETE", "DELETE HISTORY", "DROP", "EVENT", "EXECUTE", "INDEX",
    "INSERT", "LOCK TABLES", "REFERENCES", "SELECT", "SHOW VIEW", "TRIGGER", "UPDATE",
}


def validate_glance_grant_evidence(evidence: dict) -> None:
    if evidence.get("probe_ok") is not True:
        raise RuntimeError("Glance grant evidence probe failed")
    hosts = evidence.get("hosts")
    accounts = evidence.get("accounts")
    if not isinstance(hosts, list) or set(hosts) != EXPECTED_GRANT_HOSTS or len(hosts) != 3:
        raise ValueError("Glance database Host set mismatch")
    if not isinstance(accounts, dict) or set(accounts) != EXPECTED_GRANT_HOSTS:
        raise ValueError("Glance grant-account evidence mismatch")
    if evidence.get("proxy") != [] or evidence.get("roles") != []:
        raise ValueError("unexpected proxy or database-role grant for Glance")
    for host in EXPECTED_GRANT_HOSTS:
        account = accounts[host]
        global_rows = account.get("global")
        schema_rows = account.get("schema")
        if global_rows != [{"privilege": "USAGE", "grantable": "NO"}]:
            raise ValueError(f"unexpected global privilege for glance@{host}")
        if not isinstance(schema_rows, list) or not schema_rows:
            raise ValueError(f"Glance schema privileges missing for {host}")
        if any(row.get("schema") != "glance" or row.get("grantable") != "NO" for row in schema_rows):
            raise ValueError(f"unexpected schema scope/grant option for glance@{host}")
        privileges = {row.get("privilege") for row in schema_rows}
        if privileges != EXPECTED_SCHEMA_PRIVILEGES or len(schema_rows) != len(EXPECTED_SCHEMA_PRIVILEGES):
            raise ValueError(f"Glance schema privilege set mismatch for {host}")
        if account.get("table") != [] or account.get("column") != [] or account.get("routine") != []:
            raise ValueError(f"unexpected table/column/routine grant for glance@{host}")


def collect_glance_grant_evidence(connection) -> dict:
    evidence = {"probe_ok": False, "hosts": [], "accounts": {}, "proxy": [], "roles": []}
    with connection.cursor() as cursor:
        cursor.execute("SELECT Host FROM mysql.user WHERE User=%s ORDER BY Host", ("glance",))
        evidence["hosts"] = [row[0] for row in cursor.fetchall()]
        for host in evidence["hosts"]:
            grantee = f"'glance'@'{host}'"
            cursor.execute(
                "SELECT PRIVILEGE_TYPE,IS_GRANTABLE FROM information_schema.USER_PRIVILEGES "
                "WHERE GRANTEE=%s ORDER BY PRIVILEGE_TYPE", (grantee,),
            )
            global_rows = [
                {"privilege": privilege, "grantable": grantable}
                for privilege, grantable in cursor.fetchall()
            ]
            cursor.execute(
                "SELECT TABLE_SCHEMA,PRIVILEGE_TYPE,IS_GRANTABLE FROM information_schema.SCHEMA_PRIVILEGES "
                "WHERE GRANTEE=%s ORDER BY TABLE_SCHEMA,PRIVILEGE_TYPE", (grantee,),
            )
            schema_rows = [
                {"schema": schema, "privilege": privilege, "grantable": grantable}
                for schema, privilege, grantable in cursor.fetchall()
            ]
            cursor.execute(
                "SELECT TABLE_SCHEMA,TABLE_NAME,PRIVILEGE_TYPE,IS_GRANTABLE "
                "FROM information_schema.TABLE_PRIVILEGES WHERE GRANTEE=%s", (grantee,),
            )
            table_rows = [
                {"schema": schema, "table": table, "privilege": privilege, "grantable": grantable}
                for schema, table, privilege, grantable in cursor.fetchall()
            ]
            cursor.execute(
                "SELECT TABLE_SCHEMA,TABLE_NAME,COLUMN_NAME,PRIVILEGE_TYPE,IS_GRANTABLE "
                "FROM information_schema.COLUMN_PRIVILEGES WHERE GRANTEE=%s", (grantee,),
            )
            column_rows = [
                {
                    "schema": schema, "table": table, "column": column,
                    "privilege": privilege, "grantable": grantable,
                }
                for schema, table, column, privilege, grantable in cursor.fetchall()
            ]
            cursor.execute(
                "SELECT Db,Routine_name,Routine_type,Proc_priv FROM mysql.procs_priv "
                "WHERE User=%s AND Host=%s", ("glance", host),
            )
            routine_rows = [
                {"schema": schema, "routine": routine, "type": routine_type, "privilege": privilege}
                for schema, routine, routine_type, privilege in cursor.fetchall()
            ]
            evidence["accounts"][host] = {
                "global": global_rows, "schema": schema_rows,
                "table": table_rows, "column": column_rows, "routine": routine_rows,
            }
        cursor.execute(
            "SELECT Host,User,Proxied_host,Proxied_user,With_grant FROM mysql.proxies_priv "
            "WHERE User=%s OR Proxied_user=%s", ("glance", "glance"),
        )
        evidence["proxy"] = list(cursor.fetchall())
        cursor.execute(
            "SELECT Host,User,Role,Admin_option FROM mysql.roles_mapping WHERE User=%s", ("glance",),
        )
        evidence["roles"] = list(cursor.fetchall())
    evidence["probe_ok"] = True
    return evidence


if __name__ == "__main__":
    connection = pymysql.connect(unix_socket="/var/lib/mysql/mysql.sock", user="root")
    try:
        validate_glance_grant_evidence(collect_glance_grant_evidence(connection))
    finally:
        connection.close()
    print("GRANT_EVIDENCE=PASS HOSTS=%,127.0.0.1,localhost GLOBAL=USAGE SCHEMA=glance TABLE=0 COLUMN=0 ROUTINE=0 PROXY=0 DBROLE=0")
```

实际结果：数据库 `glance` 唯一，账号主机集合精确为 `%,127.0.0.1,localhost`；三个账号的全局权限都只有 `USAGE`，schema 权限都只属于 `glance`，表级/列级授权均为 0；受保护的 TCP 登录通过。

### 创建或验证 Keystone 对象

每个存在性查询都先区分查询成功与失败，再区分 0、1、重复。0 条时创建并立即重新查询；1 条时逐字段验证并跳过；2 条及以上或查询错误时停止。用户的 list/show ID、Default 域和 enabled 在进入角色授权前验证；角色授权在进入服务创建前验证；服务的 list/show ID、名称、类型和 enabled 在查询端点前验证。已有端点必须一次形成精确三接口集合；从 0 创建时则按 public、internal、admin 逐个执行，每创建一个就重新查询并验证当前接口集合、RegionOne、URL、enabled 和已验证的 service ID，任何 partial/wrong 状态都会在创建后续接口前停止。

```bash
source /root/admin-openrc || die "admin-openrc failed closed"
openstack token issue -f value -c expires >/dev/null || die "protected token issuance failed"
python3 - <<'PY'
from __future__ import annotations

import json
import os
import subprocess


def _value(row: dict, *keys: str):
    for key in keys:
        if key in row:
            return row[key]
    return None


def _exact_rows(rows: list[dict], predicate, label: str) -> list[dict]:
    matches = [row for row in rows if predicate(row)]
    if len(matches) > 1:
        raise RuntimeError(f"{label} duplicate objects: {len(matches)}")
    return matches


def subprocess_query(args: list[str]) -> object:
    completed = subprocess.run(
        ["openstack", *args, "-f", "json"], text=True, capture_output=True, check=False
    )
    if completed.returncode != 0:
        raise RuntimeError(f"OpenStack query failed: {' '.join(args)}")
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"OpenStack query returned invalid JSON: {' '.join(args)}") from error


def subprocess_mutate(args: list[str]) -> None:
    completed = subprocess.run(
        ["openstack", *args], text=True, stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE, check=False,
    )
    if completed.returncode != 0:
        redacted = list(args)
        if "--password" in redacted:
            redacted[redacted.index("--password") + 1] = "<REDACTED>"
        raise RuntimeError(f"OpenStack mutation failed: {' '.join(redacted)}")


def validate_glance_identity_evidence(evidence: dict) -> None:
    user = evidence["user"]
    service = evidence["service"]
    assignments = evidence["assignments"]
    endpoints = evidence["endpoints"]
    if not (
        user.get("id") and user.get("name") == "glance"
        and user.get("domain_id") == "default" and user.get("enabled") is True
    ):
        raise ValueError("Glance user mismatch")
    if not (
        service.get("id") and service.get("name") == "glance"
        and service.get("type") == "image" and service.get("enabled") is True
    ):
        raise ValueError("Glance service mismatch")
    if len(assignments) != 1:
        raise ValueError("Glance assignment cardinality mismatch")
    row = assignments[0]
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
        or row.get("url") != "http://controller:9292" or row.get("enabled") is not True
        for row in endpoints
    ):
        raise ValueError("Glance endpoint binding mismatch")


def validate_glance_user_stage(user_rows: list[dict], user_show: dict) -> dict:
    if len(user_rows) != 1:
        raise ValueError("Glance user stage cardinality mismatch")
    list_id = _value(user_rows[0], "ID", "id")
    show_id = _value(user_show, "id", "ID")
    user = {
        "id": str(show_id or ""), "name": _value(user_show, "name", "Name"),
        "domain_id": _value(user_show, "domain_id", "Domain"),
        "enabled": _value(user_show, "enabled", "Enabled"),
    }
    if not list_id or str(list_id) != user["id"]:
        raise ValueError("Glance user list/show ID mismatch")
    if not (
        user["name"] == "glance" and user["domain_id"] == "default"
        and user["enabled"] is True
    ):
        raise ValueError("Glance user stage exact-state mismatch")
    return user


def validate_glance_assignment_stage(
    rows: list[dict], user_id: str, project_id: str, role_id: str
) -> list[dict]:
    assignments = [{
        "role": str(_value(row, "Role", "role") or ""),
        "user": str(_value(row, "User", "user") or ""),
        "project": str(_value(row, "Project", "project") or ""),
        "group": _value(row, "Group", "group"), "domain": _value(row, "Domain", "domain"),
        "system": _value(row, "System", "system"),
        "inherited": _value(row, "Inherited", "inherited"),
    } for row in rows]
    if len(assignments) != 1:
        raise ValueError("Glance assignment stage cardinality mismatch")
    row = assignments[0]
    if not (
        row["role"] == role_id and row["user"] == user_id and row["project"] == project_id
        and row["group"] in (None, "") and row["domain"] in (None, "")
        and row["system"] in (None, "") and row["inherited"] is False
    ):
        raise ValueError("Glance assignment stage binding mismatch")
    return assignments


def validate_glance_service_stage(service_rows: list[dict], service_show: dict) -> dict:
    if len(service_rows) != 1:
        raise ValueError("Glance service stage cardinality mismatch")
    list_id = _value(service_rows[0], "ID", "id")
    show_id = _value(service_show, "id", "ID")
    service = {
        "id": str(show_id or ""), "name": _value(service_show, "name", "Name"),
        "type": _value(service_show, "type", "Type"),
        "enabled": _value(service_show, "enabled", "Enabled"),
    }
    if not list_id or str(list_id) != service["id"]:
        raise ValueError("Glance service list/show ID mismatch")
    if not (
        service["name"] == "glance" and service["type"] == "image"
        and service["enabled"] is True
    ):
        raise ValueError("Glance service stage exact-state mismatch")
    return service


def validate_glance_endpoint_stage(
    endpoint_rows: list[dict], service_id: str, expected_interfaces: set[str], query
) -> list[dict]:
    if len(endpoint_rows) != len(expected_interfaces):
        raise ValueError("Glance endpoint stage cardinality mismatch")
    endpoints = []
    for row in endpoint_rows:
        list_id = _value(row, "ID", "id")
        if not list_id:
            raise ValueError("Glance endpoint list ID missing")
        endpoint_show = query(["endpoint", "show", str(list_id)])
        show_id = _value(endpoint_show, "id", "ID")
        endpoint = {
            "id": str(show_id or ""),
            "interface": _value(endpoint_show, "interface", "Interface"),
            "region": _value(endpoint_show, "region", "Region"),
            "service_id": str(_value(endpoint_show, "service_id", "Service ID") or ""),
            "url": _value(endpoint_show, "url", "URL"),
            "enabled": _value(endpoint_show, "enabled", "Enabled"),
        }
        if str(list_id) != endpoint["id"]:
            raise ValueError("Glance endpoint list/show ID mismatch")
        if not (
            endpoint["interface"] in expected_interfaces and endpoint["region"] == "RegionOne"
            and endpoint["service_id"] == service_id and endpoint["url"] == "http://controller:9292"
            and endpoint["enabled"] is True
        ):
            raise ValueError("Glance endpoint stage exact-state mismatch")
        endpoints.append(endpoint)
    if {endpoint["interface"] for endpoint in endpoints} != expected_interfaces:
        raise ValueError("Glance endpoint stage interface-set mismatch")
    return endpoints


def ensure_glance_identity_objects(password: str, query=subprocess_query, mutate=subprocess_mutate) -> dict:
    projects = query(["project", "list", "--domain", "default"])
    project_rows = _exact_rows(projects, lambda row: _value(row, "Name", "name") == "service", "service project")
    if len(project_rows) != 1:
        raise RuntimeError("service project must already exist exactly once")
    service_project_id = _value(project_rows[0], "ID", "id")
    if not service_project_id:
        raise RuntimeError("service project ID missing")
    project_show = query(["project", "show", str(service_project_id)])
    if not (
        _value(project_show, "id", "ID") == service_project_id
        and _value(project_show, "name", "Name") == "service"
        and _value(project_show, "domain_id", "Domain") == "default"
        and _value(project_show, "enabled", "Enabled") is True
        and _value(project_show, "is_domain", "Is Domain") is False
    ):
        raise RuntimeError("service project exact-state mismatch")

    roles = query(["role", "list"])
    role_rows = _exact_rows(roles, lambda row: _value(row, "Name", "name") == "admin", "global admin role")
    if len(role_rows) != 1:
        raise RuntimeError("global admin role must exist exactly once")
    admin_role_id = _value(role_rows[0], "ID", "id")
    role_show = query(["role", "show", str(admin_role_id)])
    if not (
        admin_role_id and str(_value(role_show, "id", "ID") or "") == str(admin_role_id)
        and _value(role_show, "name", "Name") == "admin"
        and _value(role_show, "domain_id", "Domain") in (None, "")
    ):
        raise RuntimeError("admin role is not global")
    admin_role_id = str(admin_role_id)
    service_project_id = str(service_project_id)

    users = query(["user", "list", "--domain", "default"])
    user_rows = _exact_rows(users, lambda row: _value(row, "Name", "name") == "glance", "Glance user")
    if not user_rows:
        mutate(["user", "create", "--domain", "default", "--password", password, "glance"])
        users = query(["user", "list", "--domain", "default"])
        user_rows = _exact_rows(users, lambda row: _value(row, "Name", "name") == "glance", "Glance user after create")
    if len(user_rows) != 1:
        raise RuntimeError("Glance user final cardinality mismatch")
    glance_user_id = str(_value(user_rows[0], "ID", "id") or "")
    user_show = query(["user", "show", glance_user_id])
    user = validate_glance_user_stage(user_rows, user_show)
    glance_user_id = user["id"]

    raw_assignments = query(["role", "assignment", "list", "--user", glance_user_id])
    if len(raw_assignments) == 0:
        mutate(["role", "add", "--project", service_project_id, "--user", glance_user_id, admin_role_id])
        raw_assignments = query(["role", "assignment", "list", "--user", glance_user_id])
    assignments = validate_glance_assignment_stage(
        raw_assignments, glance_user_id, service_project_id, admin_role_id
    )

    services = query(["service", "list"])
    service_rows = _exact_rows(
        services,
        lambda row: _value(row, "Name", "name") == "glance" or _value(row, "Type", "type") == "image",
        "Glance image service",
    )
    if not service_rows:
        mutate(["service", "create", "--name", "glance", "--description", "OpenStack Image", "image"])
        services = query(["service", "list"])
        service_rows = _exact_rows(
            services,
            lambda row: _value(row, "Name", "name") == "glance" or _value(row, "Type", "type") == "image",
            "Glance image service after create",
        )
    if len(service_rows) != 1:
        raise RuntimeError("Glance image service final cardinality mismatch")
    image_service_id = str(_value(service_rows[0], "ID", "id") or "")
    service_show = query(["service", "show", image_service_id])
    service = validate_glance_service_stage(service_rows, service_show)
    image_service_id = service["id"]

    endpoint_rows = query(["endpoint", "list", "--service", image_service_id])
    if endpoint_rows:
        endpoints = validate_glance_endpoint_stage(
            endpoint_rows, image_service_id, {"public", "internal", "admin"}, query
        )
    else:
        endpoints = []
        created_interfaces: set[str] = set()
        for interface in ("public", "internal", "admin"):
            mutate([
                "endpoint", "create", "--region", "RegionOne", image_service_id,
                interface, "http://controller:9292",
            ])
            created_interfaces.add(interface)
            endpoint_rows = query(["endpoint", "list", "--service", image_service_id])
            endpoints = validate_glance_endpoint_stage(
                endpoint_rows, image_service_id, set(created_interfaces), query
            )

    evidence = {
        "user": user, "service": service, "assignments": assignments, "endpoints": endpoints,
        "admin_role_id": admin_role_id, "service_project_id": service_project_id,
    }
    validate_glance_identity_evidence(evidence)
    return evidence


if __name__ == "__main__":
    ensure_glance_identity_objects(os.environ["OS_PASSWORD"])
    print("IDENTITY_OBJECTS=PASS USER=glance ROLE=admin PROJECT=service SERVICE=glance:image ENDPOINTS=3")
PY
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
version_file=$(mktemp /root/.task5c-version.XXXXXX)
trap 'rm -f -- "$version_file"; unset OS_PASSWORD' EXIT
http_code=$(curl --noproxy '*' -sS -o "$version_file" -w '%{http_code}' http://controller:9292/) ||
  die "Glance version request failed"
python3 - "$http_code" "$version_file" <<'PY'
import json
import sys


def validate_glance_version_response(http_code: int, payload: dict) -> None:
    if http_code not in (200, 300):
        raise RuntimeError(f"Glance version endpoint returned HTTP {http_code}")
    versions = payload.get("versions")
    if not isinstance(versions, list):
        raise ValueError("Glance version response has no versions list")
    if not any(
        str(row.get("id", "")).lower().startswith("v2")
        and str(row.get("status", "")).upper() in {"CURRENT", "SUPPORTED"}
        for row in versions if isinstance(row, dict)
    ):
        raise ValueError("Glance v2 discovery missing")


if __name__ == "__main__":
    with open(sys.argv[2], encoding="utf-8") as stream:
        validate_glance_version_response(int(sys.argv[1]), json.load(stream))
PY
source /root/admin-openrc
openstack token issue -f value -c expires >/dev/null
openstack image list -f json | python3 -c 'import json,sys; assert json.load(sys.stdin) == []'
unset OS_PASSWORD
rm -f -- "$version_file"
trap - EXIT
```

实际结果：`openstack-glance-api` active/enabled，9292 监听 1 个，版本入口 HTTP 300，v2 发现通过，认证镜像列表为空。

## 合成镜像数据路径闭环

测试不依赖互联网镜像。任务在 `/root/.task5c-image.XXXXXX` 创建 0700 临时目录，用固定的非秘密字节生成 4224 字节 raw 文件。对象名固定为 `task5c-synthetic-validation-v1`，并同时写入 `task_owner=lab-task-5c`、`task_artifact=synthetic-validation-v1`。重跑时，0 条表示可创建；已有 1 条且两个属性正确时也停止并要求人工审计，本次运行不删除它；同名外来对象、属性不符或重复对象同样立即停止。只有本次 create 返回并登记的精确 ID，且删除前再次通过名称、ID 和两个属性核验，才可能由 `finally` 或成功路径删除，绝不按模糊名称清理。

```bash
source /root/admin-openrc || die "admin-openrc failed closed before image lifecycle"
openstack token issue -f value -c expires >/dev/null || die "protected token issuance failed"
trap 'unset OS_PASSWORD' EXIT ERR
python3 - <<'PY'
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile


IMAGE_NAME = "task5c-synthetic-validation-v1"
TASK_OWNER = "lab-task-5c"
TASK_ARTIFACT = "synthetic-validation-v1"


def _field(row: dict, *keys: str):
    for key in keys:
        if key in row:
            return row[key]
    return None


def subprocess_executor(args: list[str], expect_json: bool = False):
    command = ["openstack", *args]
    if expect_json:
        command.extend(["-f", "json"])
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"OpenStack command failed: {' '.join(args)}")
    if not expect_json:
        return None
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"OpenStack command returned invalid JSON: {' '.join(args)}") from error


def classify_task_image(rows: list[dict], name: str, owner: str, artifact: str) -> str:
    matches = [row for row in rows if _field(row, "name", "Name") == name]
    if len(matches) == 0:
        return "ABSENT"
    if len(matches) > 1:
        raise RuntimeError("ambiguous duplicate task images")
    row = matches[0]
    properties = _field(row, "properties", "Properties")
    if not isinstance(properties, dict):
        raise RuntimeError("image properties are not structured")
    if properties.get("task_owner") != owner or properties.get("task_artifact") != artifact:
        raise RuntimeError("image is not exactly task-owned")
    image_id = _field(row, "id", "ID")
    if not image_id:
        raise RuntimeError("task image ID missing")
    return str(image_id)


def _show_and_verify_owned(executor, image_id: str) -> dict:
    row = executor(["image", "show", image_id], True)
    verified_id = classify_task_image([row], IMAGE_NAME, TASK_OWNER, TASK_ARTIFACT)
    if verified_id != image_id:
        raise RuntimeError("task image ID changed")
    return row


def _delete_verified_candidate(executor, image_id: str, backend_root: Path) -> None:
    _show_and_verify_owned(executor, image_id)
    executor(["image", "delete", image_id], False)
    rows = executor(["image", "list"], True)
    if any(
        _field(row, "ID", "id") == image_id
        or _field(row, "Name", "name") == IMAGE_NAME
        for row in rows
    ):
        raise RuntimeError("task image remains after exact delete")
    if (backend_root / image_id).exists():
        raise RuntimeError("task image backend file remains after delete")


def _cleanup_owned_workdir(workdir: Path, identity: tuple[int, int], known_paths: tuple[Path, ...]) -> None:
    current = os.lstat(workdir)
    if not stat.S_ISDIR(current.st_mode) or (current.st_dev, current.st_ino) != identity:
        raise RuntimeError("task workdir identity changed")
    for path in known_paths:
        try:
            metadata = os.lstat(path)
        except FileNotFoundError:
            continue
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise RuntimeError(f"unsafe task temporary: {path.name}")
        os.unlink(path)
    if list(workdir.iterdir()):
        raise RuntimeError("unknown file remains in task workdir")
    os.rmdir(workdir)


def run_image_lifecycle(
    executor=subprocess_executor,
    work_root: Path = Path("/root"),
    backend_root: Path = Path("/var/lib/glance/images"),
) -> dict:
    work_root = Path(work_root).resolve(strict=True)
    backend_root = Path(backend_root)
    workdir = Path(tempfile.mkdtemp(prefix=".task5c-image.", dir=work_root))
    os.chmod(workdir, 0o700)
    work_metadata = os.lstat(workdir)
    if not stat.S_ISDIR(work_metadata.st_mode) or workdir.parent.resolve() != work_root:
        raise RuntimeError("exclusive task workdir is unsafe")
    identity = (work_metadata.st_dev, work_metadata.st_ino)
    payload = workdir / "payload.raw"
    download = workdir / "download.raw"
    candidate_id: str | None = None
    deleted = False
    primary_error: BaseException | None = None
    try:
        rows = executor(["image", "list"], True)
        matching = [row for row in rows if _field(row, "Name", "name") == IMAGE_NAME]
        if len(matching) > 1:
            raise RuntimeError("ambiguous duplicate task image names")
        if len(matching) == 1:
            existing_id = _field(matching[0], "ID", "id")
            if not existing_id:
                raise RuntimeError("same-name image ID missing")
            existing = executor(["image", "show", str(existing_id)], True)
            classify_task_image([existing], IMAGE_NAME, TASK_OWNER, TASK_ARTIFACT)
            raise RuntimeError("pre-existing task-owned image requires manual audit; it was not deleted")

        payload.write_bytes((b"OPENSTACK_TASK5C_SYNTHETIC_RAW\n" * 128) + bytes(range(256)))
        os.chmod(payload, 0o600)
        expected_size = payload.stat().st_size
        expected_digest = hashlib.sha256(payload.read_bytes()).digest()
        created = executor([
            "image", "create", IMAGE_NAME, "--private", "--disk-format", "raw",
            "--container-format", "bare", "--property", f"task_owner={TASK_OWNER}",
            "--property", f"task_artifact={TASK_ARTIFACT}", "--file", str(payload),
        ], True)
        candidate_id = str(_field(created, "id", "ID") or "")
        if not candidate_id:
            raise RuntimeError("created image ID missing; no deletion is safe")
        row = _show_and_verify_owned(executor, candidate_id)
        if not (
            _field(row, "status", "Status") == "active"
            and _field(row, "visibility", "Visibility") == "private"
            and _field(row, "disk_format", "Disk Format") == "raw"
            and _field(row, "container_format", "Container Format") == "bare"
            and int(_field(row, "size", "Size")) == expected_size
        ):
            raise RuntimeError("created task image state mismatch")
        executor(["image", "save", "--file", str(download), candidate_id], False)
        downloaded = download.read_bytes()
        if len(downloaded) != expected_size or hashlib.sha256(downloaded).digest() != expected_digest:
            raise RuntimeError("downloaded task image digest/size mismatch")
        _delete_verified_candidate(executor, candidate_id, backend_root)
        deleted = True
        candidate_id = None
        return {"status": "PASS", "size": expected_size, "digest_match": True}
    except BaseException as error:
        primary_error = error
        raise
    finally:
        cleanup_errors: list[BaseException] = []
        if candidate_id is not None and not deleted:
            try:
                _delete_verified_candidate(executor, candidate_id, backend_root)
            except BaseException as error:
                cleanup_errors.append(error)
        try:
            _cleanup_owned_workdir(workdir, identity, (payload, download))
        except BaseException as error:
            cleanup_errors.append(error)
        if cleanup_errors:
            if primary_error is not None:
                for cleanup_error in cleanup_errors:
                    primary_error.add_note(f"cleanup failure: {cleanup_error}")
            else:
                raise RuntimeError("Task 5C lifecycle cleanup failed") from cleanup_errors[0]


if __name__ == "__main__":
    result = run_image_lifecycle()
    print(f"IMAGE_LIFECYCLE={result['status']} SIZE={result['size']} DIGEST_MATCH=PASS DELETE=PASS TEMP=0")
PY
unset OS_PASSWORD
trap - EXIT ERR
```

实际结果：镜像状态 active，格式 raw/bare、可见性 private、大小 4224 字节；上传源与下载文件的非秘密 SHA-256 和大小一致。随后按精确 ID 删除，镜像列表、临时文件和 Glance 后端测试文件均为 0。行为测试还向下载步骤注入失败，证明 `finally` 只删除本次登记且重新验证过的 ID，既不删除同名外来对象，也不删除无关镜像；临时目录只有 inode 与创建时一致、内部只有两个已知普通文件时才清理。

## 依赖顺序驱动器与跨切片收口

本章不提供引用未定义函数的“伪一键驱动器”。实际执行入口就是前文完整的 `run_after_both_gates`：controller 与 compute 两个只读门禁全部成功以后，它才调用一个明确的下一阶段函数；测试向两个节点分别注入失败并证明 mutation 回调一次也不会触发。之后每次只执行紧邻的一个完整代码块，并在看到该阶段 PASS 证据后继续。各阶段在本文件中的位置就是唯一顺序：本地源事务、数据库与授权、Keystone 对象、配置、schema、API、合成镜像、最终双节点审计。后续根包 `openstack-placement-api`、`openstack-nova-common`、`openstack-neutron-common`、`openstack-cinder-common`、`openstack-swift-common`、`python3-horizon` 在收口时仍逐项用失败关闭的 RPM 探针证明缺失。

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
