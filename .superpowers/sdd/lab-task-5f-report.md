# Lab Task 5F 报告：Neutron 手工部署与轻量验收

基线：`bed6ffa899d4bf90de3a1d4a80a4a379d9b33a91`。

## 远端变更与备份

- controller：仅从 `openstack-local` 安装 `openstack-neutron`、`openstack-neutron-ml2`、`openstack-neutron-linuxbridge`、`ebtables`、`ipset` 及本地源解析出的依赖；建立 Neutron DB、三个精确主机范围的 `neutron` DB 账户、Default-domain `neutron` 服务用户、service 项目 admin 绑定、network 服务和 RegionOne 三端点；手工等价配置了 sysctl、Neutron、ML2、Linux bridge、L3、DHCP、metadata 与插件链接，并完成数据库同步、Nova API 重启和控制端 Neutron 服务启用。
- compute：仅从 `openstack-local` 安装 Linux bridge agent 所需包及本地源解析出的依赖；配置 sysctl、Neutron、Linux bridge agent，启用 agent 并重启 nova-compute。
- 远端备份：controller `/root/openstack-lab-backups/task-5f-20260811T142650Z`；compute `/root/openstack-lab-backups/task-5f-20260811T142924Z`。备份目录权限受限，未复制到仓库；报告及快照均未包含凭据。
- 未创建或恢复快照，未安装/进入 Cinder、Swift、Horizon，未创建 provider network、子网、路由器或实例；没有写入 `/dev/sdb` 或 `/dev/sdc`。

## 轻量验收结果

- controller：`neutron-server`、`neutron-linuxbridge-agent`、`neutron-dhcp-agent`、`neutron-metadata-agent`、`neutron-l3-agent` 均为 `active/enabled`；`openstack-nova-api` 同样为 `active/enabled`。
- compute：`neutron-linuxbridge-agent` 和 `openstack-nova-compute` 均为 `active/enabled`。
- 带 Keystone token 的 `http://controller:9696/` 返回 HTTP 200；认证 CLI 的网络和 agent 查询可用。
- agents：controller 的 Linux bridge、DHCP、Metadata、L3 agents 和 compute 的 Linux bridge agent 均为 Alive。
- 临时网络：创建一个 `task5f-private-*` 内部网络，按创建返回的精确 ID 查询并删除；最终 `openstack network list` 为 `[]`。
- 终态边界：两端 `ens34` 无 IPv4/全局 IPv6；compute `/dev/sdb` 与 `/dev/sdc` 保持 53,687,091,200 bytes 的原始数据盘身份。

## 本地教材与验证产物

- `third-edition-work/validation/manual-install/08-neutron-controller.md`
- `third-edition-work/validation/manual-install/09-neutron-compute.md`
- `third-edition-work/validation/manual-install/config-snapshots/controller-*neutron*`、`compute-*neutron*`：全部脱敏，使用 `<SERVICE_PASSWORD>` 和 `<URL_ENCODED_PASSWORD>` 占位符。
- `third-edition-work/tests/test_deployment_contract.py`：focused Neutron contract，范围仅覆盖手工顺序、关键参数、脱敏快照、轻量服务/API/agent/网络生命周期与边界。

## 偏差与风险

- 初次配置错误地使用了 SSH 登录口令作为 Neutron 的服务/消息队列口令，agents 日志报告 RabbitMQ `ACCESS_REFUSED`。根因确认后，已改为现有受限运行时 OpenStack 服务口令，并重启相应 Neutron 服务；最终 agents 全部 Alive。实际口令未写入、输出、哈希或提交。
- 该发行版的 L3 agent 在修复消息队列认证后需要等待 RPC 注册完成；使用有上限的条件轮询确认其 Alive，没有增加资源或故障注入测试。
- Windows 环境未提供 Git Bash；没有为 Bash 解析额外安装工具。对教材命令进行了人工审阅，远端服务/API 结果和 Python 契约测试作为验证依据。
