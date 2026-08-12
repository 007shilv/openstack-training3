# Lab Task 5G 报告：Cinder 手工部署与轻量验收

基线：`50d0e2e57defbd215ebd173ec91a5b20d2284212`。

## 远端变更与备份

- controller：仅从 `openstack-local` 安装 `openstack-cinder`、API、scheduler 及本地源依赖；创建 `cinder` 数据库和精确为 `%`、`127.0.0.1`、`localhost` 的授权；创建 Default 域 `cinder` 用户、service 项目 admin 绑定、`cinderv3`/`volumev3` 服务及 RegionOne 三端点；手工等价配置 Cinder，完成 `cinder-manage db sync`，启用 API/scheduler，配置 Nova 的 `os_region_name=RegionOne` 并重启 Nova API，创建 `lvm` 类型及 `LVM-ISCSI` 属性。
- compute：仅从 `openstack-local` 安装 `lvm2`、`targetcli`、`openstack-cinder-volume` 及本地源依赖；在再次严格门禁和显式确认后，仅对 `/dev/sdb` 执行 `pvcreate`、`vgcreate cinder-volumes`，配置 LVM/LIO iSCSI 后端，启用 `targetclid` 和 `openstack-cinder-volume`。
- 远端默认配置备份：controller `/root/openstack-lab-backups/task-5g-20260811T144718Z`；compute `/root/openstack-lab-backups/task-5g-20260811T145635Z`。备份仅在远端受限目录，未进入仓库。

## 磁盘初始化事实与边界

- 写入前确认 compute 身份为 `192.168.234.150`；根盘祖先为 `/dev/sda2,/dev/sda`，不含 `/dev/sdb`。
- `/dev/sdb` 是无分区、无挂载、无签名、无 PV 的精确 53,687,091,200-byte 整盘；已依授权初始化为唯一 `cinder-volumes` PV/VG。
- 未写入 `/dev/sda` 或 `/dev/sdc`；终态 `/dev/sdc` 仍是无签名 50 GiB 整盘。未创建或恢复快照，未附加卷，未进入 Swift/Horizon。
- 后续本地复审修正了教材的防护表达：根盘祖先链先检查命令返回值和非空性，再逐项规范化比较；磁盘先精确读取 PV，只有无 PV 时才检查空白签名。唯一 `/dev/sdb`→`cinder-volumes` PV 视为幂等状态并跳过 `wipefs`/`pvcreate`/`vgcreate`；孤立、外来或重复 PV 以及探针失败均拒绝。本次修订没有连接或变更虚拟机。

## 验收结果

- controller 的 `openstack-cinder-api`、`openstack-cinder-scheduler`，compute 的 `targetclid`、`openstack-cinder-volume` 均为 active/enabled。
- 8776 API 监听，带 Keystone token 的 API 调用与认证 CLI 可用；`compute@lvm#LVM-ISCSI` 后端为 up，`lvm` 卷类型属性正确。
- 创建唯一任务专属 1 GiB 卷，等待至 `available`，再使用创建返回的精确 ID 删除，并确认对象已消失；没有附加。

## 本地产物、偏差与残余教学风险

- 教材：`10-cinder-controller.md`、`11-cinder-compute.md`；脱敏快照位于 `config-snapshots/`，仅含占位符，无真实凭据和存储标识。
- focused contract 仅检查手工顺序、服务/API、后端、唯一卷生命周期与磁盘边界；它不是安装入口。
- 运行环境没有 Git Bash，未额外安装 Bash 解析器；以远端实际服务/API/卷生命周期、Python 契约和静态范围检查作为验证证据。配置工具 `openstack-config` 在该发行版缺席，实际采用系统 Python 配置解析器逐项写入已备份的包默认配置；学生教材仍要求手工 `vi` 编辑。
