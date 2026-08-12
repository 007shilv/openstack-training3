# 08 Neutron 控制节点手工部署记录

本节在已验收的 Nova 双节点基础上手工部署 Neutron 控制平面。`11-controller-neutron.sh` 只能用于核对参数与顺序，**不得执行**。所有安装、数据库、身份对象、配置编辑、数据库同步和服务启用均由学生逐条输入；本文中的 Python/Paramiko 片段只用于只读核验，绝不是安装入口。

本切片只允许创建一次任务专属的私有网络，并在验收中按其精确 ID 删除。不得创建 provider network、子网、路由器或实例；不得进入 Cinder、Swift、Horizon；不得写入 `/dev/sdb` 或 `/dev/sdc`，也不创建或恢复快照。

## 只读双节点门禁

在 controller 本机确认身份、仅有本地源、Nova 健康和后续组件仍缺席；`ens34` 不得存在 IPv4 或全局 IPv6 地址。

```bash
set -Eeuo pipefail
[[ $(hostnamectl --static) == controller ]]
ip -4 -o addr show ens33 | grep -Fq '192.168.234.151/24'
[[ -z $(ip -4 -o addr show ens34) && -z $(ip -6 -o addr show ens34 scope global) ]]
dnf -q repolist --disablerepo='*' --enablerepo='openstack-local' | grep -Fxq openstack-local
for s in openstack-nova-api openstack-nova-scheduler openstack-nova-conductor openstack-nova-novncproxy; do systemctl is-active --quiet "$s" && systemctl is-enabled --quiet "$s"; done
for p in openstack-neutron-common openstack-neutron openstack-neutron-ml2 openstack-neutron-linuxbridge openstack-cinder-common openstack-swift-common python3-horizon; do rpm -q "$p" >/dev/null 2>&1 && exit 1 || [[ $? -eq 1 ]]; done
[[ $(mysql -uroot -NBe "SELECT COUNT(*) FROM information_schema.SCHEMATA WHERE SCHEMA_NAME IN ('neutron','cinder')") == 0 ]]
```

两节点远程复核只加载已复核的主机密钥，拒绝未知或变化的密钥；密码仅保存在运行时内存中，不能写入命令历史、文件、快照或教材产物。

```python
from pathlib import Path
import paramiko

HOSTS = {
    "controller": ("192.168.234.151", Path(".superpowers/sdd/known_hosts.controller")),
    "compute": ("192.168.234.150", Path(".superpowers/sdd/known_hosts.compute")),
}

def connect_read_only(name: str, password: str) -> paramiko.SSHClient:
    host, known_hosts = HOSTS[name]
    client = paramiko.SSHClient()
    client.load_host_keys(str(known_hosts))
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    client.connect(host, username="root", password=password, look_for_keys=False, allow_agent=False,
                   timeout=10, auth_timeout=10, banner_timeout=10)
    return client
```

在 compute 以同样方式重新执行身份、本地源、Nova、`ens34` 检查，并只读确认 `/dev/sdb`、`/dev/sdc` 均为 50 GiB 无子设备、无文件系统和无签名的 disk。任一查询错误、已存在 Neutron 部分状态或磁盘漂移都停止，不把错误当作“对象不存在”。

## 控制节点本地源软件包

先确认每一个所需 RPM 可以只从 `openstack-local` 取得，再手工安装。禁止外部源、`--allowerasing`、`--nodeps`、`--skip-broken` 和任何删除/降级操作；安装事务若出现 Removing、Erasing、Obsoleting、Replacing 或 Downgrading 立即停止并审查 `dnf history info`。

```bash
set -Eeuo pipefail
dnf repoquery --available --disablerepo='*' --enablerepo='openstack-local' \
  openstack-neutron openstack-neutron-ml2 openstack-neutron-linuxbridge ebtables ipset >/dev/null
dnf -y --disablerepo='*' --enablerepo='openstack-local' --setopt=install_weak_deps=False install \
  openstack-neutron openstack-neutron-ml2 openstack-neutron-linuxbridge ebtables ipset
dnf history info "$(dnf history | awk 'NR==3 {print $1}')"
rpm -V openstack-neutron openstack-neutron-ml2 openstack-neutron-linuxbridge
```

第一次编辑前，把软件包默认配置备份到本节点受限目录，例如 `/root/openstack-lab-backups/task-5f-<UTC>/`；备份包含 `neutron.conf`、ML2/Linux bridge、L3、DHCP、metadata 与 sysctl 文件（原文件存在时）。备份不包含口令，路径和清单写入本任务报告。随后手工建立 bridge netfilter 配置并立即核验：

```bash
cat >/etc/sysctl.d/99-openstack-neutron.conf <<'EOF'
net.bridge.bridge-nf-call-iptables = 1
net.bridge.bridge-nf-call-ip6tables = 1
EOF
modprobe br_netfilter
sysctl --system
sysctl -n net.bridge.bridge-nf-call-iptables
sysctl -n net.bridge.bridge-nf-call-ip6tables
```

## neutron 数据库与三条主机授权

在 controller 的 MariaDB 中逐条输入以下 SQL；将三个 `<DB_PASSWORD>` 手工替换为同一 Neutron 数据库口令。这里刻意不使用自动化循环或脚本化授权。

```sql
CREATE DATABASE neutron;
CREATE USER 'neutron'@'localhost' IDENTIFIED BY '<DB_PASSWORD>';
CREATE USER 'neutron'@'127.0.0.1' IDENTIFIED BY '<DB_PASSWORD>';
CREATE USER 'neutron'@'%' IDENTIFIED BY '<DB_PASSWORD>';
GRANT ALL PRIVILEGES ON neutron.* TO 'neutron'@'localhost';
GRANT ALL PRIVILEGES ON neutron.* TO 'neutron'@'127.0.0.1';
GRANT ALL PRIVILEGES ON neutron.* TO 'neutron'@'%';
FLUSH PRIVILEGES;
```

完成后只读核验数据库及主机范围恰为 `localhost`、`127.0.0.1`、`%` 三条；不得把口令或 `SHOW GRANTS` 原文复制到仓库或报告。

```bash
mysql -uroot -NBe "SELECT COUNT(*) FROM information_schema.SCHEMATA WHERE SCHEMA_NAME='neutron'"
mysql -uroot -NBe "SELECT Host FROM mysql.user WHERE User='neutron' ORDER BY Host"
```

## 身份、服务和端点

加载管理员环境后，按以下条目创建并立即查询每一个对象。用户必须属于 Default 域，角色为 service 项目中的全局 admin；服务名为 `neutron`、类型为 `network` 并且启用。三个端点均为 RegionOne 的 `http://controller:9696`。

```bash
source /root/admin-openrc
openstack user create --domain Default --password '<SERVICE_PASSWORD>' neutron
openstack user show neutron
openstack role add --project service --user neutron admin
openstack role assignment list --user neutron --project service --role admin
openstack service create --name neutron --description 'OpenStack Networking' network
openstack service show neutron
openstack endpoint create --region RegionOne network public http://controller:9696
openstack endpoint create --region RegionOne network internal http://controller:9696
openstack endpoint create --region RegionOne network admin http://controller:9696
openstack endpoint list --service neutron
```

如任一创建命令提示对象已存在，先查询其 ID、域、启用状态、服务类型、Region、接口和 URL；只有完全一致才继续，重复、缺少或错误绑定均停止处理。

## 手工编辑控制节点配置

建立插件链接，再逐一使用 `vi` 编辑下列全部文件。每项都应手工输入并核对；`<URL_ENCODED_PASSWORD>` 为经过 URL 编码的同一运行时口令，`<SERVICE_PASSWORD>` 是原始服务口令。**不要**把实际口令写入教材快照。

```bash
ln -s /etc/neutron/plugins/ml2/ml2_conf.ini /etc/neutron/plugin.ini
vi /etc/neutron/neutron.conf
```

```ini
[DEFAULT]
core_plugin = ml2
service_plugins = router
transport_url = rabbit://openstack:<URL_ENCODED_PASSWORD>@controller
auth_strategy = keystone
notify_nova_on_port_status_changes = true
notify_nova_on_port_data_changes = true

[database]
connection = mysql+pymysql://neutron:<URL_ENCODED_PASSWORD>@127.0.0.1/neutron

[keystone_authtoken]
www_authenticate_uri = http://controller:5000
auth_url = http://controller:5000
memcached_servers = controller:11211
auth_type = password
project_domain_name = Default
user_domain_name = Default
project_name = service
username = neutron
password = <SERVICE_PASSWORD>

[nova]
auth_url = http://controller:5000
auth_type = password
project_domain_name = Default
user_domain_name = Default
region_name = RegionOne
project_name = service
username = nova
password = <SERVICE_PASSWORD>

[oslo_concurrency]
lock_path = /var/lib/neutron/tmp

[experimental]
linuxbridge = true
```

```bash
vi /etc/neutron/plugins/ml2/ml2_conf.ini
```

```ini
[ml2]
type_drivers = flat,vxlan
tenant_network_types = vxlan
mechanism_drivers = linuxbridge,l2population
extension_drivers = port_security

[ml2_type_flat]
flat_networks = provider

[ml2_type_vxlan]
vni_ranges = 1:1000

[securitygroup]
enable_ipset = true
```

```bash
vi /etc/neutron/plugins/ml2/linuxbridge_agent.ini
```

```ini
[linux_bridge]
physical_interface_mappings = provider:ens34

[vxlan]
enable_vxlan = true
local_ip = 192.168.234.151
l2_population = true

[securitygroup]
enable_security_group = true
firewall_driver = neutron.agent.linux.iptables_firewall.IptablesFirewallDriver
```

```bash
vi /etc/neutron/l3_agent.ini
```

```ini
[DEFAULT]
interface_driver = linuxbridge
```

```bash
vi /etc/neutron/dhcp_agent.ini
```

```ini
[DEFAULT]
interface_driver = linuxbridge
dhcp_driver = neutron.agent.linux.dhcp.Dnsmasq
enable_isolated_metadata = true
```

```bash
vi /etc/neutron/metadata_agent.ini
```

```ini
[DEFAULT]
nova_metadata_host = controller
metadata_proxy_shared_secret = <SERVICE_PASSWORD>
```

逐个以只读方式复核 `provider:ens34`，本机 VXLAN 地址 `.151`、VNI `1:1000`、ML2 flat+VXLAN、Linux bridge experimental 标志和 metadata shared secret 已设置；同时确认 `ens34` 仍然没有地址，不能为了验证映射而为其配置 IP。

## 数据库同步与启用控制节点服务

以 neutron 身份手工同步数据库；返回成功后才重启 Nova API，随后一次性启用并启动 Neutron server、Linux bridge、DHCP、metadata、L3 agents。服务启动命令不是配置编辑或数据库同步的替代品。

```bash
su -s /bin/sh -c 'neutron-db-manage --config-file /etc/neutron/neutron.conf --config-file /etc/neutron/plugins/ml2/ml2_conf.ini upgrade head' neutron
systemctl restart openstack-nova-api
systemctl enable --now neutron-server neutron-linuxbridge-agent neutron-dhcp-agent neutron-metadata-agent neutron-l3-agent
for s in neutron-server neutron-linuxbridge-agent neutron-dhcp-agent neutron-metadata-agent neutron-l3-agent openstack-nova-api; do systemctl is-active --quiet "$s" && systemctl is-enabled --quiet "$s"; done
ss -H -lnt '( sport = :9696 )'
```

将最终实际配置复制为脱敏快照：所有数据库、RabbitMQ、Keystone、Nova 与 metadata 口令分别替换为 `<URL_ENCODED_PASSWORD>` 或 `<SERVICE_PASSWORD>`，不得保留真实口令或其散列。计算节点完成后，按下一节的轻量验收检查 API、agents 和唯一私有网络的完整生命周期。
