# 10 Cinder 控制节点手工部署

本节在第 08、09 节 Neutron 验收后执行。`13-controller-cinder.sh` 仅供核对参数和顺序，**严禁执行**。学生逐条输入命令、手工编辑配置；不进入 Swift/Horizon，不创建快照，不附加卷。

## 只读双节点门禁

先在 controller 复核身份、本地源、Nova/Neutron 健康和 Cinder 缺席；使用经复核的 known_hosts 及 `paramiko.RejectPolicy()` 对 compute 作只读复核。此阶段不写 `/dev/sdb`、`/dev/sdc`。

```bash
set -Eeuo pipefail
[[ $(hostnamectl --static) == controller ]]
ip -4 -o addr show ens33 | grep -Fq '192.168.234.151/24'
dnf -q repolist --disablerepo='*' --enablerepo='openstack-local' | grep -Fxq openstack-local
for s in openstack-nova-api neutron-server neutron-linuxbridge-agent neutron-dhcp-agent neutron-metadata-agent neutron-l3-agent; do systemctl is-active --quiet "$s" && systemctl is-enabled --quiet "$s"; done
rpm -q openstack-cinder-common >/dev/null 2>&1 && exit 1 || [[ $? -eq 1 ]]
[[ $(mysql -uroot -NBe "SELECT COUNT(*) FROM information_schema.SCHEMATA WHERE SCHEMA_NAME='cinder'") == 0 ]]
```

## 本地源安装、备份与数据库

仅使用 `openstack-local`；出现 Removing、Erasing、Obsoleting、Replacing 或 Downgrading 立即停止。编辑前将包默认文件备份到远端仅 root 可读目录。

```bash
set -Eeuo pipefail
dnf repoquery --available --disablerepo='*' --enablerepo='openstack-local' openstack-cinder openstack-cinder-api openstack-cinder-scheduler >/dev/null
dnf -y --disablerepo='*' --enablerepo='openstack-local' --setopt=install_weak_deps=False install openstack-cinder openstack-cinder-api openstack-cinder-scheduler
dnf history info "$(dnf history | awk 'NR==3 {print $1}')"
rpm -V openstack-cinder openstack-cinder-api openstack-cinder-scheduler
umask 077; backup=/root/openstack-lab-backups/task-5g-<UTC>; install -d -m 700 "$backup"
cp -a /etc/cinder/cinder.conf /etc/nova/nova.conf "$backup"/
```

在 MariaDB 逐条执行；真实口令仅运行时输入，绝不写入教材、快照或历史。

```sql
CREATE DATABASE cinder;
CREATE USER 'cinder'@'localhost' IDENTIFIED BY '<DB_PASSWORD>';
CREATE USER 'cinder'@'127.0.0.1' IDENTIFIED BY '<DB_PASSWORD>';
CREATE USER 'cinder'@'%' IDENTIFIED BY '<DB_PASSWORD>';
GRANT ALL PRIVILEGES ON cinder.* TO 'cinder'@'localhost';
GRANT ALL PRIVILEGES ON cinder.* TO 'cinder'@'127.0.0.1';
GRANT ALL PRIVILEGES ON cinder.* TO 'cinder'@'%';
FLUSH PRIVILEGES;
```

## 身份、服务、端点与控制面配置

`cinder` 用户必须为 Default 域用户，在 service 项目获得全局 admin；启用 `cinderv3`/`volumev3`，三个 RegionOne 端点均为 `http://controller:8776/v3/%(project_id)s`。对象已存在时必须先逐项核对而非盲目重建。

```bash
source /root/admin-openrc
openstack user create --domain Default --password '<SERVICE_PASSWORD>' cinder
openstack role add --project service --user cinder admin
openstack service create --name cinderv3 --description 'OpenStack Block Storage' volumev3
openstack endpoint create --region RegionOne volumev3 public 'http://controller:8776/v3/%(project_id)s'
openstack endpoint create --region RegionOne volumev3 internal 'http://controller:8776/v3/%(project_id)s'
openstack endpoint create --region RegionOne volumev3 admin 'http://controller:8776/v3/%(project_id)s'
```

手工 `vi /etc/cinder/cinder.conf`，其中 `<URL_ENCODED_PASSWORD>` 为 URL 编码后的运行时口令：

```ini
[DEFAULT]
transport_url = rabbit://openstack:<URL_ENCODED_PASSWORD>@controller
auth_strategy = keystone
my_ip = 192.168.234.151
glance_api_servers = http://controller:9292
default_volume_type = lvm
[database]
connection = mysql+pymysql://cinder:<URL_ENCODED_PASSWORD>@127.0.0.1/cinder
[keystone_authtoken]
www_authenticate_uri = http://controller:5000
auth_url = http://controller:5000
memcached_servers = controller:11211
auth_type = password
project_domain_name = Default
user_domain_name = Default
project_name = service
username = cinder
password = <SERVICE_PASSWORD>
[oslo_concurrency]
lock_path = /var/lib/cinder/tmp
[nova]
auth_url = http://controller:5000
auth_type = password
project_domain_name = Default
user_domain_name = Default
region_name = RegionOne
project_name = service
username = nova
password = <SERVICE_PASSWORD>
```

```bash
su -s /bin/sh -c 'cinder-manage db sync' cinder
systemctl enable --now openstack-cinder-api openstack-cinder-scheduler
vi /etc/nova/nova.conf # [cinder] 中加入 os_region_name = RegionOne
systemctl restart openstack-nova-api
source /root/admin-openrc
openstack volume type create lvm
openstack volume type set --property volume_backend_name=LVM-ISCSI lvm
openstack volume type show lvm
```
