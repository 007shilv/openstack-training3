# Task 5 研究底稿：openEuler 24.03 LTS SP3 上的基础服务与 Keystone（OpenStack 2023.1 Antelope）

## 1. 研究范围与口径

- 事实冻结日期：**2026-07-31**。资料检索日期为 2026-08-12，但本文不引入冻结日之后发生的新事实。
- 教材实验平台：openEuler 24.03 LTS SP3；OpenStack 实验版本：2023.1 Antelope；控制节点：`controller`（`192.168.234.151`）。
- 本底稿只服务于第二版母稿的第5章基础服务和第6章 Keystone 改写，不是部署验收报告。
- 教材写法必须是：Linux 命令逐条输入、使用 `vi` 手工编辑配置文件、手工执行数据库操作、手工启动服务。
- 本底稿不提供任何 Python 程序、远程执行器、Shell 函数、条件循环、一键脚本、门禁程序或自动验证程序。软件包名中出现的 `python3-PyMySQL`、`python3-memcached`、`python3-openstackclient`、`python3-mod_wsgi` 是发行版 RPM 名称，不是教材中的 Python 编程内容。
- `agent-reach` 命令在当前环境不可用，本次按技能降级规则仅使用 OpenStack、Keystone、openEuler 官方一手资料，并用本地已经实测的手工记录核对 openEuler 包名、路径和参数。
- research 技能通常建议将研究派给后台研究者；本任务明确禁止派发，因此由当前任务直接完成。

## 2. 版本边界与不得混淆的事实

1. OpenStack 2023.1 的代号是 **Antelope**，协调版本于 2023-03-22 发布。OpenStack 官方到冻结日已将 2023.1 标注为旧的、未维护版本。因此教材只能称它为“本书实验版本”或“适配本地离线源的教学版本”，不能称为2026年的最新OpenStack版本。
2. 第三版前部介绍OpenStack社区和产业时，可以更新至冻结日的社区状态；第5、6章的命令和配置必须明确落在 **OpenStack 2023.1 Antelope**，不能把新版本概览中的软件包名、默认配置或API行为直接套入Antelope实验。
3. openEuler官方确认24.03 LTS SP3面向服务器、云计算和AI场景，内核基线为Linux 6.6。该事实可用于信创平台背景介绍，但不能推导出“OpenStack上游官方认证了SP3+Antelope”这一结论。
4. 本地离线源中的Antelope服务包主要来自openEuler 24.03 LTS SP2构建，已在SP3主机上完成实际部署。教材应表述为“本书经实训验证的兼容组合”，不得写成OpenStack社区或openEuler官方发布的通用兼容性承诺。
5. 本地实测的Keystone根包为`openstack-keystone-23.0.1-1.oe2403sp2`，与Antelope的Keystone 23系列相符；不能将2026.1版本的Keystone安装参数写入本章。

## 3. 第5章与第6章的依赖顺序

教材应保留第二版“前一实训完成后再进行后一实训”的任务链，但不写成门禁或验收合同。推荐顺序如下：

1. 两节点已完成主机名、管理地址、`/etc/hosts`、本地软件源和时间同步配置。
2. 在controller安装基础软件包。
3. 配置并启动MariaDB。
4. 启动RabbitMQ，创建`openstack`消息队列用户并授权。
5. 配置并启动Memcached。
6. 安装OpenStack统一命令行客户端。
7. 安装Keystone和Apache组件。
8. 创建Keystone数据库、数据库用户及授权。
9. 使用`vi`修改`/etc/keystone/keystone.conf`。
10. 手工同步Keystone数据库。
11. 初始化Fernet密钥仓和Credential密钥仓。
12. 执行`keystone-manage bootstrap`，初始化Default域、admin项目、admin用户、角色、identity服务和三类端点。
13. 配置Apache与Keystone WSGI，启用并启动`httpd`。
14. 使用`vi`创建`admin-openrc`并加载环境变量。
15. 创建供后续各组件服务用户使用的`service`项目。
16. 到此结束Keystone部署，进入下一章Glance；不在本章追加API、端口、Token或资源验证。

OpenStack上游Keystone安装教程把“创建数据库”列为安装服务包之前的前置条件。第二版教材原有流程是“先安装组件、再创建数据库”。两者在功能上并不冲突；为保持母稿流程，可继续先安装RPM，但必须保证在执行`keystone-manage db_sync`前已完成建库、建用户和授权。

## 4. 第5章基础服务教学内容

### 4.1 四项基础服务的作用

| 服务 | 教材中的准确作用 | 不应使用的夸大说法 |
|---|---|---|
| MariaDB | 保存Keystone、Glance、Nova、Neutron、Cinder等控制面服务的持久化元数据。数据库通常部署在controller。 | 不说MariaDB保存虚拟机磁盘、镜像文件或全部云数据。 |
| RabbitMQ | 为OpenStack各服务之间传递RPC请求、操作指令和状态信息，解耦API、调度器、计算与网络等进程。 | 不说RabbitMQ本身负责资源调度，也不说它保存所有业务状态。 |
| Memcached | 为身份认证相关数据提供高速缓存，减少重复认证和数据库访问。Fernet令牌不需要逐条持久化到数据库，但仍要正确理解缓存与令牌密钥仓是不同机制。 | 不说Memcached是Keystone数据库，也不说令牌永久保存在Memcached。 |
| OpenStackClient | 通过统一的`openstack`命令访问多个OpenStack服务API，替代大量旧的项目专用客户端。 | 不说客户端是OpenStack服务端组件，也不把安装客户端写成API验证。 |

### 4.2 最小手工安装

在controller执行。教学环境只使用已经准备好的`openstack-local`本地源：

```bash
dnf -y --disablerepo='*' --enablerepo='openstack-local' install \
  mariadb-config mariadb mariadb-server python3-PyMySQL \
  rabbitmq-server memcached python3-memcached python3-openstackclient
```

本地实测代表版本为MariaDB 10.5.29、RabbitMQ 3.9.23、Memcached 1.6.22和OpenStackClient 6.2.0。教材可在环境说明表中列出这些实测版本，但不应将RPM小版本写成OpenStack上游统一版本。

### 4.3 MariaDB最小配置

使用`vi`创建配置文件：

```bash
vi /etc/my.cnf.d/openstack.cnf
```

输入：

```ini
[mysqld]
bind-address = 0.0.0.0
default-storage-engine = innodb
innodb_file_per_table = on
max_connections = 4096
collation-server = utf8_general_ci
character-set-server = utf8
```

参数教学口径：

- `bind-address`决定MariaDB监听地址。本地实测配置为`0.0.0.0`，方便后续双节点组件访问；这只适用于与外部网络隔离的教学环境。OpenStack官方示例更强调绑定controller管理地址，生产环境应绑定`192.168.234.151`或其他受控管理地址，并配合防火墙和访问控制。
- `innodb`作为默认存储引擎，适合OpenStack服务需要的事务处理。
- `innodb_file_per_table`使InnoDB表使用独立表空间。
- `max_connections`提高控制面多服务并发连接上限。
- 字符集与排序规则保持教材实验环境的一致性。

分开执行启用和启动命令，符合第二版逐步操作风格：

```bash
systemctl enable mariadb.service
systemctl start mariadb.service
mysql_secure_installation
```

在`mysql_secure_installation`交互过程中，将MariaDB root密码设为`qwer1234`，删除匿名用户，禁止root远程登录，删除test数据库并重新载入权限表。本密码规则只用于断网、隔离、可随时重置的课堂实验。

### 4.4 RabbitMQ最小配置

```bash
systemctl enable rabbitmq-server.service
systemctl start rabbitmq-server.service
rabbitmqctl add_user openstack qwer1234
rabbitmqctl set_permissions -p / openstack ".*" ".*" ".*"
```

教学解释：`openstack`是消息队列账户，不是Linux用户，也不是Keystone用户；三个正则表达式依次授予默认虚拟主机`/`上的配置、写入和读取权限。后续服务配置中的`transport_url`使用该账户连接RabbitMQ。

### 4.5 Memcached最小配置

```bash
vi /etc/sysconfig/memcached
```

保留文件原有变量并将内容整理为：

```ini
PORT="11211"
USER="memcached"
MAXCONN="1024"
CACHESIZE="64"
OPTIONS="-l 127.0.0.1,::1,192.168.234.151"
```

然后执行：

```bash
systemctl enable memcached.service
systemctl start memcached.service
```

官方安装指南使用`controller`主机名，本地实测采用其管理地址`192.168.234.151`。两种写法的目的相同：使控制节点本地进程和通过管理网络访问的OpenStack服务可以连接Memcached。教材采用实测IP写法，避免主机名解析变化造成歧义。

### 4.6 OpenStack统一客户端

`python3-openstackclient`已在4.2的软件包命令中安装。本节只说明`openstack`是统一命令入口，不执行`openstack --version`、Token申请或任何服务查询。后续创建Keystone服务对象以及各组件的用户、服务和端点均使用该命令。

### 4.7 第5章停止边界

Memcached启动并完成OpenStackClient安装后，第5章部署结束。正文不应加入：

- `systemctl status`或`systemctl is-active`；
- `ss`端口检查；
- `mysql SELECT 1`或服务器变量查询；
- `rabbitmqctl authenticate_user`、用户列表和权限列表；
- Memcached写入/读取测试；
- `openstack --version`；
- RPM、DNF事务、日志、回滚和审计记录。

## 5. Keystone理论教学口径

### 5.1 Keystone的定位

Keystone是OpenStack的Identity服务。它承担身份认证、授权所需身份对象管理、Token签发以及服务目录管理。可沿用第二版“云平台大门与钥匙”的比喻，但应补充：Keystone负责确认身份并把作用域、角色和服务目录写入认证结果；各业务服务仍依据自己的策略规则决定某项操作是否允许。

### 5.2 核心对象

| 对象 | 教材定义 | 关键关系 |
|---|---|---|
| Domain（域） | Identity API v3中的管理边界和命名空间，容纳项目、用户和组，可用于委派域级管理。 | 用户、组、项目都归属于某个域；本书使用`Default`域。 |
| Project（项目） | 云资源所有权、隔离和配额的主要边界，可对应客户、组织、账户或教学小组。 | 用户并非“天然属于一个项目”，要通过角色授权获得项目中的权限；旧资料中的tenant应更新为project。 |
| User（用户） | 代表人员、系统或服务的数字身份，可使用凭据向Keystone认证。 | OpenStack各组件通常各有一个服务用户，并加入`service`项目。 |
| Group（组） | 同一域中的用户集合。 | 把角色授予组后，该组成员继承相应域或项目作用域中的授权；组不是项目。 |
| Role（角色） | 权限名称或授权标签，随Token传递。 | “用户或组 + 作用域 + 角色”共同形成角色授权；角色的实际权限由目标服务策略解释。 |
| Token（令牌） | Keystone验证凭据后签发的、有有效期的承载式访问凭据。 | Token可包含用户、项目/域/系统作用域、角色和服务目录；客户端随后携带Token访问其他服务。 |
| Service（服务） | 注册在Keystone中的逻辑API服务条目，如`identity`、`image`、`compute`。 | 一个Service可以关联多个Endpoint。 |
| Endpoint（端点） | 访问服务API的网络地址，通常为URL。 | 端点包含Region、接口类型和URL；本实验为`public`、`internal`、`admin`三类接口。 |
| Catalog（服务目录） | 已注册Service和Endpoint的集合，供客户端发现云平台API地址。 | 目录可随认证结果返回；服务无端点时，客户端无法正常发现访问地址。 |
| Policy（策略） | 把角色、作用域和请求属性映射到具体API操作的规则。 | Antelope各服务通常使用`policy.yaml`及代码内默认策略；Keystone授予角色，具体服务执行策略。 |

### 5.3 三类端点的准确解释

- `public`：面向最终用户或外部客户端的服务入口。
- `internal`：面向内部服务或管理网络访问的入口。
- `admin`：用于管理访问语义的接口标识，但不应把它理解为自动绕过认证或策略的“超级端口”。
- 双节点教学环境为简化网络，将三类端点都指向`http://controller:5000/v3/`。这是教学拓扑的简化，不表示三类端点在生产环境必然使用同一网络。
- Keystone Identity v2 API已经移除，Antelope不再使用旧的35357管理员端口。三类v3端点都使用5000端口。

### 5.4 Fernet、Credential与Memcached的区别

- `[token] provider = fernet`选择Fernet令牌提供者。Fernet令牌不需要逐条保存到数据库，但需要Keystone拥有用于加密和解密令牌的Fernet密钥。
- `keystone-manage fernet_setup`建立Fernet密钥仓。
- `keystone-manage credential_setup`建立保护Keystone Credential数据的密钥仓；它不是重复创建Token密钥。
- Memcached是运行时缓存，不能替代Fernet或Credential密钥仓，也不是数据库备份。

## 6. 第6章 Keystone最小手工部署步骤

以下步骤采用本地已实测的openEuler包名和文件路径，只保留安装所必需的命令与配置。

### 步骤一：安装Keystone和Apache组件

```bash
dnf -y --disablerepo='*' --enablerepo='openstack-local' install \
  openstack-keystone httpd python3-mod_wsgi
```

openEuler本地仓中，旧教程写的`mod_wsgi`能力由`python3-mod_wsgi`实际RPM提供。教材应直接写实际包名。

### 步骤二：创建Keystone数据库及用户授权

```bash
mysql -uroot -pqwer1234
```

在MariaDB提示符下逐条输入：

```sql
CREATE DATABASE keystone;
CREATE USER 'keystone'@'localhost' IDENTIFIED BY 'qwer1234';
CREATE USER 'keystone'@'127.0.0.1' IDENTIFIED BY 'qwer1234';
CREATE USER 'keystone'@'%' IDENTIFIED BY 'qwer1234';
GRANT ALL PRIVILEGES ON keystone.* TO 'keystone'@'localhost';
GRANT ALL PRIVILEGES ON keystone.* TO 'keystone'@'127.0.0.1';
GRANT ALL PRIVILEGES ON keystone.* TO 'keystone'@'%';
FLUSH PRIVILEGES;
EXIT;
```

官方教程创建`localhost`和`%`两条授权。本地实测配置用`127.0.0.1`连接数据库，因此增加`keystone@127.0.0.1`，并为三条账户设置相同的隔离教学密码。

### 步骤三：编辑Keystone主配置文件

```bash
vi /etc/keystone/keystone.conf
```

在`[database]`段设置：

```ini
[database]
connection = mysql+pymysql://keystone:qwer1234@127.0.0.1/keystone
```

在`[token]`段设置：

```ini
[token]
provider = fernet
```

同一配置段中如果存在其他生效的`connection`或`provider`项，应删除或注释，避免重复参数。`qwer1234`不含URL保留字符，可直接用于本教学连接串；生产口令若包含`@`、`:`、`/`、`%`等字符，必须进行URL编码或使用专门的凭据管理方案。

### 步骤四：同步Keystone数据库

```bash
su -s /bin/sh -c "keystone-manage db_sync" keystone
```

该命令必须以`keystone`系统用户执行。数据库同步属于部署动作，应保留；同步后的表数量、`alembic_version`或SQL查询属于验证，应从教材部署步骤删除。

### 步骤五：初始化两类密钥仓

```bash
keystone-manage fernet_setup --keystone-user keystone --keystone-group keystone
keystone-manage credential_setup --keystone-user keystone --keystone-group keystone
```

上述命令只在首次部署执行。教材不显示、复制或截图密钥内容。

### 步骤六：初始化Keystone身份服务

```bash
keystone-manage bootstrap \
  --bootstrap-password qwer1234 \
  --bootstrap-username admin \
  --bootstrap-project-name admin \
  --bootstrap-role-name admin \
  --bootstrap-service-name keystone \
  --bootstrap-admin-url http://controller:5000/v3/ \
  --bootstrap-internal-url http://controller:5000/v3/ \
  --bootstrap-public-url http://controller:5000/v3/ \
  --bootstrap-region-id RegionOne
```

教学解释：该命令初始化Default域、admin用户、admin项目和初始角色授权，同时注册`keystone`身份服务、`RegionOne`及三类Identity v3端点。执行bootstrap以后，不要再手工重复创建identity服务和同名端点。

### 步骤七：配置Apache与Keystone WSGI

```bash
vi /etc/httpd/conf/httpd.conf
```

在配置文件中加入或修改：

```apache
ServerName controller
```

建立Keystone WSGI配置链接：

```bash
ln -s /usr/share/keystone/wsgi-keystone.conf /etc/httpd/conf.d/wsgi-keystone.conf
```

启用并启动Apache：

```bash
systemctl enable httpd.service
systemctl start httpd.service
```

本发行包使用Apache承载Keystone API，没有需要另行启动的`keystone.service`。不要照搬旧版35357端口或旧的Apache双端口配置。

### 步骤八：创建管理员环境变量文件

```bash
vi /root/admin-openrc
```

输入：

```bash
export OS_PROJECT_DOMAIN_NAME=Default
export OS_USER_DOMAIN_NAME=Default
export OS_PROJECT_NAME=admin
export OS_USERNAME=admin
export OS_PASSWORD=qwer1234
export OS_AUTH_URL=http://controller:5000/v3
export OS_IDENTITY_API_VERSION=3
export OS_IMAGE_API_VERSION=2
export OS_REGION_NAME=RegionOne
```

设置文件权限并加载：

```bash
chmod 600 /root/admin-openrc
. /root/admin-openrc
```

OpenRC文件是后续手工创建用户、服务和端点的操作环境。直接保存教学密码只限本书的隔离实验；生产环境不得复用统一密码，应使用安全的凭据存储、独立服务密码和最小权限。

### 步骤九：创建service项目

```bash
openstack project create --domain default \
  --description "Service Project" service
```

`service`项目用于容纳后续Glance、Placement、Nova、Neutron、Cinder等组件的服务用户。创建该项目属于平台初始化，不是验证操作。

### 6.1 第6章停止边界

完成`service`项目创建后即结束Keystone部署。本章正文不得继续加入：

- `openstack token issue`；
- `openstack user list`、`project list`、`service list`、`endpoint list`；
- `curl http://controller:5000/v3/`；
- 5000/35357端口检查；
- Apache、Keystone、MariaDB状态检查；
- Keystone数据表数量和迁移版本检查；
- Fernet/Credential文件数量、属主、权限或摘要检查；
- 重跑分类、marker、幂等性程序、审计、回滚和故障注入。

以上内容如果教师确需保留，只能进入教师参考资料或项目验收记录，不能进入学生版部署正文。

## 7. 第二版旧命令与第三版替换表

| 第二版常见写法 | 第三版应替换为 | 修改原因 |
|---|---|---|
| CentOS 7及旧OpenStack软件源 | openEuler 24.03 LTS SP3上的`openstack-local`离线源和Antelope包 | 实验操作系统、发行版和软件源已经更换。 |
| `yum -y install ...` | `dnf -y --disablerepo='*' --enablerepo='openstack-local' install ...` | openEuler 24.03使用DNF；明确只使用教学离线源。 |
| `python2-PyMySQL` | `python3-PyMySQL` | openEuler本地仓的数据库驱动RPM名称。教材不展开编程。 |
| `mod_wsgi` | `python3-mod_wsgi` | openEuler SP3仓中的实际RPM提供者。 |
| `crudini --set ...` | `vi /etc/keystone/keystone.conf`后手工填写配置段 | 用户要求部署章节全部手工编辑配置文件。 |
| `mysql -uroot -p000000` | `mysql -uroot -pqwer1234` | 按第三版隔离教学环境的统一密码约定更新。 |
| `GRANT ... IDENTIFIED BY ...`一条语句完成建用户和授权 | 先`CREATE USER ... IDENTIFIED BY ...`，再`GRANT ...` | 与当前MariaDB账户管理逻辑更清晰，也和本地实测步骤一致。 |
| Keystone v2、`admin_token`或35357管理员端口 | Identity API v3、`keystone-manage bootstrap`和5000端口 | v2 API及旧管理员端口已经淘汰；Antelope使用v3。 |
| 手工再次创建`keystone`服务和Identity端点 | 由`keystone-manage bootstrap`一次创建 | 避免重复服务和重复端点。 |
| `admin-openrc.sh`中旧tenant变量 | `/root/admin-openrc`中的`OS_PROJECT_*`与Identity v3变量 | OpenStackClient统一使用project术语。 |
| 各项目旧客户端，如`keystone`命令 | 统一使用`openstack`命令 | OpenStackClient提供统一命令结构。 |
| 安装脚本及脚本解读 | 删除 | 第5、6章只保留逐条Linux命令和手工配置。 |
| 安装完成后的表查询、Token、端口、API和状态验证 | 删除 | 本轮教材要求“只部署不验证”。 |

## 8. 密码与安全说明

本书统一使用`qwer1234`仅有一个目的：降低隔离课堂环境中频繁输入不同密码造成的学习干扰。正文首次出现该密码时应以醒目提示说明：

> `qwer1234`只用于无公网入口、无生产数据、可随时重置的教学实验。生产环境必须为数据库root、各服务数据库用户、RabbitMQ用户、Keystone管理员和各服务用户设置彼此独立的高强度密码，并启用TLS、最小网络开放、秘密管理和定期轮换。

不能将该统一密码描述为最佳实践，也不能把本教材的SELinux/防火墙简化设置推广到生产部署。

## 9. 官方来源审计表

| 编号 | 官方来源 | 所属机构/项目 | 本底稿采用的事实 | 版本与适用范围 |
|---|---|---|---|---|
| S1 | [OpenStack 2023.1 Antelope release](https://releases.openstack.org/antelope/index.html) | OpenStack Releases | Antelope发布日期、交付物和维护状态 | 2023.1；冻结日口径 |
| S2 | [OpenStack 2023.1 Installation Guides](https://docs.openstack.org/2023.1/install/) | OpenStack Documentation | 2023.1服务安装文档入口及旧版本标识 | 2023.1 |
| S3 | [SQL database for RHEL and CentOS](https://docs.openstack.org/install-guide/environment-sql-database-rdo.html) | OpenStack Installation Guide | MariaDB作用、软件包、`openstack.cnf`参数及服务启动方式 | 通用RHEL系指南；参数用本地实测校准 |
| S4 | [Message queue for RHEL and CentOS](https://docs.openstack.org/install-guide/environment-messaging-rdo.html) | OpenStack Installation Guide | RabbitMQ作用、`openstack`用户和三项权限 | 通用RHEL系指南 |
| S5 | [Memcached for RHEL and CentOS](https://docs.openstack.org/install-guide/environment-memcached-rdo.html) | OpenStack Installation Guide | Memcached作用、包名、监听controller管理网络及启动方式 | 通用RHEL系指南 |
| S6 | [OpenStack packages for RHEL and CentOS](https://docs.openstack.org/install-guide/environment-packages-rdo.html) | OpenStack Installation Guide | `python3-openstackclient`是统一客户端RPM；发行版负责软件包 | 通用RHEL系指南，不用于声称openEuler=RHEL |
| S7 | [Keystone 2023.1 install and configure](https://docs.openstack.org/keystone/2023.1/install/keystone-install-rdo.html) | Keystone | 建库、`keystone.conf`、`db_sync`、Fernet/Credential、bootstrap、Apache和OpenRC变量 | Keystone 23 / OpenStack 2023.1 |
| S8 | [Keystone 2023.1 identity concepts](https://docs.openstack.org/keystone/2023.1/admin/identity-concepts.html) | Keystone | Domain、Project、User、Group、Role、Token、Service、Endpoint和policy教学定义 | Keystone 23 / Identity v3 |
| S9 | [Keystone 2023.1 bootstrapping](https://docs.openstack.org/keystone/2023.1/admin/bootstrap.html) | Keystone | bootstrap创建初始用户、项目、角色、服务和端点；不使用`ADMIN_TOKEN` | Keystone 23 |
| S10 | [Identity API v3](https://docs.openstack.org/api-ref/identity/v3/) | OpenStack API Reference | Token、作用域、服务目录、三类endpoint interface及RBAC | Identity API v3 |
| S11 | [Create and manage services and service users](https://docs.openstack.org/keystone/2023.1/admin/manage-services.html) | Keystone | Service Catalog用于服务发现；Service与Endpoint关系 | Keystone 23 |
| S12 | [Create domain, projects, users, and roles](https://docs.openstack.org/keystone/2023.1/install/keystone-users-rdo.html) | Keystone | `service`项目的用途和创建命令 | Keystone 23 / OpenStack 2023.1 |
| S13 | [Create OpenStack client environment scripts](https://docs.openstack.org/keystone/2023.1/install/keystone-openrc-rdo.html) | Keystone | `admin-openrc`变量、敏感凭据保护和加载方法 | Keystone 23 / OpenStack 2023.1 |
| S14 | [openEuler 24.03 LTS SP3下载页](https://www.openeuler.org/en/download/) | openEuler社区 | SP3版本、Linux 6.6及云计算适用场景 | openEuler 24.03 LTS SP3 |
| S15 | [openEuler 24.03 LTS SP3快速入门](https://docs.openeuler.org/zh/docs/24.03_LTS_SP3/server/quickstart/quickstart/quick_start_new.html) | openEuler社区 | DNF、本地repo、chronyd及系统安装基本口径 | openEuler 24.03 LTS SP3 |
| S16 | [openEuler SP3 Apache服务器配置](https://docs.openeuler.org/en/docs/24.03_LTS_SP3/server/administration/administrator/configuring_the_web_server.html) | openEuler社区 | `httpd`软件包及`systemctl enable/start`方式 | openEuler 24.03 LTS SP3 |

## 10. 本地实测记录核对表

| 本地记录 | 只采用的内容 | 明确不迁入教材的内容 |
|---|---|---|
| `validation/manual-install/01-base.md` | 节点地址、`openstack-local`源、openEuler SP3、Antelope release包及基础依赖顺序 | Python修改文件程序、断言、磁盘门禁、RPM审计、回滚记录 |
| `validation/manual-install/02-infrastructure.md` | openEuler包名、MariaDB参数、RabbitMQ用户与权限、Memcached监听地址、OpenStackClient版本事实 | 预检函数、状态/API/端口验证、Python缓存测试、事务审计 |
| `validation/manual-install/03-keystone.md` | Keystone包名和版本、数据库三主机账户、`keystone.conf`连接参数、Fernet/Credential、bootstrap、Apache/WSGI、OpenRC和`service`项目 | 远程程序、Python SQL/配置程序、marker、证据分类、幂等驱动器、Token/API/端口验证和回滚说明 |

## 11. Concerns与编写决策

1. **Antelope已经未维护。** 教材必须区分“产业和社区最新介绍”与“实验版本”，并说明采用Antelope是因为本地离线源、教学稳定性和已完成实训适配，而非因为它仍是最新版本。
2. **SP2构建包运行在SP3属于本书实测组合。** 上游官方资料不能为该组合提供兼容性背书，书稿不能写成普遍保证。
3. **统一密码`qwer1234`安全性低。** 只能用于隔离教学；正式版必须出现明显安全提示。
4. **MariaDB监听`0.0.0.0`是本地实测值，但暴露范围大。** 为保持脚本和手工教材一致，本章可保留该值，同时明确生产环境绑定管理地址；若编委决定改为`192.168.234.151`，应在实验机上重新做一次部署确认后再定稿。
5. **`mysql_secure_installation`会改变MariaDB root认证状态。** 本地实测记录使用了本地root免密套接字方式，而本书现在要求统一`qwer1234`。采用密码登录的教材路径应作为正式实验环境重新走一遍后再截图；在此之前不能声称该交互结果已经由现有记录验证。
6. **包名带`python3-`不等于教材编程。** 这些RPM是OpenStack运行时和统一客户端依赖，可以出现在DNF命令中；正文不得出现Python脚本、解释器命令或代码讲解。
7. **只部署不验证。** OpenStack官方安装教程通常包含“verify operation”，本书此次明确不采用该部分。所有验证脚本、状态查询和测试资源都留在教师验收资料，不进入第5、6章学生正文。
8. **服务与端点不能重复创建。** `keystone-manage bootstrap`已经创建identity服务和三类端点，后文不得再照搬旧版手工注册Keystone服务的命令。
9. **策略不是角色本身。** 书稿应避免把“admin角色”等同于某组固定API权限；角色只是授权标签，最终权限取决于各服务策略及作用域。
10. **截图内容。** 第5、6章截图应呈现学生刚执行的Linux命令、`vi`配置片段和创建反馈，不出现验证结果、Token值、密码明文回显、密钥内容、审计目录或开发工具界面。
