# Keystone 手工部署与验证记录

本记录对应 controller `192.168.234.151` 上的 OpenStack 2023.1 Antelope Keystone。安装以 Task 5A 已验收的 MariaDB、RabbitMQ、Memcached 和 OpenStack CLI 为前置条件，compute `192.168.234.150` 在本阶段只做只读磁盘审计。所有命令均按实际执行顺序编排，未运行 `06-controller-keystone.sh` 或任何复制脚本。

依赖顺序必须固定为：起始状态门禁 → 离线包事务 → 数据库和三主机授权 → 配置和原包备份 → 数据库同步 → Fernet/credential 密钥 → bootstrap → Apache/WSGI → API/CLI 和 `service` 项目 → 双节点收口。前一门禁失败时不得跳到后一门禁。

## 严格会话与起始状态

在 controller 开启一个新的 root Bash 会话。错误陷阱只显示行号和命令名，不显示运行时秘密。

```bash
set -Eeuo pipefail

die() {
  printf 'ERROR: %s\n' "$*" >&2
  return 1
}

on_error() {
  local line=$1 command=$2
  printf 'ERROR: line %s failed: %s\n' "$line" "$command" >&2
}
trap 'on_error "$LINENO" "$BASH_COMMAND"' ERR

assert_packages_absent() {
  local package output rc
  rpm -q rpm >/dev/null || die "RPM database probe failed"
  for package in "$@"; do
    if output=$(LC_ALL=C rpm -q "$package" 2>&1); then
      die "package must be absent at this gate: $package"
    else
      rc=$?
      [[ $rc -eq 1 && $output == "package $package is not installed" ]] ||
        die "RPM absence probe failed: $package"
    fi
  done
}

assert_starting_state() {
  local service repo
  [[ $(hostnamectl --static) == controller ]] || die "controller hostname drift"
  ip -4 -o addr show dev ens33 | grep -Fq '192.168.234.151/24' || die "ens33 address drift"
  [[ -z $(ip -4 -o addr show dev ens34) ]] || die "ens34 must not have IPv4"
  for service in chronyd mariadb rabbitmq-server memcached; do
    systemctl is-active --quiet "$service" || die "$service inactive"
    systemctl is-enabled --quiet "$service" || die "$service disabled"
  done
  [[ $(mysql -uroot --batch --skip-column-names -e 'SELECT 1;') == 1 ]] ||
    die "MariaDB local access failed"
  repo=$(dnf -q repolist --disablerepo='*' --enablerepo='openstack-local') ||
    die "isolated repository probe failed"
  grep -Fq 'openstack-local' <<<"$repo" || die "openstack-local missing"
  assert_packages_absent openstack-keystone openstack-glance openstack-placement-api \
    openstack-nova-common openstack-neutron-common openstack-cinder-common \
    openstack-swift-common python3-horizon
}

assert_starting_state
```

起始审计结果为 PASS：四项前置服务均 `active/enabled`，ens34 无 IPv4，Keystone 及后续服务包均未安装，Keystone 数据库、配置、密钥、bootstrap marker 和 5000 监听均不存在。

## 仅离线源的软件包事务

`mod_wsgi` 是安装能力名，本地仓中的实际提供者是 `python3-mod_wsgi`。先同时验证直接候选、递归依赖和能力提供者，随后用 `--assumeno` 做零变更事务。验证函数要求三个解析后的根包均存在、每一行候选均属于 `openstack-local`、事务主动中止且无移除、降级或替换动作。

```bash
validate_keystone_preflight() {
  local candidates=$1 preflight=$2 package_name
  [[ -n $candidates && -n $preflight ]] || die "empty package preflight evidence"
  if awk -F'|' 'NF != 2 || $2 != "openstack-local" { bad=1 } END { exit bad ? 0 : 1 }' <<<"$candidates"; then
    die "package candidate escaped openstack-local"
  fi
  for package_name in openstack-keystone httpd python3-mod_wsgi; do
    grep -Fxq "$package_name|openstack-local" <<<"$candidates" ||
      die "resolved transaction root missing: $package_name"
  done
  grep -Eq 'Install[[:space:]]+[1-9][0-9]*[[:space:]]+Packages?' <<<"$preflight" ||
    die "positive install count not proven"
  grep -Fq 'Operation aborted' <<<"$preflight" || die "preflight did not abort"
  if grep -Eiq '(^|[[:space:]])(Removing|Erasing|Obsoleting|Replacing|Downgrading)([[:space:]:]|$)' <<<"$preflight"; then
    die "unsafe package action detected"
  fi
}

roots=(openstack-keystone httpd mod_wsgi)
direct=$(dnf -q repoquery --disablerepo='*' --enablerepo='openstack-local' \
  --qf '%{name}|%{repoid}' "${roots[@]}")
provider=$(dnf -q repoquery --disablerepo='*' --enablerepo='openstack-local' \
  --whatprovides mod_wsgi --qf '%{name}|%{repoid}')
resolved=$(dnf -q repoquery --disablerepo='*' --enablerepo='openstack-local' \
  --requires --resolve --recursive --qf '%{name}|%{repoid}' "${roots[@]}")
candidates=$(printf '%s\n%s\n%s\n' "$direct" "$provider" "$resolved" |
  sed '/^[[:space:]]*$/d' | sort -u)

set +e
preflight=$(LC_ALL=C dnf --assumeno --setopt=install_weak_deps=False \
  --disablerepo='*' --enablerepo='openstack-local' install openstack-keystone httpd mod_wsgi 2>&1)
preflight_rc=$?
set -e
[[ $preflight_rc -eq 1 ]] || die "unexpected preflight exit: $preflight_rc"
validate_keystone_preflight "$candidates" "$preflight"

dnf -y --setopt=install_weak_deps=False \
  --disablerepo='*' --enablerepo='openstack-local' install openstack-keystone httpd mod_wsgi
rpm -q openstack-keystone httpd python3-mod_wsgi
```

实际预检为 99 个安装项、99 个事务表仓库行，全部来自 `openstack-local`，零 Removing/Erasing/Obsoleting/Replacing/Downgrading。DNF Transaction ID 为 5，RPM 数量增加 99。根包版本为：

```text
openstack-keystone  23.0.1-1.oe2403sp2  noarch
httpd               2.4.58-15.oe2403sp3 x86_64
python3-mod_wsgi    5.0.0-1.oe2403sp3   x86_64
```

本步骤没有外部仓库回退，也没有使用破坏依赖一致性的参数。

## 创建数据库、用户与授权

运行时密码仅从 `/root/.openstack-lab-secrets` 读入内存。数据库账户名、主机和密码都作为 PyMySQL 参数传递；特别是 `%` 主机也作为参数，不进行 SQL 字符串拼接。

```bash
[[ $(stat -c '%U:%G %a' /root/.openstack-lab-secrets) == 'root:root 600' ]] ||
  die "runtime secret metadata drift"
[[ $(wc -l </root/.openstack-lab-secrets) -eq 1 ]] || die "runtime secret line-count drift"
IFS= read -r secret_record </root/.openstack-lab-secrets
case "$secret_record" in
  OPENSTACK_DEPLOY_PASSWORD=?*) OPENSTACK_DEPLOY_PASSWORD=${secret_record#OPENSTACK_DEPLOY_PASSWORD=} ;;
  *) die "runtime secret format drift" ;;
esac
secret_record=
export OPENSTACK_DEPLOY_PASSWORD
MYSQL_SOCKET=$(mysql -uroot --batch --skip-column-names -e 'SELECT @@socket;')
[[ -S $MYSQL_SOCKET ]] || die "MariaDB socket probe failed"
export MYSQL_SOCKET

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
        cursor.execute("CREATE DATABASE IF NOT EXISTS keystone")
        for host in hosts:
            cursor.execute(
                "CREATE USER IF NOT EXISTS %s@%s IDENTIFIED BY %s",
                ("keystone", host, password),
            )
            cursor.execute(
                "ALTER USER %s@%s IDENTIFIED BY %s",
                ("keystone", host, password),
            )
            cursor.execute(
                "GRANT ALL PRIVILEGES ON keystone.* TO %s@%s",
                ("keystone", host),
            )
        cursor.execute("FLUSH PRIVILEGES")
finally:
    connection.close()

probe = pymysql.connect(
    host="127.0.0.1", user="keystone", password=password,
    database="keystone", charset="utf8mb4", connect_timeout=5,
)
try:
    with probe.cursor() as cursor:
        cursor.execute("SELECT 1")
        if cursor.fetchone() != (1,):
            raise RuntimeError("protected database probe failed")
finally:
    probe.close()
PY

unset OPENSTACK_DEPLOY_PASSWORD MYSQL_SOCKET
mysql -uroot --batch --skip-column-names -e \
  "SELECT Host FROM mysql.user WHERE User='keystone' ORDER BY Host;"
```

三个数据库账户记录分别是 `keystone@localhost`、`keystone@127.0.0.1` 和 `keystone@%`。它们都只对 `keystone.*` 获得全部权限；未显示认证串或密码散列。实际授权集为 `%,127.0.0.1,localhost`，受保护登录 PASS，此时 schema 仍为 0 表。

首次执行中，旧写法把 `%` 放进 PyMySQL 格式字符串，客户端在创建第三个账户前拒绝该语句。严格会话当场停止，只留下空数据库和前两个账户。只读确认后采用上面的三项参数化命令幂等补齐。教材只保留修正后的命令，并用行为测试覆盖 `%` 主机。

## 保存原包配置并配置 Keystone

配置前运行 `rpm -V openstack-keystone httpd python3-mod_wsgi`，无差异。将包默认文件保存到只允许 root 访问的备份目录；实际目录是 `/root/openstack-lab-backups/task-5b-20260811T072646Z`。

```bash
backup_dir=/root/openstack-lab-backups/task-5b-20260811T072646Z
install -d -m 0700 -o root -g root "$backup_dir"
(
  cd /
  cp -a --parents \
    etc/keystone/keystone.conf \
    etc/httpd/conf/httpd.conf \
    usr/share/keystone/wsgi-keystone.conf \
    "$backup_dir"
)
```

下列程序保留 `root:keystone 0640`，把密码进行 URL 编码后原子替换配置。真实连接串不输出、不散列、不复制到教材。

```bash
IFS= read -r secret_record </root/.openstack-lab-secrets
case "$secret_record" in
  OPENSTACK_DEPLOY_PASSWORD=?*) OPENSTACK_DEPLOY_PASSWORD=${secret_record#OPENSTACK_DEPLOY_PASSWORD=} ;;
  *) die "runtime secret format drift" ;;
esac
secret_record=
export OPENSTACK_DEPLOY_PASSWORD

python3 - <<'PY'
import configparser
import os
from pathlib import Path
import stat
import tempfile
from urllib.parse import quote

path = Path("/etc/keystone/keystone.conf")
metadata = path.stat(follow_symlinks=False)
if not stat.S_ISREG(metadata.st_mode):
    raise RuntimeError("keystone.conf is not a regular file")
parser = configparser.RawConfigParser(interpolation=None)
with path.open("r", encoding="utf-8") as stream:
    parser.read_file(stream)
for section in ("database", "token"):
    if not parser.has_section(section):
        parser.add_section(section)
encoded = quote(os.environ["OPENSTACK_DEPLOY_PASSWORD"], safe="")
parser.set("database", "connection", f"mysql+pymysql://keystone:{encoded}@127.0.0.1/keystone")
parser.set("token", "provider", "fernet")
descriptor, temporary_name = tempfile.mkstemp(prefix=".keystone.conf.task5b.", dir=str(path.parent))
try:
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        parser.write(stream)
        stream.flush()
        os.fsync(stream.fileno())
    os.chown(temporary_name, metadata.st_uid, metadata.st_gid)
    os.chmod(temporary_name, stat.S_IMODE(metadata.st_mode))
    os.replace(temporary_name, path)
finally:
    if os.path.exists(temporary_name):
        os.unlink(temporary_name)
PY
restorecon -F /etc/keystone/keystone.conf
unset OPENSTACK_DEPLOY_PASSWORD
```

脱敏快照用 `<DB_PASSWORD>` 替换完整 URL 编码后的密码字段；占位符所在位置保持连接 URL 的语义不变。

## 同步数据库

必须以 `keystone` 系统用户运行同步，成功后才允许生成密钥。

```bash
su -s /bin/sh -c 'keystone-manage db_sync' keystone

table_count=$(mysql -uroot --batch --skip-column-names -e \
  "SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA='keystone';")
[[ $table_count -eq 49 ]] || die "Keystone schema table count drift"
required_tables=$(mysql -uroot --batch --skip-column-names -e \
  "SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA='keystone' AND TABLE_NAME IN ('assignment','endpoint','local_user','project','role','service','user') ORDER BY TABLE_NAME;" |
  paste -sd, -)
[[ $required_tables == 'assignment,endpoint,local_user,project,role,service,user' ]] ||
  die "required Keystone table missing"
[[ $(mysql -uroot --batch --skip-column-names -D keystone -e \
  'SELECT COUNT(*) FROM alembic_version;') -eq 2 ]] || die "Alembic version rows drift"
```

实际结果为 49 表、7 个关键表齐全、`alembic_version` 2 行。首次验证误用旧迁移表名后在探针处停止；`db_sync` 本身已成功。只读识别 Antelope 实际表名后改为上面的 `alembic_version` 并幂等重跑。

## 初始化并保护密钥仓

只允许两种状态：目录和文件完全不存在，或已经存在完整的 `0`、`1` 两文件集合。部分集合、多余文件、符号链接、属主或模式差异均停止。已存在的有效集合只验证，不静默轮换。

```bash
KEYSTONE_KEY_OWNER=keystone:keystone

classify_key_repository() {
  local directory=$1 entries path
  if [[ ! -e $directory && ! -L $directory ]]; then
    printf '%s\n' ABSENT
    return 0
  fi
  [[ -d $directory && ! -L $directory ]] || die "key repository is not a real directory"
  entries=$(find "$directory" -mindepth 1 -maxdepth 1 -printf '%f\n' | sort) ||
    die "cannot enumerate key repository"
  [[ $entries == $'0\n1' ]] || die "key repository is partial or has extra entries"
  [[ $(stat -c '%U:%G %a' "$directory") == "$KEYSTONE_KEY_OWNER 700" ]] ||
    die "key repository directory metadata mismatch"
  for path in "$directory/0" "$directory/1"; do
    [[ -f $path && ! -L $path ]] || die "key entry is not a regular file"
    [[ $(stat -c '%U:%G %a' "$path") == "$KEYSTONE_KEY_OWNER 600" ]] ||
      die "key entry metadata mismatch"
  done
  printf '%s\n' VALID
}

ensure_key_repository() {
  local kind=$1 directory=$2 state
  state=$(classify_key_repository "$directory") || die "$kind key classification failed"
  case "$state" in
    ABSENT)
      case "$kind" in
        fernet) keystone-manage fernet_setup --keystone-user keystone --keystone-group keystone ;;
        credential) keystone-manage credential_setup --keystone-user keystone --keystone-group keystone ;;
        *) die "unknown key type" ;;
      esac
      ;;
    VALID) : "validate existing set; do not rotate" ;;
    *) die "unknown key state" ;;
  esac
  [[ $(classify_key_repository "$directory") == VALID ]] || die "$kind keys invalid"
}

ensure_key_repository fernet /etc/keystone/fernet-keys
ensure_key_repository credential /etc/keystone/credential-keys
```

实际两套目录均由不存在状态初始化为 `0`、`1`，目录 `keystone:keystone 0700`，文件 `keystone:keystone 0600`。记录中没有密钥内容或摘要。

## 一次性 bootstrap 与完整证据门

marker 不是成功证据。先直接查询数据库，把状态分为 `ABSENT`、`FULL`、`PARTIAL`。只有全部不存在且 marker 不存在时才运行 bootstrap；全部记录精确存在时可跳过或恢复 marker；任何部分状态都停止。该 RPM 用字符串 `<<null>>` 表示无域角色，探针同时兼容 SQL NULL 和这个实际哨兵。

```bash
bootstrap_action() {
  local state=$1 marker=$2
  case "$state:$marker" in
    ABSENT:absent) printf '%s\n' BOOTSTRAP ;;
    FULL:present) printf '%s\n' SKIP ;;
    FULL:absent) printf '%s\n' RECOVER_MARKER ;;
    ABSENT:present) die "marker exists but bootstrap records are absent" ;;
    PARTIAL:*) die "partial bootstrap evidence requires diagnosis" ;;
    *) die "unknown bootstrap state" ;;
  esac
}

probe_bootstrap_state() {
  MYSQL_SOCKET=$(mysql -uroot --batch --skip-column-names -e 'SELECT @@socket;')
  export MYSQL_SOCKET
  python3 - <<'PY'
import os
import pymysql

connection = pymysql.connect(
    unix_socket=os.environ["MYSQL_SOCKET"], user="root", database="keystone", charset="utf8mb4"
)
queries = (
    ("admin_project", "SELECT COUNT(*) FROM project WHERE name='admin' AND domain_id='default' AND enabled=1 AND is_domain=0", 1),
    ("admin_user", "SELECT COUNT(*) FROM local_user AS l JOIN user AS u ON u.id=l.user_id WHERE l.name='admin' AND l.domain_id='default' AND u.enabled=1", 1),
    ("admin_role", "SELECT COUNT(*) FROM role WHERE name='admin' AND (domain_id IS NULL OR domain_id='<<null>>')", 1),
    ("assignment", "SELECT COUNT(*) FROM assignment AS a JOIN local_user AS l ON l.user_id=a.actor_id JOIN project AS p ON p.id=a.target_id JOIN role AS r ON r.id=a.role_id WHERE a.type='UserProject' AND l.name='admin' AND l.domain_id='default' AND p.name='admin' AND p.domain_id='default' AND r.name='admin' AND a.inherited=0", 1),
    ("identity", "SELECT COUNT(*) FROM service WHERE type='identity' AND enabled=1", 1),
    ("region", "SELECT COUNT(*) FROM region WHERE id='RegionOne'", 1),
    ("endpoint_total", "SELECT COUNT(*) FROM endpoint AS e JOIN service AS s ON s.id=e.service_id WHERE s.type='identity'", 3),
    ("admin", "SELECT COUNT(*) FROM endpoint AS e JOIN service AS s ON s.id=e.service_id WHERE s.type='identity' AND e.enabled=1 AND e.region_id='RegionOne' AND e.url='http://controller:5000/v3/' AND e.interface='admin'", 1),
    ("internal", "SELECT COUNT(*) FROM endpoint AS e JOIN service AS s ON s.id=e.service_id WHERE s.type='identity' AND e.enabled=1 AND e.region_id='RegionOne' AND e.url='http://controller:5000/v3/' AND e.interface='internal'", 1),
    ("public", "SELECT COUNT(*) FROM endpoint AS e JOIN service AS s ON s.id=e.service_id WHERE s.type='identity' AND e.enabled=1 AND e.region_id='RegionOne' AND e.url='http://controller:5000/v3/' AND e.interface='public'", 1),
)
observed = []
try:
    with connection.cursor() as cursor:
        for name, sql, expected in queries:
            cursor.execute(sql)
            observed.append((name, cursor.fetchone()[0], expected))
finally:
    connection.close()
if all(actual == 0 for _name, actual, _expected in observed):
    state = "ABSENT"
elif all(actual == expected for _name, actual, expected in observed):
    state = "FULL"
else:
    state = "PARTIAL"
print(f"BOOTSTRAP_STATE={state}")
PY
  unset MYSQL_SOCKET
}

marker=/root/.keystone-bootstrap-complete
state_output=$(probe_bootstrap_state)
state=${state_output#BOOTSTRAP_STATE=}
marker_state=absent
if [[ -e $marker || -L $marker ]]; then
  [[ -f $marker && ! -L $marker && $(stat -c '%U:%G %a' "$marker") == 'root:root 600' ]] ||
    die "bootstrap marker metadata drift"
  marker_state=present
fi
action=$(bootstrap_action "$state" "$marker_state")
```

根据决策结果执行且只执行一个分支：

```bash
case "$action" in
  BOOTSTRAP)
    IFS= read -r secret_record </root/.openstack-lab-secrets
    case "$secret_record" in
      OPENSTACK_DEPLOY_PASSWORD=?*) ADMIN_PASS=${secret_record#OPENSTACK_DEPLOY_PASSWORD=} ;;
      *) die "runtime secret format drift" ;;
    esac
    secret_record=
    keystone-manage bootstrap \
      --bootstrap-password "$ADMIN_PASS" \
      --bootstrap-username admin \
      --bootstrap-project-name admin \
      --bootstrap-role-name admin \
      --bootstrap-service-name keystone \
      --bootstrap-admin-url http://controller:5000/v3/ \
      --bootstrap-internal-url http://controller:5000/v3/ \
      --bootstrap-public-url http://controller:5000/v3/ \
      --bootstrap-region-id RegionOne
    unset ADMIN_PASS
    [[ $(probe_bootstrap_state) == BOOTSTRAP_STATE=FULL ]] || die "bootstrap evidence incomplete"
    install -o root -g root -m 0600 /dev/null "$marker"
    ;;
  RECOVER_MARKER)
    [[ $state == FULL ]] || die "marker recovery requires FULL evidence"
    install -o root -g root -m 0600 /dev/null "$marker"
    ;;
  SKIP)
    [[ $state == FULL ]] || die "skip requires FULL evidence"
    ;;
esac
[[ $(probe_bootstrap_state) == BOOTSTRAP_STATE=FULL ]] || die "final evidence incomplete"
```

bootstrap 实际创建：Default 域、admin 项目、admin 用户、reader/member/admin 角色及隐含关系、admin 用户的 admin 项目角色授权和 system 授权、`keystone` identity 服务、RegionOne，以及 public/internal/admin 三个 v3 端点。

首次 bootstrap 后，旧探针假设 `role.domain_id IS NULL`，而本包保存为 `<<null>>`，所以在写 marker 前停止。逐项只读确认全部记录精确后，用修正探针得到 FULL，执行 `RECOVER_MARKER`，未再次运行 bootstrap、未重设密码。再运行一次得到 `SKIP`，证明 marker 与数据库证据共同控制幂等性。

## Apache 与 Keystone WSGI

创建独立的 ServerName 文件，避免重复修改主配置；WSGI 目标若已存在但不是精确符号链接则停止。

```bash
cat >/etc/httpd/conf.d/00-servername.conf <<'EOF'
ServerName controller
EOF
chown root:root /etc/httpd/conf.d/00-servername.conf
chmod 0644 /etc/httpd/conf.d/00-servername.conf
restorecon -F /etc/httpd/conf.d/00-servername.conf

wsgi_source=/usr/share/keystone/wsgi-keystone.conf
wsgi_link=/etc/httpd/conf.d/wsgi-keystone.conf
[[ -f $wsgi_source && ! -L $wsgi_source ]] || die "package WSGI source missing"
if [[ -L $wsgi_link ]]; then
  [[ $(readlink "$wsgi_link") == "$wsgi_source" ]] || die "WSGI link target drift"
elif [[ -e $wsgi_link ]]; then
  die "WSGI destination is not a symlink"
else
  ln -s "$wsgi_source" "$wsgi_link"
fi

httpd -t
systemctl enable --now httpd
[[ $(ss -H -lnt '( sport = :5000 )' | wc -l) -eq 1 ]] || die "port 5000 listener mismatch"
[[ -z $(ss -H -lnt '( sport = :35357 )') ]] || die "legacy 35357 must not listen"
[[ $(curl --noproxy '*' -sS -o /dev/null -w '%{http_code}' \
  --connect-timeout 5 --max-time 10 http://controller:5000/v3/) == 200 ]] || die "v3 API failed"
[[ $(curl --noproxy '*' -sS -o /dev/null -w '%{http_code}' \
  --connect-timeout 5 --max-time 10 http://controller:5000/not-a-keystone-api-path) == 404 ]] ||
  die "unknown service path did not return 404"
```

验证结果：Apache 配置语法 OK，ServerName 为 controller，WSGI 链接目标精确；只有一个 5000 监听，旧 35357 未监听，`/v3/` 返回 200，非 API 路径返回 404。

## 无嵌入凭据的 admin-openrc 与 CLI 验证

`admin-openrc` 本身不保存密码。每次 source 都要求秘密文件是 root 所有、0600、非符号链接且只有一条格式正确的记录；任何异常都会清除 `OS_PASSWORD` 并返回失败。

```bash
cat >/root/admin-openrc <<'EOF'
# Keystone administrator environment; no credential is stored in this file.
_openstack_load_admin_env() {
  local secret_file=/root/.openstack-lab-secrets secret_record line_count metadata
  [[ -f $secret_file && ! -L $secret_file ]] || return 1
  metadata=$(stat -c '%U:%G %a' "$secret_file") || return 1
  [[ $metadata == 'root:root 600' ]] || return 1
  line_count=$(wc -l <"$secret_file") || return 1
  [[ $line_count -eq 1 ]] || return 1
  IFS= read -r secret_record <"$secret_file" || return 1
  case "$secret_record" in
    OPENSTACK_DEPLOY_PASSWORD=?*) export OS_PASSWORD=${secret_record#OPENSTACK_DEPLOY_PASSWORD=} ;;
    *) secret_record=; return 1 ;;
  esac
  secret_record=
  export OS_PROJECT_DOMAIN_NAME=Default
  export OS_USER_DOMAIN_NAME=Default
  export OS_PROJECT_NAME=admin
  export OS_USERNAME=admin
  export OS_AUTH_URL=http://controller:5000/v3
  export OS_IDENTITY_API_VERSION=3
  export OS_IMAGE_API_VERSION=2
  export OS_REGION_NAME=RegionOne
}
if ! _openstack_load_admin_env; then
  unset OS_PASSWORD
  unset -f _openstack_load_admin_env
  return 1 2>/dev/null || exit 1
fi
unset -f _openstack_load_admin_env
EOF
chown root:root /root/admin-openrc
chmod 0600 /root/admin-openrc
restorecon -F /root/admin-openrc
source /root/admin-openrc
openstack token issue -f value -c expires >/dev/null
```

令牌只验证签发成功，不输出 token ID。随后精确验证 identity 服务与端点。以下 Python 验证器在教材测试中可直接从代码块提取，并对缺项、重复接口、错误 Region 或 URL 的变体失败。

```bash
service_json=$(mktemp)
endpoint_json=$(mktemp)
trap 'rm -f -- "$service_json" "$endpoint_json"' EXIT
openstack service list -f json >"$service_json"
identity_service_id=$(
python3 - "$service_json" <<'PY'
import json
import sys

stream = open(sys.argv[1], "r", encoding="utf-8") if len(sys.argv) > 1 else sys.stdin
with stream:
    IDENTITY_SERVICE_ROWS = [row for row in json.load(stream) if row.get("Type") == "identity"]
if len(IDENTITY_SERVICE_ROWS) != 1 or IDENTITY_SERVICE_ROWS[0].get("Name") != "keystone":
    raise SystemExit("identity service mismatch")
print(IDENTITY_SERVICE_ROWS[0].get("ID", ""))
PY
)
[[ -n $identity_service_id ]] || die "identity service ID empty"
[[ $(openstack service show "$identity_service_id" -f value -c enabled) == True ]] ||
  die "identity service disabled"

openstack endpoint list --service identity -f json >"$endpoint_json"
python3 - "$endpoint_json" <<'PY'
import json
import sys

EXPECTED_INTERFACES = {"admin", "internal", "public"}
EXPECTED_URL = "http://controller:5000/v3/"
stream = open(sys.argv[1], "r", encoding="utf-8") if len(sys.argv) > 1 else sys.stdin
with stream:
    rows = json.load(stream)
if len(rows) != 3:
    raise SystemExit("identity endpoint cardinality mismatch")
if {row.get("Interface") for row in rows} != EXPECTED_INTERFACES:
    raise SystemExit("identity endpoint interface set mismatch")
if any(row.get("Region") != "RegionOne" for row in rows):
    raise SystemExit("identity endpoint region mismatch")
if any(row.get("Service Type") != "identity" for row in rows):
    raise SystemExit("identity endpoint service type mismatch")
if any(row.get("URL") != EXPECTED_URL for row in rows):
    raise SystemExit("identity endpoint URL mismatch")
PY
rm -f -- "$service_json" "$endpoint_json"
trap - EXIT
```

`service` 项目只允许 0 或 1 条。这个 OpenStack CLI 版本不支持 `project list --name`，所以先取得 Default 域的 JSON，再本地精确过滤；命令失败不会误判为“不存在”。

```bash
ensure_service_project() {
  local rows count
  rows=$(openstack project list --domain default -f json | python3 -c '
import json, sys
for row in json.load(sys.stdin):
    if row.get("Name") == "service":
        print(row.get("ID", ""))
') || die "service project list probe failed"
  count=$(sed '/^[[:space:]]*$/d' <<<"$rows" | wc -l)
  case "$count" in
    0) openstack project create --domain default --description 'Service Project' service >/dev/null ;;
    1) : "service project already exists" ;;
    *) die "service project cardinality mismatch: $count" ;;
  esac
  [[ $(openstack project show service -f value -c name) == service ]] || die "service project name mismatch"
  [[ $(openstack project show service -f value -c domain_id) == default ]] || die "service project domain mismatch"
  [[ $(openstack project show service -f value -c enabled) == True ]] || die "service project disabled"
}

ensure_service_project
unset OS_PASSWORD
```

实际验证：token 签发成功但未显示；admin 项目、用户、admin 角色及其项目角色授权各唯一；identity 服务唯一且启用；RegionOne 的 admin/internal/public 端点各一、总数三，URL 均为 `http://controller:5000/v3/`；`service` 项目连续运行两次仍只有一个。

## 最终顺序驱动器与双节点收口

最终驱动器把全部状态验证重新串成依赖链。它不代替紧跟每次变更执行的门禁。

```bash
stage_starting_state() {
  for service in chronyd mariadb rabbitmq-server memcached; do
    systemctl is-active --quiet "$service" && systemctl is-enabled --quiet "$service" || return 1
  done
}

stage_package_transaction() {
  rpm -q openstack-keystone httpd python3-mod_wsgi >/dev/null
}

stage_database() {
  [[ $(mysql -uroot --batch --skip-column-names -e \
    "SELECT Host FROM mysql.user WHERE User='keystone' ORDER BY Host;" | paste -sd, -) == '%,127.0.0.1,localhost' ]]
}

stage_configuration() {
  [[ $(stat -c '%U:%G %a' /etc/keystone/keystone.conf) == 'root:keystone 640' ]]
}

stage_schema() {
  [[ $(mysql -uroot --batch --skip-column-names -D keystone -e \
    'SELECT COUNT(*) FROM alembic_version;') -eq 2 ]]
}

stage_keys() {
  [[ $(classify_key_repository /etc/keystone/fernet-keys) == VALID ]]
  [[ $(classify_key_repository /etc/keystone/credential-keys) == VALID ]]
}

stage_bootstrap() {
  [[ $(probe_bootstrap_state) == BOOTSTRAP_STATE=FULL ]]
  [[ -f /root/.keystone-bootstrap-complete && ! -L /root/.keystone-bootstrap-complete ]]
}

stage_apache() {
  systemctl is-active --quiet httpd && systemctl is-enabled --quiet httpd
  [[ $(curl --noproxy '*' -sS -o /dev/null -w '%{http_code}' http://controller:5000/v3/) == 200 ]]
}

stage_identity_validation() {
  source /root/admin-openrc
  openstack token issue -f value -c expires >/dev/null
  unset OS_PASSWORD
}

stage_cross_slice_audit() {
  assert_packages_absent openstack-glance openstack-placement-api openstack-nova-common \
    openstack-neutron-common openstack-cinder-common openstack-swift-common python3-horizon
}

run_keystone_sequence() {
  stage_starting_state
  stage_package_transaction
  stage_database
  stage_configuration
  stage_schema
  stage_keys
  stage_bootstrap
  stage_apache
  stage_identity_validation
  stage_cross_slice_audit
}

run_keystone_sequence
```

在 compute 上执行以下只读审计。当前 compute 未安装 `pvs`，本切片不越界安装 lvm2。这里用 `lsblk` 验证块设备、50 GiB、TYPE、无子设备/文件系统/挂载和完整根祖先排除；`blkid -p` 只接受“无签名”的 RC=2；`wipefs --no-act` 必须成功且无签名输出。任一未知错误都失败。该结论仅覆盖当前可见分区、挂载和磁盘签名，不能表述为已经用 `pvs` 证明 PV 层状态。

```bash
assert_compute_data_disk() {
  local device=$1 expected_size=$2 root_source root_chain facts wipefs_output rc
  [[ -b $device ]] || die "$device is not a block device"
  [[ $(blockdev --getsize64 "$device") == "$expected_size" ]] || die "$device size drift"
  [[ $(lsblk -dnro TYPE "$device") == disk ]] || die "$device is not a whole disk"
  root_source=$(findmnt -nro SOURCE /) || die "root source probe failed"
  root_source=$(readlink -f "$root_source") || die "root source canonicalization failed"
  root_chain=$(lsblk -s -nrpo NAME "$root_source") || die "root ancestry probe failed"
  grep -Fxq "$device" <<<"$root_chain" && die "$device is a root ancestor"
  [[ $(lsblk -nrpo NAME "$device" | sed '/^[[:space:]]*$/d' | wc -l) -eq 1 ]] ||
    die "$device has child devices"
  facts=$(lsblk -dnro FSTYPE,MOUNTPOINT "$device") || die "$device fact probe failed"
  [[ -z ${facts//[[:space:]]/} ]] || die "$device has filesystem or mount"
  wipefs_output=$(wipefs --no-act --noheadings --output TYPE "$device") ||
    die "$device read-only signature inventory failed"
  [[ -z ${wipefs_output//[[:space:]]/} ]] || die "$device contains a wipefs signature"
  if blkid -p "$device" >/dev/null 2>&1; then
    die "$device contains a signature"
  else
    rc=$?
    [[ $rc -eq 2 ]] || die "$device signature probe failed"
  fi
}

assert_compute_data_disk /dev/sdb 53687091200
assert_compute_data_disk /dev/sdc 53687091200
assert_packages_absent openstack-keystone openstack-glance openstack-placement-api \
  openstack-nova-common openstack-neutron-common openstack-cinder-common \
  openstack-swift-common python3-horizon
```

最终 controller 审计为 PASS：chronyd、MariaDB、RabbitMQ、Memcached、HTTPD 均 active/enabled，Keystone API/CLI、三个端点和唯一 `service` 项目通过，Glance 及后续包缺席。compute 审计为 PASS：两块盘仍为 50 GiB 整盘，无子设备、文件系统、挂载或可见签名，后续包缺席，未执行磁盘写入。

初始临时 compute 审计曾以 `pvs ... || true` 掩盖 `pvs` 工具缺席；该写法未写磁盘，但不是可靠证据，已从修正后的过程删除。后续 Cinder/Swift 切片必须先只从 `openstack-local` 安装 lvm2，再执行 PV 层检查与完整破坏性操作门禁，未通过不得初始化 `/dev/sdb` 或 `/dev/sdc`。

## 诊断、回滚与教学安全说明

- 包事务若不再解析为仅 `openstack-local` 或出现移除/降级/替换，停止并修复离线依赖闭包；不得绕过依赖。
- 数据库授权失败时只查询数据库名和 `User/Host`，不得显示 `authentication_string`。部分创建可用参数化命令幂等补齐；不得先删库来掩盖原因。
- 配置异常时比较 `/root/openstack-lab-backups/task-5b-20260811T072646Z` 中的原包副本。恢复前先停止 HTTPD，并确认不会覆盖后续切片的新配置。
- `db_sync` 使用 Alembic，本环境的版本表是 `alembic_version`。不要照搬旧版 `migrate_version` 探针。
- 密钥仓出现部分集合或模式异常时停止诊断，不能再次执行 setup 来覆盖或轮换；生产环境还要制定密钥轮换和备份制度。
- bootstrap marker 只能辅助防重入，必须与数据库或 API 的完整证据一起使用。`PARTIAL` 状态不得自动修补。
- HTTPD 故障先运行 `httpd -t`、检查 `journalctl -u httpd` 和 `/var/log/httpd/keystone.log`；不得在未确认 WSGI 链接和配置语法前反复重启。
- `admin-openrc` 只允许 root 读取，source 后用完应 `unset OS_PASSWORD`。教材、截图和 Git 中不得出现密码、token、cookie、Fernet/credential 密钥或带凭据 URL。
- 当前为隔离教学环境，SELinux 处于 Permissive 且 firewalld 停止。生产部署应恢复 Enforcing、最小开放网络端口、启用 TLS、分离数据库与服务密码，并使用专用秘密管理与审计系统。
