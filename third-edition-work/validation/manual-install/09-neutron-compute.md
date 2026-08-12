# 09 Neutron 计算节点手工部署与轻量验收

本节必须在控制节点第 08 节已经完成、`neutron-server` 已可用后执行。`12-compute-neutron.sh` 只能参考参数和顺序，**绝不能执行**。学生须手工安装、手工编辑所有参数、手工 enable/start 服务；本节最后的 Python 函数是对已收集结果的 focused contract，不参与安装。

## 再次只读门禁

在 compute 写入前再次确认主机、地址、本地源、Nova 和数据盘；同时从 controller 只读确认 Nova 仍健康且 Neutron 控制服务已启用。`ens34` 必须没有 IPv4 和全局 IPv6 地址，`/dev/sdb`、`/dev/sdc` 必须保持原来的空白 50 GiB disk 状态。

```bash
set -Eeuo pipefail
[[ $(hostnamectl --static) == compute ]]
ip -4 -o addr show ens33 | grep -Fq '192.168.234.150/24'
[[ -z $(ip -4 -o addr show ens34) && -z $(ip -6 -o addr show ens34 scope global) ]]
dnf -q repolist --disablerepo='*' --enablerepo='openstack-local' | grep -Fxq openstack-local
systemctl is-active --quiet openstack-nova-compute && systemctl is-enabled --quiet openstack-nova-compute
for d in /dev/sdb /dev/sdc; do [[ -b $d && $(blockdev --getsize64 "$d") == 53687091200 && $(lsblk -dnro TYPE "$d") == disk ]]; [[ $(lsblk -nrpo NAME "$d" | sed '/^$/d' | wc -l) -eq 1 ]]; [[ -z $(wipefs --no-act --noheadings --output TYPE "$d") ]]; blkid -p "$d" >/dev/null 2>&1 && exit 1 || [[ $? -eq 2 ]]; done
```

任何盘、`ens34`、宿主身份或源状态的偏差都停止。不要格式化、分区、初始化 LVM 或向数据盘写入；本切片同样不创建快照。

## 计算节点本地源软件包

仅从 `openstack-local` 手工预检和安装 Linux bridge agent 依赖。禁止外部源和不安全 DNF 标志；事务历史中不得有 Removing、Erasing、Obsoleting、Replacing 或 Downgrading。

```bash
set -Eeuo pipefail
dnf repoquery --available --disablerepo='*' --enablerepo='openstack-local' openstack-neutron-linuxbridge ebtables ipset >/dev/null
dnf -y --disablerepo='*' --enablerepo='openstack-local' --setopt=install_weak_deps=False install openstack-neutron-linuxbridge ebtables ipset
dnf history info "$(dnf history | awk 'NR==3 {print $1}')"
rpm -V openstack-neutron-linuxbridge
```

首次修改前，把 `/etc/neutron/neutron.conf`、`/etc/neutron/plugins/ml2/linuxbridge_agent.ini` 和 sysctl 默认文件（若存在）备份到 `/root/openstack-lab-backups/task-5f-<UTC>/`。备份只保留在远端受限目录，报告记录目录而非任何口令。

## 计算节点 sysctl 与配置

手工创建 bridge netfilter 文件并立即加载，然后使用 `vi` 手工编辑两个 Neutron 文件。`<URL_ENCODED_PASSWORD>` 是 URL 编码后的运行时口令；不得把真实口令写入快照、报告或命令历史。

```bash
cat >/etc/sysctl.d/99-openstack-neutron.conf <<'EOF'
net.bridge.bridge-nf-call-iptables = 1
net.bridge.bridge-nf-call-ip6tables = 1
EOF
modprobe br_netfilter
sysctl --system
vi /etc/neutron/neutron.conf
```

```ini
[DEFAULT]
transport_url = rabbit://openstack:<URL_ENCODED_PASSWORD>@controller
auth_strategy = keystone

[oslo_concurrency]
lock_path = /var/lib/neutron/tmp

[experimental]
linuxbridge = true
```

```bash
vi /etc/neutron/plugins/ml2/linuxbridge_agent.ini
```

```ini
[linux_bridge]
physical_interface_mappings = provider:ens34

[vxlan]
enable_vxlan = true
local_ip = 192.168.234.150
l2_population = true

[securitygroup]
enable_security_group = true
firewall_driver = neutron.agent.linux.iptables_firewall.IptablesFirewallDriver
```

逐项核对计算节点的 `.150`、`provider:ens34`、VXLAN、L2 population、安全组和 Linux bridge experimental 标志；再次确认 `ens34` 仍无地址。没有计算节点数据库同步步骤。

## 启用计算节点服务

先启用 Linux bridge agent，再重启 nova-compute，使其重新读取 Neutron 集成配置。两个服务都应为 active 且 enabled。

```bash
systemctl enable --now neutron-linuxbridge-agent
systemctl restart openstack-nova-compute
systemctl is-active --quiet neutron-linuxbridge-agent
systemctl is-enabled --quiet neutron-linuxbridge-agent
systemctl is-active --quiet openstack-nova-compute
systemctl is-enabled --quiet openstack-nova-compute
```

## 轻量最终验收

在 controller 加载 `/root/admin-openrc`。只做服务、Neutron API/认证 CLI、network agents 和**一个**任务专属私有网络的创建、查询、按精确 ID 删除；不创建 provider network、子网、路由器、实例或任何持久网络。

```bash
set -Eeuo pipefail
for s in neutron-server neutron-linuxbridge-agent neutron-dhcp-agent neutron-metadata-agent neutron-l3-agent openstack-nova-api; do systemctl is-active --quiet "$s" && systemctl is-enabled --quiet "$s"; done
source /root/admin-openrc
token=$(openstack token issue -f value -c id)
curl --noproxy '*' -fsS -H "X-Auth-Token: $token" http://controller:9696/ >/dev/null
unset token
openstack network agent list
openstack network list
```

`openstack network agent list` 必须显示 controller 的 DHCP、L3、Metadata、Linux bridge agent 以及 compute 的 Linux bridge agent 均为 Alive；若 agent 不是 Alive，先检查对应服务和配置，不应通过创建额外资源掩盖问题。

```bash
set -Eeuo pipefail
source /root/admin-openrc
network_name="task5f-private-$(date -u +%Y%m%d%H%M%S)"
network_id=$(openstack network create --internal "$network_name" -f value -c id)
[[ -n $network_id ]]
openstack network show "$network_id"
openstack network list --name "$network_name"
openstack network delete "$network_id"
if openstack network show "$network_id" >/dev/null 2>&1; then echo 'task-owned network remains' >&2; exit 1; fi
```

最后重新检查两台机器的 `ens34` 均无 IPv4/全局 IPv6，且 compute 的 `/dev/sdb`、`/dev/sdc` 仍为无签名空白 50 GiB disk。清理仅限上述 `network_id`，不使用按名称模糊删除。

## Focused Neutron contract（仅验收，不安装）

将无秘密的服务/API/agent/网络生命周期和边界事实收集成下列字典后再调用验证器。它不连接主机、不写配置、不创建资源，也不能代替前文的逐条手工命令。

```python
from __future__ import annotations

def validate_neutron_lightweight_evidence(evidence: dict[str, object]) -> None:
    services = evidence.get("services")
    expected_services = {
        "controller": {"neutron-server", "neutron-linuxbridge-agent", "neutron-dhcp-agent", "neutron-metadata-agent", "neutron-l3-agent"},
        "compute": {"neutron-linuxbridge-agent", "openstack-nova-compute"},
    }
    if not isinstance(services, dict) or set(services) != set(expected_services) or any(
        set(services[node]) != expected for node, expected in expected_services.items()
    ):
        raise ValueError("Neutron service active/enabled evidence mismatch")
    if evidence.get("api") != {"http": 200, "authenticated": True}:
        raise ValueError("Neutron API or authenticated CLI evidence mismatch")
    agents = evidence.get("agents")
    if agents != {
        "alive": True, "hosts": ["controller", "compute"],
        "types": ["DHCP agent", "L3 agent", "Linux bridge agent", "Metadata agent"],
    }:
        raise ValueError("Neutron agent evidence mismatch")
    lifecycle = evidence.get("network_lifecycle")
    if not isinstance(lifecycle, dict) or not (
        str(lifecycle.get("name_prefix", "")).startswith("task5f-private-")
        and lifecycle.get("created") is True and lifecycle.get("listed") is True
        and lifecycle.get("deleted_exact_id") is True and lifecycle.get("absent_after_delete") is True
    ):
        raise ValueError("task-owned network lifecycle mismatch")
    if evidence.get("boundaries") != {
        "ens34_address_free": True, "compute_disks_unchanged": True,
        "routers": [], "subnets": [], "instances": [], "provider_networks": [],
    }:
        raise ValueError("Neutron task boundary mismatch")
```
