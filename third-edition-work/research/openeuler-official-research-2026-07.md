# openEuler 官方事实核查（事实冻结：2026-07-31）

## 0. 范围、方法与证据等级

- **用途**：为云计算教材第三版提供可直接采用或改写的 openEuler 事实底稿；不构成产品选型、合规认定或安全认证意见。
- **事实冻结点**：2026-07-31。网页访问日期统一为 **2026-08-12**；只纳入冻结点之前已经发生或公布的事实。动态下载页在访问时可能继续更新，因此涉及版本状态时同时用版本表、发行说明和官方仓库交叉核对。
- **来源边界**：只采用 openEuler、开放原子开源基金会及 openEuler 社区官方文档/官方新闻/官方仓库。OpenInfra 一节只转述 openEuler 官方对合作的表述；未找到可在本轮核对中用于界定双方正式法律或成员关系的 OpenInfra 官方条款，故不作扩张解释。
- **检索降级披露**：原计划使用 `agent-reach`；上级任务已执行 `agent-reach doctor --json`，环境返回“command not found”。本轮依照 agent-reach 技能的网页检索/网页读取回退路径，限定官方域名检索。该降级不改变“仅用官方一手来源”的证据标准，但无法提供 Agent Reach 的渠道体检记录。
- **标签**：
  - **[已核实事实]**：官方页面直接陈述，或官方版本表/仓库直接显示。
  - **[推断]**：由两个或以上官方事实推得，正文明确说明推断链，不能改写成官方原话。
  - **[教学表述]**：为教材组织的解释性语言，不是项目方认证、政策结论或市场结论。
- **置信度**：高＝官方制度、版本化文档或仓库直接支持；中＝官方新闻/社区 SIG 文档支持，但范围、时效或另一方确认有限；低＝本报告不采用为正文事实。

## 1. 可直接进入教材的核心结论

1. **[已核实事实｜高]** OpenAtom openEuler（简称 openEuler）是由开放原子开源基金会孵化及运营、面向数字基础设施的开源操作系统项目。官方 FAQ 将其称为 Linux 发行版，场景覆盖服务器、云、边缘和嵌入式。openEuler 社区于 **2019-12-31** 正式成立；官方早期记录还表明，2019-09-17 宣布将在当年年底开源，随后社区基础设施于年底启用。[S1][S2]
2. **[已核实事实｜高]** 官方社区材料记载：openEuler 于 **2021-11-09** 正式贡献给开放原子开源基金会，并在基金会治理框架下成为首批项目群之一。现行《openEuler 项目群开源治理制度》（最后修订：2024 年 3 月）明确，项目群由开放原子开源基金会孵化及运营，并在基金会制度和知识产权政策框架内开放治理。[S3][S4]
3. **[已核实事实｜高]** 现行治理结构中，openEuler 项目群工作委员会（简称 **openEuler 委员会**）是业务最高决策机构；项目群办公室负责日常执行；技术委员会负责技术决策，另设品牌委员会、用户委员会等。技术委员会委员候选与 SIG/子项目 Maintainer 体系相连，不能把社区简单描述为某一家企业的内部项目。[S4]
4. **[已核实事实｜高]** **openEuler 24.03 LTS** 是一个 LTS 版本族。官方生命周期页称该 LTS 于 **2024 年 6 月**发布、内核为 6.6；“24.03”是版本流名称，不宜仅凭名称反推实际公开发布日期为 2024 年 3 月。[S5][S6]
5. **[已核实事实｜高]** **openEuler 24.03 LTS SP3** 的精确身份是：24.03 LTS 版本族中的 SP3，官方版本表给出的发布月为 **2025/12**、计划 EOL 为 **2027/12**；SP3 发行说明明确写明运行于 **Linux kernel 6.6**。截至 2026-07-31，官方版本表已经列出 **SP4（2026/06，计划 EOL 2027/03）**，所以 SP3 不能写成“最新 openEuler 版本”或“24.03 LTS 最新 SP”。[S5][S7][S8]
6. **[推断｜高]** 依据自 2025 年 8 月生效的 LTS+SP 规则，12 月发布的是“大 SP”，原则生命周期 24 个月；SP3 于 2025/12 发布、计划 EOL 2027/12，因此 SP3 属于该规则下的**大 SP**。SP4 于 2026/06 发布、计划 EOL 2027/03，符合“6 月可选小 SP、原则生命周期 9 个月”的规则。这里“SP3 是大 SP”是规则与版本表的合并推断，不是下载页逐字标签。[S5][S7]
7. **[已核实事实｜高]** SP3 的标准/Everything/Debug、Edge、Desktop ISO 与 VM 镜像在发行说明中明确列出 x86_64 和 AArch64；嵌入式产物另列 AArch64 与 Arm32。官方 SP3 仓库的 ISO 目录还列有 `loongarch64` 与 `riscv64`，官方下载筛选器把 SP3 与 x86_64、aarch64、ARM32、LoongArch64、RISC-V 关联。[S7][S9]
8. **[教学表述｜高]** 因不同架构对应的介质、场景和成熟度并不相同，教材宜写“openEuler 社区面向多种处理器架构提供不同形态的发行产物”，并要求读者按**具体版本—具体介质—具体硬件型号**查询兼容性清单；不宜概括成“在所有场景全面支持所有国产 CPU”。[S7][S9][S10]
9. **[已核实事实｜高]** SP3 官方运维文档把 RPM 作为软件包管理基础，列出 `rpm -q/-qa/-qi` 等查询方式；DNF 用于解析仓库和依赖并执行 `repolist`、`install`、`upgrade`、`list`、`info`、`search`、`check-update`、`remove`、`history`、`makecache`、`clean` 等操作。[S11]
10. **[已核实事实｜高]** SP3 官方文档使用 `systemctl` 启停、重启、查看状态以及设置服务开机启用/禁用；用户与组管理沿用 Linux 常见的 `useradd`、`passwd`、`id` 等工具，账户信息涉及 `/etc/passwd`、`/etc/shadow`、`/etc/group`。[S12][S13]
11. **[已核实事实｜中]** SP3 文档中心在“Virtualization”下提供 OpenStack User Guide 入口；openEuler OpenStack SIG 将目标表述为“在 openEuler 之上提供原生的 OpenStack”。这足以说明 openEuler 社区开展 OpenStack 软件包、适配、测试和使用文档工作，但不足以推出“openEuler 是 OpenStack 的一个版本”或“SP3 支持某一 OpenStack 版本全集”。[S14][S15]
12. **[已核实事实｜中]** openEuler 官方 2024 年材料称其与 OpenInfra 开展技术合作/深化合作，并提到参与 OpenInfra PTG、为 OpenStack 兼容性测试提供虚拟资源等。安全写法是“openEuler 社区与 OpenInfra/OpenStack 社区开展技术协作”；不要写成“openEuler 隶属于 OpenInfra”或“openEuler 是 OpenInfra 托管项目”。[S16][S17]

## 2. 项目起源与治理：推荐教材口径

### 2.1 核实链

- **[已核实事实]** 2019-09-17，openEuler 被宣布将在年底开源；2019-12-31，社区基础设施正式启用。官方 FAQ 将 2019-12-31 记为社区正式成立日。[S1][S2]
- **[已核实事实]** 2021-11-09，openEuler 正式贡献给开放原子开源基金会。[S3]
- **[已核实事实]** 现行章程称其全称为“OpenAtom openEuler 项目群”，由开放原子开源基金会孵化及运营，采取治理组织领导下的项目自治，并受基金会章程、项目管理制度及知识产权政策约束。[S4]
- **[已核实事实]** openEuler 委员会负责重大业务决策；技术委员会负责技术决策；项目群办公室负责日常执行；品牌委员会和用户委员会分别承担品牌与用户工作。[S4]
- **[推断]** 可以说 openEuler 经历了“从最初的企业主导走向基金会框架下的产业/社区共建治理”；该概括有官方回顾材料支持。但不要进一步推断“任何单一厂商已完全没有影响力”，因为委员、捐赠人与贡献主体仍会实际参与治理。[S3][S4]

### 2.2 可用文本

> **[教学表述]** openEuler 社区于 2019 年底正式成立，2021 年 11 月贡献给开放原子开源基金会。现行治理采用项目群制度：openEuler 委员会承担重大业务决策，技术委员会负责技术方向，项目群办公室负责日常执行，并通过 SIG 和 Maintainer 机制组织具体技术协作。因而，openEuler 既有企业发起和早期投入的历史，也应按基金会框架下的开源社区项目来理解。

## 3. 24.03 LTS/SP 生命周期与 SP3 精确身份

| 项目 | 截至 2026-07-31 的结论 | 类型/置信度 | 依据 |
|---|---|---|---|
| 版本族 | openEuler 24.03 LTS | 已核实/高 | 生命周期页、官方下载页 [S5][S7] |
| LTS 首版本实际发布 | 2024 年 6 月（官方发布文章日期 2024-06-12） | 已核实/高 | [S5][S6] |
| SP3 全称 | openEuler 24.03 LTS SP3 | 已核实/高 | [S7][S8] |
| SP3 发布月 | 2025/12 | 已核实/高 | 官方版本表 [S7] |
| SP3 计划 EOL | 2027/12 | 已核实/高 | 官方版本表 [S7] |
| SP3 性质 | 12 月“大 SP”，原则 24 个月 | 推断/高 | 生命周期规则 + 版本表 [S5][S7] |
| 内核基线 | Linux kernel 6.6 | 已核实/高 | SP3 Release Notes → Key Features → Kernel Innovations [S8] |
| 截止日较新 SP | SP4，2026/06 发布，计划 EOL 2027/03 | 已核实/高 | 官方版本表 [S7] |
| SP3 是否“最新” | 否 | 已核实/高 | SP4 已在冻结点前发布 [S7] |

现行生命周期规则（**自 2025 年 8 月起生效**）应按两个层次理解：[S5]

- LTS 全版本生命周期为 6 年：4 年全面支持 + 2 年维护支持；生命周期结束前可以组建联合维护团队申请可选的 2 年延长。**这不等于每个 SP 都自动支持 6 年或 8 年。**
- LTS 内部 SP 原则上分为：6 月可选“小 SP”，生命周期 9 个月；12 月“大 SP”，生命周期 24 个月。大规模使用，官方规则建议选择大 SP。
- 全面支持包含 CVE、Bugfix、新硬件支持和少量兼容性新特性；维护/扩展支持限于“主要”以上 CVE 和 Bug 修复。社区生命周期不是商业厂商 SLA。

### 3.1 精确介质名称（用于实验指导）

官方 SP3 发行说明直接列出：[S9]

- `openEuler-24.03-LTS-SP3-x86_64-dvd.iso`
- `openEuler-24.03-LTS-SP3-aarch64-dvd.iso`
- 对应的 `everything`、`everything-debug`、Edge、Desktop ISO
- `openEuler-24.03-LTS-SP3-x86_64.qcow2.xz`
- `openEuler-24.03-LTS-SP3-aarch64.qcow2.xz`
- 官方仓库根目录：`https://repo.openeuler.org/openEuler-24.03-LTS-SP3/`

**[教学表述]** 实验开始先核对三项：`cat /etc/os-release` 查看发行版标识，`uname -r` 查看当前运行内核，`rpm -q kernel` 查看已安装内核包。不要把教材截图中的某个具体 `6.6.x-...` 包号写成所有 SP3 安装的固定值；官方只在发行特性页确认 6.6 基线，更新仓中的补丁级包号会变化。

## 4. 架构、介质与生态：避免夸大“信创”结论

### 4.1 已核实边界

- SP3 Release Notes 的服务器 ISO/VM 表明确列出 x86_64 与 AArch64；嵌入式表明确列出 AArch64、Arm32 产物。[S9]
- 官方 SP3 仓库 `ISO/` 目录包含 `aarch64/`、`loongarch64/`、`riscv64/`、`x86_64/`；其中不同目录的时间与产物并不完全相同。[S10]
- 官方下载页把 SP3 与 x86_64、aarch64、ARM32、LoongArch64、RISC-V 关联，但具体下载项随所选架构/场景变化。[S7]
- SP3 嵌入式特性页写明其 Embedded Linux 面向 AArch64、x86_64、AArch32、RISC-V，并把 LoongArch 写为未来扩展方向；这进一步说明“架构支持”必须带上子版本/场景，不能只引用网站页脚的总括列表。[S8]
- 官方要求按兼容性流程测试硬件，通过后才进入 Compatibility List；迁移指导也要求检查整机和 RAID/NIC/FC/IB/GPU/SSD/TPM/AI 等部件。[S18][S19]

### 4.2 安全措辞

> **[教学表述]** openEuler 面向数字基础设施，社区为多种处理器架构和服务器、云、边缘、嵌入式等场景提供发行产物与适配工作。实际部署时，应以目标版本的安装介质、软件仓、硬件兼容性清单和应用验证结果为准。

> **[教学表述]** 在介绍“可信的本土数字基础设施”时，可把 openEuler 作为国内开源基础软件社区治理、多架构适配、软件供应链与云平台适配的教学案例。若进入生产或关键信息系统，应进一步核验具体社区/商业发行版、硬件认证、漏洞响应、维护周期和服务合同；“开源”“由国内基金会孵化”本身不自动等于合规认证、安全等级或“自主可控”结论。

## 5. DNF/RPM 与系统管理基础

### 5.1 RPM 与 DNF

**[已核实事实｜高]** SP3 文档将 RPM 描述为软件包管理基础，软件包信息写入 RPM 数据库；DNF 面向仓库、依赖与事务管理。[S11]

适合教材的最小命令集：

```bash
# 查询已安装 RPM 包
rpm -q bash
rpm -qa
rpm -qi bash

# 查看仓库、搜索和查看包信息
dnf repolist --enabled
dnf search nginx
dnf info nginx

# 安装、更新检查、升级、卸载与事务历史
sudo dnf install nginx
dnf check-update
sudo dnf upgrade
sudo dnf remove nginx
dnf history
```

**[教学表述]** DNF 是日常从仓库安装/升级的首选教学入口；`rpm` 更适合查询、校验或处理本地 RPM。不要在正文暗示跳过签名检查。官方文档要求安装前核对包签名，并列有 RPM GPG 密钥导入机制。[S11]

**教材勘误提醒**：SP3 的“Common Configurations”页面中若干 `rpm` 示例输出仍带 `oe2203sp2`/22.03 SP2 样例，且 GPG key 示例路径也写 22.03 LTS SP2。可采用命令语义，不应把这些示例版本号复制成 SP3 的实际包版本或密钥路径。[S11]

### 5.2 服务、账户与网络

```bash
# 服务管理（以 sshd 为例）
systemctl status sshd
sudo systemctl start sshd
sudo systemctl restart sshd
sudo systemctl enable sshd

# 用户与身份
sudo useradd student
sudo passwd student
id student

# 基本网络查看
ip addr
ip route
```

- **[已核实事实]** SP3 文档使用 `systemctl start/stop/restart/status/enable/disable` 管理服务，并提醒此类操作需要 root 权限。[S12]
- **[已核实事实]** 用户管理采用 `useradd`、`passwd`、`id`，核心账户文件包括 `/etc/passwd`、`/etc/shadow`、`/etc/group`。[S13]
- **[教学表述]** 课堂上应使用 `sudo` 和最小权限账户，修改配置前备份，修改后先做语法检查再重载/重启服务；不要把“直接用 root 登录并关闭防火墙/SELinux”设置为通用步骤。

## 6. 与 OpenInfra / OpenStack 的关系

### 6.1 可以说什么

- **[已核实事实｜中]** openEuler SP3 文档中心在 Virtualization 分类下提供 OpenStack User Guide 入口。[S14]
- **[已核实事实｜中]** openEuler OpenStack SIG 的公开目标是“在 openEuler 之上提供原生的 OpenStack，构建开放可靠的云计算技术栈”，并开展 RPM、安装、测试和贡献工作。[S15]
- **[已核实事实｜中]** openEuler 官方 2024 年文章称 openEuler 参与 OpenInfra PTG、支持 OpenStack 兼容性测试，并在 2024 年 11 月宣布与 OpenInfra 深化合作。[S16][S17]

### 6.2 必须保留的限制

- OpenStack 是云基础设施管理平台，openEuler 是操作系统/发行版项目；二者不是同一层次的软件。
- OpenInfra 是独立基金会/社区体系；openEuler 由开放原子开源基金会孵化及运营。技术合作不等于隶属关系。
- OpenStack SIG 支持矩阵页面在本次访问时只明确列到 `openEuler 24.03 LTS` 与 Wallaby/Antelope，没有列出 `24.03 LTS SP3` 行。因此，本报告**不把该矩阵外推为 SP3 的精确 OpenStack 支持清单**。[S15]

推荐教材句：

> **[教学表述]** openEuler 社区设有 OpenStack SIG，围绕在 openEuler 上的软件包构建、适配、测试和部署文档开展工作；openEuler 社区也与 OpenInfra 社区进行技术交流与协作。具体 OpenStack 版本和组件的可用性，应查阅目标 openEuler 版本对应的 SIG 支持矩阵并完成部署验证。

## 7. 禁止或应撤回的表述

以下句子在本轮官方证据下不可写入教材正文：

1. **“openEuler 是完全自主研发、100% 国产代码、没有国外开源组件的操作系统。”** 开源 Linux 发行版由大量不同上游组件构成；官方许可页也明确各组件适用相应开源许可证。
2. **“openEuler 已获得国家信创目录/国家自主可控认证/等保认证，因此天然适用于所有关键系统。”** 本轮无此官方证据；项目身份不能替代具体产品和部署的认证。
3. **“openEuler 可以无条件替代 CentOS/RHEL/Ubuntu，应用无需改造。”** 官方迁移指导要求对硬件、软件依赖和配置做兼容性评估。[S19]
4. **“openEuler 全面支持 ARM、x86、RISC-V、LoongArch、PowerPC、SW-64 的所有硬件和全部场景。”** 官网总括口径、具体 SP3 介质和嵌入式子系统口径并不相同，必须细化到产物和兼容清单。
5. **“openEuler 24.03 LTS SP3 是截至 2026 年 7 月的最新版本/最新 SP。”** 错误；SP4 已于 2026/06 发布。[S7]
6. **“24.03 LTS SP3 自动获得 6 年或 8 年支持。”** 错误；全 LTS 版本族与单个 SP 的生命周期规则不同。SP3 官方计划 EOL 是 2027/12。[S5][S7]
7. **“SP3 使用原封不动的上游 Linux 6.6.0 内核。”** 官方只确认 6.6 基线；不能由此推断固定补丁级或没有 openEuler 补丁。
8. **“社区生命周期等于厂商提供 7×24 SLA。”** 社区支持策略不等于商业服务合同。
9. **“openEuler 属于 OpenInfra / 是 OpenInfra 托管项目 / 是 OpenStack 的一个发行版。”** 无依据且混淆项目归属与软件层次。
10. **“SP3 已官方支持 OpenStack Wallaby 和 Antelope 的全部组件。”** OpenStack SIG 页面只明确到 24.03 LTS 基线，未给出 SP3 专属矩阵，不能外推。[S15]
11. **“OpenInfra 已对 SP3 提供正式认证或商业支持。”** openEuler 官方材料可证明合作表述，不能代替 OpenInfra 侧的认证、成员或支持合同证据。
12. **“openEuler 就是 Huawei EulerOS，仍由华为单独拥有和决策。”** 忽略了 2021 年贡献给开放原子开源基金会及现行项目群治理制度；但也不应反向写成“华为已与项目完全无关”。
13. **“openEuler 所有组件统一采用 MulanPSL2。”** 官方 Terms of Use 区分项目集合性作品许可与各开源组件各自适用的许可证。[S20]

## 8. 官方来源审计表

所有来源访问日期：**2026-08-12**。

| 编号 | 官方来源（标题、版本/日期、章节或页面） | 直接 URL | 支撑要点 | 置信度 |
|---|---|---|---|---|
| S1 | *General Community Questions*；Common FAQ；“What is openEuler”“What is the openEuler community like” | https://docs.openeuler.org/en/docs/common/faq/general/general_faq.html | 基金会孵化运营、Linux 发行版、2019-12-31 成立 | 高 |
| S2 | 《openEuler开源社区基础设施上线》；2020-01-01；正文 | https://www.openeuler.org/zh/blog/openeuler/20200101.html | 2019-09-17 宣布年底开源、基础设施启用 | 高 |
| S3 | 《openEuler委员会主席江大勇：激发原创力量，逐梦数智未来》；2022-12-28；治理回顾段 | https://www.openeuler.org/zh/news/20221228-summit | 2021-11-09 正式贡献给开放原子开源基金会、治理转型 | 高 |
| S4 | 《openEuler项目群开源治理制度》；最后修订 2024-03；第一章、第三章第九至十四条 | https://www.openeuler.org/zh/community/charter/ | 项目名称、基金会关系、治理原则、委员会/办公室/TC 职责 | 高 |
| S5 | *Version Lifecycles*；规则自 2025-08 生效；“Overall”“LTS+SP” | https://www.openeuler.org/en/other/lifecycle/ | LTS 4+2、可选 +2、6 月小 SP 9 个月、12 月大 SP 24 个月、支持范围 | 高 |
| S6 | *openEuler 24.03 LTS: The First AI-Native Open Source Operating System*；2024-06-12 | https://www.openeuler.org/en/news/20240612-openEuler%2024.03%20LTS-The%20First%20AI-Native%20Open%20Source%20Operating%20System/ | 24.03 LTS 发布时点的官方佐证 | 高 |
| S7 | *Download Community Release*；版本表；SP3/SP4 条目 | https://www.openeuler.org/en/download/?version=openEuler+24.03+LTS | SP3 2025/12、EOL 2027/12；SP4 2026/06、EOL 2027/03；架构/场景筛选 | 高（动态页） |
| S8 | *Key Features*；Version 24.03 LTS SP3；“Kernel Innovations”“Embedded” | https://docs.openeuler.org/en/docs/24.03_LTS_SP3/server/releasenotes/releasenotes/key_features.html | SP3 Linux 6.6 基线；嵌入式架构边界 | 高 |
| S9 | *OS Installation*；Version 24.03 LTS SP3；“Release Packages”“Hardware Compatibility” | https://docs.openeuler.org/en/docs/24.03_LTS_SP3/server/releasenotes/releasenotes/os_installation.html | 精确 ISO/VM/嵌入式产物名、最低配置与兼容性清单入口 | 高 |
| S10 | 官方仓库索引；`openEuler-24.03-LTS-SP3/ISO/`；目录时间 2025-12 至 2026-03 | https://repo.openeuler.org/openEuler-24.03-LTS-SP3/ISO/ | aarch64、loongarch64、riscv64、x86_64 目录实证 | 高 |
| S11 | *Common Configurations*；Version 24.03 LTS SP3；“Managing RPM Packages”“DNF commands”“Configuring SSH” | https://docs.openeuler.org/en/docs/24.03_LTS_SP3/server/maintenance/common_skills/common_configurations.html | RPM/DNF 命令与签名、仓库、SSH 服务；另揭示旧版示例残留 | 高（示例版本号需排除） |
| S12 | *Configuring the Web Server*；Version 24.03 LTS SP3；“Managing httpd/Managing Nginx” | https://docs.openeuler.org/en/docs/24.03_LTS_SP3/server/administration/administrator/configuring_the_web_server.html | systemctl 启停/状态/启用/禁用与权限要求 | 高 |
| S13 | *User and User Group Management*；Version 24.03 LTS SP3；“Managing Users” | https://docs.openeuler.org/en/docs/24.03_LTS_SP3/server/administration/administrator/user_and_user_group_management.html | useradd/passwd/id、账户文件 | 高 |
| S14 | *Virtualization*；Version 24.03 LTS SP3；文档索引 | https://docs.openeuler.org/en/docs/24.03_LTS_SP3/virtualization/index.html | SP3 文档中心提供 OpenStack User Guide 入口 | 中 |
| S15 | *openEuler OpenStack SIG*；“SIG 工作目标和范围”“OpenStack版本支持列表”；访问时矩阵列至 24.03 LTS | https://openstack-sig.readthedocs.io/zh/latest/ | 在 openEuler 上提供 OpenStack；矩阵不含 SP3 专行，禁止外推 | 中（SIG 文档可能滞后） |
| S16 | 《openEuler的国际化征程与全球化战略的深化》；2024-06-25；OpenInfra 段 | https://www.openeuler.org/zh/news/20240719-24032/20240719-24032.html | openEuler 官方所述 PTG、兼容性测试与合作 | 中（单方官方表述） |
| S17 | *openEuler Monthly Bulletin – November*；2024-11-30；全球合作段 | https://www.openeuler.org/en/news/20241130/openEuler%20Monthly%20Bulletin%20-%20November.html | 官方宣布与 OpenInfra 等深化合作 | 中（单方官方表述） |
| S18 | *Hardware Compatibility Test*；流程页；“Compatibility Test Process” | https://www.openeuler.org/en/compatibility/hardware/ | 硬件兼容测试、审核后进入兼容性清单 | 高 |
| S19 | *Guidelines for Migrating to openEuler*；“Migration Assessment”“Designing a Migration Plan” | https://www.openeuler.org/en/migration/guidance/ | 迁移需评估硬件、软件依赖、配置和跨架构适配 | 高 |
| S20 | *Terms of Use*；Version 24.03 LTS SP3；“Copyright and Licenses” | https://docs.openeuler.org/en/docs/24.03_LTS_SP3/server/releasenotes/releasenotes/terms_of_use.html | 集合性作品与各组件许可证的区分 | 高 |

## 9. 给主稿作者的最短替换段

> openEuler 是由开放原子开源基金会孵化及运营、面向数字基础设施的开源 Linux 操作系统项目，社区采用 openEuler 委员会、技术委员会、项目群办公室和 SIG 等协作治理机制。openEuler 24.03 LTS SP3 于 2025 年 12 月发布，采用 Linux 6.6 内核基线，官方计划维护至 2027 年 12 月；截至 2026 年 7 月，24.03 LTS 版本族还已发布 SP4，因此 SP3 不应称为“最新版本”。openEuler 使用 RPM 软件包体系，并以 DNF 进行仓库和依赖管理，服务管理通常使用 systemctl。社区为多种处理器架构和服务器、云、边缘、嵌入式等场景提供不同发行产物，实际部署需以具体版本介质、兼容性清单和测试结果为准。openEuler 社区设有 OpenStack SIG，并与 OpenInfra/OpenStack 社区开展适配、测试和技术协作，但 openEuler 并非 OpenInfra 托管项目，也不能由合作关系推导出特定版本的认证或商业支持。
