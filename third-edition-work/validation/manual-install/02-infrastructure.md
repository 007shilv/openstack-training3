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

## 软件包预检与安装

先检查脚本中提到的 MariaDB 配置包冲突：

```bash
rpm -q mysql-config
dnf -q repoquery --disablerepo='*' --enablerepo='openstack-local' \
  --conflicts mariadb-config
```

实际结果为 `mysql-config is not installed`，而本地 `mariadb-config` 未声明冲突，因此没有执行卸载。

Task 4B 补齐经完整可信链验证的 `mysql-selinux` 和 `memcached-selinux` 后，执行无变更事务预检：

```bash
dnf --assumeno --setopt=install_weak_deps=False \
  --disablerepo='*' --enablerepo='openstack-local' install \
  mariadb-config mariadb mariadb-server python3-PyMySQL \
  rabbitmq-server memcached python3-memcached python3-openstackclient
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
restorecon -F "$tmp" >/dev/null 2>&1 || true
mv "$tmp" /etc/my.cnf.d/openstack.cnf
trap - EXIT
restorecon -F /etc/my.cnf.d/openstack.cnf >/dev/null 2>&1 || true
```

启动并检查：

```bash
systemctl enable --now mariadb
systemctl is-active mariadb
systemctl is-enabled mariadb
mysql -uroot --batch --skip-column-names \
  -e 'SELECT 1 AS local_sql_access;'
mysql -uroot --batch --skip-column-names \
  -e 'SELECT @@bind_address,@@default_storage_engine,@@innodb_file_per_table,@@max_connections,@@collation_server,@@character_set_server;'
ss -ltn '( sport = :3306 )'
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

`<RABBIT_PASS>` 是文档占位符，实际值只从 `/root/.openstack-lab-secrets` 读入当前非交互 shell 的临时变量，从未输出。实际执行逻辑：

```bash
secret_record=$(</root/.openstack-lab-secrets)
case "$secret_record" in
  OPENSTACK_DEPLOY_PASSWORD=*)
    RABBIT_PASS=${secret_record#OPENSTACK_DEPLOY_PASSWORD=}
    ;;
  *)
    exit 41
    ;;
esac
test -n "$RABBIT_PASS"

systemctl enable --now rabbitmq-server
rabbitmqctl add_user openstack "$RABBIT_PASS" >/dev/null
rabbitmqctl change_password openstack "$RABBIT_PASS" >/dev/null
rabbitmqctl set_permissions -p / openstack '.*' '.*' '.*' >/dev/null
rabbitmqctl authenticate_user openstack "$RABBIT_PASS" >/dev/null 2>&1
unset RABBIT_PASS secret_record
```

再次运行时，若用户已经存在，应跳过 `add_user`，只执行 `change_password` 和权限设置。验证命令不显示密码：

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
restorecon -F "$tmp" >/dev/null 2>&1 || true
mv "$tmp" /etc/sysconfig/memcached
trap - EXIT
restorecon -F /etc/sysconfig/memcached >/dev/null 2>&1 || true
systemctl enable --now memcached
```

服务与监听检查：

```bash
systemctl is-active memcached
systemctl is-enabled memcached
ss -lnt '( sport = :11211 )'
```

实际监听：

```text
192.168.234.151:11211
127.0.0.1:11211
[::1]:11211
```

使用已安装的 `python3-memcached` 对三个监听逐一执行短期 set/get/delete：

```bash
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
    assert client.set(key, 'PASS', time=10), server
    assert client.get(key) == 'PASS', server
    client.delete(key)
print('python3-memcached set/get: PASS on 127.0.0.1, ::1, 192.168.234.151')
PY
```

本发行版 `python3-memcached 1.59` 的 IPv6 连接串必须带 `inet6:` 前缀；普通 `::1` 或 `[::1]:11211` 会在客户端解析阶段失败，这不是 Memcached 监听故障。

## OpenStack CLI

前三项基础设施门禁均通过后，最后执行：

```bash
openstack --version
```

实际输出：

```text
openstack 6.2.0
```

此处只验证客户端可执行。没有安装 Keystone、Glance、Placement、Nova、Neutron、Cinder、Swift 或 Horizon 服务包，也没有创建任何 OpenStack 数据库、用户、服务或端点。

## 最终验证

```bash
systemctl is-active mariadb rabbitmq-server memcached
systemctl is-enabled mariadb rabbitmq-server memcached
rpm -q openstack-keystone openstack-glance openstack-placement-api \
  openstack-nova-common openstack-neutron-common openstack-cinder-common \
  openstack-swift-common python3-horizon 2>/dev/null || true
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
