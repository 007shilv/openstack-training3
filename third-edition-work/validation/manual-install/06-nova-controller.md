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
rpm -q openstack-keystone openstack-glance openstack-glance-api openstack-placement-api openstack-placement-common python3-placement >/dev/null || die 'reviewed prerequisite absent'
for port in 5000 8778 9292; do lines=$(ss -H -lnt "( sport = :$port )") || die "listener probe failed: $port"; [[ $(sed '/^[[:space:]]*$/d' <<<"$lines" | wc -l) -eq 1 ]] || die "prerequisite listener mismatch: $port"; done
for db in keystone glance placement; do [[ $(mysql -uroot -NBe "SELECT COUNT(*) FROM information_schema.SCHEMATA WHERE SCHEMA_NAME='$db'") == 1 ]] || die "$db database mismatch"; done
[[ $(mysql -uroot -NBe "SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA='keystone'") == 49 ]] || die 'Keystone table count mismatch'
[[ $(mysql -uroot -NBe "SELECT version_num FROM keystone.alembic_version ORDER BY version_num" | paste -sd, -) == '29e87d24a316,e25ffa003242' ]] || die 'Keystone migration heads mismatch'
[[ $(mysql -uroot -NBe "SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA='glance'") == 14 ]] || die 'Glance table count mismatch'
[[ $(mysql -uroot -NBe "SELECT version_num FROM glance.alembic_version") == 2023_1_contract01 ]] || die 'Glance migration head mismatch'
[[ $(mysql -uroot -NBe "SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA='placement'") == 13 ]] || die 'Placement table count mismatch'
[[ $(mysql -uroot -NBe "SELECT version_num FROM placement.alembic_version") == 422ece571366 ]] || die 'Placement migration head mismatch'
upgrade=$(placement-status upgrade check) || die 'Placement upgrade query failed'
[[ $(grep -Fc 'Result: Success' <<<"$upgrade") -eq 3 ]] || die 'Placement upgrade success count mismatch'
! grep -Eq 'Result: (Failure|Warning)' <<<"$upgrade" || die 'Placement upgrade non-success result'
for db in nova_api nova nova_cell0 neutron cinder; do [[ $(mysql -uroot -NBe "SELECT COUNT(*) FROM information_schema.SCHEMATA WHERE SCHEMA_NAME='$db'") == 0 ]] || die "later database exists: $db"; done
[[ $(mysql -uroot -NBe "SELECT COUNT(*) FROM mysql.user WHERE User IN ('nova','neutron','cinder','swift')") == 0 ]] || die 'later DB user exists'
for p in python3-nova novnc openstack-nova-compute openstack-neutron-common openstack-cinder-common openstack-swift-common python3-horizon; do absent "$p"; done
for port in 8774 6080 9696 8776 8080; do listener_absent "$port"; done
[[ -z $(find /root -mindepth 1 -maxdepth 1 -name '.task5e-*' -print -quit) ]] || die 'Task5E temporary exists before gate'
source /root/admin-openrc
work=$(mktemp -d /root/.task5e-start.XXXXXX); trap 'rm -f -- "$work"/*; rmdir -- "$work" 2>/dev/null || :; unset OS_PASSWORD token' EXIT
openstack token issue -f value -c expires >/dev/null || die 'token failed'
openstack project list --domain default -f json >"$work/projects.json" || die 'project query failed'
openstack role list -f json >"$work/roles.json" || die 'role query failed'
openstack user list --domain default -f json >"$work/users.json" || die 'user query failed'
openstack service list -f json >"$work/services.json" || die 'service query failed'
openstack endpoint list -f json >"$work/endpoints.json" || die 'endpoint query failed'
openstack image list -f json >"$work/images.json" || die 'image query failed'
[[ $(curl --noproxy '*' -sS -o "$work/keystone.json" -w '%{http_code}' http://controller:5000/v3/) == 200 ]] || die 'Keystone API query failed'
[[ $(curl --noproxy '*' -sS -o "$work/glance.json" -w '%{http_code}' http://controller:9292/) == 300 ]] || die 'Glance API query failed'
[[ $(curl --noproxy '*' -sS -o "$work/placement.json" -w '%{http_code}' http://controller:8778/) == 200 ]] || die 'Placement API query failed'
python3 - "$work" <<'PY'
import json,pathlib,subprocess,sys
p=pathlib.Path(sys.argv[1]); load=lambda n:json.loads((p/n).read_text())
projects,roles,users,services,endpoints,images=(load(n) for n in ('projects.json','roles.json','users.json','services.json','endpoints.json','images.json'))
project=[x for x in projects if x.get('Name')=='service']; role=[x for x in roles if x.get('Name')=='admin']
if len(project)!=1 or len(role)!=1 or not project[0].get('ID') or not role[0].get('ID'): raise SystemExit('service project/global role cardinality mismatch')
shown_project=json.loads(subprocess.run(['openstack','project','show',project[0]['ID'],'-f','json'],text=True,capture_output=True,check=True).stdout)
shown_role=json.loads(subprocess.run(['openstack','role','show',role[0]['ID'],'-f','json'],text=True,capture_output=True,check=True).stdout)
if not (shown_project.get('name')=='service' and shown_project.get('domain_id')=='default' and shown_project.get('enabled') is True and shown_project.get('is_domain') is False): raise SystemExit('service project property mismatch')
if not (shown_role.get('name')=='admin' and shown_role.get('domain_id') is None): raise SystemExit('global admin role property mismatch')
expected={'identity':('keystone','http://controller:5000/v3/'),'image':('glance','http://controller:9292'),'placement':('placement','http://controller:8778')}
if len(services)!=3 or {x.get('Type') for x in services}!=set(expected): raise SystemExit('exact prerequisite services mismatch')
for typ,(name,url) in expected.items():
 rows=[x for x in services if x.get('Type')==typ and x.get('Name')==name]
 if len(rows)!=1: raise SystemExit(f'{typ} service mismatch')
 detail=json.loads(subprocess.run(['openstack','service','show',rows[0]['ID'],'-f','json'],text=True,capture_output=True,check=True).stdout)
 if detail.get('enabled') is not True: raise SystemExit(f'{typ} service disabled')
 eps=[x for x in endpoints if x.get('Service Type')==typ]
 if len(eps)!=3 or {x.get('Interface') for x in eps}!={'admin','internal','public'}: raise SystemExit(f'{typ} endpoint interface mismatch')
 if any(x.get('Region')!='RegionOne' or x.get('URL')!=url for x in eps): raise SystemExit(f'{typ} endpoint binding mismatch')
 for ep in eps:
  shown=json.loads(subprocess.run(['openstack','endpoint','show',ep['ID'],'-f','json'],text=True,capture_output=True,check=True).stdout)
  if shown.get('service_id')!=rows[0]['ID'] or shown.get('enabled') is not True: raise SystemExit(f'{typ} endpoint ID binding mismatch')
for name in ('glance','placement'):
 matches=[x for x in users if x.get('Name')==name]
 if len(matches)!=1: raise SystemExit(f'{name} service user cardinality mismatch')
 detail=json.loads(subprocess.run(['openstack','user','show',matches[0]['ID'],'-f','json'],text=True,capture_output=True,check=True).stdout)
 if detail.get('domain_id')!='default' or detail.get('enabled') is not True: raise SystemExit(f'{name} user property mismatch')
 assignments=json.loads(subprocess.run(['openstack','role','assignment','list','--user',matches[0]['ID'],'--project',project[0]['ID'],'--role',role[0]['ID'],'-f','json'],text=True,capture_output=True,check=True).stdout)
 if len(assignments)!=1 or assignments[0].get('User')!=matches[0]['ID'] or assignments[0].get('Project')!=project[0]['ID'] or assignments[0].get('Role')!=role[0]['ID']: raise SystemExit(f'{name} role binding mismatch')
if [x for x in users if x.get('Name') in {'nova','neutron','cinder','swift'}]: raise SystemExit('later user exists')
if len(endpoints)!=9: raise SystemExit('exact nine endpoints mismatch')
if images: raise SystemExit('Glance images must be empty before Nova')
keystone,glance,placement=(load(n) for n in ('keystone.json','glance.json','placement.json'))
kv=keystone.get('version',{}); gv=glance.get('versions'); pv=placement.get('versions')
if kv.get('id')!='v3.14' or kv.get('status')!='stable': raise SystemExit('Keystone API version mismatch')
if not isinstance(gv,list) or len([x for x in gv if x.get('id')=='v2.15' and x.get('status')=='CURRENT'])!=1: raise SystemExit('Glance API current version mismatch')
if not isinstance(pv,list) or len(pv)!=1 or pv[0].get('id')!='v1.0' or pv[0].get('status')!='CURRENT' or pv[0].get('max_version')!='1.39': raise SystemExit('Placement API version mismatch')
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
listener_absent(){ local port=$1 out; out=$(ss -H -lnt "( sport = :$port )") || die "listener probe failed: $port"; [[ -z $out ]] || die "unexpected listener: $port"; }
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
for s in chronyd sshd; do systemctl is-active --quiet "$s" && systemctl is-enabled --quiet "$s" || die "$s mismatch"; done
for p in python3-nova novnc openstack-nova-api openstack-nova-conductor openstack-nova-novncproxy openstack-nova-scheduler openstack-neutron-common openstack-cinder-common openstack-swift-common python3-horizon; do absent "$p"; done
[[ ! -e /etc/nova/compute_id && ! -L /etc/nova/compute_id ]] || die 'compute_id exists'
for port in 5000 6080 8774 8778 9292 9696 8776 8080; do listener_absent "$port"; done
[[ -z $(find /root -mindepth 1 -maxdepth 1 -name '.task5e-*' -print -quit) ]] || die 'Task5E temporary exists before compute gate'
disk /dev/sdb; disk /dev/sdc
printf 'COMPUTE_NOVA_GATE=PASS\n'
'''


def validate_nova_start_evidence(role: str, evidence: dict[str, object]) -> None:
    """Fail closed on the complete, non-secret evidence collected by a Nova start gate."""
    expected_host = {"controller": ("controller", "192.168.234.151/24"),
                     "compute": ("compute", "192.168.234.150/24")}
    if role not in expected_host:
        raise ValueError("unknown Nova gate role")
    hostname, address = expected_host[role]
    if evidence.get("probe_errors") != []:
        raise RuntimeError("Nova start evidence contains a probe error")
    if not (
        evidence.get("hostname") == hostname
        and evidence.get("ens33") == address
        and evidence.get("ens34_ipv4") == []
        and evidence.get("ntp") is True
        and evidence.get("enabled_repositories") == ["openstack-local"]
    ):
        raise ValueError("Nova start host or repository evidence mismatch")

    later = evidence.get("nova_and_later")
    if not isinstance(later, dict):
        raise ValueError("Nova/later absence evidence missing")
    if role == "compute":
        if later != {"packages": [], "compute_id": "absent", "temporary": []}:
            raise ValueError("compute Nova/later state is not absent")
        disks = evidence.get("disks")
        if not isinstance(disks, dict) or set(disks) != {"/dev/sdb", "/dev/sdc"}:
            raise ValueError("compute disk set mismatch")
        expected_disk = {"bytes": 53687091200, "type": "disk", "root_ancestor": False,
                         "children": 0, "filesystem": "", "mountpoint": "",
                         "wipefs": [], "blkid_rc": 2}
        if any(disks[name] != expected_disk for name in sorted(disks)):
            raise ValueError("compute blank-disk evidence mismatch")
        return

    if set(evidence.get("prerequisite_packages", [])) != {
        "openstack-keystone", "openstack-glance-api", "openstack-placement-api"
    }:
        raise ValueError("controller prerequisite package set mismatch")
    if set(evidence.get("prerequisite_services", [])) != {
        "chronyd", "mariadb", "rabbitmq-server", "memcached", "httpd", "openstack-glance-api"
    }:
        raise ValueError("controller prerequisite service set mismatch")
    project = evidence.get("service_project")
    role_row = evidence.get("global_admin_role")
    if not isinstance(project, dict) or not (
        project.get("id") and project.get("name") == "service"
        and project.get("domain_id") == "default" and project.get("enabled") is True
        and project.get("is_domain") is False
    ):
        raise ValueError("service project evidence mismatch")
    if not isinstance(role_row, dict) or not (
        role_row.get("id") and role_row.get("name") == "admin" and role_row.get("domain_id") is None
    ):
        raise ValueError("global admin role evidence mismatch")

    users = evidence.get("users")
    if not isinstance(users, list) or len(users) != 2 or {row.get("name") for row in users} != {"glance", "placement"}:
        raise ValueError("prerequisite service-user cardinality mismatch")
    for user in users:
        if not (
            user.get("id") and user.get("domain_id") == "default" and user.get("enabled") is True
            and user.get("project_id") == project["id"] and user.get("role_id") == role_row["id"]
        ):
            raise ValueError("prerequisite service-user binding mismatch")

    services = evidence.get("services")
    if not isinstance(services, list) or len(services) != 3:
        raise ValueError("prerequisite service cardinality mismatch")
    expected_services = {"identity": "keystone", "image": "glance", "placement": "placement"}
    by_type = {row.get("type"): row for row in services}
    if set(by_type) != set(expected_services) or any(
        by_type[service_type].get("name") != name
        or not by_type[service_type].get("id")
        or by_type[service_type].get("enabled") is not True
        for service_type, name in expected_services.items()
    ):
        raise ValueError("prerequisite service exact state mismatch")

    endpoints = evidence.get("endpoints")
    expected_urls = {"identity": "http://controller:5000/v3/", "image": "http://controller:9292",
                     "placement": "http://controller:8778"}
    if not isinstance(endpoints, list) or len(endpoints) != 9:
        raise ValueError("exact nine prerequisite endpoints required")
    for service_type, url in expected_urls.items():
        rows = [row for row in endpoints if row.get("service") == service_type]
        if len(rows) != 3 or {row.get("interface") for row in rows} != {"admin", "internal", "public"}:
            raise ValueError("prerequisite endpoint interface set mismatch")
        if any(
            row.get("region") != "RegionOne" or row.get("url") != url
            or row.get("enabled") is not True
            or row.get("service_id") != by_type[service_type]["id"]
            for row in rows
        ):
            raise ValueError("prerequisite endpoint binding mismatch")

    if evidence.get("apis") != {
        "keystone": {"http": 200, "id": "v3.14", "status": "stable"},
        "glance": {"http": 300, "id": "v2.15", "status": "CURRENT"},
        "placement": {"http": 200, "id": "v1.0", "status": "CURRENT", "max_version": "1.39"},
    }:
        raise ValueError("prerequisite API version evidence mismatch")
    if evidence.get("schemas") != {
        "keystone": {"tables": 49, "heads": ["29e87d24a316", "e25ffa003242"]},
        "glance": {"tables": 14, "heads": ["2023_1_contract01"]},
        "placement": {"tables": 13, "heads": ["422ece571366"]},
    }:
        raise ValueError("prerequisite schema or migration-head evidence mismatch")
    if evidence.get("placement_upgrade") != {"rc": 0, "successes": 3, "failures": 0, "warnings": 0}:
        raise ValueError("Placement upgrade evidence mismatch")
    if evidence.get("placement_providers") != []:
        raise ValueError("Placement providers must be exactly empty before Nova")
    expected_later = {"packages": [], "databases": [], "db_users": [], "users": [],
                      "services": [], "endpoints": [], "listeners": [], "temporary": []}
    if later != expected_later:
        raise ValueError("controller Nova/later state is not exactly absent")


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

完整事务不是四个根包数组。实际 DNF history 每一条新 NEVRA、升级前旧 NEVRA、动作与来源仓库都保存在 `transaction-evidence/`，并由下面的只读校验器与当前 RPM、当前 `openstack-local` repo metadata 三方逐条比较。证据文件是 JSON 文本，便于教材测试重放；其中没有口令、token 或连接 URL。

```python
from __future__ import annotations

import json
from pathlib import Path


def load_nova_transaction_evidence(path: Path) -> dict[str, object]:
    try:
        evidence = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise RuntimeError("Nova transaction evidence cannot be read") from error
    if not isinstance(evidence, dict):
        raise ValueError("Nova transaction evidence is not an object")
    return evidence


def validate_nova_transaction_evidence(node: str, evidence: dict[str, object]) -> None:
    expected = {"controller": {"transaction_id": 8, "install": 40, "upgrade": 0, "old": 0},
                "compute": {"transaction_id": 3, "install": 398, "upgrade": 5, "old": 5}}
    if node not in expected or evidence.get("node") != node:
        raise ValueError("Nova transaction node mismatch")
    contract = expected[node]
    if evidence.get("transaction_id") != contract["transaction_id"] or evidence.get("history_rc") != 0 \
            or evidence.get("rpm_rc") != 0 or evidence.get("repoquery_rc") != 0:
        raise RuntimeError("Nova transaction provenance probe failed")
    if evidence.get("unsafe_actions") != []:
        raise ValueError("unsafe DNF action present")
    history_new = evidence.get("history_new")
    history_old = evidence.get("history_old")
    current_rpm = evidence.get("current_rpm")
    repository_metadata = evidence.get("repository_metadata")
    if not all(isinstance(rows, list) for rows in (history_new, history_old, current_rpm, repository_metadata)):
        raise ValueError("Nova transaction row collection missing")
    if len(history_new) != contract["install"] + contract["upgrade"] or len(history_old) != contract["old"]:
        raise ValueError("Nova transaction history cardinality mismatch")
    if any(not isinstance(row, dict) or set(row) != {"action", "nevra", "repo"} for row in history_new):
        raise ValueError("Nova new history row shape mismatch")
    if sum(row["action"] == "Install" for row in history_new) != contract["install"] \
            or sum(row["action"] == "Upgrade" for row in history_new) != contract["upgrade"]:
        raise ValueError("Nova new history action mismatch")
    if any(row["action"] not in {"Install", "Upgrade"} or row["repo"] != "openstack-local" for row in history_new):
        raise ValueError("Nova new history action or repository mismatch")
    new_nevras = [row["nevra"] for row in history_new]
    if any(not isinstance(nevra, str) or not nevra for nevra in new_nevras) or len(new_nevras) != len(set(new_nevras)):
        raise ValueError("Nova new history NEVRA missing or duplicate")
    if len(current_rpm) != len(new_nevras) or set(current_rpm) != set(new_nevras):
        raise ValueError("DNF history and current RPM NEVRA sets differ")
    if any(not isinstance(row, dict) or set(row) != {"nevra", "repo"} for row in repository_metadata):
        raise ValueError("repository metadata row shape mismatch")
    if len(repository_metadata) != len(new_nevras) or {row["nevra"] for row in repository_metadata} != set(new_nevras) \
            or any(row["repo"] != "openstack-local" for row in repository_metadata):
        raise ValueError("DNF history and openstack-local metadata sets differ")
    if node == "controller":
        if history_old != []:
            raise ValueError("controller transaction unexpectedly has old rows")
        return
    if any(not isinstance(row, dict) or set(row) != {"action", "nevra", "repo", "replaced_by", "current_absent"}
           for row in history_old):
        raise ValueError("compute old history row shape mismatch")
    upgraded_to = {row["nevra"] for row in history_new if row["action"] == "Upgrade"}
    if any(row["action"] != "Upgraded" or row["repo"] != "@System" or row["current_absent"] is not True
           or row["replaced_by"] not in upgraded_to for row in history_old):
        raise ValueError("compute old upgraded-row replacement mismatch")
    if len({row["nevra"] for row in history_old}) != contract["old"] \
            or {row["replaced_by"] for row in history_old} != upgraded_to:
        raise ValueError("compute old/new upgrade pairing mismatch")
```

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

真实事务号为 8，计划、仓库行、历史 Install 行和 RPM 增量均为 40。完整 40 条 action/NEVRA/repo、40 条当前 RPM 和 40 条 repo metadata 保存在 `transaction-evidence/nova-controller-transaction.txt`，三方集合逐条一致，不再用四个根包数组代替完整凭据。四个根包是 `openstack-nova-api-27.3.0-1.oe2403sp2.noarch`、`openstack-nova-conductor-27.3.0-1.oe2403sp2.noarch`、`openstack-nova-novncproxy-27.3.0-1.oe2403sp2.noarch` 和 `openstack-nova-scheduler-27.3.0-1.oe2403sp2.noarch`；同一增量还包括 `openstack-nova-common-27.3.0-1.oe2403sp2.noarch`、`python3-nova-27.3.0-1.oe2403sp2.noarch`、novnc 及其 34 个依赖。全部来自 `openstack-local`，zero remove/replace。

## 三个数据库与最小授权

学生在 controller 上手工进入 MariaDB，依次输入下面的 SQL。把 `<NOVA_SERVICE_PASSWORD>` 替换为课堂统一服务口令；尖括号占位符本身不能照抄。这里保留三类 Host，是为了同时覆盖本机 socket/回环地址和双节点实验网访问；每个账号只获得三个 Nova schema 的权限，没有全局管理权限。

```sql
mysql -uroot
CREATE DATABASE nova_api;
CREATE DATABASE nova;
CREATE DATABASE nova_cell0;
CREATE USER 'nova'@'localhost' IDENTIFIED BY '<NOVA_SERVICE_PASSWORD>';
CREATE USER 'nova'@'127.0.0.1' IDENTIFIED BY '<NOVA_SERVICE_PASSWORD>';
CREATE USER 'nova'@'%' IDENTIFIED BY '<NOVA_SERVICE_PASSWORD>';
GRANT ALL PRIVILEGES ON nova_api.* TO 'nova'@'localhost';
GRANT ALL PRIVILEGES ON nova.* TO 'nova'@'localhost';
GRANT ALL PRIVILEGES ON nova_cell0.* TO 'nova'@'localhost';
GRANT ALL PRIVILEGES ON nova_api.* TO 'nova'@'127.0.0.1';
GRANT ALL PRIVILEGES ON nova.* TO 'nova'@'127.0.0.1';
GRANT ALL PRIVILEGES ON nova_cell0.* TO 'nova'@'127.0.0.1';
GRANT ALL PRIVILEGES ON nova_api.* TO 'nova'@'%';
GRANT ALL PRIVILEGES ON nova.* TO 'nova'@'%';
GRANT ALL PRIVILEGES ON nova_cell0.* TO 'nova'@'%';
EXIT;
```

完成后先执行本节后面的非凭据授权校验，确认“3 库、3 Host、9 个 schema scope、无额外权限”再进入身份阶段。下面的参数化代码是教材测试用的安全重放与失败分类器，不替代学生逐条输入上述 SQL。

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


def collect_nova_grant_evidence(cursor: object) -> dict[str, object]:
    """Collect only non-credential grant metadata from the live MariaDB cursor."""
    cursor.execute("SELECT User,Host FROM mysql.user WHERE User=%s ORDER BY Host", ("nova",))
    accounts = [tuple(row) for row in cursor.fetchall()]
    evidence: dict[str, object] = {"hosts": sorted(row[1] for row in accounts), "accounts": {}}
    for host in ("%", "127.0.0.1", "localhost"):
        grantee = f"'nova'@'{host}'"
        cursor.execute("SELECT PRIVILEGE_TYPE,IS_GRANTABLE FROM information_schema.USER_PRIVILEGES WHERE GRANTEE=%s ORDER BY PRIVILEGE_TYPE", (grantee,))
        global_rows = [list(row) for row in cursor.fetchall()]
        cursor.execute("SELECT TABLE_SCHEMA,PRIVILEGE_TYPE,IS_GRANTABLE FROM information_schema.SCHEMA_PRIVILEGES WHERE GRANTEE=%s ORDER BY TABLE_SCHEMA,PRIVILEGE_TYPE", (grantee,))
        schema_rows = [list(row) for row in cursor.fetchall()]
        cursor.execute("SELECT TABLE_SCHEMA,TABLE_NAME,PRIVILEGE_TYPE FROM information_schema.TABLE_PRIVILEGES WHERE GRANTEE=%s ORDER BY TABLE_SCHEMA,TABLE_NAME,PRIVILEGE_TYPE", (grantee,))
        table_rows = [list(row) for row in cursor.fetchall()]
        cursor.execute("SELECT TABLE_SCHEMA,TABLE_NAME,COLUMN_NAME,PRIVILEGE_TYPE FROM information_schema.COLUMN_PRIVILEGES WHERE GRANTEE=%s ORDER BY TABLE_SCHEMA,TABLE_NAME,COLUMN_NAME,PRIVILEGE_TYPE", (grantee,))
        column_rows = [list(row) for row in cursor.fetchall()]
        cursor.execute("SELECT Db,Routine_name,Routine_type,Proc_priv FROM mysql.procs_priv WHERE User=%s AND Host=%s ORDER BY Db,Routine_name", ("nova", host))
        routine_rows = [list(row) for row in cursor.fetchall()]
        evidence["accounts"][host] = {"global": global_rows, "schema": schema_rows,
                                      "table": table_rows, "column": column_rows, "routine": routine_rows}
    cursor.execute("SELECT User,Host,Proxied_user,Proxied_host,With_grant FROM mysql.proxies_priv WHERE User=%s ORDER BY Host", ("nova",))
    evidence["proxy"] = [list(row) for row in cursor.fetchall()]
    cursor.execute("SELECT User,Host,Role,Admin_option FROM mysql.roles_mapping WHERE User=%s ORDER BY Host,Role", ("nova",))
    evidence["roles"] = [list(row) for row in cursor.fetchall()]
    return evidence


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

学生先加载管理员环境，逐条执行下列命令。用户口令通过交互提示输入，避免进入 shell 历史；每条创建命令之后都要立即执行对应的 `list/show` 查询，只有唯一对象及其 ID、属性和绑定完全正确时才继续。

```bash
set -Eeuo pipefail
source /root/admin-openrc
openstack user create --domain default --password-prompt nova
openstack user list --domain default
openstack user show nova
openstack role add --project service --user nova admin
openstack role assignment list --project service --user nova --role admin
openstack service create --name nova --description "OpenStack Compute" compute
openstack service list
openstack service show nova
openstack endpoint create --region RegionOne compute public http://controller:8774/v2.1
openstack endpoint list --service compute
openstack endpoint create --region RegionOne compute internal http://controller:8774/v2.1
openstack endpoint list --service compute
openstack endpoint create --region RegionOne compute admin http://controller:8774/v2.1
openstack endpoint list --service compute
unset OS_PASSWORD
```

如果某对象已经存在，不要再次创建；先用唯一 ID 逐级核对。0 条可创建，1 条且全部属性正确可复用，重复、部分端点、错误 ID 或查询错误一律停止。下面的 Python 是对上述手工命令进行 focused-test 重放的分类器，不是一键安装脚本。

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
    endpoint_details: list[dict] = []
    for row in endpoints:
        item = query(["endpoint", "show", row["ID"]])
        if not (item.get("id") == row["ID"] and item.get("interface") == row.get("Interface")
                and item.get("service_id") == service_id and item.get("region") == "RegionOne"
                and item.get("url") == NOVA_URL and item.get("enabled") is True):
            raise ValueError("Nova endpoint binding mismatch")
        endpoint_details.append(item)
    return {"user": user, "assignment": assignment, "service": shown, "endpoints": endpoint_details,
            "service_project_id": project_id, "admin_role_id": role_id}


def validate_nova_identity_evidence(evidence: dict[str, object]) -> None:
    user = evidence.get("user")
    assignment = evidence.get("assignment")
    service = evidence.get("service")
    endpoints = evidence.get("endpoints")
    project_id = evidence.get("service_project_id")
    role_id = evidence.get("admin_role_id")
    if not isinstance(user, dict) or not (
        user.get("id") and user.get("name") == "nova" and user.get("domain_id") == "default"
        and user.get("enabled") is True
    ):
        raise ValueError("Nova user evidence mismatch")
    if not project_id or not role_id or not isinstance(assignment, dict) or assignment != {
        "Role": role_id, "User": user["id"], "Project": project_id,
        "Group": "", "Domain": "", "System": "", "Inherited": False,
    }:
        raise ValueError("Nova global-admin assignment evidence mismatch")
    if not isinstance(service, dict) or not (
        service.get("id") and service.get("name") == "nova" and service.get("type") == "compute"
        and service.get("enabled") is True
    ):
        raise ValueError("Nova service evidence mismatch")
    if not isinstance(endpoints, list) or len(endpoints) != 3 or {
        row.get("interface") for row in endpoints if isinstance(row, dict)
    } != set(INTERFACES):
        raise ValueError("Nova endpoint evidence cardinality mismatch")
    if any(
        not row.get("id") or row.get("service_id") != service["id"]
        or row.get("region") != "RegionOne" or row.get("url") != NOVA_URL
        or row.get("enabled") is not True
        for row in endpoints
    ):
        raise ValueError("Nova endpoint evidence binding mismatch")
```

实际结果为 USER=1、ASSIGNMENT=1、SERVICE=1、ENDPOINTS=3。首次角色写入的客户端进程返回非零，门禁在服务创建前停止；随后精确 ID 诊断证明用户唯一、授权为空，同一绑定成功后才继续。没有自动重试掩盖重复或错误 ID。

## 控制节点原子配置

第一次改写前，`rpm -V openstack-nova-common` 无输出；软件包默认文件以元数据和字节校验备份到 `/root/openstack-lab-backups/task-5e-20260811T113129Z/nova.conf.package-default`。写入器在同目录使用排他、非跟随临时文件，完成 owner/mode、文件 fsync、原子替换和目录 fsync；失败只清理由本进程创建且 inode 未变化的临时文件。

课堂安装必须手工编辑。先备份软件包默认文件，再使用 `vi` 打开配置文件，把 `<SERVICE_PASSWORD>` 换成服务口令，把 `<URL_ENCODED_DB_PASSWORD>` 换成对数据库口令进行 URL 编码后的值。输入完成后保存退出，再逐节对照核查；不能运行后面的测试写入器代替本步骤。

```bash
cp -a /etc/nova/nova.conf /etc/nova/nova.conf.package-default
vi /etc/nova/nova.conf
```

```ini
[DEFAULT]
enabled_apis = osapi_compute,metadata
transport_url = rabbit://openstack:<URL_ENCODED_DB_PASSWORD>@controller
my_ip = 192.168.234.151
use_neutron = true
firewall_driver = nova.virt.firewall.NoopFirewallDriver

[api_database]
connection = mysql+pymysql://nova:<URL_ENCODED_DB_PASSWORD>@127.0.0.1/nova_api

[database]
connection = mysql+pymysql://nova:<URL_ENCODED_DB_PASSWORD>@127.0.0.1/nova

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
server_listen = $my_ip
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

[scheduler]
discover_hosts_in_cells_interval = 300

[neutron]
auth_url = http://controller:5000
auth_type = password
project_domain_name = Default
user_domain_name = Default
region_name = RegionOne
project_name = service
username = neutron
password = <SERVICE_PASSWORD>
service_metadata_proxy = true
metadata_proxy_shared_secret = <SERVICE_PASSWORD>

[cinder]
os_region_name = RegionOne
```

```bash
chown root:nova /etc/nova/nova.conf
chmod 0640 /etc/nova/nova.conf
```

下面的原子写入器只用于教材测试验证最终参数、失败清理和快照脱敏，不是学生安装入口。

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


def validate_written_nova_config(target: Path, password: str, uid: int, gid: int, ops: object = os) -> None:
    metadata = ops.lstat(target)
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1 or metadata.st_uid != uid \
            or metadata.st_gid != gid or stat.S_IMODE(metadata.st_mode) != 0o640:
        raise ValueError("controller nova.conf metadata mismatch")
    try:
        payload = target.read_bytes()
    except OSError as error:
        raise RuntimeError("controller nova.conf read failed") from error
    if payload != build_nova_config(password).encode("utf-8"):
        raise ValueError("controller nova.conf exact content mismatch")
```

真实文件为 root:nova、0640、单硬链接。RabbitMQ 和数据库 URL 中的口令先做 URL 编码；快照使用 `<URL_ENCODED_DB_PASSWORD>` 和 `<SERVICE_PASSWORD>`。`[neutron]` 与 `[cinder]` 是为后续切片预留的 inactive dependencies，本节没有 Nova 工作负载，因此它们不会触发网络或卷操作；只有后续组件通过自己的门禁后才能激活业务路径。

## API 数据库、cell0 与 cell1

模式迁移严格以 nova 系统用户执行。cell0 使用保留的全零 UUID；cell1 只在完全不存在时创建。列表与数据库证据只读取 UUID、name、disabled，不显示包含凭据的 transport/database URL。

```python
from __future__ import annotations

import uuid


def classify_cell_state(evidence: dict[str, object]) -> str:
    """Classify only sanitized cell rows; query errors and URL-bearing evidence fail closed."""
    if set(evidence) != {"query_ok", "rows"}:
        raise ValueError("cell evidence contains forbidden or missing fields")
    if evidence.get("query_ok") is not True:
        raise RuntimeError("cell query did not complete successfully")
    rows = evidence.get("rows")
    if not isinstance(rows, list):
        raise ValueError("cell rows missing")
    normalized: list[tuple[str, str]] = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"name", "uuid", "disabled"}:
            raise ValueError("cell row shape mismatch")
        if row.get("disabled") is not False:
            raise ValueError("disabled cell is not accepted")
        name = row.get("name")
        value = row.get("uuid")
        if not isinstance(name, str) or not isinstance(value, str):
            raise ValueError("cell name or UUID type mismatch")
        normalized.append((name, value))
    if len(normalized) != len(set(normalized)):
        raise ValueError("duplicate cell row")
    if len(normalized) == 0:
        return "create-cell0-then-cell1"
    cell0 = ("cell0", "00000000-0000-0000-0000-000000000000")
    if len(normalized) == 1:
        if normalized[0] != cell0:
            raise ValueError("single cell is not the exact cell0 mapping")
        return "create-cell1"
    if len(normalized) != 2 or cell0 not in normalized:
        raise ValueError("cell cardinality or cell0 mapping mismatch")
    cell1_rows = [row for row in normalized if row[0] == "cell1"]
    if len(cell1_rows) != 1:
        raise ValueError("cell1 cardinality mismatch")
    try:
        parsed = uuid.UUID(cell1_rows[0][1])
    except (ValueError, AttributeError) as error:
        raise ValueError("cell1 UUID mismatch") from error
    if parsed.int == 0 or str(parsed) != cell1_rows[0][1]:
        raise ValueError("cell1 UUID mismatch")
    return "exact"


def validate_nova_controller_schema(evidence: dict[str, object]) -> None:
    if evidence.get("query_ok") is not True:
        raise RuntimeError("Nova controller schema query failed")
    if evidence.get("api") != {"tables": 32, "head": "b30f573d3377"}:
        raise ValueError("nova_api schema/head mismatch")
    if evidence.get("main") != {"tables": 110, "head": "960aac0e09ea"}:
        raise ValueError("nova main schema/head mismatch")
    if evidence.get("cell0") != {"tables": 110, "head": "960aac0e09ea"}:
        raise ValueError("nova_cell0 schema/head mismatch")
    cells = evidence.get("cells")
    if not isinstance(cells, dict) or classify_cell_state(cells) != "exact":
        raise ValueError("Nova exact cell state mismatch")
    if evidence.get("upgrade") != {"rc": 0, "successes": 7, "failures": 0, "warnings": 0}:
        raise ValueError("Nova controller upgrade evidence mismatch")
```

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
