# 02 控制节点基础设施：MariaDB、RabbitMQ、Memcached 与 OpenStack CLI

## 顺序门禁

本记录只在 `01-base.md` 的两节点身份、解析、时间和本地仓库门禁全部通过后执行。实际顺序为：

```text
controller package preflight
  -> package installation and RPM/DNF-history verification
  -> MariaDB configuration, startup, SQL verification
  -> RabbitMQ startup, user, permission, authentication verification
  -> Memcached configuration, listener and client verification
  -> OpenStack CLI version verification
```

每个箭头都是硬门禁；后一步没有与前一步并行执行。任一步失败先诊断并重验，不跳过。

从 controller 新开一个 root shell，并先建立严格会话；本页全部 `bash` 片段在该会话中按顺序执行：

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

所有显示命令都由本页的断言函数包裹；只有断言返回 0 才进入下一阶段。

## 软件包预检与安装

先定义 fail-closed 的 RPM 缺席断言，再检查脚本中提到的 MariaDB 配置包冲突。只有 RPM 查询返回 1 且英文规范输出精确表示“未安装”才接受；返回 0 是已安装，其他返回码或异常文本都是探针故障：

```bash
assert_packages_absent() {
  local package output rc
  LC_ALL=C rpm -q rpm >/dev/null 2>&1 || die "RPM database health probe failed"
  for package in "$@"; do
    if output=$(LC_ALL=C rpm -q "$package" 2>&1); then
      die "later-stage package is already installed: $package"
    else
      rc=$?
      [[ "$rc" -eq 1 ]] || die "RPM query failed for $package (rc=$rc)"
      [[ "$output" == "package $package is not installed" ]] || \
        die "unexpected RPM absence response for $package"
    fi
  done
}

assert_packages_absent mysql-config
dnf -q repoquery --disablerepo='*' --enablerepo='openstack-local' \
  --conflicts mariadb-config
```

实际结果为 `mysql-config is not installed`，而本地 `mariadb-config` 未声明冲突，因此没有执行卸载。

Task 4B 补齐经完整可信链验证的 `mysql-selinux` 和 `memcached-selinux` 后，执行无变更事务预检。`--assumeno` 的退出码 1 是本次唯一允许的非零结果，并且输出必须同时证明 163 个安装项、主动中止、没有移除类动作；其他返回码或输出差异均停止：

```bash
if preflight=$(LC_ALL=C dnf --assumeno --setopt=install_weak_deps=False \
    --disablerepo='*' --enablerepo='openstack-local' install \
    mariadb-config mariadb mariadb-server python3-PyMySQL \
    rabbitmq-server memcached python3-memcached python3-openstackclient 2>&1); then
  die "package preflight unexpectedly committed or returned success"
else
  rc=$?
  [[ "$rc" -eq 1 ]] || die "package preflight probe failed (rc=$rc)"
fi
grep -Eq 'Install[[:space:]]+163 Packages' <<<"$preflight" || \
  die "package preflight install count changed"
grep -q 'Operation aborted' <<<"$preflight" || die "package preflight did not abort"
if grep -Eiq '(^|[[:space:]])(Removing|Erasing|Obsoleting|Replacing)([[:space:]]|$)' <<<"$preflight"; then
  die "package preflight contains a removal-class action"
fi
```

预检结果：`Install 163 Packages`、`Operation aborted`（`--assumeno` 的预期退出），零 Removing/Erasing/Obsoleting/Replacing 条目。确认后执行同一包集合：

```bash
dnf -y --setopt=install_weak_deps=False \
  --disablerepo='*' --enablerepo='openstack-local' install \
  mariadb-config mariadb mariadb-server python3-PyMySQL \
  rabbitmq-server memcached python3-memcached python3-openstackclient
```

本次没有使用 `--allowerasing`、`--nodeps`、`--skip-broken` 或任何外部软件源。DNF Transaction ID 为 4，Return-Code 为 Success，163 项全部显示 `Install ... @openstack-local`，无移除或降级动作。

直接包和 policy provider 验证：

```bash
rpm -q mariadb-config mariadb mariadb-server python3-PyMySQL \
  rabbitmq-server memcached python3-memcached python3-openstackclient \
  mysql-selinux memcached-selinux policycoreutils-python-utils
dnf history info last
```

代表性版本：

```text
mariadb-server-10.5.29-4.oe2403sp3.x86_64
python3-PyMySQL-1.0.2-1.oe2403sp2.noarch
rabbitmq-server-3.9.23-2.oe2403sp3.x86_64
memcached-1.6.22-4.oe2403sp3.x86_64
python3-memcached-1.59-3.oe2403sp3.noarch
python3-openstackclient-6.2.0-1.oe2403sp2.noarch
mysql-selinux-1.0.10-1.oe2403sp3.noarch
memcached-selinux-1.6.22-4.oe2403sp3.x86_64
```

## MariaDB

实际创建 `/etc/my.cnf.d/openstack.cnf`：

```bash
test ! -e /etc/my.cnf.d/openstack.cnf
tmp=$(mktemp /etc/my.cnf.d/.openstack.cnf.task5a.XXXXXX)
trap 'rm -f -- "$tmp"' EXIT
cat > "$tmp" <<'EOF'
[mysqld]
bind-address = 0.0.0.0
default-storage-engine = innodb
innodb_file_per_table = on
max_connections = 4096
collation-server = utf8_general_ci
character-set-server = utf8
EOF
chown root:root "$tmp"
chmod 0644 "$tmp"
if command -v restorecon >/dev/null 2>&1; then
  restorecon -F "$tmp" >/dev/null
fi
mv "$tmp" /etc/my.cnf.d/openstack.cnf
trap - EXIT
if command -v restorecon >/dev/null 2>&1; then
  restorecon -F /etc/my.cnf.d/openstack.cnf >/dev/null
fi
```

启动并检查：

```bash
systemctl enable --now mariadb

assert_mariadb() {
  local sql_probe live_variables
  systemctl is-active --quiet mariadb || die "MariaDB is not active"
  systemctl is-enabled --quiet mariadb || die "MariaDB is not enabled"
  sql_probe=$(mysql -uroot --batch --skip-column-names \
    -e 'SELECT 1 AS local_sql_access;') || die "MariaDB local SQL probe failed"
  grep -qx '1' <<<"$sql_probe" || die "MariaDB SELECT 1 returned an unexpected value"
  live_variables=$(mysql -uroot --batch --skip-column-names \
    -e 'SELECT @@bind_address,@@default_storage_engine,@@innodb_file_per_table,@@max_connections,@@collation_server,@@character_set_server;') || \
    die "MariaDB live-variable probe failed"
  grep -qx $'0.0.0.0\tInnoDB\t1\t4096\tutf8_general_ci\tutf8' <<<"$live_variables" || \
    die "MariaDB live variables differ from openstack.cnf"
  ss -H -ltn '( sport = :3306 )' | \
    awk '$4 == "0.0.0.0:3306" { found=1 } END { exit !found }' || \
    die "MariaDB is not listening on 0.0.0.0:3306"
}

assert_mariadb
```

脱敏代表性输出：

```text
mariadb active=active enabled=enabled
1
0.0.0.0  InnoDB  1  4096  utf8_general_ci  utf8
LISTEN 0 869 0.0.0.0:3306 0.0.0.0:*
```

只有本地 `SELECT 1` 与六个配置变量均匹配后才进入 RabbitMQ。

## RabbitMQ

`<RABBIT_PASS>` 是文档占位符，实际值只从 `/root/.openstack-lab-secrets` 读入当前非交互 shell 的临时变量，从未输出。`configure_rabbitmq` 明确区分用户不存在与已存在两条重跑路径：不存在时先创建；已存在时跳过创建；两条路径都更新密码、重设权限并做受保护认证。认证失败分支先清除变量再调用 `die`，不会被后续 `unset` 的成功状态掩盖：

```bash
load_rabbit_password() {
  local secret_record
  secret_record=$(</root/.openstack-lab-secrets) || die "cannot read runtime secret"
  case "$secret_record" in
    OPENSTACK_DEPLOY_PASSWORD=*)
      RABBIT_PASS=${secret_record#OPENSTACK_DEPLOY_PASSWORD=}
      ;;
    *)
      die "runtime secret record has an unexpected format"
      ;;
  esac
  [[ -n "$RABBIT_PASS" ]] || die "runtime secret is empty"
  secret_record=
}

configure_rabbitmq() {
  local rabbit_password=$1
  systemctl enable --now rabbitmq-server
  if rabbitmqctl list_users | \
      awk '$1 == "openstack" { found=1 } END { exit !found }'; then
    : "openstack user already exists; keep the idempotent update path"
  else
    rabbitmqctl add_user openstack "$rabbit_password" >/dev/null
  fi
  rabbitmqctl change_password openstack "$rabbit_password" >/dev/null
  rabbitmqctl set_permissions -p / openstack '.*' '.*' '.*' >/dev/null
  if ! rabbitmqctl authenticate_user openstack "$rabbit_password" >/dev/null 2>&1; then
    unset rabbit_password
    die "RabbitMQ protected authentication failed"
  fi
  unset rabbit_password
}

assert_rabbitmq() {
  local rabbit_password=$1 users permissions
  systemctl is-active --quiet rabbitmq-server || die "RabbitMQ is not active"
  systemctl is-enabled --quiet rabbitmq-server || die "RabbitMQ is not enabled"
  users=$(rabbitmqctl list_users) || die "RabbitMQ user probe failed"
  awk '$1 == "openstack" { count++ } END { exit !(count == 1) }' <<<"$users" || \
    die "RabbitMQ openstack user is absent or duplicated"
  permissions=$(rabbitmqctl list_user_permissions openstack) || \
    die "RabbitMQ permission probe failed"
  awk '$1 == "/" && $2 == ".*" && $3 == ".*" && $4 == ".*" { found=1 } END { exit !found }' \
    <<<"$permissions" || die "RabbitMQ permissions differ from the required triple"
  if ! rabbitmqctl authenticate_user openstack "$rabbit_password" >/dev/null 2>&1; then
    unset rabbit_password
    die "RabbitMQ protected authentication assertion failed"
  fi
  unset rabbit_password
}

RABBIT_PASS=
load_rabbit_password
configure_rabbitmq "$RABBIT_PASS"
assert_rabbitmq "$RABBIT_PASS"
unset RABBIT_PASS
```

验证显示命令不含密码；真正的用户唯一性、权限三元组和认证成功已经由 `assert_rabbitmq` 判定：

```bash
systemctl is-active rabbitmq-server
systemctl is-enabled rabbitmq-server
rabbitmqctl list_users
rabbitmqctl list_user_permissions openstack
```

实际输出：

```text
rabbitmq-server active=active enabled=enabled
user        tags
openstack   []
vhost  configure  write  read
/      .*         .*     .*
protected authentication: PASS
```

诊断中确认本发行包不支持 `--formatter=tsv`；因此教材使用上面经实际验证的原生表格输出。该显示兼容问题不影响用户创建、密码更新、权限设置或认证检查。

## Memcached

软件包首次创建 `/etc/sysconfig/memcached` 后，先保存包默认配置：

```bash
cp -a /etc/sysconfig/memcached \
  /root/openstack-lab-backups/task-5a-20260811T043901Z/etc-sysconfig-memcached.package-default
```

实际写入配置：

```bash
tmp=$(mktemp /etc/sysconfig/.memcached.task5a.XXXXXX)
trap 'rm -f -- "$tmp"' EXIT
cat > "$tmp" <<'EOF'
PORT="11211"
USER="memcached"
MAXCONN="1024"
CACHESIZE="64"
OPTIONS="-l 127.0.0.1,::1,192.168.234.151"
EOF
chown root:root "$tmp"
chmod 0644 "$tmp"
if command -v restorecon >/dev/null 2>&1; then
  restorecon -F "$tmp" >/dev/null
fi
mv "$tmp" /etc/sysconfig/memcached
trap - EXIT
if command -v restorecon >/dev/null 2>&1; then
  restorecon -F /etc/sysconfig/memcached >/dev/null
fi
systemctl enable --now memcached
```

服务、监听集合和读写验证由一个断言函数完成。监听必须与三个预期地址精确相等，不能多出通配地址或其他接口；Python 客户端的 set/get/delete 任一步失败均显式抛出异常并使阶段非零退出：

```bash
assert_memcached() {
  local expected_listeners actual_listeners
  systemctl is-active --quiet memcached || die "Memcached is not active"
  systemctl is-enabled --quiet memcached || die "Memcached is not enabled"
  expected_listeners=$(printf '%s\n' \
    '127.0.0.1:11211' \
    '192.168.234.151:11211' \
    '[::1]:11211' | sort)
  actual_listeners=$(ss -H -lnt '( sport = :11211 )' | awk '{print $4}' | sort -u) || \
    die "Memcached listener probe failed"
  [[ "$actual_listeners" == "$expected_listeners" ]] || \
    die "Memcached listener set differs from the required three addresses"

  python3 - <<'PY'
import memcache

servers = (
    'inet:127.0.0.1:11211',
    'inet6:[::1]:11211',
    'inet:192.168.234.151:11211',
)
for server in servers:
    client = memcache.Client([server], socket_timeout=2)
    key = 'task5a_listener_check'
    if not client.set(key, 'PASS', time=10):
        raise RuntimeError(f'memcached set failed: {server}')
    if client.get(key) != 'PASS':
        raise RuntimeError(f'memcached get failed: {server}')
    if not client.delete(key):
        raise RuntimeError(f'memcached delete failed: {server}')
    if client.get(key) is not None:
        raise RuntimeError(f'memcached delete verification failed: {server}')
PY
}

assert_memcached
```

实际监听：

```text
192.168.234.151:11211
127.0.0.1:11211
[::1]:11211
```

本发行版 `python3-memcached 1.59` 的 IPv6 连接串必须带 `inet6:` 前缀；普通 `::1` 或 `[::1]:11211` 会在客户端解析阶段失败，这不是 Memcached 监听故障。

## OpenStack CLI

前三项基础设施门禁均通过后，最后执行：

```bash
assert_openstack_cli() {
  local version
  version=$(openstack --version 2>&1) || die "OpenStack CLI execution failed"
  [[ "$version" == "openstack 6.2.0" ]] || die "unexpected OpenStack CLI version: $version"
}

assert_openstack_cli
```

实际输出：

```text
openstack 6.2.0
```

此处只验证客户端可执行。没有安装 Keystone、Glance、Placement、Nova、Neutron、Cinder、Swift 或 Horizon 服务包，也没有创建任何 OpenStack 数据库、用户、服务或端点。

## 最终验证

下面的阶段驱动器把安装后状态重新串成同一真实短路链；它不替代各节紧随变更执行的断言，而是证明收口时仍满足相同顺序。`run_infrastructure_sequence` 中每个调用只有在前一调用返回 0 后才会开始：

```bash
stage_package_install() {
  rpm -q mariadb-config mariadb mariadb-server python3-PyMySQL \
    rabbitmq-server memcached python3-memcached python3-openstackclient \
    mysql-selinux memcached-selinux policycoreutils-python-utils >/dev/null || \
    die "one or more infrastructure packages are absent"
}

stage_mariadb() {
  assert_mariadb
}

stage_rabbitmq() {
  local RABBIT_PASS=
  load_rabbit_password
  assert_rabbitmq "$RABBIT_PASS"
  unset RABBIT_PASS
}

stage_memcached() {
  assert_memcached
}

stage_openstack_cli() {
  assert_openstack_cli
}

run_infrastructure_sequence() {
  stage_package_install
  stage_mariadb
  stage_rabbitmq
  stage_memcached
  stage_openstack_cli
}

run_infrastructure_sequence

later_packages=(
  openstack-keystone
  openstack-glance
  openstack-placement-api
  openstack-nova-common
  openstack-neutron-common
  openstack-cinder-common
  openstack-swift-common
  python3-horizon
)
assert_packages_absent "${later_packages[@]}"
ss -lnt '( sport = :3306 or sport = :5672 or sport = :11211 )'
```

结果：三服务均 `active/enabled`；MariaDB 监听 `0.0.0.0:3306`，RabbitMQ 监听 `*:5672`，Memcached 只监听三个指定地址；所有后续服务包均未安装。compute 未安装任何本页基础设施包，`/dev/sdb` 和 `/dev/sdc` 仍为空白 50 GiB 整盘。

## 诊断与回滚说明

- 包事务必须先用 `--assumeno` 证明可解、只来自 `openstack-local` 且无移除类动作；如果依赖失败，应补齐并复核离线供应链，禁止使用 `--allowerasing`、`--nodeps` 或网络源绕过。
- MariaDB 失败时先运行 `mariadbd --help --verbose` 或检查 `journalctl -u mariadb`，再核对 `openstack.cnf`；不得跳过 SQL 和变量验证。
- RabbitMQ 失败时检查主机名解析、`journalctl -u rabbitmq-server`、原生 `list_users` 和 `list_user_permissions`；不得输出密码进行“验证”。
- Memcached 失败时先区分服务监听与客户端连接串解析；本环境 IPv6 客户端语法是 `inet6:[::1]:11211`。
- 回滚命令未执行。配置回滚只应在核对备份后恢复 `/etc/sysconfig/memcached` 的包默认副本并重启；`openstack.cnf` 是本任务新建文件，移除前必须先停止 MariaDB 并确认后续切片尚未创建数据库。
- 本实验为隔离教学环境。生产部署应按角色收窄 MariaDB、RabbitMQ 和 Memcached 监听及防火墙规则，启用 TLS、独立强密码和密钥管理系统，并恢复 SELinux Enforcing。

## 后续依赖顺序

后续切片不得并行抢跑，固定依赖顺序为：

```text
Keystone
  -> Glance
  -> Placement / Nova
  -> Neutron
  -> Cinder / Swift
  -> Horizon
```

其中每一层必须完成数据库、服务、端点、配置同步和 API/CLI 验证，才允许进入下一层。Cinder/Swift 虽获准在纯实验环境初始化数据盘，仍必须保留 fail-closed 的系统盘、根盘祖先、签名、分区、挂载和 LVM 状态检查。
