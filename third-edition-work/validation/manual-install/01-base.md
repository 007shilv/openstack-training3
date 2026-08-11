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

## 实验拓扑与起始状态

| 节点 | 管理地址 | 管理接口 | 第二接口 | 用途 |
| --- | --- | --- | --- | --- |
| controller | `192.168.234.151/24` | `ens33` | `ens34`，无 IP | 控制节点与本地仓库 |
| compute | `192.168.234.150/24` | `ens33` | `ens34`，无 IP | 计算节点 |

在两节点分别执行以下只读核验：

```bash
cat /etc/os-release
hostnamectl --static
ip -4 -o addr show dev ens33
ip -4 -o addr show dev ens34 || true
ip -4 route
findmnt -n -o SOURCE,FSTYPE,TARGET /
lsblk -b -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS
rpm -qa --qf '%{NAME}-%{VERSION}-%{RELEASE}.%{ARCH}\n' | sort
rpm -q openstack-release-antelope mariadb-server rabbitmq-server \
  memcached python3-openstackclient 2>/dev/null || true
```

compute 额外执行：

```bash
for disk in /dev/sdb /dev/sdc; do
  if blkid -p "$disk" >/dev/null 2>&1; then
    echo "$disk: signature-present"
  else
    rc=$?
    echo "$disk: no-visible-signature, rc=$rc"
  fi
done
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

两节点均以同一保留式方法更新 `/etc/hosts`。该命令只移除旧的 controller/compute 映射，再追加唯一的精确映射，其他条目和注释保持不变：

```bash
tmp=$(mktemp /etc/.hosts.task5a.XXXXXX)
awk '{
  keep=1
  if ($1=="192.168.234.151" || $1=="192.168.234.150") keep=0
  for (i=2; i<=NF; i++)
    if ($i=="controller" || $i=="compute") keep=0
  if (keep) print
}' /etc/hosts > "$tmp"
printf '%s\n' \
  '192.168.234.151 controller' \
  '192.168.234.150 compute' >> "$tmp"
chown root:root "$tmp"
chmod 0644 "$tmp"
restorecon -F "$tmp" >/dev/null 2>&1 || true
mv -f "$tmp" /etc/hosts
restorecon -F /etc/hosts >/dev/null 2>&1 || true
```

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
getenforce
systemctl is-active firewalld || true
systemctl is-enabled firewalld || true
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
restorecon -F /etc/yum.repos.d/openEuler.repo \
  /etc/yum.repos.d/openstack-antelope.repo >/dev/null 2>&1 || true
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
systemctl is-active chronyd
systemctl is-enabled chronyd
chronyc tracking
chronyc sources
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

随后通过两端均使用复核 host key 的 SFTP 会话，把该文件从 controller 直接流式写入 compute 的独占 root-only 临时文件，再原子改名为同一路径；没有生成本地副本，也没有把文件内容返回到执行记录。只验证以下元数据条件：两端文件均非空、大小相同、属主 `root:root`、模式 `0600`。

```bash
stat -c '%a:%U:%G' /root/.openstack-lab-secrets
test -s /root/.openstack-lab-secrets
```

代表性结果：

```text
controller: 600:root:root, non-empty
compute:    600:root:root, non-empty
metadata parity: PASS
```

## 收口检查

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
