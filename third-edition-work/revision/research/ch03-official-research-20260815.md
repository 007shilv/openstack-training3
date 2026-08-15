# 第三章“原生 OpenStack 云平台”官方资料研究底稿

- 调研日期：2026-08-15
- 教材事实截止日：2026-07-31
- 资料范围：仅采用 OpenStack、OpenInfra Foundation 的官方发布页、项目文档、技术委员会治理资料和官方项目页面。
- 工具说明：已按 `agent-reach` 技能先执行环境检查，但当前 PowerShell 环境未安装或未识别 `agent-reach` 命令行；随后按任务约定改用网页检索与网页阅读工具，并逐项限定到官方域名。本文未采用媒体报道、厂商白皮书或百科材料。
- 使用提示：本文是第三章写作的事实底稿，不是可直接排版的章稿。本次未取得 2026-07-31 的官方页面归档快照；状态口径统一表述为“2026-08-15核验官方页面，并结合官方日程推定2026-07-31状态”。推定还参考官方已公布的发布日期和维护阶段规则。底稿与来源清单均区分“页面核验日”和“教材事实截止日”，不把 2026-08-15 页面假称为 2026-07-31 快照。

## 一、可直接用于章稿的关键结论

1. OpenStack 形成于 2010 年初：Rackspace 的云文件/云服务器开源工作与 Anso Labs 为 NASA 开发的 Nova 原型汇合；首届设计峰会于 2010 年 7 月 13—14 日在奥斯汀举行，项目于 7 月 21 日在 OSCON 正式宣布。早期两个基础项目是 Nova（计算）与 Swift（对象存储）。[OpenStack Project Team Guide：项目起源](https://docs.openstack.org/project-team-guide/introduction.html)；[OpenStack 官方发布公告](https://www.openstack.org/blog/introducing-openstack/)
2. OpenStack 不是单一软件包，而是由一组通过 API 协同的开源云服务组成的 IaaS 平台；官方概述称其统一管理数据中心的大规模计算、存储和网络资源，并以公共认证机制、Dashboard、CLI 和 SDK 提供访问入口。[OpenStack Software 概述](https://www.openstack.org/software/)
3. 2026-08-15 核验的官方发布页显示 2026.1 Gazpacho 为 Maintained、2026.2 Hibiscus 为 Development；结合 Gazpacho 已于 2026-04-01 首发和 Hibiscus 计划于 2026-09-30 发布的官方日程，推定 2026-07-31 最新已发布且处于 Maintained 状态的协调版本是 **2026.1 Gazpacho**，同时它是 SLURP 版本；**2026.2 Hibiscus** 当时尚未发布，不能写成“已发布”或“最新稳定版”。[OpenStack Releases 总览](https://releases.openstack.org/)；[Gazpacho 发布页](https://releases.openstack.org/gazpacho/index.html)；[Hibiscus 日程](https://releases.openstack.org/hibiscus/schedule.html)
4. 官方 Hibiscus 日程列明第二里程碑和 Membership Freeze 为 2026-07-02，2026-07-27 至 31 日为 R-9 周，第三里程碑/功能冻结计划在 8 月 27 日，最终发布计划在 9 月 30 日；据此可直接推定 2026-07-31 的 Hibiscus 仍处开发周期。第三章可以介绍“下一版本开发状态”，但不能用其开发中功能作为稳定能力承诺。[Hibiscus 日程](https://releases.openstack.org/hibiscus/schedule.html)
5. **SLURP** 的官方全称是 **Skip Level Upgrade Release Process**，含义是每隔一个协调版本指定一个 SLURP 版本，并测试、支持相邻 SLURP 版本之间的跨一级升级路径；它不是“长期支持版（LTS）”的同义词，也不等于无限期安全维护。[OpenStack TC：Release Cadence Adjustment](https://governance.openstack.org/tc/resolutions/20220210-release-cadence-adjustment.html)
6. OpenStack 2023.1 Antelope 是第一个正式采用该机制的 SLURP 版本，首发于 2023-03-22。2026-08-15 核验的官方发布页将其列为 **Unmaintained**；结合其发布日期、官方维护阶段规则及后续 SLURP 已发布的时间线，本文据此推定 2026-07-31 亦处于 Unmaintained，而不是把 8 月 15 日页面当作 7 月 31 日快照。[OpenStack TC：Unmaintained 取代 Extended Maintenance](https://governance.openstack.org/tc/resolutions/20230724-unmaintained-branches.html)；[Antelope 发布页](https://releases.openstack.org/antelope/index.html)
7. “Unmaintained”并不等于代码立即不可用，也不等于 EOL；其精确含义是：**不再产生正式发行且CI承诺降低；仍可按Unmaintained政策接受适当修复**。教材将 Antelope 固定为可复现实训基线时，必须明确它是**课程环境冻结版本**，不能称为“当前 Maintained 版本”。[Stable Branches：维护阶段](https://docs.openstack.org/project-team-guide/stable-branches.html)
8. 官方安装指南给出的最小服务顺序是 Keystone、Glance、Placement、Nova、Neutron；安装完最小集合后，官方建议再部署 Horizon 与 Cinder。教材可将前五项称为“本书最小云平台核心服务”，而不宜宣称它们是 OpenStack 治理文件定义的唯一“核心项目”。[OpenStack 安装指南：安装服务](https://docs.openstack.org/install-guide/openstack-services.html)
9. OpenStack 与 openEuler 的关系宜写为“上游云平台与 Linux 发行版/下游打包集成的关系”。官方 DevStack 文档称其尝试支持 Ubuntu LTS、Rocky Linux 9 和 openEuler；官方 diskimage-builder 还提供 `openeuler-minimal` 镜像元素。这些事实证明 openEuler 已进入部分上游工具的适配范围，但**不能据此推出某一 OpenStack＋openEuler 组合获得上游生产支持，更不能据此直接推出‘符合信创认证’**。[DevStack Quick Start](https://docs.openstack.org/devstack/latest/)；[diskimage-builder：openeuler-minimal](https://docs.openstack.org/diskimage-builder/latest/elements/openeuler-minimal/README.html)

## 二、起源、使命与治理

### 2.1 起源与演进

OpenStack 的官方项目团队指南对起源的描述比“NASA 与 Rackspace 联合研发”更精确：Rackspace 希望重写并开源其云基础设施代码；同时，Anso Labs 在 NASA 合同下发布了 Nova 的测试代码，两条工作线汇合形成 OpenStack。项目于 2010 年 7 月正式公布。2012 年 9 月，独立的 OpenStack Foundation 成立，基金会董事会负责组织目标、预算与商标，Technical Committee（TC）负责上游技术事务；2020 年 User Committee 并入 TC，不再作为独立治理机构。[官方项目历史](https://docs.openstack.org/project-team-guide/introduction.html)

2025 年 6 月，OpenInfra Foundation 正式成为 Linux Foundation 的一部分；官方同时说明 OpenInfra 的社区治理模式和技术项目流程被保留。现行 OpenInfra Charter 将 OpenInfra Foundation 定义为 Linux Foundation 的 directed fund，由其 Governing Board 指导；各 Technical Project 的技术治理仍依相应项目章程执行。[OpenInfra 加入 Linux Foundation 公告](https://openinfra.org/blog/openinfra-joins-linux-foundation)；[OpenInfra Foundation Charter](https://openinfra.org/legal/charter/)

### 2.2 截至截止日的治理结构

- **OpenInfra Governing Board**：监督 OpenInfra Foundation 及其所保护的资产与组织资源，包括 OpenStack 商标等。[OpenStack Governance 总览](https://governance.openstack.org/)
- **OpenStack Technical Committee**：由贡献者直接选举，对 OpenStack 的技术事务具有监督权，覆盖开发者、运营者和最终用户相关的技术治理。[OpenStack TC](https://governance.openstack.org/tc/)
- **Project Teams**：直接负责具体软件交付物或 QA、Release Management 等共同开发职能；所有官方项目团队均在 TC 监督下。[OpenStack Project Teams](https://governance.openstack.org/tc/reference/projects/)
- **SIG、Working Group、Popup Team**：处理跨项目主题、长期共同兴趣或限时跨项目目标，不应与发布具体服务的 Project Team 混为一谈。[OpenStack Governance 总览](https://governance.openstack.org/)

OpenStack 的技术决定不由 Rackspace、NASA、Linux Foundation 或某一家会员企业单独决定；基金会治理、TC 技术治理和项目团队交付是相互关联但不同的层次。

### 2.3 基金会组织职责

2012年9月成立的OpenStack Foundation为项目提供中立的组织载体，负责品牌、商标、资金、社区活动和产业生态，技术委员会则管理上游技术事务。2020年10月19日，Open Infrastructure Foundation被正式宣布为OpenStack Foundation的继任组织，支持范围扩展到OpenStack、Kata Containers、StarlingX、Airship和Zuul等开放基础设施项目。[OpenInfra Foundation成立公告](https://openinfra.org/blog/introducing-the-open-infrastructure-foundation/)

2025年6月，OpenInfra Foundation完成与Linux Foundation的整合。现行章程将其定义为Linux Foundation体系下的专项基金，成员类别包括Platinum、Gold、Silver和Associate，并保留个人会员参与计划。Governing Board的投票成员包括Platinum代表、Gold代表和个人会员代表，负责预算、政策、商标、生态事务及技术项目生命周期的总体框架。[OpenInfra现行章程](https://openinfra.org/legal/charter/)；[OpenInfra官方概述](https://openinfra.org/about/)

OpenStack Technical Committee是OpenStack的技术治理机构，由活跃贡献者选举产生，负责技术治理模型、官方项目范围、跨项目问题和最终技术协调。Project Teams负责正式软件交付，PTL协调日常工作；SIG、Working Group和Popup Team分别承担长期共同主题、受委托治理职能和限时跨项目目标。[TC章程](https://governance.openstack.org/tc/reference/charter.html)；[治理组织比较](https://governance.openstack.org/tc/reference/comparison-of-official-group-structures.html)

### 2.4 四项开放原则及实施流程

Open Source、Open Design、Open Development和Open Community源自OpenStack社区，后来成为OpenInfra Foundation支持各项目的共同原则。Open Source强调开放许可证、可研究修改再分发、可实际部署扩展和不以人为削弱功能形成“开放核心”；Open Design强调功能路线和架构设计公开；Open Development强调开发活动、评价标准和参与机会公开；Open Community强调开发者、用户与商业生态在平等规则下共同参与。[四项开放原则](https://openinfra.org/four-opens/)；[Open Source](https://openinfra.org/four-opens/open-source/)；[Open Design](https://openinfra.org/four-opens/open-design/)；[Open Development](https://openinfra.org/four-opens/open-development/)；[Open Community](https://openinfra.org/four-opens/open-community/)

OpenStack把原则落实为可观察的工作流：较大功能先通过公开规格讨论；代码经Gerrit提交并保存每个补丁集与评审意见；Zuul为补丁执行持续集成任务，必要检查通过后才允许合并；官方交付物由Release Management团队通过openstack/releases仓库协调，版本请求同样接受评审并触发自动化发布。[开放开发](https://docs.openstack.org/project-team-guide/open-development.html)；[代码评审](https://docs.openstack.org/project-team-guide/review-the-openstack-way.html)；[Zuul状态](https://docs.openstack.org/contributors/common/zuul-status.html)；[发布管理](https://docs.openstack.org/project-team-guide/release-management.html)

自2025年7月1日起，OpenStack新提交使用Developer Certificate of Origin，提交信息需包含有效的Signed-off-by，由OpenDev代码评审系统检查。DCO用于确认贡献者有权提交相关内容，取代此前的CLA流程，不改变公开评审和自动化测试要求。[DCO决议](https://governance.openstack.org/tc/resolutions/20250520-replace-the-cla-with-dco-for-all-contributions.html)

## 三、发布节奏、SLURP 与版本状态证据

OpenStack 协调发布延续约六个月一个周期。2022 年 TC 决议没有取消六个月节奏，而是在此基础上把每隔一个版本指定为 SLURP，使部署者可以选择每六个月逐版升级，也可以对齐 SLURP 后以约一年周期升级到下一个 SLURP。跨越两个以上 SLURP 周期并不在普通跳级升级保证之内，滚动升级/不停机升级也不能由“SLURP”一词自动推出。[Release Cadence Adjustment](https://governance.openstack.org/tc/resolutions/20220210-release-cadence-adjustment.html)

### 表 3-A　版本状态矩阵（2026-08-15核验官方页面，并结合官方日程推定2026-07-31状态）

| 系列 | 类型 | 首发/计划日期 | 推定的 2026-07-31 状态 | 教材可用表述 |
|---|---|---:|---|---|
| 2023.1 Antelope | SLURP | 2023-03-22 | Unmaintained | 冻结的课程实训基线；不再产生正式发行且CI承诺降低；仍可按Unmaintained政策接受适当修复 |
| 2024.1 Caracal | SLURP | 2024-04-03 | Unmaintained | 不再产生正式发行且CI承诺降低；仍可按Unmaintained政策接受适当修复 |
| 2025.1 Epoxy | SLURP | 2025-04-02 | Maintained | 推定在事实截止日仍处 Maintained 阶段 |
| 2025.2 Flamingo | 非 SLURP | 2025-10-01 | Maintained | Gazpacho 前一个半年版 |
| 2026.1 Gazpacho | SLURP | 2026-04-01 | Maintained | 推定为事实截止日最新已发布的 Maintained 版本 |
| 2026.2 Hibiscus | 非 SLURP | 计划 2026-09-30 | Development | 官方日程直接表明事实截止日仍在开发周期，不能称为已发布版本 |

证据口径：状态页于 2026-08-15 核验，未取得 2026-07-31 归档；7 月 31 日状态依据官方现行状态、不可逆的已发布日期、Hibiscus 明确日程和维护阶段规则综合推定。直接来源：[OpenStack Releases](https://releases.openstack.org/)；[Gazpacho](https://releases.openstack.org/gazpacho/index.html)；[Hibiscus Schedule](https://releases.openstack.org/hibiscus/schedule.html)；[Antelope](https://releases.openstack.org/antelope/index.html)。

### 表 3-B　Antelope 与 Gazpacho 上游首发组件版本对照

下表仅表示各协调版本发布页列出的**上游系列首发版本**，不是 openEuler 仓库中的 RPM 版本，也不是本书离线包的最终版本。下游发行版可能包含后续点版本或补丁回移，应另由实训仓库清单核验。

| 服务 | 2023.1 Antelope 首发版本 | 2026.1 Gazpacho 首发版本 |
|---|---:|---:|
| Keystone | 23.0.0 | 29.0.0 |
| Glance | 26.0.0 | 32.0.0 |
| Placement | 9.0.0 | 15.0.0 |
| Nova | 27.0.0 | 33.0.0 |
| Neutron | 22.0.0 | 28.0.0 |
| Cinder | 22.0.0 | 28.0.0 |
| Horizon | 23.1.0 | 25.6.0 |
| Swift | 2.31.0 | 2.37.0 |

直接来源：[Antelope 发布页](https://releases.openstack.org/antelope/index.html)；[Gazpacho 发布页](https://releases.openstack.org/gazpacho/index.html)。

### 3.1 Antelope 作为“冻结实训版本”的准确含义

推荐章稿表述：

> 本书实训环境固定采用 OpenStack 2023.1 Antelope，以保证软件包、配置项、命令顺序和实验结果可重复。Antelope 是首个 SLURP 版本；2026 年 8 月 15 日核验的官方页面将其列为 Unmaintained，结合官方时间线推定 2026 年 7 月 31 日亦处于该阶段。“固定采用”是教材的课程环境选择；Unmaintained 阶段不再产生正式发行且CI承诺降低；仍可按Unmaintained政策接受适当修复。生产环境应根据安全维护、发行版支持、驱动兼容和升级路径另行选型。

不推荐使用“Antelope 是长期支持版”“Antelope 仍是当前 Maintained 版本”“SLURP 等于 LTS”三类表述。官方维护政策明确：Maintained 阶段约 18 个月并产生正式发行；Unmaintained 阶段不再产生正式发行且CI承诺降低；仍可按Unmaintained政策接受适当修复；EOL 才是分支不再接受更改。[Stable Branches](https://docs.openstack.org/project-team-guide/stable-branches.html)

## 四、核心服务、常用扩展服务与基础依赖

官方文档并不存在一个永久不变、覆盖所有部署的“九大核心组件”口径。教材最好分别使用“最小部署服务”“本书实训服务”“常用扩展服务”和“基础依赖”四个概念。官方 2026.1 安装指南、Project Navigator 和 TC Base Services 文件分别服务于不同目的，不能混成一张无来源的“核心项目表”。[2026.1 安装指南](https://docs.openstack.org/2026.1/install/)；[Project Navigator](https://www.openstack.org/software/project-navigator/openstack-components)；[TC Base Services](https://governance.openstack.org/tc/reference/base-services.html)

### 表 3-C　教材建议的服务分层

| 层次 | 项目/服务 | 主要作用 | 口径依据 |
|---|---|---|---|
| 最小部署 | Keystone | 身份认证、授权及服务目录 | 官方最小安装顺序；TC 也列为 base service |
| 最小部署 | Glance | 镜像发现、登记、获取与存储 | 官方最小安装顺序；Nova 从镜像启动实例时依赖它 |
| 最小部署 | Placement | 记录资源提供者的库存与占用，向调度提供分配候选 | 官方最小安装顺序；Nova 基本功能依赖 |
| 最小部署 | Nova | 创建和管理计算实例，协调调度与计算节点 | 官方最小安装顺序 |
| 最小部署 | Neutron | 为实例提供虚拟/物理网络连接、端口和安全组等 | 官方最小安装顺序 |
| 建议安装 | Horizon | OpenStack 官方 Web 管理界面 | 官方建议在最小集合后安装 |
| 建议安装 | Cinder | 持久化块存储 | 官方建议在最小集合后安装；Nova 可选集成 |
| 常用扩展 | Swift、Manila | 对象存储、共享文件系统 | Project Navigator 的 Storage 类别 |
| 常用扩展 | Heat | 模板化编排复合云应用 | Project Navigator 的 Orchestration 类别 |
| 常用扩展 | Ceilometer、Aodh | 遥测数据采集与告警 | 2026.1 项目安装指南 |
| 常用扩展 | Octavia、Designate | 负载均衡与 DNS 服务 | Project Navigator 的 Networking 类别 |
| 常用扩展 | Barbican | 密钥和机密管理 | Project Navigator 的 Shared Services 类别 |
| 常用扩展 | Ironic、Cyborg | 裸机供给与加速器生命周期管理 | Project Navigator 的 Hardware Lifecycle 类别 |
| 常用扩展 | Magnum、Trove | 容器编排引擎供给、数据库即服务 | Project Navigator 的 Workload Provisioning 类别 |
| 外部/基础依赖 | SQL 数据库、消息队列、etcd、Castellan 兼容密钥库 | 服务数据、RPC/消息、分布式协调、机密存储 | TC Base Services；并非都属于面向用户的 OpenStack 云服务 |

Nova 官方 2026.1 文档明确指出，其基本运行需要 Keystone、Glance、Neutron 和 Placement；Nova 可进一步集成 Cinder 等服务。因此把 Nova 单独画成“全部 OpenStack”会丢失服务间依赖关系。[Nova 2026.1 概述](https://docs.openstack.org/nova/2026.1/)

## 五、逻辑架构的教材化表达

官方架构设计指南指出，终端用户可以通过 Dashboard、CLI 和 API 访问云服务；服务共同使用 Identity，服务之间主要通过公开 API 交互。该架构指南的组件图较旧，页面自身也提示它主要基于较早版本，因此教材应保留其稳定的交互原则，但按 2026.1 的服务目录重新绘图，不应原样复制旧图的项目清单。[OpenStack Logical Architecture](https://docs.openstack.org/arch-design/design.html)

建议按五层重新表达：

1. **访问层**：Horizon、OpenStackClient、SDK、REST API。
2. **身份与服务发现层**：Keystone 认证、授权、令牌及服务目录；服务目录使 API 客户端在认证后发现各服务端点。[Keystone Service Catalog](https://docs.openstack.org/keystone/latest/contributor/service-catalog.html)
3. **控制服务层**：Nova、Neutron、Glance、Placement、Cinder，以及按需增加的 Heat、Octavia、Barbican 等。
4. **公共支撑层**：SQL 数据库、消息队列、etcd、密钥存储等；Nova 内部通过 REST、RPC/消息队列和数据库协调 API、Scheduler、Conductor、Compute 等进程。[Nova System Architecture](https://docs.openstack.org/nova/latest/admin/architecture)
5. **资源层**：计算节点与虚拟机监控器、物理/虚拟网络、块存储后端、对象存储节点等。

控制面与资源面应分色显示：API、认证、调度、数据库和消息队列属于控制路径；计算节点上的实例、数据包转发和存储 I/O 属于资源/数据路径。官方最小示例架构至少需要控制节点和计算节点；块存储与对象存储可增加相应节点，且该示例明确是学习用最小概念验证，不是生产架构。[安装指南：Overview](https://docs.openstack.org/install-guide/overview.html)

## 六、一次实例创建的概念调用链

下列顺序适合教材画成时序图，但应标为“典型镜像启动流程（概念级）”。实际内部顺序会受 Cells、从卷启动、预创建端口、网络资源请求和部署驱动影响，不能把图中的每一步写成对所有部署都完全一致的事务顺序。

1. 用户在 Horizon、CLI 或 SDK 中选择规格、镜像、网络、安全组和密钥对，向 Nova Compute API 提交 Create Server 请求。Horizon 是官方 Web UI，OpenStackClient 是推荐的统一 CLI。[Nova 2026.1](https://docs.openstack.org/nova/2026.1/)；[Horizon 2026.1](https://docs.openstack.org/horizon/2026.1/)
2. 客户端先向 Keystone 认证并获得令牌与服务目录；Nova API 接收 REST 请求，执行认证、授权、参数和配额等检查。Keystone 服务目录可随令牌创建/验证响应返回，用于定位各服务端点。[Keystone Service Catalog](https://docs.openstack.org/keystone/latest/contributor/service-catalog.html)
3. Nova API/Conductor 建立实例构建请求并进入调度。Nova 的 API、Scheduler、Conductor、Compute 通过 HTTP 或 oslo.messaging/RPC 协同，Conductor承担构建/调整大小等协调和数据库代理职责。[Nova System Architecture](https://docs.openstack.org/nova/latest/admin/architecture)
4. Nova Scheduler 把资源需求发送给 Placement；Placement返回可满足需求的资源提供者与 allocation candidates，Scheduler再进行过滤、称重、主机选择并声明资源分配。[Nova Scheduling](https://docs.openstack.org/nova/latest/reference/scheduling.html)；[Placement Usage](https://docs.openstack.org/placement/latest/user/)
5. 对于自动创建的网络连接，Nova 与 Neutron 协同创建/绑定端口并应用安全组。安全组在 Neutron 中是端口属性；创建服务器并连接网络会形成端口。[Nova Security Groups](https://docs.openstack.org/nova/2026.1/user/security-groups.html)
6. 选定主机后，Nova Conductor 通过消息路径把构建任务交给目标 `nova-compute`；`nova-compute` 通过计算驱动控制 KVM/libvirt 等虚拟化后端。[Nova System Architecture](https://docs.openstack.org/nova/latest/admin/architecture)
7. 镜像启动时，计算节点从 Glance 获取镜像并在本地形成实例磁盘；Horizon 用户文档明确说明从镜像启动时会在实例所在计算节点创建镜像本地副本。[Horizon：Launch and manage instances](https://docs.openstack.org/horizon/2026.1/user/launch-instances.html)
8. 如果采用从卷启动或附加持久卷，Nova 再与 Cinder 协同完成卷创建/连接；这属于可选分支，不应画成所有镜像启动都必经的步骤。[Nova 2026.1](https://docs.openstack.org/nova/2026.1/)；[Horizon：Create and manage volumes](https://docs.openstack.org/horizon/2026.1/user/manage-volumes.html)
9. `nova-compute` 调用虚拟机监控器创建实例，Neutron 完成端口绑定与数据平面连接；Nova 更新实例状态，用户随后可经 API、Dashboard 或控制台查看结果。

## 七、OpenStack、openEuler 与“信创平台”的客观边界

### 可以写的事实

- OpenStack 是开放的云基础设施软件，提供计算、存储和网络资源的统一 API 管理；其模块化服务可由不同 Linux 发行版进行打包和集成。[OpenStack Software](https://www.openstack.org/software/)
- OpenStack 官方安装指南指出，由于发布节奏不同，各 Linux 发行版会自行发布或以其他方式提供 OpenStack 软件包。这说明“OpenStack 上游系列版本”和“发行版仓库软件包”是两个层次。[OpenStack packages for RHEL and CentOS](https://docs.openstack.org/install-guide/environment-packages-rdo.html)
- OpenStack 上游的 DevStack 当前文档将 openEuler 列入“尝试支持”的 Linux 系统之一，但同时指出 Ubuntu 是测试最充分、通常最顺利的选择。DevStack 是开发/测试环境工具，不能把其支持声明等同于生产级发行版认证。[DevStack Quick Start](https://docs.openstack.org/devstack/latest/)
- OpenStack 的 diskimage-builder 具有 `openeuler-minimal` 元素，可构建 openEuler 最小镜像；其测试说明还列出 openEuler 22.03 LTS 的构建测试。这可以作为 openEuler 与 OpenStack 上游工具生态存在技术衔接的证据。[openeuler-minimal](https://docs.openstack.org/diskimage-builder/latest/elements/openeuler-minimal/README.html)；[Tested Distributions](https://docs.openstack.org/diskimage-builder/latest/user_guide/supported_distros.html)

### 不能仅凭本次官方材料推出的结论

- 不能写“OpenStack 官方认证 openEuler 24.03 LTS SP3＋Antelope 为受支持组合”；本次限定的上游资料没有给出该生产支持矩阵。
- 不能写“OpenStack 本身就是信创产品”或“部署 OpenStack 即满足信创要求”；“信创”涉及具体政策、产品名录、供应链、密码合规和测评范围，OpenStack/OpenInfra 官方资料不提供此类中国合规认定。
- 不能把“openEuler 作为 DevStack 主机”“openEuler 作为云镜像来宾系统”“openEuler 仓库提供 OpenStack RPM”三个事实混成同一层面的兼容性结论。

推荐章稿表述：

> OpenStack 提供厂商中立的开源云控制框架，openEuler 提供 Linux 操作系统与下游软件包环境。二者结合可形成面向国产软硬件生态的私有云技术路线，但具体版本组合的兼容性、维护责任、安全更新和合规结论，应以 openEuler 仓库、集成验证记录及相关测评结果为准。本书采用的组合是经过课程环境验证的实训基线，不代表 OpenStack 上游发布了该组合的生产支持声明。

## 八、适合第三章的图表清单

以下清单严格同步已批准的第三章设计，共 9 幅图和 4 张表。图3.1—图3.7采用统一配色和中文术语重新绘制；图3.8—图3.9优先采集隔离教学环境中的真实 Horizon 界面并脱敏，平台不可达时才采用官方 Horizon 素材作为后备。按用户既定要求，图下不另设“注：……”说明；来源信息应进入正文引用或参考文献。

### 8.1 图片建议（批准设计：9 幅）

| 建议编号与标题 | 类型 | 画面要点 | 直接官方 URL |
|---|---|---|---|
| 图3.1 OpenStack发展与开放治理演变 | **重绘** | 2010 项目起源→2012 Foundation→2020 User Committee 并入 TC→2025 OpenInfra 成为 Linux Foundation directed fund | [项目历史](https://docs.openstack.org/project-team-guide/introduction.html)、[OpenInfra 加入 Linux Foundation](https://openinfra.org/blog/openinfra-joins-linux-foundation) |
| 图3.2 OpenStack社区治理与项目协作关系 | **重绘** | OpenInfra Governing Board、OpenStack TC、Project Teams、贡献者和用户之间的关系 | [Governance](https://governance.openstack.org/)、[Project Teams](https://governance.openstack.org/tc/reference/projects/)、[OpenInfra Charter](https://openinfra.org/legal/charter/) |
| 图3.3 OpenStack逻辑架构 | **重绘** | 访问层、控制层、资源层以及 API、Keystone、消息队列和数据库；控制面与资源面分色 | [Logical Architecture](https://docs.openstack.org/arch-design/design.html)、[Nova Architecture](https://docs.openstack.org/nova/latest/admin/architecture)、[TC Base Services](https://governance.openstack.org/tc/reference/base-services.html) |
| 图3.4 OpenStack核心服务与资源对象 | **重绘** | 展示教材核心服务及其管理对象：身份、镜像、资源库存、实例、网络、卷、对象与界面 | [Install Services](https://docs.openstack.org/install-guide/openstack-services.html)、[Project Navigator](https://www.openstack.org/software/project-navigator/openstack-components) |
| 图3.5 OpenStack版本发布与教材版本边界 | **重绘** | Antelope、Gazpacho、Hibiscus 与 SLURP 关系；状态注明“2026-08-15核验官方页面，并结合官方日程推定2026-07-31状态” | [Release 总览](https://releases.openstack.org/)、[SLURP 决议](https://governance.openstack.org/tc/resolutions/20220210-release-cadence-adjustment.html)、[Hibiscus 日程](https://releases.openstack.org/hibiscus/schedule.html) |
| 图3.6 OpenStack扩展项目生态 | **重绘** | 按编排、裸金属、存储、网络、安全、容器和监控分组 | [Project Navigator](https://www.openstack.org/software/project-navigator/openstack-components)、[2026.1 Install Guides](https://docs.openstack.org/2026.1/install/) |
| 图3.7 实例创建过程中的服务协作 | **重绘时序图** | Horizon/CLI→Keystone→Nova API/Conductor→Placement/Scheduler→Neutron/Glance→nova-compute；Cinder 为可选分支 | [Nova Scheduling](https://docs.openstack.org/nova/latest/reference/scheduling.html)、[Nova Architecture](https://docs.openstack.org/nova/latest/admin/architecture)、[Keystone Service Catalog](https://docs.openstack.org/keystone/latest/contributor/service-catalog.html) |
| 图3.8 Antelope教学云Horizon登录与项目概览 | **本地真实截图并脱敏；官方素材后备** | 展示登录入口和项目概览，不显示账号、令牌、Cookie、UUID及无关桌面区域 | [Horizon 2026.1](https://docs.openstack.org/horizon/2026.1/)、[Horizon 用户文档](https://docs.openstack.org/horizon/2026.1/user/) |
| 图3.9 Horizon资源页面与OpenStack服务关系 | **本地真实截图组合并脱敏；官方素材后备** | 以实例、镜像、网络、卷和项目页面对应 Nova、Glance、Neutron、Cinder、Keystone | [Horizon 实例管理](https://docs.openstack.org/horizon/2026.1/admin/manage-instances.html)、[Horizon 卷管理](https://docs.openstack.org/horizon/2026.1/user/manage-volumes.html) |

### 8.2 表格建议（批准设计：4 张）

| 建议编号与标题 | 核心字段 | 直接官方 URL |
|---|---|---|
| 表3-1 OpenStack核心服务及其主要资源对象 | 服务名、项目名、主要资源对象、最小部署/教材范围 | [Project Navigator](https://www.openstack.org/software/project-navigator/openstack-components)、[Install Services](https://docs.openstack.org/install-guide/openstack-services.html) |
| 表3-2 Antelope、Gazpacho与Hibiscus版本状态比较 | 发布日期、SLURP、2026-08-15 页面状态、推定的 2026-07-31 状态、教材定位 | [OpenStack Releases](https://releases.openstack.org/)、[Gazpacho](https://releases.openstack.org/gazpacho/index.html)、[Antelope](https://releases.openstack.org/antelope/index.html)、[Hibiscus Schedule](https://releases.openstack.org/hibiscus/schedule.html) |
| 表3-3 OpenStack常用扩展项目及典型应用场景 | 项目名、服务类别、典型场景、是否按需部署 | [Project Navigator](https://www.openstack.org/software/project-navigator/openstack-components)、[2026.1 Install Guides](https://docs.openstack.org/2026.1/install/) |
| 表3-4 Horizon、命令行、REST API和SDK访问方式比较 | 入口、使用对象、适用任务、自动化能力 | [OpenStack Software](https://www.openstack.org/software/)、[Nova 2026.1](https://docs.openstack.org/nova/2026.1/)、[Horizon 2026.1](https://docs.openstack.org/horizon/2026.1/) |

## 九、写作核查清单

- 先写明状态证据口径：“2026-08-15核验官方页面，并结合官方日程推定2026-07-31状态”；再写“截至 2026-07-31，最新已发布的 Maintained 版本为 2026.1 Gazpacho”。不要把 8 月 15 日页面假称为 7 月 31 日归档快照，也不要写“当前最新版本为 Hibiscus”。
- 写“Hibiscus 正在开发，计划 2026-09-30 发布”；不要提前写其最终版本号、完整特性或稳定承诺。
- 写“SLURP 支持相邻 SLURP 之间的跨一级升级流程”；不要写“SLURP=LTS”或“可跳过任意多个版本”。
- 写“Antelope 是冻结的课程实训版本；Unmaintained 阶段不再产生正式发行且CI承诺降低；仍可按Unmaintained政策接受适当修复”；不要把它写成当前 Maintained 版本。
- 把 Keystone、Glance、Placement、Nova、Neutron称为“官方最小部署所需服务”；Horizon、Cinder称为“官方建议追加服务”。
- 逻辑架构图按当前项目目录重绘；旧 Architecture Design Guide 只用于稳定的交互原则，不原样复制旧项目清单。
- 实例创建图标明“概念级典型流程”，Cinder 使用虚线可选分支，避免暗示所有实例都从卷启动。
- openEuler 只写“部分上游工具存在适配/构建支持”和“下游集成验证”；不从技术适配直接推导政策合规或生产认证。
- 上游组件版本与本书 RPM/离线源版本分栏呈现，禁止用协调版本首发号替换实训仓库中的点版本号。

## 十、核心官方入口

- [OpenStack Releases](https://releases.openstack.org/)
- [OpenStack 2026.1 Gazpacho](https://releases.openstack.org/gazpacho/index.html)
- [OpenStack 2026.2 Hibiscus Schedule](https://releases.openstack.org/hibiscus/schedule.html)
- [OpenStack 2023.1 Antelope](https://releases.openstack.org/antelope/index.html)
- [OpenStack Governance](https://governance.openstack.org/)
- [OpenStack Project Teams](https://governance.openstack.org/tc/reference/projects/)
- [OpenStack Project Team Guide：Introduction](https://docs.openstack.org/project-team-guide/introduction.html)
- [OpenStack Project Team Guide：Stable Branches](https://docs.openstack.org/project-team-guide/stable-branches.html)
- [OpenStack Project Navigator](https://www.openstack.org/software/project-navigator/openstack-components)
- [OpenStack 2026.1 Documentation](https://docs.openstack.org/2026.1/)
