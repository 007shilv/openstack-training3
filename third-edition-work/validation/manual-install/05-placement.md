# Placement 手工部署与验证记录

本记录对应 controller `192.168.234.151` 上的 OpenStack 2023.1 Antelope Placement 9.0.0，承接已复审的 Keystone 与 Glance 状态。compute `192.168.234.150` 在本阶段仍只做只读审计。没有创建或恢复虚拟机快照，没有执行原脚本 `08-controller-placement.sh`，没有安装 Nova 及后续服务，没有创建资源提供者，也没有对 `/dev/sdb`、`/dev/sdc` 做任何写操作。

严格依赖顺序为：双节点起始门 → 仅本地源的软件包事务 → Placement 数据库与三主机授权 → Keystone 用户、角色、服务和端点 → 软件包默认配置备份与原子配置 → 数据库模式同步 → 升级检查 → Apache/Placement API → 认证资源提供者查询 → 跨切片收口审计。查询失败、未知状态、重复对象和部分对象均不是“对象不存在”，必须停止。

本次实际结果是：包事务安装 6 个 RPM，全部来自 `openstack-local`；Placement 模式包含精确 13 张表，Alembic 头为 `422ece571366`；HTTPD 在 5000 和 8778 各有一个监听；版本发现返回 HTTP 200 和 `v1.0`；认证资源提供者查询成功并得到空列表。空列表表示 Nova compute 尚未注册资源提供者，不表示查询失败。

## 双节点只读起始门

以下工作站程序只读取两个节点。连接只加载逐节点已复审的 `known_hosts`，未知或变化的主机密钥由 `RejectPolicy` 拒绝。controller 必须先完整通过，才连接 compute；两者都通过后才允许调用写阶段。

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
assert_listener_absent(){
  local port=$1 out
  if ! out=$(ss -H -lnt "( sport = :$port )" 2>&1); then die "listener probe failed: $port"; fi
  [[ -z $out ]] || die "unexpected listener: $port"
}
EXPECTED_PLACEMENT_RPMS=(openstack-placement-api openstack-placement-common python3-microversion-parse python3-os-resource-classes python3-os-traits python3-placement)
assert_placement_transaction_absent(){
  local installed=0 p out rc
  for p in "${EXPECTED_PLACEMENT_RPMS[@]}"; do
    if out=$(LC_ALL=C rpm -q "$p" 2>&1); then installed=$((installed+1)); else
      rc=$?; [[ $rc -eq 1 && $out == "package $p is not installed" ]] || die "Placement RPM probe failed: $p"
    fi
  done
  if (( installed > 0 && installed < ${#EXPECTED_PLACEMENT_RPMS[@]} )); then die "partial Placement package state: $installed/6"; fi
  (( installed == 0 )) || die "complete Placement package transaction already present"
}
[[ $(hostnamectl --static) == controller ]] || die "hostname drift"
ip -4 -o addr show ens33 | grep -Fq '192.168.234.151/24' || die "ens33 drift"
[[ -z $(ip -4 -o addr show ens34) ]] || die "ens34 must have no IPv4"
timedatectl show -p NTPSynchronized --value | grep -Fxq yes || die "clock unsynchronized"
dnf -q repolist --disablerepo='*' --enablerepo='openstack-local' | grep -Fq openstack-local || die "local repo missing"
for s in chronyd mariadb rabbitmq-server memcached httpd openstack-glance-api; do
  systemctl is-active --quiet "$s" && systemctl is-enabled --quiet "$s" || die "$s state mismatch"
done
rpm -q openstack-keystone openstack-glance openstack-glance-api >/dev/null || die "reviewed package missing"
assert_placement_transaction_absent
for p in openstack-nova-common openstack-nova-api openstack-nova-compute openstack-neutron-common openstack-cinder-common openstack-swift-common python3-horizon; do absent "$p"; done
[[ $(mysql -uroot -NBe "SELECT COUNT(*) FROM information_schema.SCHEMATA WHERE SCHEMA_NAME='glance'") == 1 ]] || die "Glance database mismatch"
[[ $(mysql -uroot -NBe "SELECT COUNT(*) FROM information_schema.SCHEMATA WHERE SCHEMA_NAME='placement'") == 0 ]] || die "Placement database exists"
[[ -z $(mysql -uroot -NBe "SELECT Host FROM mysql.user WHERE User='placement'") ]] || die "Placement DB users exist"
for db in nova nova_api nova_cell0 neutron cinder; do [[ $(mysql -uroot -NBe "SELECT COUNT(*) FROM information_schema.SCHEMATA WHERE SCHEMA_NAME='$db'") == 0 ]] || die "later database exists: $db"; done
[[ $(mysql -uroot -NBe "SELECT COUNT(*) FROM mysql.user WHERE User IN ('nova','neutron','cinder','swift')") == 0 ]] || die "later database user exists"
for port in 8778 8774 9696 8776 8080; do assert_listener_absent "$port"; done
[[ ! -e /usr/bin/placement-api && ! -L /usr/bin/placement-api ]] || die "placement-api executable already exists"
secret=/root/.openstack-lab-secrets
[[ -f $secret && ! -L $secret && $(stat -c '%U:%G %a %h' "$secret") == 'root:root 600 1' ]] || die "secret unsafe"
[[ $(awk 'END{print NR}' "$secret") -eq 1 ]] && grep -Eq '^OPENSTACK_DEPLOY_PASSWORD=.+$' "$secret" || die "secret shape drift"
[[ -f /root/admin-openrc && ! -L /root/admin-openrc && $(stat -c '%U:%G %a %h' /root/admin-openrc) == 'root:root 600 1' ]] || die "admin-openrc unsafe"
source /root/admin-openrc
openstack token issue -f value -c expires >/dev/null || die "token failed"
tmp=$(mktemp -d /root/.task5d-start.XXXXXX); trap 'rm -f -- "$tmp"/*.json; rmdir -- "$tmp" 2>/dev/null || :; unset OS_PASSWORD' EXIT
openstack project list --domain default -f json >"$tmp/projects.json" || die "project query failed"
openstack role list -f json >"$tmp/roles.json" || die "role query failed"
service_project_id=$(python3 -c "import json,sys;r=[x for x in json.load(open(sys.argv[1])) if x.get('Name')=='service'];assert len(r)==1 and r[0].get('ID');print(r[0]['ID'])" "$tmp/projects.json") || die "service project classifier failed"
admin_role_id=$(python3 -c "import json,sys;r=[x for x in json.load(open(sys.argv[1])) if x.get('Name')=='admin'];assert len(r)==1 and r[0].get('ID');print(r[0]['ID'])" "$tmp/roles.json") || die "global admin role classifier failed"
openstack project show "$service_project_id" -f json >"$tmp/project-show.json" || die "service project show failed"
openstack role show "$admin_role_id" -f json >"$tmp/role-show.json" || die "global admin role show failed"
openstack user list --domain default -f json >"$tmp/users.json" || die "user query failed"
openstack service list -f json >"$tmp/services.json" || die "service query failed"
openstack endpoint list -f json >"$tmp/endpoints.json" || die "endpoint query failed"
openstack image list -f json >"$tmp/images.json" || die "image query failed"
python3 - "$tmp" <<'PY'
import json,pathlib,sys
p=pathlib.Path(sys.argv[1]); load=lambda n:json.loads((p/n).read_text())
projects,roles,project_show,role_show,users,services,endpoints,images=(load(n) for n in ('projects.json','roles.json','project-show.json','role-show.json','users.json','services.json','endpoints.json','images.json'))
project=[x for x in projects if x.get('Name')=='service']
role=[x for x in roles if x.get('Name')=='admin']
if len(project)!=1 or not project[0].get('ID'): raise SystemExit('service project cardinality mismatch')
if len(role)!=1 or not role[0].get('ID'): raise SystemExit('global admin role cardinality mismatch')
if not (project_show.get('id')==project[0]['ID'] and project_show.get('name')=='service' and project_show.get('domain_id')=='default' and project_show.get('enabled') is True and project_show.get('is_domain') is False): raise SystemExit('service project property mismatch')
if not (role_show.get('id')==role[0]['ID'] and role_show.get('name')=='admin' and role_show.get('domain_id') is None): raise SystemExit('global admin role property mismatch')
if len([x for x in users if x.get('Name')=='glance'])!=1: raise SystemExit('Glance user mismatch')
if [x for x in users if x.get('Name') in {'placement','nova','neutron','cinder','swift'}]: raise SystemExit('Placement or later Keystone user exists')
for typ,name,url in (('identity','keystone','http://controller:5000/v3/'),('image','glance','http://controller:9292')):
    svc=[x for x in services if x.get('Type')==typ]
    if len(svc)!=1 or svc[0].get('Name')!=name: raise SystemExit(f'{typ} service mismatch')
    eps=[x for x in endpoints if x.get('Service Type')==typ]
    if len(eps)!=3 or {x.get('Interface') for x in eps}!={'public','internal','admin'}: raise SystemExit(f'{typ} endpoints mismatch')
    if any(x.get('Region')!='RegionOne' or x.get('URL')!=url for x in eps): raise SystemExit(f'{typ} endpoint binding mismatch')
later_types={'placement','compute','network','volume','volumev2','volumev3','object-store'}
if [x for x in services if x.get('Type') in later_types or x.get('Name') in {'placement','nova','neutron','cinder','swift'}]: raise SystemExit('Placement or later service exists')
if [x for x in endpoints if x.get('Service Type') in later_types or x.get('URL')=='http://controller:8778']: raise SystemExit('Placement or later endpoint exists')
if images: raise SystemExit('retained task image exists')
PY
rm -f -- "$tmp"/*.json; rmdir -- "$tmp"; trap - EXIT; unset OS_PASSWORD
printf 'CONTROLLER_GATE=PASS\n'
'''

COMPUTE_GATE = r'''set -Eeuo pipefail
die(){ printf 'ERROR: %s\n' "$*" >&2; exit 1; }
absent(){ local p=$1 out rc; if out=$(LC_ALL=C rpm -q "$p" 2>&1); then die "unexpected package: $p"; else rc=$?; [[ $rc -eq 1 && $out == "package $p is not installed" ]] || die "RPM probe failed: $p"; fi; }
EXPECTED_PLACEMENT_RPMS=(openstack-placement-api openstack-placement-common python3-microversion-parse python3-os-resource-classes python3-os-traits python3-placement)
assert_placement_transaction_absent(){ local installed=0 p out rc; for p in "${EXPECTED_PLACEMENT_RPMS[@]}"; do if out=$(LC_ALL=C rpm -q "$p" 2>&1); then installed=$((installed+1)); else rc=$?; [[ $rc -eq 1 && $out == "package $p is not installed" ]] || die "Placement RPM probe failed: $p"; fi; done; if (( installed>0 && installed<${#EXPECTED_PLACEMENT_RPMS[@]} )); then die "partial Placement package state: $installed/6"; fi; (( installed==0 )) || die "complete Placement package transaction already present"; }
disk(){ local d=$1 root chain facts sig rc; [[ -b $d && $(blockdev --getsize64 "$d") == 53687091200 && $(lsblk -dnro TYPE "$d") == disk ]] || die "$d identity drift"; root=$(readlink -f "$(findmnt -nro SOURCE /)"); chain=$(lsblk -s -nrpo NAME "$root"); grep -Fxq "$d" <<<"$chain" && die "$d is a root ancestor"; [[ $(lsblk -nrpo NAME "$d" | sed '/^$/d' | wc -l) -eq 1 ]] || die "$d has children"; facts=$(lsblk -dnro FSTYPE,MOUNTPOINT "$d"); [[ -z ${facts//[[:space:]]/} ]] || die "$d has filesystem or mount"; sig=$(wipefs --no-act --noheadings --output TYPE "$d"); [[ -z ${sig//[[:space:]]/} ]] || die "$d has signature"; if blkid -p "$d" >/dev/null 2>&1; then die "$d contains signature"; else rc=$?; [[ $rc -eq 2 ]] || die "$d blkid probe failed"; fi; }
[[ $(hostnamectl --static) == compute ]] || die "hostname drift"
ip -4 -o addr show ens33 | grep -Fq '192.168.234.150/24' || die "ens33 drift"
[[ -z $(ip -4 -o addr show ens34) ]] || die "ens34 must have no IPv4"
timedatectl show -p NTPSynchronized --value | grep -Fxq yes || die "clock unsynchronized"
systemctl is-active --quiet chronyd && systemctl is-enabled --quiet chronyd || die "chronyd mismatch"
dnf -q repolist --disablerepo='*' --enablerepo='openstack-local' | grep -Fq openstack-local || die "local repo missing"
assert_placement_transaction_absent
for p in openstack-nova-common openstack-nova-api openstack-nova-compute openstack-neutron-common openstack-cinder-common openstack-swift-common python3-horizon; do absent "$p"; done
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

```

本块只定义严格连接与只读门，不再提供“打印 PASS”的伪入口。后文唯一入口 `run_guarded_placement_deployment` 把完整 `run_placement_deployment` 作为 mutation callback：controller 与 compute 依次成功并关闭门禁连接以后才开始软件包阶段；任一门失败时部署阶段调用数严格为 0。controller 还会对 8778、8774、9696、8776、8080 逐端口执行失败关闭探针；监听存在或 `ss` 探针异常都会中止。

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

安装后不能只验证根包或数量。下面把 DNF 历史与当前 RPM 数据库作为两条独立证据链；两者必须得到同一组 6 个精确 NEVRA，历史仓库只能是 `@openstack-local`，动作只能是 Install，且 `zero remove/replace`。

```bash
set -Eeuo pipefail
EXACT_PLACEMENT_TRANSACTION_NEVRAS=(
  openstack-placement-api-9.0.0-1.oe2403sp2.noarch
  openstack-placement-common-9.0.0-1.oe2403sp2.noarch
  python3-microversion-parse-1.0.1-2.oe2403sp2.noarch
  python3-os-resource-classes-1.1.0-1.oe2403sp2.noarch
  python3-os-traits-2.10.0-1.oe2403sp2.noarch
  python3-placement-9.0.0-1.oe2403sp2.noarch
)
# 与交互命令 `dnf history info 7` 等价；这里固定 LC_ALL 便于机器校验。
history=$(LC_ALL=C dnf -q history info 7)
grep -Fq 'Return-Code    : Success' <<<"$history"
[[ $(grep -Ec '^[[:space:]]+Install .*@openstack-local$' <<<"$history") -eq 6 ]]
! grep -Eiq '^[[:space:]]+(Erase|Removed|Obsolet|Replac|Downgrad)' <<<"$history"
for nevra in "${EXACT_PLACEMENT_TRANSACTION_NEVRAS[@]}"; do
  grep -Fq "Install $nevra" <<<"$history"
done
installed=$(rpm -q --qf '%{NAME}-%{VERSION}-%{RELEASE}.%{ARCH}\n' \
  openstack-placement-api openstack-placement-common python3-microversion-parse \
  python3-os-resource-classes python3-os-traits python3-placement | sort)
expected=$(printf '%s\n' "${EXACT_PLACEMENT_TRANSACTION_NEVRAS[@]}" | sort)
[[ $installed == "$expected" ]]
printf 'PLACEMENT_TRANSACTION_AUDIT=PASS RPM_DELTA=6 REPO_ROWS=6 NEVRAS=6 ACTION=Install zero remove/replace\n'
```

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


def collect_placement_grant_evidence(cursor: object) -> dict:
    cursor.execute("SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME=%s",("placement",))
    if cursor.fetchall() != (("placement",),): raise RuntimeError("Placement database cardinality mismatch")
    cursor.execute("SELECT Host FROM mysql.user WHERE User=%s ORDER BY Host",("placement",))
    hosts=[row[0] for row in cursor.fetchall()]
    evidence={"hosts":hosts,"accounts":{},"proxy":[],"roles":[]}
    for host in hosts:
        grantee="'placement'@'"+host+"'"
        cursor.execute("SELECT PRIVILEGE_TYPE,IS_GRANTABLE FROM information_schema.USER_PRIVILEGES WHERE GRANTEE=%s",(grantee,))
        global_rows=[list(row) for row in cursor.fetchall()]
        cursor.execute("SELECT TABLE_SCHEMA,PRIVILEGE_TYPE,IS_GRANTABLE FROM information_schema.SCHEMA_PRIVILEGES WHERE GRANTEE=%s",(grantee,))
        schema_rows=[list(row) for row in cursor.fetchall()]
        object_rows={}
        for name in ("TABLE_PRIVILEGES","COLUMN_PRIVILEGES"):
            cursor.execute(f"SELECT * FROM information_schema.{name} WHERE GRANTEE=%s",(grantee,))
            object_rows[name.split('_')[0].lower()]=[list(row) for row in cursor.fetchall()]
        cursor.execute("SELECT Db,Routine_name,Routine_type,Proc_priv FROM mysql.procs_priv WHERE User=%s AND Host=%s",("placement",host))
        evidence["accounts"][host]={"global":global_rows,"schema":schema_rows,"table":object_rows["table"],"column":object_rows["column"],"routine":[list(row) for row in cursor.fetchall()]}
    cursor.execute("SELECT Host,User,Proxied_host,Proxied_user,With_grant FROM mysql.proxies_priv WHERE User=%s OR Proxied_user=%s",("placement","placement"))
    evidence["proxy"]=[list(row) for row in cursor.fetchall()]
    cursor.execute("SELECT Host,User,Role,Admin_option FROM mysql.roles_mapping WHERE User=%s OR Role=%s",("placement","placement"))
    evidence["roles"]=[list(row) for row in cursor.fetchall()]
    return evidence


if __name__ == "__main__":
    import pymysql
    root=pymysql.connect(unix_socket="/var/lib/mysql/mysql.sock",user="root",charset="utf8mb4")
    try:
        with root.cursor() as cursor:
            grant_evidence=collect_placement_grant_evidence(cursor)
        validate_placement_grant_evidence(grant_evidence)
    finally: root.close()
    print("PLACEMENT_GRANT_WIRING=PASS")
```

数据库创建块结束后必须立即完整执行上述 Python 块：真实路径先调用 `collect_placement_grant_evidence`，再紧接着调用 `validate_placement_grant_evidence`，任何探针异常都会阻止 Keystone 阶段。实际结果：数据库仅一份，账户主机精确为 `%`、`127.0.0.1`、`localhost`；三账户全局权限仅 `USAGE`，数据库级权限只属于 `placement.*`，表、列、例程、代理和数据库角色行均为 0，受保护 TCP 登录成功。

## Keystone 对象的分阶段创建

必须先 `source /root/admin-openrc` 并隐藏令牌输出。每一阶段都采用“查询 → 0/1/重复分类 → 必要时创建 → 重新查询 → 立即验证”的屏障；用户没有通过前不能授权，授权没有通过前不能创建服务，服务没有通过前不能创建端点。下面的核心函数可由真实 OpenStack CLI 适配器调用，也便于课堂注入错误状态进行验证。

```python
from __future__ import annotations

import json
import os
from pathlib import Path
import stat
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


def load_runtime_secret_record(path: Path = Path("/root/.openstack-lab-secrets")) -> str:
    descriptor=os.open(str(path),os.O_RDONLY|getattr(os,"O_NOFOLLOW",0))
    try:
        metadata=os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid!=0 or metadata.st_gid!=0 or stat.S_IMODE(metadata.st_mode)!=0o600 or metadata.st_nlink!=1:
            raise RuntimeError("runtime secret metadata mismatch")
        data=os.read(descriptor,65537)
        if len(data)>65536: raise RuntimeError("runtime secret too large")
    finally: os.close(descriptor)
    lines=data.decode("utf-8").splitlines()
    if len(lines)!=1 or not lines[0].startswith("OPENSTACK_DEPLOY_PASSWORD="):
        raise RuntimeError("runtime secret shape mismatch")
    value=lines[0].split("=",1)[1]
    if not value: raise RuntimeError("runtime secret is empty")
    return value


if __name__ == "__main__":
    if not os.environ.get("OS_AUTH_URL") or not os.environ.get("OS_PASSWORD"):
        raise SystemExit("source protected /root/admin-openrc first")
    executor=OpenStackExecutor()
    token_evidence=executor.query(["token","issue"])
    if not isinstance(token_evidence,dict) or not token_evidence.get("expires"):
        raise SystemExit("protected token issuance failed")
    placement_password=load_runtime_secret_record()
    identity_evidence=ensure_placement_identity_objects(placement_password,executor.query,executor.mutate)
    validate_placement_identity_evidence(identity_evidence)
    placement_password=""
    os.environ.pop("OS_PASSWORD",None)
    print("PLACEMENT_IDENTITY_WIRING=PASS")
```

真实执行前运行 `source /root/admin-openrc`，随后完整执行上述 Python 块。主路径实际构造 subprocess 适配器、从受保护文件加载秘密、隐藏令牌结果、调用 `ensure_placement_identity_objects`，并紧接着调用 `validate_placement_identity_evidence`；删除任一调用都会破坏接线契约。最终只有一个启用的 Default 域 `placement` 用户、一个绑定到 `service` 项目的全局 `admin` 授权、一个启用的 `placement:placement` 服务，以及 public/internal/admin 三个 RegionOne 端点；URL 均为 `http://controller:8778`。

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


def validate_written_placement_config(target: Path,password: str,owner_uid: int,owner_gid: int) -> None:
    metadata=target.lstat()
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid!=owner_uid or metadata.st_gid!=owner_gid or stat.S_IMODE(metadata.st_mode)!=0o640 or metadata.st_nlink!=1:
        raise RuntimeError("Placement config metadata gate failed")
    if target.read_text(encoding="utf-8")!=build_placement_config(password):
        raise RuntimeError("Placement config content gate failed")


def load_config_runtime_secret(path: Path=Path("/root/.openstack-lab-secrets")) -> str:
    fd=os.open(str(path),os.O_RDONLY|getattr(os,"O_NOFOLLOW",0))
    try:
        metadata=os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid!=0 or metadata.st_gid!=0 or stat.S_IMODE(metadata.st_mode)!=0o600 or metadata.st_nlink!=1:
            raise RuntimeError("runtime secret metadata mismatch")
        lines=os.read(fd,65537).decode("utf-8").splitlines()
    finally: os.close(fd)
    if len(lines)!=1 or not lines[0].startswith("OPENSTACK_DEPLOY_PASSWORD=") or not lines[0].split("=",1)[1]:
        raise RuntimeError("runtime secret shape mismatch")
    return lines[0].split("=",1)[1]


if __name__ == "__main__":
    import grp
    config_path=Path("/etc/placement/placement.conf")
    placement_gid=grp.getgrnam("placement").gr_gid
    runtime_password=load_config_runtime_secret()
    write_placement_config(config_path,runtime_password,0,placement_gid)
    validate_written_placement_config(config_path,runtime_password,0,placement_gid)
    runtime_password=""
    print("PLACEMENT_CONFIG_WIRING=PASS")
```

真实路径执行上述完整代码块：秘密加载后立即调用 `write_placement_config`，并紧接着调用 `validate_written_placement_config`，通过后才允许模式同步。真实文件为 root:placement、0640。脱敏快照把数据库 URL 中的编码口令替换为 `<URL_ENCODED_DB_PASSWORD>`，把服务口令替换为 `<SERVICE_PASSWORD>`；替换后仍保留“数据库 URL 必须编码”的教学含义。

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

软件包默认 `/etc/httpd/conf.d/00-placement-api.conf` 除 8778 虚拟主机外，还在服务器全局声明 `Alias /placement-api` 和 `Location /placement-api`。实际复审前证明当前文件仍与既有 package-default 备份逐字一致；当时 `http://controller:5000/placement-api` 返回 Placement HTTP 200，说明 Placement 被暴露在 Keystone 端口。保留 package-default 备份不变，手工硬化当前文件：只保留 8778 VirtualHost 内的根 WSGI，删除全局 Alias/Location。

下面是实际写入器。它只接受“当前等于既有 package-default”或“当前已经等于硬化结果”两种状态；未知第三状态停止。写入使用排他临时文件、inode 清理、文件和目录 fsync、原子替换，最终 owner/mode 为 root:root、0640。

```python
from __future__ import annotations

import os
from pathlib import Path
import stat
import uuid


HARDENED_PLACEMENT_WSGI = '''Listen 8778

<VirtualHost *:8778>
  WSGIProcessGroup placement-api
  WSGIApplicationGroup %{GLOBAL}
  WSGIPassAuthorization On
  WSGIDaemonProcess placement-api processes=3 threads=1 user=placement group=placement
  WSGIScriptAlias / /usr/bin/placement-api
  <IfVersion >= 2.4>
    ErrorLogFormat "%M"
  </IfVersion>
  ErrorLog /var/log/placement/placement-api.log
  <Directory /usr/bin>
    <IfVersion >= 2.4>
      Require all granted
    </IfVersion>
    <IfVersion < 2.4>
      Order allow,deny
      Allow from all
    </IfVersion>
  </Directory>
</VirtualHost>
'''


def write_hardened_placement_wsgi(
    target: Path,owner_uid: int,owner_gid: int,ops: object=os,nonce: str|None=None
) -> None:
    nonce=nonce or uuid.uuid4().hex
    temporary=target.parent/f".00-placement-api.conf.task5d.{nonce}"
    flags=ops.O_WRONLY|ops.O_CREAT|ops.O_EXCL|getattr(ops,"O_NOFOLLOW",0)
    descriptor=None;created=False;identity=None
    try:
        descriptor=ops.open(str(temporary),flags,0o640);created=True
        metadata=ops.fstat(descriptor);identity=(metadata.st_dev,metadata.st_ino)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink!=1: raise RuntimeError("unsafe WSGI temporary")
        ops.fchmod(descriptor,0o640);ops.fchown(descriptor,owner_uid,owner_gid)
        data=HARDENED_PLACEMENT_WSGI.encode("utf-8");offset=0
        while offset<len(data):
            written=ops.write(descriptor,data[offset:])
            if written<=0: raise OSError("short WSGI write")
            offset+=written
        ops.fsync(descriptor);ops.close(descriptor);descriptor=None
        ops.replace(str(temporary),str(target));created=False
        directory=ops.open(str(target.parent),ops.O_RDONLY|getattr(ops,"O_DIRECTORY",0))
        try:ops.fsync(directory)
        finally:ops.close(directory)
    finally:
        if descriptor is not None:ops.close(descriptor)
        if created and identity is not None:
            try:current=ops.lstat(temporary)
            except FileNotFoundError:current=None
            if current is not None and (current.st_dev,current.st_ino)==identity and stat.S_ISREG(current.st_mode) and current.st_nlink==1:ops.unlink(temporary)


def harden_package_placement_wsgi(
    target: Path=Path("/etc/httpd/conf.d/00-placement-api.conf"),
    backup: Path=Path("/root/openstack-lab-backups/task-5d-20260811T100131Z/00-placement-api.conf.package-default"),
) -> None:
    package_default=backup.read_text(encoding="utf-8")
    current=target.read_text(encoding="utf-8")
    if current==package_default:
        if "Alias /placement-api" not in package_default or "<Location /placement-api>" not in package_default:
            raise RuntimeError("backup is not the reviewed package default")
        write_hardened_placement_wsgi(target,0,0)
    elif current!=HARDENED_PLACEMENT_WSGI:
        raise RuntimeError("unknown Placement WSGI state")
    metadata=target.lstat()
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid!=0 or metadata.st_gid!=0 or stat.S_IMODE(metadata.st_mode)!=0o640 or metadata.st_nlink!=1:
        raise RuntimeError("hardened WSGI metadata mismatch")
    if target.read_text(encoding="utf-8")!=HARDENED_PLACEMENT_WSGI:
        raise RuntimeError("hardened WSGI content mismatch")


if __name__ == "__main__":
    harden_package_placement_wsgi()
    print("PLACEMENT_WSGI_ATOMIC_HARDEN=PASS")
```

只有模式与升级门都通过，且上述写入器与紧随其后的 Apache 配置检查通过后才能重启 Apache。

```bash
set -Eeuo pipefail
wsgi=/etc/httpd/conf.d/00-placement-api.conf
[[ $(stat -c '%U:%G %a %h' "$wsgi") == 'root:root 640 1' ]]
backup=/root/openstack-lab-backups/task-5d-20260811T100131Z/00-placement-api.conf.package-default
[[ -f $backup && ! -L $backup && $(stat -c '%U:%G %a %h' "$backup") == 'root:root 640 1' ]]
grep -Fxq 'Listen 8778' "$wsgi"
grep -Fq '<VirtualHost *:8778>' "$wsgi"
grep -Fq 'WSGIPassAuthorization On' "$wsgi"
grep -Fq 'WSGIScriptAlias / /usr/bin/placement-api' "$wsgi"
! grep -Fq 'Alias /placement-api' "$wsgi"
! grep -Fq '<Location /placement-api>' "$wsgi"
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
placement_status=$(curl --noproxy '*' -sS -o /tmp/.placement-version -w '%{http_code}' http://controller:8778/)
[[ $placement_status == 200 ]]
keystone_status=$(curl --noproxy '*' -sS -o /tmp/.keystone-version -w '%{http_code}' http://controller:5000/v3/)
[[ $keystone_status == 200 ]]
python3 - <<'PY'
import json
placement=json.load(open('/tmp/.placement-version'));versions=placement.get('versions')
if not isinstance(versions,list) or len(versions)!=1 or versions[0].get('id')!='v1.0' or versions[0].get('status')!='CURRENT' or versions[0].get('max_version')!='1.39':raise SystemExit('8778 is not exact Placement')
keystone=json.load(open('/tmp/.keystone-version'));version=keystone.get('version',{})
if not str(version.get('id','')).startswith('v3.') or version.get('status') not in {'stable','CURRENT','SUPPORTED'}:raise SystemExit('5000 is not Keystone v3')
PY
for port in 80 5000; do
  [[ $(curl --noproxy '*' -sS -o /tmp/.non-placement-$port -w '%{http_code}' "http://controller:$port/placement-api") == 404 ]]
done
rm -f /tmp/.placement-version /tmp/.keystone-version /tmp/.non-placement-80 /tmp/.non-placement-5000
```

复审硬化实际结果：`TASK5D_APACHE_HARDEN=PASS WSGI=root-vhost-8778-only PLACEMENT=8778:200:v1.0:CURRENT:1.39 KEYSTONE=5000:200:v3 PATH80=404 PATH5000=404`。既有 package-default 备份保持未改；当前快照记录硬化后的有效 WSGI 文件。

版本发现必须同时验证状态码和 JSON 结构，不能只以 `curl` 退出码判断服务可用。

先运行 `source /root/admin-openrc`，再在同一受保护 shell 中完整执行紧随其后的 Python 块；该块自行隐藏捕获令牌并实际调用严格 validator，而不是只定义函数。完成后立即清除变量。

```bash
source /root/admin-openrc
# 现在完整执行下面的 Python 块；看到 PASS 后运行 unset OS_PASSWORD。
```

```python
import json
import os
import subprocess


def validate_placement_version_response(status: int, payload: dict) -> dict:
    if status != 200:
        raise RuntimeError(f"unexpected Placement version HTTP status: {status}")
    versions=payload.get("versions")
    if not isinstance(versions,list) or len(versions)!=1:
        raise ValueError("Placement version cardinality mismatch")
    version=versions[0]
    if not (
        version.get("id")=="v1.0" and version.get("status")=="CURRENT"
        and version.get("max_version")=="1.39"
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
        if not isinstance(row,dict) or not row.get("uuid") or not row.get("name") or "generation" not in row:
            raise ValueError("invalid resource-provider row")
    return providers


def run_placement_api_validation(request: object) -> dict:
    version_status,version_payload=request("/",False)
    validate_placement_version_response(version_status,version_payload)
    unauth_status,_unauth_payload=request("/resource_providers",False)
    if unauth_status!=401: raise RuntimeError("unauthenticated Placement query must return 401")
    provider_status,provider_payload=request("/resource_providers",True)
    providers=classify_resource_provider_response(provider_status,provider_payload)
    return {"status":"PASS","providers":len(providers)}


def curl_placement_request(path: str,authenticated: bool) -> tuple[int,dict]:
    command=["curl","--noproxy","*","-sS","-w","\\n%{http_code}","-H","Accept: application/json"]
    if authenticated:
        token=os.environ.get("PLACEMENT_TOKEN","")
        if not token: raise RuntimeError("protected Placement token is absent")
        command.extend(["-H",f"X-Auth-Token: {token}","-H","OpenStack-API-Version: placement 1.39"])
    command.append("http://controller:8778"+path)
    completed=subprocess.run(command,text=True,capture_output=True)
    if completed.returncode: raise RuntimeError("Placement curl transport failed")
    body,separator,status=completed.stdout.rpartition("\n")
    if not separator or not status.isdigit(): raise RuntimeError("Placement curl status framing failed")
    try: payload=json.loads(body) if body else {}
    except json.JSONDecodeError as error: raise ValueError("Placement response is not JSON") from error
    return int(status),payload


def acquire_placement_token() -> str:
    completed=subprocess.run(["openstack","token","issue","-f","value","-c","id"],text=True,capture_output=True)
    token=completed.stdout.strip()
    if completed.returncode or not token: raise RuntimeError("protected token acquisition failed")
    return token


if __name__ == "__main__":
    os.environ["PLACEMENT_TOKEN"]=acquire_placement_token()
    api_evidence=run_placement_api_validation(curl_placement_request)
    os.environ.pop("PLACEMENT_TOKEN",None)
    print(f"PLACEMENT_API_WIRING=PASS PROVIDERS={api_evidence['providers']}")
```

常规环境可使用 `openstack resource provider list`。本地教学仓库没有 `python3-osc-placement`，系统也没有相应 CLI entry point，因此该命令返回精确的 `Unknown command ['resource', 'provider', 'list']`。这不是认证、端点或策略故障；在禁止外部源的边界内，本节只保留上面的 `run_placement_api_validation(curl_placement_request)` 作为唯一权威验证入口。它携带仅存在于内存中的 Keystone 令牌，同时严格验证 8778 根版本体、未认证 401、认证 200、JSON 列表和非空成员结构；不再并列保留仅检查 HTTP 200 与首个版本 ID 的弱 Bash 实现。不能退化为未认证请求，也不能为了得到非空结果手工创建资源提供者。

实际结果：根版本发现为 HTTP 200、`v1.0`；未认证资源提供者路径为 401；认证查询为 HTTP 200 且 `resource_providers=[]`。因此结论是“查询成功、当前 0 个资源提供者”，而不是“查询失败”。资源提供者应在下一切片由 Nova compute 自动注册。

## 跨切片收口审计

controller 最终要求 chronyd、MariaDB、RabbitMQ、Memcached、HTTPD 和 Glance API 都 active+enabled；Keystone 令牌、Glance 镜像列表与 Placement 认证查询都必须成功；identity、image、placement 三个服务及各自三个端点必须精确；Nova 及后续软件包、数据库、用户、服务和端点必须缺席。

以下是实际最终双节点审计入口。controller 完全通过后才连接 compute；任一节点探针异常都会抛错，不会返回总 PASS。

```python
from __future__ import annotations

from pathlib import Path
from typing import Callable

import paramiko


FINAL_HOSTS={
 "controller":("192.168.234.151",Path(".superpowers/sdd/known_hosts.controller")),
 "compute":("192.168.234.150",Path(".superpowers/sdd/known_hosts.compute")),
}

FINAL_CONTROLLER_AUDIT=r'''set -Eeuo pipefail
die(){ printf 'ERROR: %s\n' "$*" >&2;exit 1; }
absent(){ local p=$1 o rc;if o=$(LC_ALL=C rpm -q "$p" 2>&1);then die "later package: $p";else rc=$?;[[ $rc -eq 1 && $o == "package $p is not installed" ]]||die "RPM probe failed: $p";fi; }
load_secret(){ local n=$1 p=/root/.openstack-lab-secrets m v rc;local -a a=();[[ -f $p && ! -L $p ]]||return 1;if readlink -- "$p">/dev/null 2>&1;then return 1;else rc=$?;[[ $rc -eq 1 ]]||return 1;fi;m=$(stat -c '%U:%G %a %h' "$p");[[ $m == 'root:root 600 1' ]]||return 1;mapfile -t a <"$p";[[ ${a[0]+x} && ! ${a[1]+x} && ${a[0]} =~ ^OPENSTACK_DEPLOY_PASSWORD=(.+)$ ]]||return 1;v=${BASH_REMATCH[1]};printf -v "$n" '%s' "$v"; }
[[ $(hostnamectl --static) == controller ]]||die 'hostname';ip -4 -o addr show ens33|grep -Fq '192.168.234.151/24'||die 'ens33';[[ -z $(ip -4 -o addr show ens34) ]]||die 'ens34'
timedatectl show -p NTPSynchronized --value|grep -Fxq yes||die 'clock';dnf -q repolist --disablerepo='*' --enablerepo='openstack-local'|grep -Fq openstack-local||die 'repo'
for s in chronyd mariadb rabbitmq-server memcached httpd openstack-glance-api;do systemctl is-active --quiet "$s"&&systemctl is-enabled --quiet "$s"||die "$s";done
rpm -q openstack-keystone openstack-glance openstack-glance-api openstack-placement-api openstack-placement-common python3-microversion-parse python3-os-resource-classes python3-os-traits python3-placement >/dev/null||die 'required packages'
for p in openstack-nova-common openstack-nova-api openstack-nova-compute openstack-neutron-common openstack-cinder-common openstack-swift-common python3-horizon;do absent "$p";done
for db in nova nova_api nova_cell0 neutron cinder;do [[ $(mysql -uroot -NBe "SELECT COUNT(*) FROM information_schema.SCHEMATA WHERE SCHEMA_NAME='$db'") == 0 ]]||die "later DB $db";done
[[ $(mysql -uroot -NBe "SELECT COUNT(*) FROM mysql.user WHERE User IN ('nova','neutron','cinder','swift')") == 0 ]]||die 'later DB user'
[[ $(mysql -uroot -NBe "SELECT Host FROM mysql.user WHERE User='placement' ORDER BY Host"|paste -sd, -) == '%,127.0.0.1,localhost' ]]||die 'Placement grant hosts'
tables=$(mysql -uroot -NBe "SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA='placement'")||die 'tables'
TABLES="$tables" python3 - <<'PY'
import os
a={x for x in os.environ['TABLES'].splitlines() if x};e={'alembic_version','allocations','consumer_types','consumers','inventories','placement_aggregates','projects','resource_classes','resource_provider_aggregates','resource_provider_traits','resource_providers','traits','users'}
if a!=e or len(a)!=13:raise SystemExit('exact Placement table set mismatch')
PY
[[ $(mysql -uroot -NBe 'SELECT version_num FROM placement.alembic_version') == 422ece571366 ]]||die 'head'
upgrade=$(placement-status upgrade check)||die 'upgrade';[[ $(grep -Fc 'Result: Success'<<<"$upgrade") -eq 3 ]]||die 'upgrade results';grep -Eq 'Result: (Failure|Warning)'<<<"$upgrade"&&die 'upgrade non-success'||:
load_secret OPENSTACK_DEPLOY_PASSWORD||die 'secret';export OPENSTACK_DEPLOY_PASSWORD
python3 - <<'PY'
import configparser,os,pathlib,yaml
from urllib.parse import quote
p=configparser.RawConfigParser(strict=True);p.read('/etc/placement/placement.conf')
e={('placement_database','connection'):'mysql+pymysql://placement:'+quote(os.environ['OPENSTACK_DEPLOY_PASSWORD'],safe='')+'@127.0.0.1/placement',('api','auth_strategy'):'keystone',('keystone_authtoken','www_authenticate_uri'):'http://controller:5000',('keystone_authtoken','auth_url'):'http://controller:5000/v3',('keystone_authtoken','memcached_servers'):'controller:11211',('keystone_authtoken','auth_type'):'password',('keystone_authtoken','project_domain_name'):'Default',('keystone_authtoken','user_domain_name'):'Default',('keystone_authtoken','project_name'):'service',('keystone_authtoken','username'):'placement',('keystone_authtoken','password'):os.environ['OPENSTACK_DEPLOY_PASSWORD'],('oslo_policy','policy_file'):'policy.yaml'}
for k,v in e.items():
 if p.get(*k,raw=True)!=v:raise SystemExit(f'config mismatch {k}')
if yaml.safe_load(pathlib.Path('/etc/placement/policy.yaml').read_text()) not in (None,{}):raise SystemExit('policy override')
PY
unset OPENSTACK_DEPLOY_PASSWORD;unset -f load_secret
[[ $(stat -c '%U:%G %a %h' /etc/placement/placement.conf) == 'root:placement 640 1' ]]||die 'config metadata';[[ $(stat -c '%U:%G %a %h' /etc/placement/policy.yaml) == 'root:placement 640 1' ]]||die 'policy metadata'
wsgi=/etc/httpd/conf.d/00-placement-api.conf;[[ $(stat -c '%U:%G %a %h' "$wsgi") == 'root:root 640 1' ]]||die 'WSGI metadata';grep -Fq 'WSGIScriptAlias / /usr/bin/placement-api' "$wsgi"||die 'WSGI root';grep -Fq 'Alias /placement-api' "$wsgi"&&die 'global alias'||:;grep -Fq '<Location /placement-api>' "$wsgi"&&die 'global location'||:;apachectl configtest 2>&1|grep -Fxq 'Syntax OK'||die 'Apache syntax'
for port in 5000 8778 9292;do [[ $(ss -H -lntp "( sport = :$port )"|sed '/^$/d'|wc -l) -eq 1 ]]||die "listener $port";done
for port in 8774 9696 8776 8080;do [[ -z $(ss -H -lnt "( sport = :$port )") ]]||die "later listener $port";done
tmp=$(mktemp -d /root/.task5d-final-doc.XXXXXX);cleanup(){ rm -f -- "$tmp"/*;rmdir -- "$tmp" 2>/dev/null||:;unset OS_PASSWORD token;};trap cleanup EXIT
[[ $(curl --noproxy '*' -sS -o "$tmp/placement.json" -w '%{http_code}' http://controller:8778/) == 200 ]]||die 'Placement HTTP'
[[ $(curl --noproxy '*' -sS -o "$tmp/keystone.json" -w '%{http_code}' http://controller:5000/v3/) == 200 ]]||die 'Keystone HTTP'
for port in 80 5000;do [[ $(curl --noproxy '*' -sS -o "$tmp/path-$port" -w '%{http_code}' "http://controller:$port/placement-api") == 404 ]]||die "Placement outside 8778: $port";done
python3 - "$tmp" <<'PY'
import json,pathlib,sys
p=pathlib.Path(sys.argv[1]);pv=json.loads((p/'placement.json').read_text()).get('versions');kv=json.loads((p/'keystone.json').read_text()).get('version',{})
if not isinstance(pv,list) or len(pv)!=1 or pv[0].get('id')!='v1.0' or pv[0].get('status')!='CURRENT' or pv[0].get('max_version')!='1.39':raise SystemExit('8778 not exact Placement')
if not str(kv.get('id','')).startswith('v3.') or kv.get('status') not in {'stable','CURRENT','SUPPORTED'}:raise SystemExit('5000 not Keystone')
PY
source /root/admin-openrc||die 'openrc';openstack token issue -f value -c expires>/dev/null||die 'token'
openstack project list --domain default -f json>"$tmp/projects.json"||die 'projects';openstack role list -f json>"$tmp/roles.json"||die 'roles';openstack user list --domain default -f json>"$tmp/users.json"||die 'users';openstack service list -f json>"$tmp/services.json"||die 'services';openstack endpoint list -f json>"$tmp/endpoints.json"||die 'endpoints';openstack image list -f json>"$tmp/images.json"||die 'images'
python3 - "$tmp" <<'PY'
import json,pathlib,subprocess,sys
p=pathlib.Path(sys.argv[1]);load=lambda n:json.loads((p/n).read_text());projects,roles,users,services,endpoints,images=(load(x) for x in ('projects.json','roles.json','users.json','services.json','endpoints.json','images.json'))
project=[x for x in projects if x.get('Name')=='service'];role=[x for x in roles if x.get('Name')=='admin']
if len(project)!=1 or len(role)!=1:raise SystemExit('project/role cardinality')
expected={'identity':('keystone','http://controller:5000/v3/'),'image':('glance','http://controller:9292'),'placement':('placement','http://controller:8778')}
if len(services)!=3 or {x.get('Type') for x in services}!=set(expected):raise SystemExit('exact three services mismatch')
for typ,(name,url) in expected.items():
 s=[x for x in services if x.get('Type')==typ and x.get('Name')==name]
 if len(s)!=1:raise SystemExit(f'{typ} service mismatch')
 shown=json.loads(subprocess.run(['openstack','service','show',s[0]['ID'],'-f','json'],text=True,capture_output=True,check=True).stdout)
 if shown.get('enabled') is not True:raise SystemExit(f'{typ} service disabled')
 eps=[x for x in endpoints if x.get('Service Type')==typ]
 if len(eps)!=3 or {x.get('Interface') for x in eps}!={'public','internal','admin'} or any(x.get('Region')!='RegionOne' or x.get('URL')!=url for x in eps):raise SystemExit(f'{typ} endpoint mismatch')
 for ep in eps:
  detail=json.loads(subprocess.run(['openstack','endpoint','show',ep['ID'],'-f','json'],text=True,capture_output=True,check=True).stdout)
  if detail.get('service_id')!=s[0]['ID'] or detail.get('enabled') is not True:raise SystemExit(f'{typ} endpoint binding')
for name in ('glance','placement'):
 u=[x for x in users if x.get('Name')==name]
 if len(u)!=1:raise SystemExit(f'{name} user')
 detail=json.loads(subprocess.run(['openstack','user','show',u[0]['ID'],'-f','json'],text=True,capture_output=True,check=True).stdout)
 if detail.get('enabled') is not True or detail.get('domain_id')!='default':raise SystemExit(f'{name} user properties')
 a=json.loads(subprocess.run(['openstack','role','assignment','list','--user',u[0]['ID'],'-f','json'],text=True,capture_output=True,check=True).stdout)
 if len(a)!=1 or a[0].get('Role')!=role[0]['ID'] or a[0].get('Project')!=project[0]['ID'] or a[0].get('User')!=u[0]['ID']:raise SystemExit(f'{name} assignment')
if any(x.get('Name') in {'nova','neutron','cinder','swift'} for x in users):raise SystemExit('later user')
if len(endpoints)!=9:raise SystemExit('exact nine endpoints mismatch')
if images:raise SystemExit('retained image')
PY
token=$(openstack token issue -f value -c id)||die 'token capture';[[ -n $token ]]||die 'empty token'
[[ $(curl --noproxy '*' -sS -o "$tmp/providers.json" -w '%{http_code}' -H "X-Auth-Token: $token" -H 'OpenStack-API-Version: placement 1.39' http://controller:8778/resource_providers) == 200 ]]||die 'provider HTTP';unset token
python3 - "$tmp/providers.json" <<'PY'
import json,sys
p=json.load(open(sys.argv[1])).get('resource_providers')
if not isinstance(p,list) or p:raise SystemExit('authenticated provider result is not exact empty list')
PY
cleanup;trap - EXIT
[[ -z $(find /root -mindepth 1 -maxdepth 1 -name '.task5d-*' -print) ]]||die 'Task5D temporary remains'
printf 'FINAL_CONTROLLER_AUDIT=PASS SERVICES=3 ENDPOINTS=9 TABLES=13 HEAD=422ece571366 UPGRADE=3 PROVIDERS=0 LATER=0 TEMP=0\n'
'''

FINAL_COMPUTE_AUDIT=r'''set -Eeuo pipefail
die(){ printf 'ERROR: %s\n' "$*" >&2;exit 1; }
absent(){ local p=$1 o rc;if o=$(LC_ALL=C rpm -q "$p" 2>&1);then die "unexpected package $p";else rc=$?;[[ $rc -eq 1 && $o == "package $p is not installed" ]]||die "RPM probe $p";fi; }
disk(){ local d=$1 root chain facts sig rc;[[ -b $d && $(blockdev --getsize64 "$d") == 53687091200 && $(lsblk -dnro TYPE "$d") == disk ]]||die "$d identity";root=$(readlink -f "$(findmnt -nro SOURCE /)")||die 'root';chain=$(lsblk -s -nrpo NAME "$root")||die 'ancestry';grep -Fxq "$d"<<<"$chain"&&die "$d root ancestor";[[ $(lsblk -nrpo NAME "$d"|sed '/^$/d'|wc -l) -eq 1 ]]||die "$d children";facts=$(lsblk -dnro FSTYPE,MOUNTPOINT "$d")||die "$d facts";[[ -z ${facts//[[:space:]]/} ]]||die "$d filesystem";sig=$(wipefs --no-act --noheadings --output TYPE "$d")||die "$d wipefs";[[ -z ${sig//[[:space:]]/} ]]||die "$d signature";if blkid -p "$d">/dev/null 2>&1;then die "$d blkid signature";else rc=$?;[[ $rc -eq 2 ]]||die "$d blkid probe";fi; }
[[ $(hostnamectl --static) == compute ]]||die 'hostname';ip -4 -o addr show ens33|grep -Fq '192.168.234.150/24'||die 'ens33';[[ -z $(ip -4 -o addr show ens34) ]]||die 'ens34';timedatectl show -p NTPSynchronized --value|grep -Fxq yes||die 'clock';systemctl is-active --quiet chronyd&&systemctl is-enabled --quiet chronyd||die 'chronyd';dnf -q repolist --disablerepo='*' --enablerepo='openstack-local'|grep -Fq openstack-local||die 'repo'
for p in openstack-placement-api openstack-placement-common python3-microversion-parse python3-os-resource-classes python3-os-traits python3-placement openstack-nova-common openstack-nova-api openstack-nova-compute openstack-neutron-common openstack-cinder-common openstack-swift-common python3-horizon;do absent "$p";done
for port in 5000 8778 9292 8774 9696 8776 8080;do [[ -z $(ss -H -lnt "( sport = :$port )") ]]||die "unexpected listener $port";done
disk /dev/sdb;disk /dev/sdc
[[ -z $(find /root -mindepth 1 -maxdepth 1 -name '.task5d-*' -print) ]]||die 'Task5D temp'
printf 'FINAL_COMPUTE_AUDIT=PASS PLACEMENT_AND_LATER_PACKAGES=0 SDB=blank50G SDC=blank50G TEMP=0\n'
'''


def connect_final_node(name: str,password: str) -> paramiko.SSHClient:
    host,known_hosts=FINAL_HOSTS[name];client=paramiko.SSHClient();client.load_host_keys(str(known_hosts));client.set_missing_host_key_policy(paramiko.RejectPolicy());client.connect(host,username="root",password=password,look_for_keys=False,allow_agent=False,timeout=10,auth_timeout=10,banner_timeout=10);return client


def run_final_script(client: paramiko.SSHClient,script: str) -> None:
    stdin,stdout,stderr=client.exec_command("bash -s");stdin.write(script);stdin.channel.shutdown_write();rc=stdout.channel.recv_exit_status()
    if rc:raise RuntimeError(stderr.read().decode("utf-8","replace"))


def run_placement_final_audits(password: str,connector: Callable|None=None,runner: Callable|None=None) -> dict:
    connector=connector or connect_final_node;runner=runner or run_final_script
    for name,script in (("controller",FINAL_CONTROLLER_AUDIT),("compute",FINAL_COMPUTE_AUDIT)):
        client=connector(name,password)
        try:runner(client,script)
        finally:client.close()
    return {"status":"FINAL_AUDIT_PASS"}
```

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

初次实现的审计结果为 `CONTROLLER_TASK5D_FINAL_AUDIT=PASS` 和 `COMPUTE_TASK5D_FINAL_AUDIT=PASS`。复审补强后直接从本节 `FINAL_CONTROLLER_AUDIT`、`FINAL_COMPUTE_AUDIT` 常量提取并远端执行，结果为：`FINAL_CONTROLLER_AUDIT=PASS SERVICES=3 ENDPOINTS=9 TABLES=13 HEAD=422ece571366 UPGRADE=3 PROVIDERS=0 LATER=0 TEMP=0`；`FINAL_COMPUTE_AUDIT=PASS PLACEMENT_AND_LATER_PACKAGES=0 SDB=blank50G SDC=blank50G TEMP=0`。

### 真实依赖接线驱动器

各节代码不是只定义不用的函数。下面的依赖驱动器把软件包证据、授权 collector/validator、subprocess 身份适配器、秘密加载、身份 ensure/validator、原子 Placement 配置写入/复核、模式、升级、Apache、实际 HTTP API validator 和最终双节点审计串成唯一顺序。每个写调用后都紧接只读 gate；任一异常自然短路，后续方法不会执行。`run_guarded_placement_deployment` 是唯一执行入口：它先实际调用前文严格 Paramiko 双节点门，再把完整 `run_placement_deployment(runtime)` 作为 mutation callback；不能用打印 PASS 的回调代替。`runtime` 是把本节各个已给出的远端阶段封装为同名方法的部署适配器，连接对象不跨门禁阶段复用。

```python
def run_placement_deployment(runtime: object) -> dict:
    package_evidence=runtime.package_stage()
    runtime.validate_package_evidence(package_evidence)

    grant_cursor=runtime.database_and_grant_stage()
    grant_evidence=collect_placement_grant_evidence(grant_cursor)
    validate_placement_grant_evidence(grant_evidence)

    placement_password=runtime.load_runtime_secret()
    try:
        executor=OpenStackExecutor()
        identity_evidence=ensure_placement_identity_objects(placement_password,executor.query,executor.mutate)
        validate_placement_identity_evidence(identity_evidence)

        write_placement_config(runtime.config_path,placement_password,0,runtime.placement_gid)
        validate_written_placement_config(runtime.config_path,placement_password,0,runtime.placement_gid)

        schema_evidence=runtime.schema_stage()
        runtime.validate_schema_evidence(schema_evidence)
        upgrade_evidence=runtime.upgrade_stage()
        runtime.validate_upgrade_evidence(upgrade_evidence)
        apache_evidence=runtime.apache_hardening_stage()
        runtime.validate_apache_evidence(apache_evidence)

        api_evidence=run_placement_api_validation(curl_placement_request)
        if api_evidence!={"status":"PASS","providers":0}:
            raise RuntimeError("Placement API gate mismatch")
        final_evidence=runtime.final_dual_node_audit()
        if final_evidence.get("status")!="FINAL_AUDIT_PASS":
            raise RuntimeError("final dual-node audit mismatch")
        return {"status":"PASS","providers":0}
    finally:
        placement_password=""


def run_guarded_placement_deployment(
    password: str,
    runtime: object,
    connector=None,
    runner=None,
) -> dict:
    result: dict[str, object]={}

    def mutation() -> None:
        result["evidence"]=run_placement_deployment(runtime)

    run_after_both_placement_gates(
        password,
        mutation,
        connector=connector or connect_node,
        runner=runner or run_gate,
    )
    evidence=result.get("evidence")
    if evidence!={"status":"PASS","providers":0}:
        raise RuntimeError("guarded Placement deployment result mismatch")
    return evidence
```

## 故障诊断与回滚边界

- 软件包事务失败：保留完整 DNF 输出与历史 ID，先审计候选仓库和删除/降级动作；不要使用不安全依赖参数继续。
- 数据库或 Keystone 出现部分对象：停止并列出精确对象、ID、绑定关系和授权元数据。不要把部分状态当作可覆盖状态，也不要删除身份对象来“重来”。
- 配置写入失败：原子替换前目标不变；只删除 inode 未变化的本任务临时文件。恢复时可使用 Task 5D 备份的 package-default 文件，但恢复配置会使当前数据库和身份对象失去服务端配置，必须作为完整变更窗口处理。
- 模式同步后校验失败：先只读比较表集合和迁移头，不重复同步来掩盖探针错误。本次 MariaDB 排序差异就是这样处理的。
- 升级检查失败：8778 必须保持未开放。根据检查项修复；不得忽略 RC 2。本次先备份并等价迁移空策略，再重新检查。
- API 认证失败：分别检查 HTTP 状态、版本体、Keystone token、端点、WSGI 授权转发和策略。CLI 插件缺失必须与 401/403/5xx 区分。

教学环境继承了 `gpgcheck=0`、SELinux Permissive、firewalld disabled 和明文 HTTP 等隔离实验选择。生产环境必须启用软件包签名、强制访问控制、防火墙和 TLS；数据库口令、服务用户口令与管理员口令应独立并由专用密钥系统轮换；Apache/Placement 应纳入高可用、容量、日志、备份和审计设计。空的策略覆盖意味着使用代码内默认策略，不等于“没有访问控制”。
