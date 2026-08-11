# 06 Nova 控制节点手工部署记录

本节在已经复审通过的 Keystone、Glance 和 Placement 之上部署 OpenStack Nova 27.3.0（Antelope）。本实验没有创建或恢复快照，也没有运行 `09-controller-nova.sh`；脚本只用于理解目标状态，实际操作均按“先门禁、后写入，前一步完整通过才进入下一步”的顺序手工完成。

依赖顺序为：双节点单一起始门 → Nova 控制节点软件包 → 三个数据库与最小授权 → Nova 身份对象 → 控制节点原子配置 → API 数据库、cell0 与 cell1 → 控制平面服务与 API → 重新执行计算节点写前门。查询失败、重复对象、部分状态或未知返回值一律停止，不能把错误解释成“不存在”。

## 双节点单一起始门

下面的入口依次连接 controller 与 compute。每个连接只加载该节点已经复审的主机密钥，并通过 `paramiko.RejectPolicy()` 拒绝未知或变化的密钥；两节点都通过后才调用写阶段。起始门检查固定地址、无 IPv4 的 ens34、时间同步、唯一离线仓库、Keystone/Glance/Placement 的完整状态、空的 Placement `resource_providers`、Nova 与后续组件的完全缺席，以及 compute 两块 50 GiB 空白数据盘。Nova 包出现 1～N-1 个时属于 `partial Nova package state`，必须停止。

```python
from __future__ import annotations

from pathlib import Path
from typing import Callable

import paramiko


HOSTS = {
    "controller": ("192.168.234.151", Path(".superpowers/sdd/known_hosts.controller")),
    "compute": ("192.168.234.150", Path(".superpowers/sdd/known_hosts.compute")),
}

CONTROLLER_GATE = r'''set -Eeuo pipefail
die(){ printf 'ERROR: %s\n' "$*" >&2; exit 1; }
absent(){ local p=$1 out rc; if out=$(LC_ALL=C rpm -q "$p" 2>&1); then die "unexpected package: $p"; else rc=$?; [[ $rc -eq 1 && $out == "package $p is not installed" ]] || die "RPM probe failed: $p"; fi; }
listener_absent(){ local port=$1 out; out=$(ss -H -lnt "( sport = :$port )") || die "listener probe failed: $port"; [[ -z $out ]] || die "unexpected listener: $port"; }
NOVA_PACKAGES=(openstack-nova-common openstack-nova-api openstack-nova-conductor openstack-nova-novncproxy openstack-nova-scheduler)
installed=0
for p in "${NOVA_PACKAGES[@]}"; do
  if rpm -q "$p" >/dev/null 2>&1; then installed=$((installed+1)); else [[ $? -eq 1 ]] || die "Nova package probe failed: $p"; fi
done
(( installed == 0 )) || { (( installed < ${#NOVA_PACKAGES[@]} )) && die "partial Nova package state: $installed/${#NOVA_PACKAGES[@]}"; die 'complete Nova package state already exists'; }
[[ $(hostnamectl --static) == controller ]] || die 'hostname drift'
ip -4 -o addr show ens33 | grep -Fq '192.168.234.151/24' || die 'ens33 drift'
[[ -z $(ip -4 -o addr show ens34) ]] || die 'ens34 must have no IPv4'
[[ $(timedatectl show -p NTPSynchronized --value) == yes ]] || die 'clock unsynchronized'
dnf -q repolist --disablerepo='*' --enablerepo='openstack-local' | grep -Fq openstack-local || die 'local repo missing'
for s in chronyd mariadb rabbitmq-server memcached httpd openstack-glance-api; do systemctl is-active --quiet "$s" && systemctl is-enabled --quiet "$s" || die "$s mismatch"; done
rpm -q openstack-keystone openstack-glance-api openstack-placement-api >/dev/null || die 'reviewed prerequisite absent'
for db in keystone glance placement; do [[ $(mysql -uroot -NBe "SELECT COUNT(*) FROM information_schema.SCHEMATA WHERE SCHEMA_NAME='$db'") == 1 ]] || die "$db database mismatch"; done
for db in nova_api nova nova_cell0 neutron cinder; do [[ $(mysql -uroot -NBe "SELECT COUNT(*) FROM information_schema.SCHEMATA WHERE SCHEMA_NAME='$db'") == 0 ]] || die "later database exists: $db"; done
[[ $(mysql -uroot -NBe "SELECT COUNT(*) FROM mysql.user WHERE User IN ('nova','neutron','cinder','swift')") == 0 ]] || die 'later DB user exists'
for p in openstack-nova-compute openstack-neutron-common openstack-cinder-common openstack-swift-common python3-horizon; do absent "$p"; done
for port in 8774 6080 9696 8776 8080; do listener_absent "$port"; done
source /root/admin-openrc
work=$(mktemp -d /root/.task5e-start.XXXXXX); trap 'rm -f -- "$work"/*; rmdir -- "$work" 2>/dev/null || :; unset OS_PASSWORD token' EXIT
openstack token issue -f value -c expires >/dev/null || die 'token failed'
openstack user list --domain default -f json >"$work/users.json" || die 'user query failed'
openstack service list -f json >"$work/services.json" || die 'service query failed'
python3 - "$work" <<'PY'
import json,pathlib,sys
p=pathlib.Path(sys.argv[1]); load=lambda n:json.loads((p/n).read_text())
users,services=(load(n) for n in ('users.json','services.json'))
if [x for x in users if x.get('Name') in {'nova','neutron','cinder','swift'}]: raise SystemExit('later user exists')
if [x for x in services if x.get('Type') in {'compute','network','volumev3','object-store'}]: raise SystemExit('later service exists')
PY
token=$(openstack token issue -f value -c id)
status=$(curl -sS -o "$work/providers.json" -w '%{http_code}' -H "X-Auth-Token: $token" -H 'OpenStack-API-Version: placement 1.39' http://controller:8778/resource_providers)
unset token OS_PASSWORD
[[ $status == 200 ]] || die 'Placement provider query failed'
python3 - "$work/providers.json" <<'PY'
import json,sys
if json.load(open(sys.argv[1])).get('resource_providers') != []: raise SystemExit('resource_providers must be empty')
PY
rm -f -- "$work"/*; rmdir -- "$work"; trap - EXIT
printf 'CONTROLLER_NOVA_GATE=PASS\n'
'''

COMPUTE_GATE = r'''set -Eeuo pipefail
die(){ printf 'ERROR: %s\n' "$*" >&2; exit 1; }
absent(){ local p=$1 out rc; if out=$(LC_ALL=C rpm -q "$p" 2>&1); then die "unexpected package: $p"; else rc=$?; [[ $rc -eq 1 && $out == "package $p is not installed" ]] || die "RPM probe failed: $p"; fi; }
disk(){ local d=$1 root chain facts sig rc; [[ -b $d && $(blockdev --getsize64 "$d") == 53687091200 && $(lsblk -dnro TYPE "$d") == disk ]] || die "$d identity"; root=$(readlink -f "$(findmnt -nro SOURCE /)"); chain=$(lsblk -s -nrpo NAME "$root"); grep -Fxq "$d" <<<"$chain" && die "$d is a root ancestor"; [[ $(lsblk -nrpo NAME "$d" | sed '/^$/d' | wc -l) -eq 1 ]] || die "$d has children"; facts=$(lsblk -dnro FSTYPE,MOUNTPOINT "$d"); [[ -z ${facts//[[:space:]]/} ]] || die "$d has filesystem or mount"; sig=$(wipefs --no-act --noheadings --output TYPE "$d"); [[ -z ${sig//[[:space:]]/} ]] || die "$d has signature"; if blkid -p "$d" >/dev/null 2>&1; then die "$d has signature"; else rc=$?; [[ $rc -eq 2 ]] || die "$d probe error"; fi; }
NOVA_PACKAGES=(qemu libvirt openstack-nova-common openstack-nova-compute)
installed=0
for p in "${NOVA_PACKAGES[@]}"; do if rpm -q "$p" >/dev/null 2>&1; then installed=$((installed+1)); else [[ $? -eq 1 ]] || die "Nova package probe failed: $p"; fi; done
(( installed == 0 )) || { (( installed < ${#NOVA_PACKAGES[@]} )) && die "partial Nova package state: $installed/${#NOVA_PACKAGES[@]}"; die 'complete Nova compute package state already exists'; }
[[ $(hostnamectl --static) == compute ]] || die 'hostname drift'
ip -4 -o addr show ens33 | grep -Fq '192.168.234.150/24' || die 'ens33 drift'
[[ -z $(ip -4 -o addr show ens34) ]] || die 'ens34 must have no IPv4'
[[ $(timedatectl show -p NTPSynchronized --value) == yes ]] || die 'clock unsynchronized'
dnf -q repolist --disablerepo='*' --enablerepo='openstack-local' | grep -Fq openstack-local || die 'local repo missing'
for p in openstack-neutron-common openstack-cinder-common openstack-swift-common python3-horizon; do absent "$p"; done
[[ ! -e /etc/nova/compute_id && ! -L /etc/nova/compute_id ]] || die 'compute_id exists'
disk /dev/sdb; disk /dev/sdc
printf 'COMPUTE_NOVA_GATE=PASS\n'
'''


def connect_node(name: str, password: str) -> paramiko.SSHClient:
    host, known_hosts = HOSTS[name]
    client = paramiko.SSHClient()
    client.load_host_keys(str(known_hosts))
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    client.connect(host, username="root", password=password, look_for_keys=False,
                   allow_agent=False, timeout=10, auth_timeout=10, banner_timeout=10)
    return client


def run_gate(client: paramiko.SSHClient, script: str) -> None:
    stdin, stdout, stderr = client.exec_command("bash -s")
    stdin.write(script); stdin.channel.shutdown_write()
    rc = stdout.channel.recv_exit_status()
    if rc:
        raise RuntimeError(stderr.read().decode("utf-8", "replace"))


def run_after_both_nova_gates(
    password: str,
    mutation: Callable[[], None],
    connector: Callable[[str, str], paramiko.SSHClient] = connect_node,
    runner: Callable[[paramiko.SSHClient, str], None] = run_gate,
) -> None:
    for name, script in (("controller", CONTROLLER_GATE), ("compute", COMPUTE_GATE)):
        client = connector(name, password)
        try:
            runner(client, script)
        finally:
            client.close()
    mutation()
```

实际起始门输出为 `CONTROLLER_NOVA_GATE=PASS` 和 `COMPUTE_NOVA_GATE=PASS`。此时 controller 的 Placement provider 数量为 0，compute 的 `/dev/sdb`、`/dev/sdc` 均为 53687091200 字节空白整盘。

## Nova 控制节点软件包

只允许 `openstack-local`，关闭弱依赖，先执行不会安装的事务计划。计划与真实事务都拒绝 `Removing`、`Erasing`、`Obsoleting`、`Replacing`、`Downgrading`，禁止 `--allowerasing`、`--nodeps` 和 `--skip-broken`。

```bash
set -Eeuo pipefail
roots=(openstack-nova-api openstack-nova-conductor openstack-nova-novncproxy openstack-nova-scheduler)
EXACT_CONTROLLER_TRANSACTION_NEVRAS=(
  openstack-nova-api-27.3.0-1.oe2403sp2.noarch
  openstack-nova-conductor-27.3.0-1.oe2403sp2.noarch
  openstack-nova-novncproxy-27.3.0-1.oe2403sp2.noarch
  openstack-nova-scheduler-27.3.0-1.oe2403sp2.noarch
)
work=$(mktemp -d /root/.task5e-package.XXXXXX)
trap 'rm -f -- "$work"/*; rmdir -- "$work" 2>/dev/null || :' EXIT
dnf -q repoquery --disablerepo='*' --enablerepo='openstack-local' --requires --resolve --recursive --qf '%{name}|%{repoid}' "${roots[@]}" >"$work/candidates"
awk -F'|' 'NF!=2 || $2!="openstack-local"{bad=1} END{exit bad?1:0}' "$work/candidates"
set +e
LC_ALL=C dnf --assumeno --setopt=install_weak_deps=False --disablerepo='*' --enablerepo='openstack-local' install "${roots[@]}" >"$work/plan" 2>&1
rc=$?
set -e
[[ $rc -eq 1 ]] && grep -Fq 'Operation aborted' "$work/plan"
! grep -Eiq '(^|[[:space:]])(Removing|Erasing|Obsoleting|Replacing|Downgrading)([[:space:]:]|$)' "$work/plan"
LC_ALL=C dnf -y --setopt=install_weak_deps=False --disablerepo='*' --enablerepo='openstack-local' install "${roots[@]}"
history=$(LC_ALL=C dnf history info 8)
grep -Fq 'Return-Code    : Success' <<<"$history"
[[ $(grep -Ec '^[[:space:]]+Install .*@openstack-local$' <<<"$history") -eq 40 ]]
! grep -Eiq '^[[:space:]]+(Erase|Removed|Obsolet|Replac|Downgrad)' <<<"$history"
rm -f -- "$work"/*; rmdir -- "$work"; trap - EXIT
```

真实事务号为 8，计划、仓库行、历史 Install 行和 RPM 增量均为 40。`EXACT_CONTROLLER_TRANSACTION_NEVRAS` 的四个根包是 `openstack-nova-api-27.3.0-1.oe2403sp2.noarch`、`openstack-nova-conductor-27.3.0-1.oe2403sp2.noarch`、`openstack-nova-novncproxy-27.3.0-1.oe2403sp2.noarch` 和 `openstack-nova-scheduler-27.3.0-1.oe2403sp2.noarch`；同一增量还包括 `openstack-nova-common-27.3.0-1.oe2403sp2.noarch`、`python3-nova-27.3.0-1.oe2403sp2.noarch`、novnc 及其 34 个依赖。全部来自 `openstack-local`，zero remove/replace。

## 三个数据库与最小授权

运行时口令文件必须是 root:root、0600、单硬链接、单行普通文件。下面的加载器失败即返回非零，不执行 `source`，也不把口令打印到日志。

```bash
set -Eeuo pipefail
load_runtime_secret(){
  local output_name=$1 path=${2:-/root/.openstack-lab-secrets} metadata value rc
  local -a lines=()
  [[ -f $path && ! -L $path ]] || return 1
  if readlink -- "$path" >/dev/null 2>&1; then return 1; else rc=$?; [[ $rc -eq 1 ]] || return 1; fi
  metadata=$(stat -c '%U:%G %a %h' "$path") || return 1
  [[ $metadata == 'root:root 600 1' ]] || return 1
  mapfile -t lines <"$path" || return 1
  [[ ${lines[0]+present} == present && ${lines[1]+present} != present ]] || return 1
  [[ ${lines[0]} =~ ^OPENSTACK_DEPLOY_PASSWORD=(.+)$ ]] || return 1
  value=${BASH_REMATCH[1]}; printf -v "$output_name" '%s' "$value"
}
```

创建逻辑只接受“数据库和账号全无”或“精确三个数据库、三个 Host 已完整存在”两种状态。SQL 标识符来自固定白名单，用户、Host 与口令均参数化；验证只查询非凭据元数据，不查询 `authentication_string`，也不执行会显示摘要的命令。

```bash
set -Eeuo pipefail
load_runtime_secret runtime_secret
export OPENSTACK_DEPLOY_PASSWORD=$runtime_secret
unset runtime_secret
python3 - <<'PY'
import os
import pymysql

DATABASES = ("nova_api", "nova", "nova_cell0")
HOSTS = ("%", "127.0.0.1", "localhost")
password = os.environ.pop("OPENSTACK_DEPLOY_PASSWORD")
connection = pymysql.connect(unix_socket="/var/lib/mysql/mysql.sock", user="root", autocommit=False)
try:
    with connection.cursor() as cursor:
        cursor.execute("SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME IN (%s,%s,%s)", DATABASES)
        schemas = {row[0] for row in cursor.fetchall()}
        cursor.execute("SELECT User,Host FROM mysql.user WHERE User=%s", ("nova",))
        accounts = set(cursor.fetchall())
        expected_accounts = {("nova", host) for host in HOSTS}
        if not schemas and not accounts:
            for database in DATABASES:
                cursor.execute("CREATE DATABASE IF NOT EXISTS `{}`".format(database))
            for host in HOSTS:
                cursor.execute("CREATE USER IF NOT EXISTS %s@%s IDENTIFIED BY %s", ("nova", host, password))
                cursor.execute("ALTER USER %s@%s IDENTIFIED BY %s", ("nova", host, password))
                for database in DATABASES:
                    cursor.execute("GRANT ALL PRIVILEGES ON `{}`.* TO %s@%s".format(database), ("nova", host))
            connection.commit()
        elif schemas != set(DATABASES) or accounts != expected_accounts:
            raise SystemExit("partial or ambiguous Nova database state")
finally:
    connection.close()
password = ""
PY
unset OPENSTACK_DEPLOY_PASSWORD
```

最终证据为：3 个数据库、3 个 Host、9 个精确 schema scope；每个账号全局层仅 `USAGE`，数据库层仅属于 `nova_api`、`nova`、`nova_cell0`，表、列、例程、代理和数据库角色附加授权均为 0。MariaDB 本版本没有 `information_schema.ROUTINE_PRIVILEGES`，因此例程授权使用 `mysql.procs_priv` 非凭据表复核。

```python
EXPECTED_NOVA_DATABASES = {"nova_api", "nova", "nova_cell0"}
EXPECTED_NOVA_HOSTS = {"%", "127.0.0.1", "localhost"}
EXPECTED_SCHEMA_PRIVILEGES = {
    "ALTER", "ALTER ROUTINE", "CREATE", "CREATE ROUTINE", "CREATE TEMPORARY TABLES",
    "CREATE VIEW", "DELETE", "DELETE HISTORY", "DROP", "EVENT", "EXECUTE", "INDEX",
    "INSERT", "LOCK TABLES", "REFERENCES", "SELECT", "SHOW VIEW", "TRIGGER", "UPDATE",
}


def validate_nova_grant_evidence(evidence: dict) -> None:
    if set(evidence.get("hosts", [])) != EXPECTED_NOVA_HOSTS:
        raise ValueError("Nova database host set mismatch")
    accounts = evidence.get("accounts", {})
    if set(accounts) != EXPECTED_NOVA_HOSTS:
        raise ValueError("Nova account evidence mismatch")
    for host, account in accounts.items():
        if set(map(tuple, account.get("global", []))) != {("USAGE", "NO")}:
            raise ValueError(f"global privilege mismatch: {host}")
        expected = {(db, privilege, "NO") for db in EXPECTED_NOVA_DATABASES for privilege in EXPECTED_SCHEMA_PRIVILEGES}
        if set(map(tuple, account.get("schema", []))) != expected:
            raise ValueError(f"schema privilege mismatch: {host}")
        if any(account.get(name) for name in ("table", "column", "routine")):
            raise ValueError(f"fine-grained privilege exists: {host}")
    if evidence.get("proxy") or evidence.get("roles"):
        raise ValueError("proxy or database-role privilege exists")
```

## Nova 身份对象

身份阶段采用 0/1/重复/查询错误分类。目标属性是 enabled Default-domain `nova`、global-admin 项目授权；服务必须为 name=`nova`、type=`compute`；public、internal、admin 三个 RegionOne 端点必须全部绑定 `http://controller:8774/v2.1`。每次写入后执行 create/requery/immediate validation，任何错误立即停止，不使用 `|| true`。

```python
from __future__ import annotations

from typing import Callable


NOVA_URL = "http://controller:8774/v2.1"
INTERFACES = ("public", "internal", "admin")


def _one(rows: list[dict], label: str) -> dict:
    if len(rows) != 1:
        raise ValueError(f"{label} cardinality mismatch: {len(rows)}")
    return rows[0]


def ensure_nova_identity_objects(
    password: str,
    query: Callable[[list[str]], object],
    mutate: Callable[[list[str]], object],
) -> dict:
    project = _one([x for x in query(["project", "list", "--domain", "default"]) if x.get("Name") == "service"], "service project")
    role = _one([x for x in query(["role", "list"]) if x.get("Name") == "admin"], "admin role")
    project_id, role_id = project["ID"], role["ID"]
    users = [x for x in query(["user", "list", "--domain", "default"]) if x.get("Name") == "nova"]
    if not users:
        mutate(["user", "create", "--domain", "default", "--password", password, "nova"])
        users = [x for x in query(["user", "list", "--domain", "default"]) if x.get("Name") == "nova"]
    user_id = _one(users, "Nova user")["ID"]
    user = query(["user", "show", user_id])
    if not (user.get("id") == user_id and user.get("name") == "nova" and user.get("domain_id") == "default" and user.get("enabled") is True):
        raise ValueError("Nova user mismatch")
    assignments = query(["role", "assignment", "list", "--user", user_id])
    if not assignments:
        mutate(["role", "add", "--project", project_id, "--user", user_id, role_id])
        assignments = query(["role", "assignment", "list", "--user", user_id])
    assignment = _one(assignments, "Nova assignment")
    expected = {"Role": role_id, "User": user_id, "Project": project_id, "Group": "", "Domain": "", "System": "", "Inherited": False}
    if any(assignment.get(key) != value for key, value in expected.items()):
        raise ValueError("Nova assignment mismatch")
    services = [x for x in query(["service", "list"]) if x.get("Type") == "compute" or x.get("Name") == "nova"]
    if not services:
        mutate(["service", "create", "--name", "nova", "--description", "OpenStack Compute", "compute"])
        services = [x for x in query(["service", "list"]) if x.get("Type") == "compute" or x.get("Name") == "nova"]
    service_id = _one(services, "Nova service")["ID"]
    shown = query(["service", "show", service_id])
    if not (shown.get("id") == service_id and shown.get("name") == "nova" and shown.get("type") == "compute" and shown.get("enabled") is True):
        raise ValueError("Nova service mismatch")
    endpoints = query(["endpoint", "list", "--service", service_id])
    if endpoints:
        if len(endpoints) != 3:
            raise ValueError("partial Nova endpoint state")
    else:
        created: list[str] = []
        for interface in INTERFACES:
            mutate(["endpoint", "create", "--region", "RegionOne", service_id, interface, NOVA_URL])
            created.append(interface)
            stage = query(["endpoint", "list", "--service", service_id])
            if len(stage) != len(created) or {x.get("Interface") for x in stage} != set(created):
                raise ValueError("Nova endpoint stage mismatch")
    endpoints = query(["endpoint", "list", "--service", service_id])
    if len(endpoints) != 3 or {x.get("Interface") for x in endpoints} != set(INTERFACES):
        raise ValueError("Nova endpoint set mismatch")
    for row in endpoints:
        item = query(["endpoint", "show", row["ID"]])
        if not (item.get("service_id") == service_id and item.get("region") == "RegionOne" and item.get("url") == NOVA_URL and item.get("enabled") is True):
            raise ValueError("Nova endpoint binding mismatch")
    return {"user": user, "assignment": assignment, "service": shown, "endpoints": endpoints}
```

实际结果为 USER=1、ASSIGNMENT=1、SERVICE=1、ENDPOINTS=3。首次角色写入的客户端进程返回非零，门禁在服务创建前停止；随后精确 ID 诊断证明用户唯一、授权为空，同一绑定成功后才继续。没有自动重试掩盖重复或错误 ID。

## 控制节点原子配置

第一次改写前，`rpm -V openstack-nova-common` 无输出；软件包默认文件以元数据和字节校验备份到 `/root/openstack-lab-backups/task-5e-20260811T113129Z/nova.conf.package-default`。写入器在同目录使用排他、非跟随临时文件，完成 owner/mode、文件 fsync、原子替换和目录 fsync；失败只清理由本进程创建且 inode 未变化的临时文件。

```python
from __future__ import annotations

import configparser
from io import StringIO
import os
from pathlib import Path
import stat
import uuid
from urllib.parse import quote


def build_nova_config(password: str) -> str:
    encoded = quote(password, safe="")
    values = {
        "DEFAULT": {"enabled_apis": "osapi_compute,metadata", "transport_url": f"rabbit://openstack:{encoded}@controller", "my_ip": "192.168.234.151", "use_neutron": "true", "firewall_driver": "nova.virt.firewall.NoopFirewallDriver"},
        "api_database": {"connection": f"mysql+pymysql://nova:{encoded}@127.0.0.1/nova_api"},
        "database": {"connection": f"mysql+pymysql://nova:{encoded}@127.0.0.1/nova"},
        "api": {"auth_strategy": "keystone"},
        "keystone_authtoken": {"www_authenticate_uri": "http://controller:5000/", "auth_url": "http://controller:5000/", "memcached_servers": "controller:11211", "auth_type": "password", "project_domain_name": "Default", "user_domain_name": "Default", "project_name": "service", "username": "nova", "password": password},
        "service_user": {"send_service_user_token": "true", "auth_url": "http://controller:5000/v3", "auth_strategy": "keystone", "auth_type": "password", "project_domain_name": "Default", "project_name": "service", "user_domain_name": "Default", "username": "nova", "password": password},
        "vnc": {"enabled": "true", "server_listen": "$my_ip", "server_proxyclient_address": "$my_ip", "novncproxy_base_url": "http://controller:6080/vnc_auto.html"},
        "glance": {"api_servers": "http://controller:9292"}, "oslo_concurrency": {"lock_path": "/var/lib/nova/tmp"},
        "placement": {"region_name": "RegionOne", "project_domain_name": "Default", "project_name": "service", "auth_type": "password", "user_domain_name": "Default", "auth_url": "http://controller:5000/v3", "username": "placement", "password": password},
        "neutron": {"auth_url": "http://controller:5000", "auth_type": "password", "project_domain_name": "Default", "user_domain_name": "Default", "region_name": "RegionOne", "project_name": "service", "username": "neutron", "password": password, "service_metadata_proxy": "true", "metadata_proxy_shared_secret": password},
        "scheduler": {"discover_hosts_in_cells_interval": "300"}, "cinder": {"os_region_name": "RegionOne"},
    }
    parser = configparser.RawConfigParser(strict=True, interpolation=None)
    for section, options in values.items():
        if section != "DEFAULT": parser.add_section(section)
        for name, value in options.items(): parser.set(section, name, value)
    stream = StringIO(); parser.write(stream); return stream.getvalue()


def write_nova_config(target: Path, password: str, uid: int, gid: int, ops: object = os, nonce: str | None = None) -> None:
    temporary = target.parent / f".nova.conf.task5e.{nonce or uuid.uuid4().hex}"
    flags = ops.O_WRONLY | ops.O_CREAT | ops.O_EXCL | getattr(ops, "O_NOFOLLOW", 0)
    descriptor = None; created = False; identity = None
    try:
        descriptor = ops.open(str(temporary), flags, 0o640); created = True
        metadata = ops.fstat(descriptor); identity = (metadata.st_dev, metadata.st_ino)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1: raise RuntimeError("unsafe Nova config temporary")
        ops.fchmod(descriptor, 0o640); ops.fchown(descriptor, uid, gid)
        payload = build_nova_config(password).encode(); offset = 0
        while offset < len(payload):
            written = ops.write(descriptor, payload[offset:])
            if written <= 0: raise OSError("short Nova config write")
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

真实文件为 root:nova、0640、单硬链接。RabbitMQ 和数据库 URL 中的口令先做 URL 编码；快照使用 `<URL_ENCODED_DB_PASSWORD>` 和 `<SERVICE_PASSWORD>`。`[neutron]` 与 `[cinder]` 是为后续切片预留的 inactive dependencies，本节没有 Nova 工作负载，因此它们不会触发网络或卷操作；只有后续组件通过自己的门禁后才能激活业务路径。

## API 数据库、cell0 与 cell1

模式迁移严格以 nova 系统用户执行。cell0 使用保留的全零 UUID；cell1 只在完全不存在时创建。列表与数据库证据只读取 UUID、name、disabled，不显示包含凭据的 transport/database URL。

```bash
set -Eeuo pipefail
su -s /bin/sh -c 'nova-manage api_db sync' nova
[[ $(su -s /bin/sh -c 'nova-manage api_db version' nova 2>/dev/null | tail -n1) == b30f573d3377 ]]
cell0_count=$(mysql -uroot -NBe "SELECT COUNT(*) FROM nova_api.cell_mappings WHERE name='cell0'")
[[ $cell0_count == 0 || $cell0_count == 1 ]]
if [[ $cell0_count == 0 ]]; then nova-manage cell_v2 map_cell0; fi
[[ $(mysql -uroot -NBe "SELECT COUNT(*) FROM nova_api.cell_mappings WHERE name='cell0' AND uuid='00000000-0000-0000-0000-000000000000' AND disabled=0") == 1 ]]
cell1_count=$(mysql -uroot -NBe "SELECT COUNT(*) FROM nova_api.cell_mappings WHERE name='cell1'")
[[ $cell1_count == 0 || $cell1_count == 1 ]]
if [[ $cell1_count == 0 ]]; then nova-manage cell_v2 create_cell --name=cell1; fi
[[ $(mysql -uroot -NBe "SELECT COUNT(*) FROM nova_api.cell_mappings") == 2 ]]
[[ $(mysql -uroot -NBe "SELECT COUNT(*) FROM nova_api.cell_mappings WHERE name='cell1' AND disabled=0") == 1 ]]
su -s /bin/sh -c 'nova-manage db sync' nova
[[ $(su -s /bin/sh -c 'nova-manage db version' nova 2>/dev/null | tail -n1) == 960aac0e09ea ]]
```

真实模式证据是：`nova_api` 精确 32 张表、head=`b30f573d3377`；`nova` 与 `nova_cell0` 各 110 张表、head=`960aac0e09ea`；cell 映射精确为 cell0、cell1 两条，均 enabled。`nova-status upgrade check` 的 Cells v2、Placement API、Cinder API、Policy File JSON to YAML Migration、Older than N-1 computes、hw_machine_type unset、Service User Token Configuration 七项均为 Success。

## 控制平面服务与 API

只有数据库、cell 和升级检查通过后才依次启动 API、scheduler、conductor、noVNC。每次启动后立即检查 active/enabled；API 版本发现必须包含唯一 v2.1/CURRENT，认证的服务列表在 compute 安装前只能出现 controller 上的 scheduler 和 conductor。

```bash
set -Eeuo pipefail
systemctl enable --now openstack-nova-api
systemctl is-active --quiet openstack-nova-api && systemctl is-enabled --quiet openstack-nova-api
[[ $(ss -H -lnt '( sport = :8774 )' | wc -l) -eq 1 ]]
systemctl enable --now openstack-nova-scheduler
systemctl is-active --quiet openstack-nova-scheduler && systemctl is-enabled --quiet openstack-nova-scheduler
systemctl enable --now openstack-nova-conductor
systemctl is-active --quiet openstack-nova-conductor && systemctl is-enabled --quiet openstack-nova-conductor
systemctl enable --now openstack-nova-novncproxy
systemctl is-active --quiet openstack-nova-novncproxy && systemctl is-enabled --quiet openstack-nova-novncproxy
[[ $(ss -H -lnt '( sport = :6080 )' | wc -l) -eq 1 ]]
source /root/admin-openrc
openstack compute service list
unset OS_PASSWORD
```

真实结果为 8774:v2.1:CURRENT、认证访问成功、6080 唯一监听；compute 写入前仅 `nova-scheduler/controller` 与 `nova-conductor/controller` 两行，均 up/enabled。

## 重新执行计算节点写前门

Controller 完整通过后，必须立即重新执行本节 `COMPUTE_GATE`。第二次真实结果仍为：Nova/QEMU/libvirt 全部缺席，`compute_id` 缺席，ens34 无 IPv4，`/dev/sdb`、`/dev/sdc` 是 53687091200 字节空白整盘。这一步通过后才允许进入《07 Nova 计算节点手工部署记录》。

安全边界：本节不创建实例、不创建网络、不创建规格、不上传镜像；不部署 `openstack-neutron-common`、`openstack-cinder-common`、`openstack-swift-common` 或 `python3-horizon`，也不写入 `/dev/sdb`、`/dev/sdc`。
