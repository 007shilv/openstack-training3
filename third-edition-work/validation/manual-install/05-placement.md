# Placement 手工部署与验证记录

本记录对应 controller `192.168.234.151` 上的 OpenStack 2023.1 Antelope Placement 9.0.0，承接已复审的 Keystone 与 Glance 状态。compute `192.168.234.150` 在本阶段仍只做只读审计。没有创建或恢复虚拟机快照，没有执行原脚本 `08-controller-placement.sh`，没有安装 Nova 及后续服务，没有创建资源提供者，也没有对 `/dev/sdb`、`/dev/sdc` 做任何写操作。

严格依赖顺序为：双节点起始门 → 仅本地源的软件包事务 → Placement 数据库与三主机授权 → Keystone 用户、角色、服务和端点 → 软件包默认配置备份与原子配置 → 数据库模式同步 → 升级检查 → Apache/Placement API → 认证资源提供者查询 → 跨切片收口审计。查询失败、未知状态、重复对象和部分对象均不是“对象不存在”，必须停止。

本次实际结果是：包事务安装 6 个 RPM，全部来自 `openstack-local`；Placement 模式包含精确 13 张表，Alembic 头为 `422ece571366`；HTTPD 在 5000 和 8778 各有一个监听；版本发现返回 HTTP 200 和 `v1.0`；认证资源提供者查询成功并得到空列表。空列表表示 Nova compute 尚未注册资源提供者，不表示查询失败。

## 双节点只读起始门

以下工作站程序只读取两个节点。连接只加载逐节点已复审的 `known_hosts`，未知或变化的主机密钥由 `RejectPolicy` 拒绝。controller 必须先完整通过，才连接 compute；两者都通过后才允许调用写阶段。

```python
from __future__ import annotations

import getpass
import os
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
[[ $(hostnamectl --static) == controller ]] || die "hostname drift"
ip -4 -o addr show ens33 | grep -Fq '192.168.234.151/24' || die "ens33 drift"
[[ -z $(ip -4 -o addr show ens34) ]] || die "ens34 must have no IPv4"
timedatectl show -p NTPSynchronized --value | grep -Fxq yes || die "clock unsynchronized"
dnf -q repolist --disablerepo='*' --enablerepo='openstack-local' | grep -Fq openstack-local || die "local repo missing"
for s in chronyd mariadb rabbitmq-server memcached httpd openstack-glance-api; do
  systemctl is-active --quiet "$s" && systemctl is-enabled --quiet "$s" || die "$s state mismatch"
done
rpm -q openstack-keystone openstack-glance openstack-glance-api >/dev/null || die "reviewed package missing"
for p in openstack-placement-api openstack-nova-common openstack-nova-api openstack-nova-compute openstack-neutron-common openstack-cinder-common openstack-swift-common python3-horizon; do absent "$p"; done
[[ $(mysql -uroot -NBe "SELECT COUNT(*) FROM information_schema.SCHEMATA WHERE SCHEMA_NAME='glance'") == 1 ]] || die "Glance database mismatch"
[[ $(mysql -uroot -NBe "SELECT COUNT(*) FROM information_schema.SCHEMATA WHERE SCHEMA_NAME='placement'") == 0 ]] || die "Placement database exists"
[[ -z $(mysql -uroot -NBe "SELECT Host FROM mysql.user WHERE User='placement'") ]] || die "Placement DB users exist"
[[ -z $(ss -H -lnt '( sport = :8778 )') ]] || die "8778 already listens"
secret=/root/.openstack-lab-secrets
[[ -f $secret && ! -L $secret && $(stat -c '%U:%G %a %h' "$secret") == 'root:root 600 1' ]] || die "secret unsafe"
[[ $(awk 'END{print NR}' "$secret") -eq 1 ]] && grep -Eq '^OPENSTACK_DEPLOY_PASSWORD=.+$' "$secret" || die "secret shape drift"
[[ -f /root/admin-openrc && ! -L /root/admin-openrc && $(stat -c '%U:%G %a %h' /root/admin-openrc) == 'root:root 600 1' ]] || die "admin-openrc unsafe"
source /root/admin-openrc
openstack token issue -f value -c expires >/dev/null || die "token failed"
tmp=$(mktemp -d /root/.task5d-start.XXXXXX); trap 'rm -f -- "$tmp"/*.json; rmdir -- "$tmp" 2>/dev/null || :; unset OS_PASSWORD' EXIT
openstack user list --domain default -f json >"$tmp/users.json" || die "user query failed"
openstack service list -f json >"$tmp/services.json" || die "service query failed"
openstack endpoint list -f json >"$tmp/endpoints.json" || die "endpoint query failed"
openstack image list -f json >"$tmp/images.json" || die "image query failed"
python3 - "$tmp" <<'PY'
import json,pathlib,sys
p=pathlib.Path(sys.argv[1]); load=lambda n:json.loads((p/n).read_text())
users,services,endpoints,images=(load(n) for n in ('users.json','services.json','endpoints.json','images.json'))
if len([x for x in users if x.get('Name')=='glance'])!=1: raise SystemExit('Glance user mismatch')
if [x for x in users if x.get('Name')=='placement']: raise SystemExit('Placement user exists')
for typ,name,url in (('identity','keystone','http://controller:5000/v3/'),('image','glance','http://controller:9292')):
    svc=[x for x in services if x.get('Type')==typ]
    if len(svc)!=1 or svc[0].get('Name')!=name: raise SystemExit(f'{typ} service mismatch')
    eps=[x for x in endpoints if x.get('Service Type')==typ]
    if len(eps)!=3 or {x.get('Interface') for x in eps}!={'public','internal','admin'}: raise SystemExit(f'{typ} endpoints mismatch')
    if any(x.get('Region')!='RegionOne' or x.get('URL')!=url for x in eps): raise SystemExit(f'{typ} endpoint binding mismatch')
if [x for x in services if x.get('Type')=='placement' or x.get('Name')=='placement']: raise SystemExit('Placement service exists')
if [x for x in endpoints if x.get('Service Type')=='placement' or x.get('URL')=='http://controller:8778']: raise SystemExit('Placement endpoint exists')
if images: raise SystemExit('retained task image exists')
PY
rm -f -- "$tmp"/*.json; rmdir -- "$tmp"; trap - EXIT; unset OS_PASSWORD
printf 'CONTROLLER_GATE=PASS\n'
'''

COMPUTE_GATE = r'''set -Eeuo pipefail
die(){ printf 'ERROR: %s\n' "$*" >&2; exit 1; }
absent(){ local p=$1 out rc; if out=$(LC_ALL=C rpm -q "$p" 2>&1); then die "unexpected package: $p"; else rc=$?; [[ $rc -eq 1 && $out == "package $p is not installed" ]] || die "RPM probe failed: $p"; fi; }
disk(){ local d=$1 root chain facts sig rc; [[ -b $d && $(blockdev --getsize64 "$d") == 53687091200 && $(lsblk -dnro TYPE "$d") == disk ]] || die "$d identity drift"; root=$(readlink -f "$(findmnt -nro SOURCE /)"); chain=$(lsblk -s -nrpo NAME "$root"); grep -Fxq "$d" <<<"$chain" && die "$d is a root ancestor"; [[ $(lsblk -nrpo NAME "$d" | sed '/^$/d' | wc -l) -eq 1 ]] || die "$d has children"; facts=$(lsblk -dnro FSTYPE,MOUNTPOINT "$d"); [[ -z ${facts//[[:space:]]/} ]] || die "$d has filesystem or mount"; sig=$(wipefs --no-act --noheadings --output TYPE "$d"); [[ -z ${sig//[[:space:]]/} ]] || die "$d has signature"; if blkid -p "$d" >/dev/null 2>&1; then die "$d contains signature"; else rc=$?; [[ $rc -eq 2 ]] || die "$d blkid probe failed"; fi; }
[[ $(hostnamectl --static) == compute ]] || die "hostname drift"
ip -4 -o addr show ens33 | grep -Fq '192.168.234.150/24' || die "ens33 drift"
[[ -z $(ip -4 -o addr show ens34) ]] || die "ens34 must have no IPv4"
timedatectl show -p NTPSynchronized --value | grep -Fxq yes || die "clock unsynchronized"
systemctl is-active --quiet chronyd && systemctl is-enabled --quiet chronyd || die "chronyd mismatch"
dnf -q repolist --disablerepo='*' --enablerepo='openstack-local' | grep -Fq openstack-local || die "local repo missing"
for p in openstack-placement-api openstack-nova-common openstack-nova-api openstack-nova-compute openstack-neutron-common openstack-cinder-common openstack-swift-common python3-horizon; do absent "$p"; done
disk /dev/sdb; disk /dev/sdc
printf 'COMPUTE_GATE=PASS\n'
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
    _stdin, stdout, stderr = client.exec_command("bash -s")
    _stdin.write(script); _stdin.channel.shutdown_write()
    rc = stdout.channel.recv_exit_status()
    if rc:
        raise RuntimeError(stderr.read().decode("utf-8", "replace"))


def run_after_both_placement_gates(
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


if __name__ == "__main__":
    ssh_password = getpass.getpass("两节点 root SSH 密码：")
    run_after_both_placement_gates(ssh_password, lambda: print("BOTH_GATES=PASS"))
    ssh_password = ""
```

实际执行结果：`CONTROLLER_TASK5D_STARTING_GATE=PASS`，随后 `COMPUTE_TASK5D_STARTING_GATE=PASS`。第二个门未通过时不会调用写阶段。

## 仅本地源安装软件包

先查询直接候选与递归依赖，再执行不会安装的 `--assumeno` 事务。候选、事务表和实际安装都必须只出现 `openstack-local`；禁止使用 `--allowerasing`、`--nodeps`、`--skip-broken` 或外部仓库。

```bash
set -Eeuo pipefail
die(){ printf 'ERROR: %s\n' "$*" >&2; exit 1; }
validate_placement_preflight(){
  local candidates=$1 transaction=$2 count rows
  [[ -s $candidates && -s $transaction ]] || return 1
  awk -F'|' 'NF!=2 || $2!="openstack-local"{bad=1} END{exit bad?1:0}' "$candidates" || return 1
  grep -Fxq 'openstack-placement-api|openstack-local' "$candidates" || return 1
  grep -Fq 'Operation aborted' "$transaction" || return 1
  ! grep -Eiq '(^|[[:space:]])(Removing|Erasing|Obsoleting|Replacing|Downgrading)([[:space:]:]|$)' "$transaction" || return 1
  count=$(sed -nE 's/^[[:space:]]*Install[[:space:]]+([0-9]+)[[:space:]]+Packages?.*/\1/p' "$transaction" | tail -n1)
  [[ $count =~ ^[1-9][0-9]*$ ]] || return 1
  rows=$(grep -Ec '[[:space:]]openstack-local[[:space:]]' "$transaction" || :)
  [[ $rows -eq $count ]]
}
rpm -q openstack-placement-api >/dev/null 2>&1 && die 'Placement already installed' || :
work=$(mktemp -d /root/.task5d-package.XXXXXX); trap 'rm -f -- "$work"/*; rmdir -- "$work" 2>/dev/null || :' EXIT
dnf -q repoquery --disablerepo='*' --enablerepo='openstack-local' --qf '%{name}|%{repoid}' openstack-placement-api >"$work/direct"
dnf -q repoquery --disablerepo='*' --enablerepo='openstack-local' --requires --resolve --recursive --qf '%{name}|%{repoid}' openstack-placement-api >"$work/resolved"
sort -u "$work/direct" "$work/resolved" >"$work/candidates"
set +e
LC_ALL=C dnf --assumeno --setopt=install_weak_deps=False --disablerepo='*' --enablerepo='openstack-local' install openstack-placement-api >"$work/transaction" 2>&1
rc=$?
set -e
[[ $rc -eq 1 ]] || die "unexpected preflight rc=$rc"
validate_placement_preflight "$work/candidates" "$work/transaction" || die 'package preflight failed'
LC_ALL=C dnf -y --setopt=install_weak_deps=False --disablerepo='*' --enablerepo='openstack-local' install openstack-placement-api
rpm -q openstack-placement-api >/dev/null || die 'Placement package missing after transaction'
for p in openstack-nova-common openstack-nova-api openstack-nova-compute openstack-neutron-common openstack-cinder-common openstack-swift-common python3-horizon; do rpm -q "$p" >/dev/null 2>&1 && die "later package installed: $p" || :; done
rm -f -- "$work"/*; rmdir -- "$work"; trap - EXIT
```

实际事务为 DNF 历史 7：`PREFLIGHT_INSTALLS=6`、`REPO_ROWS=6`、`RPM_DELTA=6`，根包是 `openstack-placement-api-9.0.0-1.oe2403sp2.noarch`，没有删除、替换或降级。

## Placement 数据库与最小授权

运行时口令文件必须是 root:root、0600、单硬链接、单行且非符号链接。口令只进入进程内存；SQL 值使用 PyMySQL 参数绑定，不能拼接到 SQL 或输出中。

```bash
set -Eeuo pipefail
die(){ printf 'ERROR: %s\n' "$*" >&2; exit 1; }
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
db_count=$(mysql -uroot -NBe "SELECT COUNT(*) FROM information_schema.SCHEMATA WHERE SCHEMA_NAME='placement'")
db_hosts=$(mysql -uroot -NBe "SELECT Host FROM mysql.user WHERE User='placement' ORDER BY Host" | paste -sd, -)
if [[ $db_count == 0 && -z $db_hosts ]]; then create_required=yes
elif [[ $db_count == 1 && $db_hosts == '%,127.0.0.1,localhost' ]]; then create_required=no
else die 'partial/ambiguous Placement database state'
fi
load_runtime_secret OPENSTACK_DEPLOY_PASSWORD || die 'secret failed closed'
export OPENSTACK_DEPLOY_PASSWORD MYSQL_SOCKET
MYSQL_SOCKET=$(mysql -uroot -NBe 'SELECT @@socket'); [[ -S $MYSQL_SOCKET ]] || die 'MariaDB socket unsafe'
if [[ $create_required == yes ]]; then python3 - <<'PY'
import os
import pymysql

password=os.environ['OPENSTACK_DEPLOY_PASSWORD']
db=pymysql.connect(unix_socket=os.environ['MYSQL_SOCKET'],user='root',charset='utf8mb4',autocommit=True)
try:
    with db.cursor() as cursor:
        cursor.execute("CREATE DATABASE IF NOT EXISTS placement")
        for host in ('localhost','127.0.0.1','%'):
            cursor.execute("CREATE USER IF NOT EXISTS %s@%s IDENTIFIED BY %s",('placement',host,password))
            cursor.execute("ALTER USER %s@%s IDENTIFIED BY %s",('placement',host,password))
            cursor.execute("GRANT ALL PRIVILEGES ON placement.* TO %s@%s",('placement',host))
        cursor.execute('FLUSH PRIVILEGES')
finally:
    db.close()
PY
fi
python3 - <<'PY'
import os,pymysql
db=pymysql.connect(host='127.0.0.1',user='placement',password=os.environ['OPENSTACK_DEPLOY_PASSWORD'],database='placement',connect_timeout=5)
try:
    with db.cursor() as cursor:
        cursor.execute('SELECT 1')
        if cursor.fetchone()!=(1,): raise RuntimeError('protected login mismatch')
finally: db.close()
PY
unset OPENSTACK_DEPLOY_PASSWORD MYSQL_SOCKET; unset -f load_runtime_secret
```

授权审计只读取数据库名、`User/Host` 和非凭据授权元数据，不读取 `authentication_string`、密码摘要或真实口令。openEuler 所带 MariaDB 的 `ALL PRIVILEGES ON placement.*` 包含 `DELETE HISTORY`，所以必须按实际完整集合验证，不能把它误判为越权，也不能放宽其他范围。

```python
EXPECTED_SCHEMA_PRIVILEGES = {
    'ALTER','ALTER ROUTINE','CREATE','CREATE ROUTINE','CREATE TEMPORARY TABLES',
    'CREATE VIEW','DELETE','DELETE HISTORY','DROP','EVENT','EXECUTE','INDEX',
    'INSERT','LOCK TABLES','REFERENCES','SELECT','SHOW VIEW','TRIGGER','UPDATE',
}


def validate_placement_grant_evidence(evidence: dict) -> None:
    if evidence.get('hosts') != ['%','127.0.0.1','localhost']:
        raise ValueError('Placement account host set mismatch')
    accounts=evidence.get('accounts',{})
    if set(accounts)!=set(evidence['hosts']): raise ValueError('account evidence mismatch')
    for host,row in accounts.items():
        if set(map(tuple,row.get('global',[])))!={('USAGE','NO')}:
            raise ValueError(f'global privilege mismatch: {host}')
        schema={tuple(x) for x in row.get('schema',[])}
        expected={('placement',p,'NO') for p in EXPECTED_SCHEMA_PRIVILEGES}
        if schema!=expected: raise ValueError(f'schema privilege mismatch: {host}')
        if any(row.get(k) for k in ('table','column','routine')):
            raise ValueError(f'object privilege exists: {host}')
    if evidence.get('proxy') or evidence.get('roles'):
        raise ValueError('proxy or role grant exists')
```

实际结果：数据库仅一份，账户主机精确为 `%`、`127.0.0.1`、`localhost`；三账户全局权限仅 `USAGE`，数据库级权限只属于 `placement.*`，表、列、例程、代理和数据库角色行均为 0，受保护 TCP 登录成功。

## Keystone 对象的分阶段创建

必须先 `source /root/admin-openrc` 并隐藏令牌输出。每一阶段都采用“查询 → 0/1/重复分类 → 必要时创建 → 重新查询 → 立即验证”的屏障；用户没有通过前不能授权，授权没有通过前不能创建服务，服务没有通过前不能创建端点。下面的核心函数可由真实 OpenStack CLI 适配器调用，也便于课堂注入错误状态进行验证。

```python
from __future__ import annotations

import json
import subprocess
from typing import Callable


PLACEMENT_URL = "http://controller:8778"
INTERFACES = ("public", "internal", "admin")


def _one(rows: list[dict], label: str) -> dict:
    if len(rows) != 1:
        raise ValueError(f"{label} cardinality mismatch: {len(rows)}")
    return rows[0]


def _validate_user(query: Callable[[list[str]], object], user_id: str) -> dict:
    user = query(["user", "show", user_id])
    if not isinstance(user, dict) or not (
        user.get("id") == user_id and user.get("name") == "placement"
        and user.get("domain_id") == "default" and user.get("enabled") is True
    ):
        raise ValueError("Placement user stage mismatch")
    return user


def _validate_assignment(rows: list[dict], role_id: str, user_id: str, project_id: str) -> dict:
    row = _one(rows, "Placement assignment")
    expected = {
        "Role": role_id, "User": user_id, "Project": project_id,
        "Group": "", "Domain": "", "System": "", "Inherited": False,
    }
    if any(row.get(key) != value for key, value in expected.items()):
        raise ValueError("Placement assignment binding mismatch")
    return row


def _validate_service(query: Callable[[list[str]], object], service_id: str) -> dict:
    service = query(["service", "show", service_id])
    if not isinstance(service, dict) or not (
        service.get("id") == service_id and service.get("name") == "placement"
        and service.get("type") == "placement" and service.get("enabled") is True
    ):
        raise ValueError("Placement service stage mismatch")
    return service


def _validate_endpoint_stage(
    query: Callable[[list[str]], object], service_id: str, expected_interfaces: tuple[str, ...]
) -> list[dict]:
    rows = query(["endpoint", "list", "--service", service_id])
    if not isinstance(rows, list) or len(rows) != len(expected_interfaces):
        raise ValueError("Placement endpoint stage cardinality mismatch")
    if {row.get("Interface") for row in rows} != set(expected_interfaces):
        raise ValueError("Placement endpoint interface set mismatch")
    validated=[]
    for row in rows:
        endpoint_id=row.get("ID")
        if not endpoint_id: raise ValueError("Placement endpoint ID missing")
        shown=query(["endpoint", "show", endpoint_id])
        if not isinstance(shown,dict) or not (
            shown.get("id")==endpoint_id and shown.get("interface") in expected_interfaces
            and shown.get("region")=="RegionOne" and shown.get("service_id")==service_id
            and shown.get("url")==PLACEMENT_URL and shown.get("enabled") is True
        ):
            raise ValueError("Placement endpoint binding mismatch")
        validated.append(shown)
    return validated


def validate_placement_identity_evidence(evidence: dict) -> None:
    user=evidence.get("user",{}); service=evidence.get("service",{})
    if not (user.get("name")=="placement" and user.get("domain_id")=="default" and user.get("enabled") is True):
        raise ValueError("Placement user evidence mismatch")
    if not (service.get("name")=="placement" and service.get("type")=="placement" and service.get("enabled") is True):
        raise ValueError("Placement service evidence mismatch")
    _validate_assignment(evidence.get("assignments",[]),evidence["admin_role_id"],user["id"],evidence["service_project_id"])
    endpoints=evidence.get("endpoints",[])
    if len(endpoints)!=3 or {x.get("interface") for x in endpoints}!=set(INTERFACES):
        raise ValueError("Placement endpoint evidence mismatch")
    if any(x.get("service_id")!=service["id"] or x.get("region")!="RegionOne" or x.get("url")!=PLACEMENT_URL or x.get("enabled") is not True for x in endpoints):
        raise ValueError("Placement endpoint evidence binding mismatch")


def ensure_placement_identity_objects(
    password: str,
    query: Callable[[list[str]], object],
    mutate: Callable[[list[str]], object],
) -> dict:
    projects=query(["project","list","--domain","default"])
    project_row=_one([x for x in projects if x.get("Name")=="service"],"service project")
    project_id=project_row.get("ID")
    project=query(["project","show",project_id])
    if not isinstance(project,dict) or not (project.get("id")==project_id and project.get("name")=="service" and project.get("domain_id")=="default" and project.get("enabled") is True and project.get("is_domain") is False):
        raise ValueError("service project properties mismatch")
    roles=query(["role","list"])
    role_row=_one([x for x in roles if x.get("Name")=="admin"],"global admin role")
    role_id=role_row.get("ID")
    role=query(["role","show",role_id])
    if not isinstance(role,dict) or not (role.get("id")==role_id and role.get("name")=="admin" and role.get("domain_id") is None):
        raise ValueError("global admin role properties mismatch")

    users=query(["user","list","--domain","default"])
    matches=[x for x in users if x.get("Name")=="placement"]
    if len(matches)==0:
        mutate(["user","create","--domain","default","--password",password,"placement"])
        users=query(["user","list","--domain","default"])
        matches=[x for x in users if x.get("Name")=="placement"]
    user_id=_one(matches,"Placement user").get("ID")
    user=_validate_user(query,user_id)

    assignments=query(["role","assignment","list","--user",user_id])
    if len(assignments)==0:
        mutate(["role","add","--project",project_id,"--user",user_id,role_id])
        assignments=query(["role","assignment","list","--user",user_id])
    assignment=_validate_assignment(assignments,role_id,user_id,project_id)

    services=query(["service","list"])
    matches=[x for x in services if x.get("Type")=="placement" or x.get("Name")=="placement"]
    if len(matches)==0:
        mutate(["service","create","--name","placement","--description","Placement API","placement"])
        services=query(["service","list"])
        matches=[x for x in services if x.get("Type")=="placement" or x.get("Name")=="placement"]
    service_id=_one(matches,"Placement service").get("ID")
    service=_validate_service(query,service_id)

    endpoints=query(["endpoint","list","--service",service_id])
    if len(endpoints)==0:
        expected=[]
        for interface in INTERFACES:
            mutate(["endpoint","create","--region","RegionOne",service_id,interface,PLACEMENT_URL])
            expected.append(interface)
            _validate_endpoint_stage(query,service_id,tuple(expected))
    else:
        _validate_endpoint_stage(query,service_id,INTERFACES)
    endpoints=_validate_endpoint_stage(query,service_id,INTERFACES)
    evidence={"user":user,"service":service,"admin_role_id":role_id,"service_project_id":project_id,"assignments":[assignment],"endpoints":endpoints}
    validate_placement_identity_evidence(evidence)
    return evidence


class OpenStackExecutor:
    def query(self,args:list[str]) -> object:
        completed=subprocess.run(["openstack",*args,"-f","json"],text=True,capture_output=True)
        if completed.returncode: raise RuntimeError("OpenStack query failed")
        return json.loads(completed.stdout)

    def mutate(self,args:list[str]) -> object:
        completed=subprocess.run(["openstack",*args,"-f","json"],text=True,capture_output=True)
        if completed.returncode: raise RuntimeError("OpenStack mutation failed; password argument redacted")
        return json.loads(completed.stdout) if completed.stdout.strip() else None
```

真实执行中先用受保护的 `admin-openrc` 发放令牌且不显示令牌，再调用上述流程。最终只有一个启用的 Default 域 `placement` 用户、一个绑定到 `service` 项目的全局 `admin` 授权、一个启用的 `placement:placement` 服务，以及 public/internal/admin 三个 RegionOne 端点；URL 均为 `http://controller:8778`。

## 备份软件包默认文件并原子配置

先证明软件包文件未改动，再备份配置和 Apache WSGI 文件。真实备份目录为 `/root/openstack-lab-backups/task-5d-20260811T100131Z`，其中保留 `placement.conf.package-default`、`00-placement-api.conf.package-default` 和稍后迁移前的 `policy.json.package-default`。备份使用 `cp -a`，并用 `cmp` 和 owner/mode/硬链接数复核。

```bash
set -Eeuo pipefail
config=/etc/placement/placement.conf
wsgi=/etc/httpd/conf.d/00-placement-api.conf
[[ $(stat -c '%U:%G %a %h' "$config") == 'root:placement 640 1' ]]
[[ $(stat -c '%U:%G %a %h' "$wsgi") == 'root:root 640 1' ]]
rpm -V openstack-placement-api openstack-placement-common
backup=/root/openstack-lab-backups/task-5d-$(date -u +%Y%m%dT%H%M%SZ)
(umask 077; mkdir -- "$backup")
cp -a -- "$config" "$backup/placement.conf.package-default"
cp -a -- "$wsgi" "$backup/00-placement-api.conf.package-default"
cmp -s -- "$config" "$backup/placement.conf.package-default"
cmp -s -- "$wsgi" "$backup/00-placement-api.conf.package-default"
```

下面的写入器在目标目录创建排他、非跟随的临时文件，写入后同步文件和目录，再原子替换。数据库口令先用 `quote(..., safe="")` 做 URL 编码；服务口令保持原值。失败清理只删除本进程创建且 inode 未变化的临时文件。

```python
from __future__ import annotations

import configparser
import os
from pathlib import Path
import stat
import uuid
from urllib.parse import quote


def build_placement_config(password: str) -> str:
    parser=configparser.RawConfigParser(strict=True)
    values={
        "placement_database":{"connection":"mysql+pymysql://placement:"+quote(password,safe="")+"@127.0.0.1/placement"},
        "api":{"auth_strategy":"keystone"},
        "keystone_authtoken":{
            "www_authenticate_uri":"http://controller:5000",
            "auth_url":"http://controller:5000/v3",
            "memcached_servers":"controller:11211",
            "auth_type":"password",
            "project_domain_name":"Default",
            "user_domain_name":"Default",
            "project_name":"service",
            "username":"placement",
            "password":password,
        },
        "oslo_policy":{"policy_file":"policy.yaml"},
    }
    for section,options in values.items():
        parser.add_section(section)
        for name,value in options.items(): parser.set(section,name,value)
    from io import StringIO
    stream=StringIO(); parser.write(stream); return stream.getvalue()


def write_placement_config(
    target: Path,
    password: str,
    owner_uid: int,
    owner_gid: int,
    ops: object = os,
    nonce: str | None = None,
) -> None:
    nonce=nonce or uuid.uuid4().hex
    temporary=target.parent/f".placement.conf.task5d.{nonce}"
    flags=ops.O_WRONLY|ops.O_CREAT|ops.O_EXCL|getattr(ops,"O_NOFOLLOW",0)
    descriptor=None; created=False; identity=None
    try:
        descriptor=ops.open(str(temporary),flags,0o640); created=True
        metadata=ops.fstat(descriptor); identity=(metadata.st_dev,metadata.st_ino)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink!=1:
            raise RuntimeError("unsafe Placement config temporary")
        ops.fchmod(descriptor,0o640); ops.fchown(descriptor,owner_uid,owner_gid)
        payload=build_placement_config(password).encode("utf-8")
        offset=0
        while offset<len(payload):
            written=ops.write(descriptor,payload[offset:])
            if written<=0: raise OSError("short Placement config write")
            offset+=written
        ops.fsync(descriptor); ops.close(descriptor); descriptor=None
        ops.replace(str(temporary),str(target)); created=False
        directory=ops.open(str(target.parent),ops.O_RDONLY|getattr(ops,"O_DIRECTORY",0))
        try: ops.fsync(directory)
        finally: ops.close(directory)
    finally:
        if descriptor is not None: ops.close(descriptor)
        if created and identity is not None:
            try: current=ops.lstat(temporary)
            except FileNotFoundError: current=None
            if current is not None and (current.st_dev,current.st_ino)==identity and stat.S_ISREG(current.st_mode) and current.st_nlink==1:
                ops.unlink(temporary)
```

真实文件为 root:placement、0640。脱敏快照把数据库 URL 中的编码口令替换为 `<URL_ENCODED_DB_PASSWORD>`，把服务口令替换为 `<SERVICE_PASSWORD>`；替换后仍保留“数据库 URL 必须编码”的教学含义。

### 软件包策略文件迁移

第一次 `placement-status upgrade check` 返回 RC 2：`Missing Root Provider IDs` 和 `Incomplete Consumers` 成功，但 `Policy File JSON to YAML Migration` 失败。原因是软件包仍提供四字节空映射 `policy.json`。当时 Apache 尚未重启，8778 没有监听，后续阶段没有执行。

处理时先把原 `policy.json` 备份到同一 Task 5D 目录，确认它仍是软件包默认文件，再使用官方工具转换；转换结果没有任何自定义覆盖。`policy.yaml` 为 root:placement、0640，并在 `[oslo_policy]` 中显式配置。不能为了让检查通过而删除策略或忽略失败。

```bash
set -Eeuo pipefail
[[ -z $(ss -H -lnt '( sport = :8778 )') ]]
cp -a /etc/placement/policy.json "$backup/policy.json.package-default"
cmp -s /etc/placement/policy.json "$backup/policy.json.package-default"
tmp=$(mktemp /etc/placement/.policy.yaml.task5d.XXXXXX)
oslopolicy-convert-json-to-yaml --namespace placement \
  --policy-file /etc/placement/policy.json --output-file "$tmp"
python3 - "$tmp" <<'PY'
import pathlib,sys,yaml
value=yaml.safe_load(pathlib.Path(sys.argv[1]).read_text())
if value not in (None,{}): raise SystemExit('unexpected policy override')
PY
chown root:placement "$tmp"; chmod 0640 "$tmp"; sync -f "$tmp"
mv -T -- "$tmp" /etc/placement/policy.yaml
```

实际迁移后，策略内容与原空映射等价，未增加、放宽或删除 Placement 规则；第二次升级检查的三个检查项均为 `Success`。

## 模式同步与升级门

新数据库应为 0 张表；严格恢复时只允许已经完整同步的 13 张表。其他数量一律视为部分状态。模式同步只在 0 表时执行；本次第一次同步已成功，随后校验代码因依赖 MariaDB 排序而停住，因此恢复时没有重跑同步来掩盖探针错误，而是改用无序精确集合比较。

```bash
set -Eeuo pipefail
table_count=$(mysql -uroot -NBe "SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA='placement'")
[[ $table_count == 0 || $table_count == 13 ]] || { echo 'partial Placement schema' >&2; exit 1; }
[[ -z $(ss -H -lnt '( sport = :8778 )') ]] || { echo 'API exposed before schema gate' >&2; exit 1; }
if [[ $table_count == 0 ]]; then
  su -s /bin/sh -c 'placement-manage db sync' placement
fi
tables=$(mysql -uroot -NBe "SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA='placement'")
TABLES="$tables" python3 - <<'PY'
import os
actual={x for x in os.environ['TABLES'].splitlines() if x}
expected={
 'alembic_version','allocations','consumer_types','consumers','inventories',
 'placement_aggregates','projects','resource_classes','resource_provider_aggregates',
 'resource_provider_traits','resource_providers','traits','users',
}
if actual!=expected or len(actual)!=13: raise SystemExit('exact Placement table set mismatch')
PY
package_head=$(python3 - <<'PY'
from alembic.config import Config
from alembic.script import ScriptDirectory
c=Config('/usr/lib/python3.11/site-packages/placement/db/sqlalchemy/alembic.ini')
heads=ScriptDirectory.from_config(c).get_heads()
if len(heads)!=1: raise SystemExit('package head cardinality mismatch')
print(heads[0])
PY
)
[[ $package_head == 422ece571366 ]]
[[ $(mysql -uroot -NBe 'SELECT version_num FROM placement.alembic_version') == "$package_head" ]]
su -s /bin/sh -c 'placement-manage db version' placement | grep -Fq "$package_head"
upgrade=$(placement-status upgrade check)
for check in 'Missing Root Provider IDs' 'Incomplete Consumers' 'Policy File JSON to YAML Migration'; do
  grep -Fq "Check: $check" <<<"$upgrade"
done
[[ $(grep -Fc 'Result: Success' <<<"$upgrade") -eq 3 ]]
! grep -Eq 'Result: (Failure|Warning)' <<<"$upgrade"
[[ -z $(ss -H -lnt '( sport = :8778 )') ]]
```

实际模式表为 13 张，软件包和数据库迁移头都为 `422ece571366`，`placement-manage db version` 一致；三个升级检查都成功。此时仍没有 8778 监听。

## Apache、版本发现与认证查询

先验证软件包提供的 `/etc/httpd/conf.d/00-placement-api.conf`，不能自行改写 WSGI 拓扑。它声明 8778 虚拟主机、`WSGIPassAuthorization On`、placement 用户/组的守护进程以及根路径脚本别名。只有模式与升级门都通过后才能重启 Apache。

```bash
set -Eeuo pipefail
wsgi=/etc/httpd/conf.d/00-placement-api.conf
[[ $(stat -c '%U:%G %a %h' "$wsgi") == 'root:root 640 1' ]]
[[ -z $(rpm -V openstack-placement-api) ]]
grep -Fxq 'Listen 8778' "$wsgi"
grep -Fq '<VirtualHost *:8778>' "$wsgi"
grep -Fq 'WSGIPassAuthorization On' "$wsgi"
grep -Fq 'WSGIScriptAlias / /usr/bin/placement-api' "$wsgi"
apachectl configtest 2>&1 | grep -Fxq 'Syntax OK'
apachectl -t -D DUMP_VHOSTS 2>&1 | grep -Eq '8778[[:space:]].*00-placement-api\.conf'
placement-status upgrade check | grep -Fq 'Policy File JSON to YAML Migration'
systemctl restart httpd
systemctl is-active --quiet httpd && systemctl is-enabled --quiet httpd
for port in 5000 8778; do
  listeners=$(ss -H -lntp "( sport = :$port )")
  [[ $(sed '/^$/d' <<<"$listeners" | wc -l) -eq 1 ]]
  grep -Fq httpd <<<"$listeners"
done
```

版本发现必须同时验证状态码和 JSON 结构，不能只以 `curl` 退出码判断服务可用。

```python
def validate_placement_version_response(status: int, payload: dict) -> dict:
    if status != 200:
        raise RuntimeError(f"unexpected Placement version HTTP status: {status}")
    versions=payload.get("versions")
    if not isinstance(versions,list) or len(versions)!=1:
        raise ValueError("Placement version cardinality mismatch")
    version=versions[0]
    if not (
        version.get("id")=="v1.0" and version.get("status")=="CURRENT"
        and isinstance(version.get("max_version"),str) and version.get("max_version")
    ):
        raise ValueError("Placement version body mismatch")
    return version


def classify_resource_provider_response(status: int, payload: dict) -> list[dict]:
    if status != 200:
        raise RuntimeError(f"authenticated Placement query failed: HTTP {status}")
    providers=payload.get("resource_providers")
    if not isinstance(providers,list):
        raise ValueError("resource_providers is not a list")
    for row in providers:
        if not isinstance(row,dict) or not row.get("uuid"):
            raise ValueError("invalid resource-provider row")
    return providers
```

常规环境可使用 `openstack resource provider list`。本地教学仓库没有 `python3-osc-placement`，系统也没有相应 CLI entry point，因此该命令返回精确的 `Unknown command ['resource', 'provider', 'list']`。这不是认证、端点或策略故障；在禁止外部源的边界内，使用已经存在的 `curl` 作为精确可用客户端，携带内存中的 Keystone 令牌查询同一 Placement API。不能退化为未认证请求，也不能为了得到非空结果手工创建资源提供者。

```bash
set -Eeuo pipefail
tmp=$(mktemp -d /root/.task5d-query.XXXXXX)
cleanup(){ rm -f -- "$tmp"/*.json "$tmp/client-help"; rmdir -- "$tmp" 2>/dev/null || :; unset OS_PASSWORD placement_token; }
trap cleanup EXIT
status=$(curl --noproxy '*' -sS -o "$tmp/version.json" -w '%{http_code}' http://controller:8778/)
python3 - "$status" "$tmp/version.json" <<'PY'
import json,sys
status=int(sys.argv[1]); payload=json.load(open(sys.argv[2]))
if status!=200 or payload['versions'][0]['id']!='v1.0': raise SystemExit('version discovery mismatch')
PY
[[ $(curl --noproxy '*' -sS -o /dev/null -w '%{http_code}' http://controller:8778/resource_providers) == 401 ]]
source /root/admin-openrc
openstack token issue -f value -c expires >/dev/null
set +e
openstack resource provider list --help >"$tmp/client-help" 2>&1; osc_rc=$?
set -e
if [[ $osc_rc -eq 0 ]]; then
  openstack --os-placement-api-version 1.39 resource provider list -f json >"$tmp/providers.json"
  python3 -c 'import json,sys; data=json.load(open(sys.argv[1])); assert isinstance(data,list)' "$tmp/providers.json"
else
  [[ $osc_rc -eq 1 || $osc_rc -eq 2 ]]
  grep -Fq "Unknown command ['resource', 'provider', 'list']" "$tmp/client-help"
  [[ -z $(dnf -q repoquery --disablerepo='*' --enablerepo='openstack-local' --qf '%{name}|%{repoid}' 'python3-osc-placement*') ]]
  placement_token=$(openstack token issue -f value -c id); [[ -n $placement_token ]]
  provider_status=$(curl --noproxy '*' -sS -o "$tmp/providers.json" -w '%{http_code}' \
    -H "X-Auth-Token: $placement_token" -H 'OpenStack-API-Version: placement 1.39' \
    -H 'Accept: application/json' http://controller:8778/resource_providers)
  unset placement_token
  python3 - "$provider_status" "$tmp/providers.json" <<'PY'
import json,sys
status=int(sys.argv[1]); payload=json.load(open(sys.argv[2]))
if status!=200: raise SystemExit('authenticated resource-provider query failed')
providers=payload.get('resource_providers')
if not isinstance(providers,list): raise SystemExit('provider result is not a list')
print(f'PROVIDERS={len(providers)}')
PY
fi
cleanup; trap - EXIT
```

实际结果：根版本发现为 HTTP 200、`v1.0`；未认证资源提供者路径为 401；认证查询为 HTTP 200 且 `resource_providers=[]`。因此结论是“查询成功、当前 0 个资源提供者”，而不是“查询失败”。资源提供者应在下一切片由 Nova compute 自动注册。

## 跨切片收口审计

controller 最终要求 chronyd、MariaDB、RabbitMQ、Memcached、HTTPD 和 Glance API 都 active+enabled；Keystone 令牌、Glance 镜像列表与 Placement 认证查询都必须成功；identity、image、placement 三个服务及各自三个端点必须精确；Nova 及后续软件包、数据库、用户、服务和端点必须缺席。

```bash
set -Eeuo pipefail
for service in chronyd mariadb rabbitmq-server memcached httpd openstack-glance-api; do
  systemctl is-active --quiet "$service" && systemctl is-enabled --quiet "$service"
done
source /root/admin-openrc
openstack token issue -f value -c expires >/dev/null
openstack image list -f json >/dev/null
for package in openstack-nova-common openstack-nova-api openstack-nova-compute openstack-neutron-common openstack-cinder-common openstack-swift-common python3-horizon; do
  rpm -q "$package" >/dev/null 2>&1 && { echo "unexpected later package: $package" >&2; exit 1; } || :
done
[[ $(mysql -uroot -NBe 'SELECT COUNT(*) FROM placement.resource_providers') == 0 ]]
unset OS_PASSWORD
```

compute 再次执行起始门中的完整磁盘函数：两块盘都必须是 53687091200 字节的无子节点整盘，不在根文件系统完整祖先链中，`FSTYPE/MOUNTPOINT` 为空，`wipefs --no-act` 无类型，`blkid -p` 精确返回 2。本阶段没有安装 Placement、Nova 或后续包。

最终结果：`CONTROLLER_TASK5D_FINAL_AUDIT=PASS SERVICES=identity,image,placement ENDPOINTS=9 PLACEMENT_SCHEMA=13 HEAD=422ece571366 UPGRADE=PASS API=PASS PROVIDERS=0 LATER=0 TEMP=0`；`COMPUTE_TASK5D_FINAL_AUDIT=PASS LATER_PACKAGES=0 SDB=blank50G SDC=blank50G`。

## 故障诊断与回滚边界

- 软件包事务失败：保留完整 DNF 输出与历史 ID，先审计候选仓库和删除/降级动作；不要使用不安全依赖参数继续。
- 数据库或 Keystone 出现部分对象：停止并列出精确对象、ID、绑定关系和授权元数据。不要把部分状态当作可覆盖状态，也不要删除身份对象来“重来”。
- 配置写入失败：原子替换前目标不变；只删除 inode 未变化的本任务临时文件。恢复时可使用 Task 5D 备份的 package-default 文件，但恢复配置会使当前数据库和身份对象失去服务端配置，必须作为完整变更窗口处理。
- 模式同步后校验失败：先只读比较表集合和迁移头，不重复同步来掩盖探针错误。本次 MariaDB 排序差异就是这样处理的。
- 升级检查失败：8778 必须保持未开放。根据检查项修复；不得忽略 RC 2。本次先备份并等价迁移空策略，再重新检查。
- API 认证失败：分别检查 HTTP 状态、版本体、Keystone token、端点、WSGI 授权转发和策略。CLI 插件缺失必须与 401/403/5xx 区分。

教学环境继承了 `gpgcheck=0`、SELinux Permissive、firewalld disabled 和明文 HTTP 等隔离实验选择。生产环境必须启用软件包签名、强制访问控制、防火墙和 TLS；数据库口令、服务用户口令与管理员口令应独立并由专用密钥系统轮换；Apache/Placement 应纳入高可用、容量、日志、备份和审计设计。空的策略覆盖意味着使用代码内默认策略，不等于“没有访问控制”。
