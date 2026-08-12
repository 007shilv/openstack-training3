# 14 Horizon 控制节点手工部署与轻量验收

`17-controller-horizon.sh` 只可作为参数和顺序参考，**严禁执行**。本节仅在 controller `192.168.234.151` 上操作；不重配任何既有 OpenStack 服务，不创建卷、对象、网络、快照或磁盘写入。所有口令只在交互提示或运行时环境中使用，绝不写入教材、快照、浏览器导出或版本库。

## 前置只读门

在 controller 与 compute 上先确认原有服务健康，且 Horizon 不存在。Keystone、Glance、Placement 在本环境可能由 Apache WSGI 承载，因而以相应 API 探测作为服务可用性证据。

```bash
# controller
set -Eeuo pipefail
[[ $(hostnamectl --static) == controller ]]
ip -4 -o addr show ens33 | grep -Fq '192.168.234.151/24'
for service in mariadb rabbitmq-server memcached httpd \
  openstack-nova-api openstack-nova-scheduler openstack-nova-conductor \
  openstack-nova-novncproxy neutron-server openstack-cinder-api \
  openstack-cinder-scheduler openstack-swift-proxy; do
  systemctl is-active --quiet "$service"
  systemctl is-enabled --quiet "$service"
done
source /root/admin-openrc
openstack service list
openstack endpoint list --region RegionOne --long
for url in http://controller:5000/v3/ http://controller:9292/ \
  http://controller:8778/ http://controller:9696/ http://controller:8776/v3/ \
  http://controller:8080/healthcheck; do
  code=$(curl --noproxy '*' -sS -o /dev/null -w '%{http_code}' "$url")
  [[ $code =~ ^(200|300|401|403)$ ]]
done
rpm -q openstack-dashboard python3-horizon && exit 1 || true
[[ ! -e /etc/openstack-dashboard/local_settings ]]

# compute（只读；本节不得修改 compute）
[[ $(hostnamectl --static) == compute ]]
ip -4 -o addr show ens33 | grep -Fq '192.168.234.150/24'
for service in targetclid openstack-cinder-volume rsyncd \
  openstack-swift-account openstack-swift-container openstack-swift-object; do
  systemctl is-active --quiet "$service"
  systemctl is-enabled --quiet "$service"
done
pvs --noheadings --readonly -o pv_name,vg_name | grep -Eq '/dev/sdb[[:space:]]+cinder-volumes'
[[ $(blkid -o value -s TYPE /dev/sdc) == xfs ]]
[[ $(blkid -o value -s LABEL /dev/sdc) == swift-data ]]
[[ $(findmnt -nro TARGET --target /srv/node/sdc) == /srv/node/sdc ]]
```

## 仅使用本地软件源安装并备份默认配置

```bash
set -Eeuo pipefail
dnf repoquery --available --disablerepo='*' --enablerepo=openstack-local \
  openstack-dashboard python3-horizon >/dev/null
dnf -y --disablerepo='*' --enablerepo=openstack-local \
  --setopt=install_weak_deps=False install openstack-dashboard
rpm -q openstack-dashboard python3-horizon

umask 077
stamp=$(date -u +%Y%m%dT%H%M%SZ)
backup=/root/openstack-lab-backups/task-5i-controller-$stamp
install -d -m 700 "$backup"
for file in /etc/openstack-dashboard/local_settings \
  /etc/httpd/conf.d/openstack-dashboard.conf; do
  cp -a "$file" "$backup"/
done
```

不得使用外部软件源、`--allowerasing`、`--skip-broken`、降级或软件包移除。

## 用 vi 完整设置 Horizon

运行 `vi /etc/openstack-dashboard/local_settings`，在文件末尾添加以下有效设置。包生成的 `SECRET_KEY` 保持原值，严禁复制、显示、哈希或记录。`ALLOWED_HOSTS` 仅为本实验的显式主机/IP；生产环境应改成经过审核的 DNS 名称，绝不能使用通配符。

```python
# BEGIN OPENSTACK-TS HORIZON MANUAL SETTINGS
ALLOWED_HOSTS = ['controller', '192.168.234.151', 'localhost', '127.0.0.1']
OPENSTACK_HOST = 'controller'
OPENSTACK_KEYSTONE_URL = 'http://%s:5000/v3' % OPENSTACK_HOST
OPENSTACK_KEYSTONE_MULTIDOMAIN_SUPPORT = True
OPENSTACK_KEYSTONE_DEFAULT_DOMAIN = 'Default'
# 先用 source /root/admin-openrc; openstack role list 核实本环境现有普通角色。
OPENSTACK_KEYSTONE_DEFAULT_ROLE = 'member'
OPENSTACK_API_VERSIONS = {
    'identity': 3,
    'image': 2,
    'volume': 3,
}
WEBROOT = '/dashboard/'
LOGIN_URL = '/dashboard/auth/login/'
LOGOUT_URL = '/dashboard/auth/logout/'
LOGIN_REDIRECT_URL = '/dashboard/'
TIME_ZONE = 'Asia/Shanghai'
SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.memcached.PyMemcacheCache',
        'LOCATION': 'controller:11211',
    },
}
# END OPENSTACK-TS HORIZON MANUAL SETTINGS
```

本发行版的软件包 Apache 文件 `/etc/httpd/conf.d/openstack-dashboard.conf` 已提供 `WSGIScriptAlias /dashboard`、`/dashboard/static` 和 `/dashboard/media`。运行 `vi /etc/httpd/conf.d/openstack-dashboard.conf`，逐项核对这些路径；无需改写正确的包提供映射。

```bash
chown root:apache /etc/openstack-dashboard/local_settings
chmod 0640 /etc/openstack-dashboard/local_settings
source /root/admin-openrc
openstack role list
httpd -t
python3 /usr/share/openstack-dashboard/manage.py check
systemctl enable httpd
systemctl restart httpd
systemctl is-active --quiet httpd
systemctl is-enabled --quiet httpd
```

## 无状态 HTTP 验收与手工浏览器验收

```bash
set -Eeuo pipefail
httpd -t
systemctl is-active --quiet httpd
systemctl is-enabled --quiet httpd
headers=$(mktemp /tmp/task5i-dashboard-headers.XXXXXX)
login_page=$(mktemp /tmp/task5i-dashboard-login.XXXXXX)
trap 'rm -f "$headers" "$login_page"' EXIT

# 先严格验证根路径：不接受 301 或其他状态；Location 可为绝对或相对 URL，
# 但解析后的 path 和 query 必须精确匹配。
root_status=$(curl --noproxy '*' -sS -D "$headers" -o /dev/null \
  -w '%{http_code}' http://127.0.0.1/dashboard/)
[[ $root_status == 302 ]]
root_location=$(awk 'BEGIN{IGNORECASE=1} /^Location:/{sub(/^[^:]*:[[:space:]]*/, ""); sub(/\\r$/, ""); print; exit}' "$headers")
[[ -n $root_location ]]
python3 - "$root_location" <<'PY'
import sys
from urllib.parse import urlsplit

location = urlsplit(sys.argv[1])
if (location.path, location.query, location.fragment) != (
    '/dashboard/auth/login/', 'next=/dashboard/', ''
):
    raise SystemExit('dashboard redirect path/query is not exact')
PY

# 仅在登录 URL 已严格返回 200 后，才检查登录表单标记。
login_status=$(curl --noproxy '*' -sS -o "$login_page" -w '%{http_code}' \
  http://127.0.0.1/dashboard/auth/login/)
[[ $login_status == 200 ]]
page=$(<"$login_page")
grep -qi '<form' <<< "$page"
grep -qi 'username' <<< "$page"
grep -qi 'password' <<< "$page"
grep -qi 'csrfmiddlewaretoken' <<< "$page"
unset page
rm -f "$headers" "$login_page"
trap - EXIT
```

### 手工浏览器验收

浏览器可用时，手动访问 `http://controller/dashboard/`，使用既有 administrator 账户登录，确认 Overview 页面加载，然后使用界面注销。不要导出 Cookie、密码、令牌或截图；关闭标签页即可。不具备浏览器自动化条件时，以上 HTTP 表单就绪检查是本节的自动化证据，教师应在可用浏览器中按上述三步补做一次可视确认。

## 最终只读边界门

```bash
set -Eeuo pipefail
# controller：既有 API 与 Horizon 都可用。
for url in http://controller:5000/v3/ http://controller:9292/ \
  http://controller:8778/ http://controller:9696/ http://controller:8776/v3/ \
  http://controller:8080/healthcheck http://controller/dashboard/auth/login/; do
  code=$(curl --noproxy '*' -sS -o /dev/null -w '%{http_code}' "$url")
  [[ $code =~ ^(200|300|401|403)$ ]]
done
systemctl is-active --quiet httpd
systemctl is-enabled --quiet httpd

# compute：只读确认两块既有教学盘未变化。
pvs --noheadings --readonly -o pv_name,vg_name | grep -Eq '/dev/sdb[[:space:]]+cinder-volumes'
[[ $(blkid -o value -s TYPE /dev/sdc) == xfs ]]
[[ $(blkid -o value -s LABEL /dev/sdc) == swift-data ]]
[[ $(findmnt -nro TARGET --target /srv/node/sdc) == /srv/node/sdc ]]
```

## Focused Horizon contract（仅验收，不是安装入口）

```python
def validate_horizon_lightweight_evidence(evidence: dict[str, object]) -> None:
    expected = {
        'httpd': {'active': True, 'enabled': True, 'configtest': True},
        'dashboard': {'root_status': 302,
                      'login_location_path_query': '/dashboard/auth/login/?next=/dashboard/',
                      'login_status': 200, 'login_form': True},
        'settings': {'webroot': '/dashboard/', 'keystone_v3': True, 'multidomain': True,
                     'timezone': 'Asia/Shanghai', 'cache': 'controller:11211'},
        'boundaries': {'cinder_sdb_unchanged': True, 'swift_sdc_unchanged': True,
                       'snapshots_created': False, 'cookies_saved': False},
    }
    if evidence != expected:
        raise ValueError('Horizon lightweight evidence mismatch')
```
