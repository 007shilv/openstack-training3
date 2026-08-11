# openEuler OpenStack Antelope 两节点部署文档

## 1. 目标

本文档对应仓库中的最终版安装脚本，目标是在两台 openEuler 24.03 LTS SP3 主机上部署一套双节点 OpenStack Antelope，并扩展块存储与对象存储能力。

- 控制节点: `controller` `192.168.234.151/24`
- 计算节点: `compute` `192.168.234.150/24`
- 管理网卡: `ens33`
- Provider 网络映射网卡: `ens34`
- Cinder 后端磁盘: `compute:/dev/sdb`
- Swift 后端磁盘: `compute:/dev/sdc`
- 部署模式: `Keystone + Glance + Placement + Nova + Neutron + Cinder + Swift + Horizon`

说明:

- 当前最终交付内容只保留 `final-scripts/`、本地源构建脚本、部署文档和远程执行脚本。
- 所有最终安装脚本中的 `dnf` 安装入口均已改为: 优先使用本地源，远程源仅作为兜底。
- `Cinder` 采用 `LVM + iSCSI`，控制面在 `controller`，卷服务后端在 `compute`。
- `Swift` 采用 `controller` 代理节点 + `compute` 存储节点的两节点结构，当前仅有一个存储节点，因此 ring 采用 `replicas = 1`，只适用于实验环境。

## 2. 密码与约定

- root 密码: `<OPENSTACK_DEPLOY_PASSWORD>`
- OpenStack 服务密码: `<OPENSTACK_DEPLOY_PASSWORD>`
- OpenStack 管理员:
  - 用户名: `admin`
  - 密码: `<OPENSTACK_DEPLOY_PASSWORD>`
  - 域: `Default`
- MariaDB 数据库密码统一使用: `<OPENSTACK_DEPLOY_PASSWORD>`

这样处理的原因:

- OpenStack 服务密码按要求统一为 `<OPENSTACK_DEPLOY_PASSWORD>`
- 数据库连接串在当前组合下对 `@` 兼容性不稳定，因此数据库账号单独使用 `<OPENSTACK_DEPLOY_PASSWORD>`

## 3. 磁盘使用说明

新增的两块磁盘在 `compute` 节点上按如下方式使用:

- `sda`
  - 系统盘，根分区为 `sda2`
  - **严禁**用于 Cinder、Swift 或任何初始化/格式化操作

- `sdb`
  - 仅供 `Cinder` 使用
  - 脚本会把整块磁盘创建为 `PV`，并加入卷组 `cinder-volumes`
  - 不要提前在 `sdb` 上创建分区或文件系统

- `sdc`
  - 仅供 `Swift` 使用
  - 脚本会把整块磁盘格式化为标签为 `openstack-swift-data` 的 `XFS`
  - 挂载点为 `/srv/node/sdc`
  - 不要提前在 `sdc` 上创建分区或文件系统

注意:

- `14-compute-cinder.sh` 只会对 `sdb` 执行 `pvcreate`
- `16-compute-swift.sh` 会对 `sdc` 执行 `mkfs.xfs`
- 如果这两块盘已有业务数据，请先备份
- 脚本会拒绝根盘、根盘祖先、已挂载/分区或带有非预期签名的目标；首次初始化还必须显式设置 `ALLOW_DISK_INITIALIZATION=YES`。

## 4. 最终脚本目录

最终版脚本位于:

- `build_controller_local_repo.sh`
- `final-scripts/01-controller-network.sh`
- `final-scripts/02-compute-network.sh`
- `final-scripts/03-controller-base.sh`
- `final-scripts/04-compute-base.sh`
- `final-scripts/05-controller-services.sh`
- `final-scripts/06-controller-keystone.sh`
- `final-scripts/07-controller-glance.sh`
- `final-scripts/08-controller-placement.sh`
- `final-scripts/09-controller-nova.sh`
- `final-scripts/10-compute-nova.sh`
- `final-scripts/11-controller-neutron.sh`
- `final-scripts/12-compute-neutron.sh`
- `final-scripts/13-controller-cinder.sh`
- `final-scripts/14-compute-cinder.sh`
- `final-scripts/15-controller-swift.sh`
- `final-scripts/16-compute-swift.sh`
- `final-scripts/17-controller-horizon.sh`
- `remote_exec.py`

## 5. 本地源说明

### 5.1 本地源构建脚本

- `build_controller_local_repo.sh`
  - 在 `controller:/opt/openstack_repo` 下载本套部署所需 RPM 及依赖
  - 安装 `createrepo_c` 生成本地仓库元数据
  - 安装并启用 `vsftpd`
  - 生成:
    - `file:///opt/openstack_repo`
    - `ftp://192.168.234.151/openstack_repo`
  - 同时打包输出 `/opt/openstack_repo.zip`

### 5.2 最终安装脚本的本地源优先策略

所有 `final-scripts/*.sh` 都内置了相同的仓库选择逻辑:

- 如果本机存在 `/opt/openstack_repo/repodata/repomd.xml`，优先使用 `file:///opt/openstack_repo`
- 如果本机没有本地目录，但可以访问 `ftp://192.168.234.151/openstack_repo/repodata/repomd.xml`，优先使用 FTP 本地源
- 只有在本地源缺失或安装失败时，才回退到原始远程源

因此推荐的用法是:

- `controller` 先执行 `build_controller_local_repo.sh`
- `controller` 自己后续安装优先走 `file:///opt/openstack_repo`
- `compute` 后续安装优先走 `ftp://192.168.234.151/openstack_repo`

## 6. 脚本职责

### 6.1 网络与主机名

- `01-controller-network.sh`
  - 固定 controller 的 `ens33`
  - 设置主机名为 `controller`
  - 写入 `/etc/hosts`

- `02-compute-network.sh`
  - 固定 compute 的 `ens33`
  - 设置主机名为 `compute`
  - 写入 `/etc/hosts`

### 6.2 基础环境

- `03-controller-base.sh`
  - 调整 SELinux / firewalld
  - 安装 Antelope release 包
  - 将自动生成的 Antelope 软件源从 `SP3` 修正到 `SP2`
  - 安装并启用 `chronyd`
  - 在首次启动后执行 `chronyc -a makestep`
  - 安装时优先使用 controller 本地文件源

- `04-compute-base.sh`
  - 与控制节点相同的基础准备
  - 同样在首次启动后执行 `chronyc -a makestep`
  - 安装时优先使用 controller 的 FTP 本地源

### 6.3 控制节点基础服务

- `05-controller-services.sh`
  - 安装 `MariaDB`
  - 安装 `RabbitMQ`
  - 安装 `Memcached`
  - 安装 `python3-openstackclient`
  - 修复 `mysql-config` 与 `mariadb-config` 冲突
  - 显式给 RabbitMQ 默认 vhost `/` 授权

### 6.4 身份与镜像

- `06-controller-keystone.sh`
  - 初始化 Keystone 数据库
  - 配置 Fernet token
  - 执行 bootstrap
  - 生成 `/root/admin-openrc`

- `07-controller-glance.sh`
  - 初始化 Glance 数据库
  - 注册 `glance` 用户、角色、service、endpoint
  - 配置本地文件后端
  - 在服务启动后轮询 `http://controller:9292/`，再执行 CLI 校验

### 6.5 调度与计算

- `08-controller-placement.sh`
  - 初始化 Placement 数据库
  - 注册 `placement` 用户、service、endpoint
  - 通过 Apache 提供 Placement API

- `09-controller-nova.sh`
  - 初始化 `nova_api`、`nova`、`nova_cell0`
  - 注册 `nova` 用户、service、endpoint
  - 配置 controller 侧 `nova-api`、`scheduler`、`conductor`、`novncproxy`
  - 预留 `cinder` 区域配置

- `10-compute-nova.sh`
  - 安装 `nova-compute`
  - 配置 `libvirt` 使用 `qemu`
  - 显式设置 `compute_driver`
  - 固化 `/etc/nova/compute_id`
  - 预留 `cinder` 区域配置

### 6.6 网络

- `11-controller-neutron.sh`
  - 初始化 Neutron 数据库
  - 注册 `neutron` 用户、service、endpoint
  - 配置 ML2、Linux bridge、VXLAN、L3、DHCP、Metadata
  - `provider` 网络映射到 `ens34`

- `12-compute-neutron.sh`
  - 配置 compute 侧 `neutron-linuxbridge-agent`
  - 设置 `provider:ens34`
  - 配置 VXLAN 本地 IP 为 `192.168.234.150`

### 6.7 块存储

- `13-controller-cinder.sh`
  - 初始化 Cinder 数据库
  - 注册 `cinder` 用户、service、endpoint
  - 配置 `cinder-api`、`cinder-scheduler`
  - 创建默认卷类型 `lvm`

- `14-compute-cinder.sh`
  - 安装 `cinder-volume`
  - 将 `sdb` 初始化为 `cinder-volumes`
  - 配置 `LVMVolumeDriver`
  - 使用 `targetclid` 提供 iSCSI 导出

### 6.8 对象存储

- `15-controller-swift.sh`
  - 注册 `swift` 用户、service、endpoint
  - 安装 `swift-proxy`
  - 生成 `swift.conf`
  - 创建一份单副本 ring

- `16-compute-swift.sh`
  - 将 `sdc` 格式化并挂载到 `/srv/node/sdc`
  - 安装 `swift-account`、`swift-container`、`swift-object`
  - 配置 `rsyncd`
  - 生成与 controller 一致的 ring 文件

### 6.9 Dashboard

- `17-controller-horizon.sh`
  - 安装 `openstack-dashboard`
  - 配置 `WEBROOT=/dashboard/`
  - 配置缓存与 Horizon 登录路径

## 7. 执行前检查

执行最终脚本前，请确保:

- 两台主机都已经安装 openEuler 24.03 LTS SP3
- 如果要走完全离线/半离线方式，先在 `controller` 上构建本地源
- 如果本地源不存在，脚本才会自动回退到远程软件源
- `ens33` 是管理网卡
- `ens34` 已连接 Provider 网络，但不要手工给它配置 IP
- `compute` 节点的系统盘为 `sda`（根分区 `sda2`），并新增空白数据盘 `sdb` 和 `sdc`
- 可以直接使用 `root` 登录两台主机

建议先在 `compute` 节点检查:

```bash
lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINT
```

期望看到:

- `sda2` 为已挂载的根分区；`sda` 绝不可作为数据盘
- `sdb` 为未使用的 Cinder 数据盘
- `sdc` 为未使用的 Swift 数据盘

## 8. 推荐执行顺序

### 8.1 先在 controller 构建本地源

```bash
bash build_controller_local_repo.sh
```

构建完成后:

- `controller` 本地目录源: `file:///opt/openstack_repo`
- `compute` FTP 源: `ftp://192.168.234.151/openstack_repo`

### 8.2 在 controller 上执行

依次运行:

```bash
bash final-scripts/01-controller-network.sh
bash final-scripts/03-controller-base.sh
bash final-scripts/05-controller-services.sh
bash final-scripts/06-controller-keystone.sh
bash final-scripts/07-controller-glance.sh
bash final-scripts/08-controller-placement.sh
bash final-scripts/09-controller-nova.sh
bash final-scripts/11-controller-neutron.sh
bash final-scripts/13-controller-cinder.sh
bash final-scripts/15-controller-swift.sh
bash final-scripts/17-controller-horizon.sh
```

### 8.3 在 compute 上执行

依次运行:

```bash
bash final-scripts/02-compute-network.sh
bash final-scripts/04-compute-base.sh
bash final-scripts/10-compute-nova.sh
bash final-scripts/12-compute-neutron.sh
bash final-scripts/14-compute-cinder.sh
bash final-scripts/16-compute-swift.sh
```

### 8.4 更稳妥的整体顺序

如果从零开始部署，建议按下面的跨节点顺序执行:

```text
1. controller: 01-controller-network.sh
2. compute:    02-compute-network.sh
3. controller: 03-controller-base.sh
4. compute:    04-compute-base.sh
5. controller: 05-controller-services.sh
6. controller: 06-controller-keystone.sh
7. controller: 07-controller-glance.sh
8. controller: 08-controller-placement.sh
9. controller: 09-controller-nova.sh
10. compute:   10-compute-nova.sh
11. controller: 11-controller-neutron.sh
12. compute:   12-compute-neutron.sh
13. controller: 13-controller-cinder.sh
14. compute:   14-compute-cinder.sh
15. controller: 15-controller-swift.sh
16. compute:   16-compute-swift.sh
17. controller: 17-controller-horizon.sh
```

说明:

- `Cinder` 建议先跑 controller 再跑 compute
- `Swift` 建议先跑 controller 再跑 compute
- `Horizon` 放在最后，便于登录后直接看到最终服务状态

## 8. 使用 `remote_exec.py` 远程执行

如果希望在本地 Windows 机器上远程下发脚本，可以使用当前仓库的 `remote_exec.py`。该工具只接受固定的 `controller` 和 `compute` 角色；SSH 密码从受保护的 `OPENSTACK_SSH_PASSWORD` 环境变量读取，未设置时才进行交互式输入。不要把密码写入命令行、文档、历史记录或文件。

首次连接前，先把主机公钥写入一个临时的 `known_hosts` 文件，再通过受信任渠道人工核对显示的指纹；核对完成后才可把该文件传给工具。`ssh-keyscan` 只收集公钥，**不是**身份校验：

```powershell
ssh-keyscan 192.168.234.151,192.168.234.150 | Set-Content .\known_hosts.lab
ssh-keygen -lf .\known_hosts.lab
```

`known_hosts.lab` 仅保存经核对的公钥，不含密码；不应把未核对的首次连接静默信任。

controller 示例:

```powershell
python .\remote_exec.py --role controller --user root --known-hosts .\known_hosts.lab --stdin-file .\final-scripts\13-controller-cinder.sh -- bash -s
```

compute 示例:

```powershell
python .\remote_exec.py --role compute --user root --known-hosts .\known_hosts.lab --stdin-file .\final-scripts\16-compute-swift.sh -- bash -s
```

## 9. 部署后验证

在 controller 上执行:

```bash
source /root/admin-openrc
openstack service list
openstack compute service list
openstack network agent list
openstack volume service list
openstack endpoint list --service swift
curl -I http://controller:8080/healthcheck
```

期望结果:

- `keystone`、`glance`、`placement`、`nova`、`neutron`、`cinderv3`、`swift` 服务已注册
- `nova-scheduler`、`nova-conductor`、`nova-compute` 状态为 `up`
- `neutron-linuxbridge-agent`、`dhcp-agent`、`metadata-agent`、`l3-agent` 状态为 `UP`
- `cinder-scheduler` 与 `cinder-volume` 出现在卷服务列表中
- `swift` 有 `object-store` endpoint
- `http://controller:8080/healthcheck` 返回 `200 OK`

在 compute 上执行:

```bash
vgs
mount | grep '/srv/node/sdc'
systemctl is-active openstack-cinder-volume
systemctl is-active openstack-swift-account openstack-swift-container openstack-swift-object
```

期望结果:

- 存在卷组 `cinder-volumes`
- `sdc` 已挂载到 `/srv/node/sdc`
- `cinder-volume` 处于 `active`
- `swift` 三个存储主服务处于 `active`

## 10. Horizon 登录

登录地址:

- `http://192.168.234.151/dashboard/`

登录信息:

- 用户名: `admin`
- 密码: `<OPENSTACK_DEPLOY_PASSWORD>`
- 域: `Default`

## 11. 关键实现说明

### 11.1 软件源修正

`openstack-release-antelope` 在 openEuler 24.03 LTS SP3 上会生成指向 `SP3` 的 Antelope 源，但该地址不可用。

最终脚本统一做了这一步修正:

- 将 `openEuler-24.03-LTS-SP3` 替换为 `openEuler-24.03-LTS-SP2`

### 11.2 数据库密码单独处理

为了避免 SQLAlchemy / Alembic 在数据库连接串中处理 `@` 时出现兼容性问题:

- OpenStack 服务密码: `<OPENSTACK_DEPLOY_PASSWORD>`
- 数据库密码: `<OPENSTACK_DEPLOY_PASSWORD>`

### 11.3 RabbitMQ 默认 vhost 权限

最终脚本已显式执行:

```bash
rabbitmqctl set_permissions -p / openstack ".*" ".*" ".*"
```

用于避免 `nova-compute` 报:

- `access to vhost '/' refused`

### 11.3.1 本轮重装中的实际现象

在本次从零重装测试时，如果 `05-controller-services.sh` 没有完整跑完，或者人工中断后没有补跑 RabbitMQ 授权，`neutron-*` / `nova-*` / `cinder-*` 这类依赖消息队列的服务会报:

- `NOT_ALLOWED - access to vhost '/' refused for user 'openstack'`

因此在继续后续组件前，应确认:

```bash
rabbitmqctl list_permissions -p /
```

输出中必须包含 `openstack` 用户。

### 11.4 Antelope 的 compute_id

Antelope 要求 `nova-compute` 持久化节点身份。

最终脚本中已处理:

- `state_path = /var/lib/nova`
- 首次部署时创建 `/etc/nova/compute_id`

### 11.5 Neutron Linux bridge experimental 开关

当前仓库中的 Linux bridge 机制被标记为实验特性，必须显式开启:

```ini
[experimental]
linuxbridge = true
```

### 11.6 Cinder 的 LVM 后端

最终脚本中:

- `compute:/dev/sdb` 被加入卷组 `cinder-volumes`
- `cinder-volume` 使用 `cinder.volume.drivers.lvm.LVMVolumeDriver`
- iSCSI target helper 使用 `lioadm`
- systemd 服务为 `targetclid`

### 11.7 Swift 的单节点存储后端

最终脚本中:

- `compute:/dev/sdc` 被格式化为 `XFS`
- 挂载点为 `/srv/node/sdc`
- ring 只包含一个存储节点、一个设备
- `replicas = 1`

这意味着:

- 适合实验环境
- 不具备生产级副本冗余能力

### 11.8 Horizon WEBROOT

由于 Apache 将 Horizon 挂载在 `/dashboard`，最终脚本中已显式设置:

```python
WEBROOT = '/dashboard/'
LOGIN_URL = '/dashboard/auth/login/'
LOGOUT_URL = '/dashboard/auth/logout/'
LOGIN_REDIRECT_URL = '/dashboard/'
```

### 11.9 时钟同步与心跳判断

本轮重置后实际遇到过 `controller` 节点时钟严重漂移的问题，表现为:

- `chronyd` 已启动，但系统时间仍然明显落后
- `openstack volume service list` 中 `cinder-volume` 显示 `down`
- 其他依赖心跳的服务也可能出现误判

因此最终基础脚本中增加了:

```bash
chronyc -a makestep || true
chronyc tracking || true
chronyc sources || true
```

如果仍发现 `controller` 时间明显不对，建议先人工校正时间，再继续部署后续 OpenStack 组件。

## 12. 本轮重置环境实测结果

按本文档中的最终顺序在两台重置后的主机上实际执行后，最终验证结果如下:

- `compute = 192.168.234.150`
- `Cinder = compute:/dev/sdb`
- `Swift = compute:/dev/sdc`
- `nova-scheduler`、`nova-conductor`、`nova-compute` 均为 `up`
- `neutron` 控制面 agent 与 compute 的 `linuxbridge-agent` 均为 `UP`
- `cinder-scheduler` 与 `cinder-volume` 均为 `up`
- `Swift` proxy `http://controller:8080/info` 可返回版本信息
- `Horizon` 登录页 `http://192.168.234.151/dashboard/` 可正常返回 `200 OK`

## 13. 建议的后续初始化

完成平台安装后，建议继续做以下初始化工作:

- 上传测试镜像到 Glance
- 创建 flavor
- 创建 provider / external 网络
- 创建租户网络与子网
- 创建路由器
- 创建测试卷并挂载到虚机
- 使用对象存储创建测试 container 并上传对象
- 启动一台测试虚机验证整套链路

## 14. 交付说明

如果后续继续维护本项目，建议只以 `final-scripts/` 目录作为安装交付目录，其他脚本保留为历史记录，不再继续叠加修改。
