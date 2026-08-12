# 12 Swift 控制节点手工部署与轻量验收

本节在 Cinder 已通过验收后执行。`15-controller-swift.sh` 只用于核对参数和顺序，**严禁执行**。学生必须逐条输入命令、使用 `vi` 编辑配置、手工创建身份对象和 ring。真实服务密码、令牌及 Swift hash prefix/suffix 只在运行时输入，不得写入教材、命令历史或仓库。

本实验只有一个存储设备，ring 的副本数为 1；它没有冗余和故障容忍能力，只适合教学环境。

## 两节点只读门

先在 controller 执行；任何命令失败都停止：

```bash
set -Eeuo pipefail
[[ $(hostnamectl --static) == controller ]]
ip -4 -o addr show ens33 | grep -Fq '192.168.234.151/24'
for service in openstack-cinder-api openstack-cinder-scheduler; do
  systemctl is-active --quiet "$service"
  systemctl is-enabled --quiet "$service"
done
source /root/admin-openrc
openstack token issue -f value -c id >/dev/null
openstack volume service list -f value >/dev/null
! rpm -q openstack-dashboard >/dev/null 2>&1
```

再登录 compute 执行以下只读检查，确认 Cinder 的 `/dev/sdb` 保持不变、Swift 目标只能是 50 GiB 的 `/dev/sdc`：

```bash
set -Eeuo pipefail
[[ $(hostnamectl --static) == compute ]]
ip -4 -o addr show ens33 | grep -Fq '192.168.234.150/24'
for service in targetclid openstack-cinder-volume; do
  systemctl is-active --quiet "$service"
  systemctl is-enabled --quiet "$service"
done
[[ -b /dev/sdb && -b /dev/sdc ]]
[[ $(lsblk -dnro TYPE /dev/sdc) == disk ]]
[[ $(blockdev --getsize64 /dev/sdc) == 53687091200 ]]
pvs --noheadings --readonly --separator '|' -o pv_name,vg_name
```

只读输出必须显示 `/dev/sdb` 恰属于 `cinder-volumes`，且不得把 `/dev/sdc` 识别为 PV。第 13 节会在格式化前再次执行更严格的失效即停分类门。

## 本地源安装与备份

只允许 `openstack-local`，不得使用外部源、`--allowerasing` 或 `--skip-broken`：

```bash
set -Eeuo pipefail
dnf repoquery --available --disablerepo='*' --enablerepo=openstack-local \
  openstack-swift openstack-swift-common openstack-swift-proxy >/dev/null
dnf -y --disablerepo='*' --enablerepo=openstack-local \
  --setopt=install_weak_deps=False install \
  openstack-swift openstack-swift-common openstack-swift-proxy
rpm -V openstack-swift openstack-swift-common openstack-swift-proxy
umask 077
stamp=$(date -u +%Y%m%dT%H%M%SZ)
backup=/root/openstack-lab-backups/task-5h-controller-$stamp
install -d -m 700 "$backup"
for file in /etc/swift/swift.conf /etc/swift/proxy-server.conf; do
  [[ ! -e $file ]] || cp -a "$file" "$backup"/
done
```

## 身份、服务与三个端点

先用 `show/list` 判断对象是否存在；不存在才创建，存在则逐字段核对，不能盲目重复创建：

```bash
source /root/admin-openrc
openstack user show swift || openstack user create --domain Default --password-prompt swift
openstack user show swift -f yaml
openstack role add --project service --user swift admin
openstack role assignment list --project service --user swift --role admin --names
openstack service show swift || \
  openstack service create --name swift --description 'OpenStack Object Storage' object-store
openstack service show swift -f yaml
openstack endpoint create --region RegionOne object-store public \
  'http://controller:8080/v1/AUTH_%(project_id)s'
openstack endpoint create --region RegionOne object-store internal \
  'http://controller:8080/v1/AUTH_%(project_id)s'
openstack endpoint create --region RegionOne object-store admin \
  'http://controller:8080/v1/AUTH_%(project_id)s'
openstack endpoint list --service swift --region RegionOne --long
```

最终必须只有一个启用的 `swift`/`object-store` 服务；Default 域的启用 `swift` 用户在 `service` 项目拥有 global `admin`；public、internal、admin 三个启用端点的 URL 均精确为 `http://controller:8080/v1/AUTH_%(project_id)s`。如果端点已存在，先用 `openstack endpoint show <ID>` 核对，而不是再次创建。

## 手工编辑 Swift 与代理配置

运行时生成两段不同的随机值，仅复制到 `vi` 中，不输出、不做摘要、不写入仓库：

```bash
vi /etc/swift/swift.conf
```

```ini
[swift-hash]
swift_hash_path_prefix = <RUNTIME_RANDOM_PREFIX>
swift_hash_path_suffix = <RUNTIME_RANDOM_SUFFIX>

[storage-policy:0]
name = Policy-0
default = yes
```

再执行 `vi /etc/swift/proxy-server.conf`，把 `<SERVICE_PASSWORD>` 在运行时替换为 Swift 服务用户密码：

```ini
[DEFAULT]
bind_ip = 0.0.0.0
bind_port = 8080
user = swift
swift_dir = /etc/swift

[pipeline:main]
pipeline = catch_errors gatekeeper healthcheck proxy-logging cache authtoken keystoneauth proxy-logging proxy-server

[app:proxy-server]
use = egg:swift#proxy
account_autocreate = true
allow_account_management = true

[filter:catch_errors]
use = egg:swift#catch_errors

[filter:gatekeeper]
use = egg:swift#gatekeeper

[filter:healthcheck]
use = egg:swift#healthcheck

[filter:proxy-logging]
use = egg:swift#proxy_logging

[filter:cache]
use = egg:swift#memcache
memcache_servers = controller:11211

[filter:authtoken]
paste.filter_factory = keystonemiddleware.auth_token:filter_factory
www_authenticate_uri = http://controller:5000
auth_url = http://controller:5000
memcached_servers = controller:11211
auth_type = password
project_domain_name = Default
user_domain_name = Default
project_name = service
username = swift
password = <SERVICE_PASSWORD>
delay_auth_decision = true

[filter:keystoneauth]
use = egg:swift#keystoneauth
operator_roles = admin,user
reseller_prefix = AUTH
```

```bash
chown -R swift:swift /etc/swift /var/cache/swift
chmod 0640 /etc/swift/swift.conf /etc/swift/proxy-server.conf
```

## 手工创建、加入和核验 rings

只加入 compute `.150` 的设备 `sdc`，端口分别为 account 6202、container 6201、object 6200：

```bash
cd /etc/swift
swift-ring-builder account.builder create 10 1 1
swift-ring-builder container.builder create 10 1 1
swift-ring-builder object.builder create 10 1 1
swift-ring-builder account.builder add --region 1 --zone 1 --ip 192.168.234.150 --port 6202 --device sdc --weight 100
swift-ring-builder container.builder add --region 1 --zone 1 --ip 192.168.234.150 --port 6201 --device sdc --weight 100
swift-ring-builder object.builder add --region 1 --zone 1 --ip 192.168.234.150 --port 6200 --device sdc --weight 100
swift-ring-builder account.builder rebalance
swift-ring-builder container.builder rebalance
swift-ring-builder object.builder rebalance
swift-ring-builder account.builder search --region 1 --zone 1 --ip 192.168.234.150 --port 6202 --device sdc
swift-ring-builder container.builder search --region 1 --zone 1 --ip 192.168.234.150 --port 6201 --device sdc
swift-ring-builder object.builder search --region 1 --zone 1 --ip 192.168.234.150 --port 6200 --device sdc
swift-ring-builder account.builder
swift-ring-builder container.builder
swift-ring-builder object.builder
```

每份 builder 必须显示 `1.000000` replicas，且只有 region 1、zone 1、`192.168.234.150`、`sdc` 和对应端口这一条成员。

## 经核对指纹后安全复制并验证字节一致

先通过受信任渠道人工核对 compute SSH 指纹，把已审核公钥保存在 `/root/.ssh/known_hosts.swift-lab`；`ssh-keyscan` 本身不能证明身份。核对完毕后在 controller 执行：

```bash
ssh-keygen -lf /root/.ssh/known_hosts.swift-lab
cd /etc/swift
sha256sum account.ring.gz container.ring.gz object.ring.gz > /tmp/task5h-rings.sha256
scp -o StrictHostKeyChecking=yes \
  -o UserKnownHostsFile=/root/.ssh/known_hosts.swift-lab \
  swift.conf account.ring.gz container.ring.gz object.ring.gz \
  /tmp/task5h-rings.sha256 root@192.168.234.150:/tmp/
ssh -o StrictHostKeyChecking=yes \
  -o UserKnownHostsFile=/root/.ssh/known_hosts.swift-lab \
  root@192.168.234.150 \
  'install -d -m 0755 /etc/swift && install -m 0640 /tmp/swift.conf /tmp/*.ring.gz /etc/swift/ && cd /etc/swift && sha256sum -c /tmp/task5h-rings.sha256'
sha256sum account.ring.gz container.ring.gz object.ring.gz
ssh -o StrictHostKeyChecking=yes \
  -o UserKnownHostsFile=/root/.ssh/known_hosts.swift-lab \
  root@192.168.234.150 \
  'cd /etc/swift && sha256sum account.ring.gz container.ring.gz object.ring.gz'
scp -o StrictHostKeyChecking=yes \
  -o UserKnownHostsFile=/root/.ssh/known_hosts.swift-lab \
  root@192.168.234.150:/etc/swift/swift.conf /tmp/compute-swift.conf
cmp -s /etc/swift/swift.conf /tmp/compute-swift.conf
rm -f /tmp/compute-swift.conf
rm -f /tmp/task5h-rings.sha256
ssh -o StrictHostKeyChecking=yes \
  -o UserKnownHostsFile=/root/.ssh/known_hosts.swift-lab \
  root@192.168.234.150 'rm -f /tmp/task5h-rings.sha256 /tmp/swift.conf /tmp/*.ring.gz'
```

两端三份 ring 的摘要必须逐项相同；`swift.conf` 只用 `cmp` 做字节比较，禁止对包含真实 hash salt 的配置计算或记录摘要。摘要不进入仓库，ring 二进制文件也不得跟踪。

## 启动代理并验收服务

```bash
systemctl enable openstack-swift-proxy
systemctl start openstack-swift-proxy
systemctl is-active --quiet openstack-swift-proxy
systemctl is-enabled --quiet openstack-swift-proxy
ss -ltn | grep -Eq '(^|[[:space:]])[^[:space:]]*:8080[[:space:]]'
curl --noproxy '*' -fsS http://controller:8080/healthcheck
```

存储节点完成第 13 节后，再做认证 API/CLI 与唯一小对象生命周期：

```bash
set -Eeuo pipefail
source /root/admin-openrc
token=$(openstack token issue -f value -c id)
curl --noproxy '*' -fsS -H "X-Auth-Token: $token" http://controller:8080/info >/dev/null
unset token
container="task5h-container-$(date -u +%Y%m%d%H%M%S)"
object="task5h-object.txt"
source_file=$(mktemp /tmp/task5h-source.XXXXXX)
download_file=$(mktemp /tmp/task5h-download.XXXXXX)
printf 'Swift Task 5H lightweight object\n' > "$source_file"
openstack container create "$container" >/dev/null
openstack object create "$container" "$source_file" --name "$object" >/dev/null
openstack object show "$container" "$object" >/dev/null
openstack object save "$container" "$object" --file "$download_file" >/dev/null
[[ $(sha256sum "$source_file" | awk '{print $1}') == $(sha256sum "$download_file" | awk '{print $1}') ]]
openstack object delete "$container" "$object"
! openstack object show "$container" "$object" >/dev/null 2>&1
openstack container delete "$container"
! openstack container show "$container" >/dev/null 2>&1
[[ -z $(openstack container list -f value -c Name | grep -Fx "$container" || true) ]]
rm -f "$source_file" "$download_file"
```

只创建这一组任务对象；删除必须使用本次生成的精确容器名和对象名，不能模糊匹配。
