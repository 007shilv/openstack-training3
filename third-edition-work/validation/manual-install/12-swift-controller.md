# 12 Swift 控制节点手工部署

`15-controller-swift.sh` 仅用于核对参数和顺序，严禁执行。所有密码、令牌及 Swift hash prefix/suffix 只在运行时输入，绝不写入教材或快照。

先仅用本地源预检并安装：

```bash
dnf repoquery --available --disablerepo='*' --enablerepo=openstack-local openstack-swift openstack-swift-common openstack-swift-proxy
dnf -y --disablerepo='*' --enablerepo=openstack-local --setopt=install_weak_deps=False install openstack-swift openstack-swift-common openstack-swift-proxy
```

以管理员凭据逐项创建或核验 Default 域的 `swift` 用户、service 项目 global `admin` 角色、启用的 `swift` / `object-store` 服务，以及三个 RegionOne 端点：

```bash
source /root/admin-openrc
openstack user create --domain Default --password-prompt swift
openstack role add --project service --user swift admin
openstack service create --name swift --description 'OpenStack Object Storage' object-store
openstack endpoint create --region RegionOne object-store public 'http://controller:8080/v1/AUTH_%(project_id)s'
openstack endpoint create --region RegionOne object-store internal 'http://controller:8080/v1/AUTH_%(project_id)s'
openstack endpoint create --region RegionOne object-store admin 'http://controller:8080/v1/AUTH_%(project_id)s'
```

使用 `vi /etc/swift/swift.conf`，在 `[swift-hash]` 中仅输入运行时随机 prefix/suffix；并写入默认 Policy-0。使用 `vi /etc/swift/proxy-server.conf`，配置 8080、`controller:11211`、`authtoken keystoneauth` 管道和服务项目的 Swift 凭据。

在 `/etc/swift` 手工建立单副本教学 rings（生产环境必须多副本、多故障域）：

```bash
swift-ring-builder account.builder create 10 1 1
swift-ring-builder container.builder create 10 1 1
swift-ring-builder object.builder create 10 1 1
swift-ring-builder account.builder add --region 1 --zone 1 --ip 192.168.234.150 --port 6202 --device sdc --weight 100
swift-ring-builder container.builder add --region 1 --zone 1 --ip 192.168.234.150 --port 6201 --device sdc --weight 100
swift-ring-builder object.builder add --region 1 --zone 1 --ip 192.168.234.150 --port 6200 --device sdc --weight 100
swift-ring-builder account.builder rebalance
swift-ring-builder container.builder rebalance
swift-ring-builder object.builder rebalance
systemctl enable --now openstack-swift-proxy
```

将三个 `.ring.gz` 和相同的 `swift.conf` 通过已审核 known_hosts 的 SSH 安全复制至 compute；逐字节核对后才启动存储服务。不得跟踪 ring 二进制文件。
