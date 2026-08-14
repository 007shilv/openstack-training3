# 第三版第一部分官方研究收口记录（冻结至 2026-07-31）

> 用途：为第 1、3 章的改写提供**可写入**与**不得写入**的边界。本记录不是可直接排入教材的正文，也不替代出版前的滚动复核。
>
> 冻结日：2026-07-31；统一访问日：2026-08-12。除明确标为“冻结日快照”的状态外，动态网页不得以访问日的“当前”状态反推冻结日状态。

## 1. 冻结边界

| 边界 | 可采用的口径 | 处理规则 | 依据（直接 URL；标题；发布日期/页码；访问日；置信度） |
|---|---|---|---|
| 时间 | 只写截至 2026-07-31 已发生或已公开排期的事实。 | 2026-08-01 及以后发布、修订、状态变更不进入正文。 | [OpenStack Releases](https://releases.openstack.org/)；页面标题同名；动态页、无单一发布日期；访问 2026-08-12；高 |
| OpenStack 当前线 | 冻结日 Gazpacho（2026.1）为 Maintained 且为 SLURP；Hibiscus（2026.2）仍为 Development，计划 2026-09-30 发布。 | 只能写“截至冻结日”；不得写成 Hibiscus 已发布或“当前最新正式版”。 | [OpenStack Releases](https://releases.openstack.org/)；页面标题同名；动态页（冻结日状态已核定）；访问 2026-08-12；高 |
| 实训线 | Antelope（2023.1）为 SLURP，但冻结日已 Unmaintained；仅保留为固定、隔离的教学环境。 | 不可作为新建生产云推荐版本；须同屏提示其维护状态。 | [2023.1 Antelope](https://releases.openstack.org/antelope/index.html)；页面标题同名；初始发布 2023-03-22；访问 2026-08-12；高 |
| 市场统计 | 仅将 CAICT《云计算蓝皮书（2025年）》中的 2024 年实绩作为市场规模事实。 | 2025E 10857 亿元是预测值，不能写为实际发生额或与 2024 年实绩混用。 | [《云计算蓝皮书（2025年）》PDF](https://www.caict.ac.cn/kxyj/qwfb/bps/202507/P020250722583603558109.pdf)；中国信息通信研究院；2025-07；印刷页 16–17 / PDF 页 22–23；访问 2026-08-12；高 |

## 2. 可写 Claim 表

### 2.1 云计算趋势（限六类）

| 类别 | 可写 Claim（须保留限定语） | 依据（直接 URL；标题；发布日期/页码；访问日；置信度） |
|---|---|---|
| 云原生 | 云原生是一组用于在公有云、私有云和混合云等动态环境中构建、运行可扩展应用的技术与方法；可作为现代应用工程方法讲解。 | [Cloud Native Definition](https://github.com/cncf/toc/blob/main/DEFINITION.md)；CNCF TOC；页面无单一发布日期；访问 2026-08-12；高 |
| AI 云/一云多算 | 可写云平台把通用、智能和高性能算力资源池融合，并通过统一调度、管理、运维和运营提供服务；不要将其简化为“GPU 上云”。 | [《云计算蓝皮书（2025年）》PDF](https://www.caict.ac.cn/kxyj/qwfb/bps/202507/P020250722583603558109.pdf)；中国信息通信研究院；2025-07，印刷页 12–13 / PDF 页 18–19；访问 2026-08-12；高 |
| 云—边—端协同 | 可写计算资源的部署从中心云延伸到边缘和终端，重点说明低时延、数据就近处理与协同调度；不赋予未核验的性能数字。 | [《云计算蓝皮书（2025年）》PDF](https://www.caict.ac.cn/kxyj/qwfb/bps/202507/P020250722583603558109.pdf)；中国信息通信研究院；2025-07，报告相关章节；访问 2026-08-12；中 |
| 混合云/多云 | 可写跨环境应用管理是混合云、多云的教学场景；应讲身份、策略、交付、可观测性与成本治理，而不写“所有企业均采用多云”。 | [Hybrid Cloud with AWS — AWS hybrid cloud solutions](https://docs.aws.amazon.com/whitepapers/latest/hybrid-cloud-with-aws/aws-hybrid-cloud-solutions.html)；AWS；页面无单一发布日期；访问 2026-08-12；高；[Hybrid and multicloud application platform](https://cloud.google.com/solutions/hybrid-and-multicloud-application-platform)；Google Cloud；页面无单一发布日期；访问 2026-08-12；高 |
| FinOps | 可将 FinOps 写为跨职能的云成本与业务价值管理实践，作为资源使用、预算和治理的教学视角；不得把它写成某一厂商产品或强制标准。 | [What is FinOps?](https://www.finops.org/introduction/what-is-finops/)；FinOps Foundation；页面无单一发布日期；访问 2026-08-12；高 |
| 主权/可信/绿色云 | 可将数据主权、合规、安全与环境影响写为云治理的并列约束；主权云是治理框架，不等同于单一产品标签。绿色云不写节能比例或碳减排结论。 | [Sovereign Cloud Framework Explained](https://commission.europa.eu/news-and-media/news/sovereign-cloud-framework-explained-2026-06-01_en)；欧盟委员会；2026-06-01；访问 2026-08-12；高 |

### 2.2 代表厂商定位（只作产品路线示例，不作排名或市场份额结论）

| 厂商/产品路线 | 可写定位 | 依据（直接 URL；标题；发布日期/页码；访问日；置信度） |
|---|---|---|
| AWS / Outposts | AWS 以 Outposts 将部分 AWS 基础设施、服务、工具和 API 延伸到本地部署场景；可用于说明公有云与本地设施协同。 | [AWS Outposts](https://aws.amazon.com/outposts/)；AWS；页面无单一发布日期；访问 2026-08-12；高 |
| Microsoft Azure / Azure Arc | Azure Arc 面向跨本地、边缘与多云资源的管理；可用于说明混合、多云管理路线。 | [Azure Arc](https://azure.microsoft.com/products/azure-arc/)；Microsoft；页面无单一发布日期；访问 2026-08-12；高 |
| Google Cloud / GKE Enterprise | GKE Enterprise 以 Kubernetes 为基础覆盖 Google Cloud、本地及其他云；可用于说明应用平台一致性。 | [Hybrid and multicloud application platform](https://cloud.google.com/solutions/hybrid-and-multicloud-application-platform)；Google Cloud；页面无单一发布日期；访问 2026-08-12；高 |
| 阿里云 / 飞天企业版 Apsara Stack | Apsara Stack 面向企业本地部署的云平台场景；可用于说明公有云技术向专有/本地环境延伸。 | [Apsara Stack](https://www.alibabacloud.com/product/apsarastack)；Alibaba Cloud；页面无单一发布日期；访问 2026-08-12；中 |
| 华为云 / 华为云 Stack | Huawei Cloud Stack 面向混合云部署与统一管理场景；可用于说明政企云的部署路线。 | [Huawei Cloud Stack](https://www.huaweicloud.com/intl/en-us/product/hcs.html)；Huawei Cloud；页面无单一发布日期；访问 2026-08-12；中 |

### 2.2.1 第二章产品架构补充边界（冻结至 2026-07-31）

| 产品路线 | 可写的稳定架构边界 | 不得扩写的动态结论 | 依据（官方直接 URL；访问日；置信度） |
|---|---|---|---|
| VMware Cloud Foundation | 以 vSphere/ESXi 组织计算，以 vSAN 组织软件定义存储，以 NSX 组织软件定义网络，并把运营、自动化与生命周期管理纳入一体化私有云平台。 | 不写动态许可证、套餐、性能数字或“最佳私有云”结论；不把虚拟化本身等同完整云服务。 | [VMware Cloud Foundation](https://www.vmware.com/products/cloud-infrastructure/vmware-cloud-foundation)；VMware/Broadcom 官方产品页；访问 2026-08-14；高。 |
| Citrix DaaS | Citrix 管理控制平面；客户资源位置中部署 Cloud Connector 与 VDA；用户通过 Citrix Workspace 或 Gateway 访问应用和桌面，会话体验由 HDX 技术承载。 | 不写并发量、时延、版本矩阵和计费；不把 DaaS 写成通用 IaaS，也不写未经核定的安全效果。 | [Citrix DaaS overview](https://docs.citrix.com/en-us/citrix-daas/overview)；[Reference architectures](https://docs.citrix.com/en-us/tech-zone/design/reference-architectures/virtual-apps-and-desktops-service)；Citrix 官方文档；访问 2026-08-14；高。 |
| Hyper-V / Azure Local / Azure Arc | Hyper-V 由虚拟化程序、父分区、子分区与 VMBus 组成；Azure Local 建立在 Hyper-V、故障转移群集和 Storage Spaces Direct 等 Windows Server 技术之上，并通过 Azure Arc 接入 Azure 管理与治理。 | 不写节点上限、硬件清单、订阅价格或发布后新增能力；不把 Azure Arc 写成替代本地资源层。 | [Hyper-V architecture](https://learn.microsoft.com/en-us/windows-server/virtualization/hyper-v/architecture)；[Azure Local architecture](https://learn.microsoft.com/en-us/azure/azure-local/concepts/architecture)；Microsoft Learn；访问 2026-08-14；高。 |
| 国内私有云路线 | 可用华为云Stack、Apsara Stack、EasyStack、ZStack说明一体化政企云、企业专有云、OpenStack企业云和轻量化/超融合云平台等不同路线；比较到稳定技术定位为止。 | 不作排名、份额、性能和国产化比例结论；不将厂商“兼容清单”直接写成已验证的整栈能力。 | 各厂商官方产品页；截至冻结日定点核对；访问 2026-08-14；中。 |
| 国内外公有云 | 可用 AWS、Microsoft Azure、Google Cloud、阿里云、华为云和腾讯云说明区域、可用区、资源池、服务目录、身份权限、计量和运营治理等稳定共性。 | 不写区域/可用区实时数量、详细价格、产品总数、排名或市场份额；具体可用性应在使用时查官方资料。 | 各公有云官方“Regions and Availability Zones/地域和可用区”文档；访问 2026-08-14；高。 |

**第二章写作规则：**厂商只作为技术路线案例，先讲架构层次和责任边界，再讲代表产品；正文不复刻控制台，不罗列全部服务，不根据产品页面推导普遍效果。图2.1—图2.7全部采用中立重绘，图中字体不小于9磅，正文在图前引用、图后解释元素与关系。

### 2.3 OpenStack 治理、项目与发布

| 主题 | 可写 Claim | 依据（直接 URL；标题；发布日期/页码；访问日；置信度） |
|---|---|---|
| 治理原则 | OpenStack 遵循“开放源代码、开放设计、开放开发、开放社区”的“四个开放”；技术委员会负责跨项目技术治理。 | [The Four Opens](https://governance.openstack.org/tc/reference/opens.html)；OpenStack Technical Committee；页面无单一发布日期；访问 2026-08-12；高；[OpenStack Technical Committee](https://governance.openstack.org/tc/)；页面无单一发布日期；访问 2026-08-12；高 |
| 项目定位 | OpenStack 是把数据中心的计算、存储、网络资源组织为可通过 API、命令行和 Web 界面自助使用的云操作系统；“云操作系统”是功能类比，不等同于 Linux。 | [OpenStack 2026.1 Documentation](https://docs.openstack.org/2026.1/)；OpenStack；2026.1 文档集；访问 2026-08-12；高 |
| 核心项目 | 基础教学可围绕 Keystone、Glance、Placement、Nova、Neutron、Cinder、Horizon 与 Swift 的职责和协同展开；安装顺序不应被误写成唯一架构。 | [Install OpenStack services](https://docs.openstack.org/install-guide/openstack-services.html)；OpenStack Installation Guide；页面无单一发布日期；访问 2026-08-12；高 |
| 发布节奏 | OpenStack 围绕约六个月周期发布；SLURP 除相邻主版本升级外，还提供 SLURP 版本间的跳级升级路径。 | [OpenStack Releases](https://releases.openstack.org/)；OpenStack Release Team；动态页、无单一发布日期；访问 2026-08-12；高 |
| Gazpacho | 2026.1 Gazpacho 于 2026-04-01 协调发布；冻结日状态为 Maintained，且标记为 SLURP。概论可据此介绍当前社区基线。 | [2026.1 Gazpacho Release Schedule](https://releases.openstack.org/gazpacho/schedule.html)；OpenStack Release Team；日程覆盖 2025-10-02 至 2026-04-01；访问 2026-08-12；高；[OpenStack Releases](https://releases.openstack.org/)；冻结日状态快照已核定；访问 2026-08-12；高 |
| Hibiscus | 2026.2 Hibiscus 在冻结日仍为 Development，排期的协调发布日为 2026-09-30；只能写“计划”，不写成功能或已发布版本。 | [2026.2 Hibiscus Release Schedule](https://releases.openstack.org/hibiscus/schedule.html)；OpenStack Release Team；日程覆盖 2026-04-02 至 2026-09-30；访问 2026-08-12；高 |
| Antelope | 2023.1 Antelope 于 2023-03-22 初始发布，为 SLURP；冻结日为 Unmaintained。教材可固定其作隔离实训版本，但不得推荐生产部署。 | [2023.1 Antelope](https://releases.openstack.org/antelope/index.html)；OpenStack Release Team；初始发布 2023-03-22；访问 2026-08-12；高；[OpenStack Releases](https://releases.openstack.org/)；冻结日状态快照已核定；访问 2026-08-12；高 |

## 3. 版本时间线（教材可直接转绘）

| 日期/时期 | 版本与状态 | 教材写法 |
|---|---|---|
| 2023-03-22 | 2023.1 Antelope 初始发布；SLURP；冻结日 Unmaintained。 | “固定实训版本（隔离教学环境）”，紧随“不用于新建生产云”。依据：[2023.1 Antelope](https://releases.openstack.org/antelope/index.html)；标题同名；初始发布 2023-03-22；访问 2026-08-12；高。 |
| 2026-04-01 | 2026.1 Gazpacho 协调发布；SLURP；冻结日 Maintained。 | “截至冻结日的概论基线”。依据：[2026.1 Gazpacho Release Schedule](https://releases.openstack.org/gazpacho/schedule.html)；标题同名；发布 2026-04-01；访问 2026-08-12；高。 |
| 2026-07-31（冻结日） | 2026.2 Hibiscus 正在 Development 阶段。 | “开发中、不可写为已发布”。依据：[OpenStack Releases](https://releases.openstack.org/)；页面标题同名；冻结日状态已核定；访问 2026-08-12；高。 |
| 2026-09-30（冻结日后的计划） | Hibiscus 协调发布计划日。 | 仅可作为“计划于 2026-09-30 发布”，不能写成既成事实。依据：[2026.2 Hibiscus Release Schedule](https://releases.openstack.org/hibiscus/schedule.html)；标题同名；计划发布 2026-09-30；访问 2026-08-12；高。 |

## 4. CAICT 准确数据（2024 年实绩）

| 指标 | 准确表述 | 来源定位与质量 |
|---|---|---|
| 云计算市场总规模 | 2024 年我国云计算市场规模为 **8,288 亿元**，同比增长 **34.4%**。 | [《云计算蓝皮书（2025年）》PDF](https://www.caict.ac.cn/kxyj/qwfb/bps/202507/P020250722583603558109.pdf)；中国信息通信研究院；2025-07；**印刷页 16 / PDF 页 22**；访问 2026-08-12；高。 |
| 公有云 | 2024 年公有云市场规模为 **6,216 亿元**，同比增长 **36.6%**。 | 同上；印刷页 16 / PDF 页 22；访问 2026-08-12；高。 |
| 私有云 | 2024 年私有云市场规模为 **2,072 亿元**，同比增长 **29.3%**。 | 同上；印刷页 16 / PDF 页 22；访问 2026-08-12；高。 |
| 公有云 IaaS | 2024 年公有云 IaaS 市场规模为 **4,201 亿元**。 | 同上；**印刷页 17 / PDF 页 23**；访问 2026-08-12；高。 |
| SaaS | 2024 年 SaaS 市场增速为 **23.1%**，市场规模为 **682 亿元**。 | 同上；印刷页 17 / PDF 页 23；访问 2026-08-12；高。 |
| PaaS | 2024 年 PaaS 市场规模**突破 1,000 亿元**。 | 同上；印刷页 17 / PDF 页 23；访问 2026-08-12；高。 |

**禁止误用：**“2025E 10,857 亿元”是该报告给出的预测，不是 2025 年实绩；在本次冻结稿中不作为市场实际数据使用。依据同上；报告预测项；访问 2026-08-12；高。

## 5. 现有底稿必须更正或删除的内容

| 位置/问题 | 必须处理 | 正确替换或删除规则 |
|---|---|---|
| `01-industry-openstack-openeuler-update.md` 第 35 行 CAICT 页码“第 21—22 页” | **更正**。 | 改为：总规模、公有云、私有云数据见**印刷页 16 / PDF 页 22**；IaaS、SaaS、PaaS 数据见**印刷页 17 / PDF 页 23**。不得笼统合并为“第 21—22 页”。 |
| 同行“智能算力服务成为主要增量”“SaaS 增长受企业级智能应用和智能体推动” | **删除或另找逐字可核官方证据**。 | 本收口记录只确认第 16–17 印刷页的市场规模、增速与分类数据；不得由这些数值自行推出增长原因。 |
| 同行将 2024 数据与未来规模混写的风险 | **删除 2025E 作为实际值的写法**。 | 2025E 10,857 亿元仅能在明确标注“预测”时出现；本书本次不采用。 |
| 第 165 行“截至冻结日的最新受支持版本/当前受支持版本” | **改写为时间快照**。 | 写为“截至 2026-07-31，Gazpacho 为 Maintained 的 SLURP 版本；Hibiscus 仍在开发中”。不要用访问日的“当前”替代冻结日。 |
| 第 165 行及其后任何 Hibiscus 描述 | **限制**。 | 仅保留“计划于 2026-09-30 协调发布”；删除已发布、成熟度、功能亮点、项目版本等断言。 |
| 第 199–201 行 Antelope 的教学定位 | **补强警示**。 | 与“2023-03-22 发布、SLURP、冻结日 Unmaintained”并列；明确仅限隔离教学环境，不作生产建议。 |
| 第 116 行“5,500 万计算核心、500 名贡献者、100 个组织、9,000 项变更” | **删除，除非逐项回到所引官方文章并定位复核**。 | 该数字不属于本次收口所需的最低事实集；不以概括性宣传数字支撑教材技术判断。 |
| 第 69 行的 AWS/Google 例子 | **保留为“路线示例”并降调**。 | 不写厂商优劣、市场份额或能力全覆盖；只说明各自官方页面明确的混合/多云产品定位。 |

## 6. 不可写事项

1. 不写 2026-07-31 后发生的版本发布、项目状态、政策、统计修订或产品功能。
2. 不把 Hibiscus 的计划发布日、日程节点或开发分支写成已发布功能、稳定能力或“最新正式版”。
3. 不把 Antelope 写成仍受维护版本，不把教学软件栈或 SP2 仓 + SP3 系统组合写成社区官方生产支持承诺。
4. 不把 CAICT 的 2025E 10,857 亿元写成实际市场规模；不杜撰市场份额、厂商排名、增速原因或国际可比结论。
5. 不以厂商产品页推导“所有企业”的实践普及率，也不将营销页列出的服务清单改写成不带条件的性能、安全或合规承诺。
6. 不将实验步骤、命令、密钥、账号、内部地址、未脱敏截图或未经验证的本地结果并入本研究记录。

## 7. Agent Reach 不可用时的降级说明

本次按要求先尝试 `agent-reach doctor --json`，但该命令在工作环境中未安装或未加入 PATH，无法调用。为不扩大检索范围，随即停止 Agent Reach 路径，仅使用：

- 仓库既有的官方来源登记表与现有底稿中的直接官方 URL；
- OpenStack Release Team 的 Gazpacho、Hibiscus、Antelope 及 Releases 官方页面进行定点复核；
- CAICT 已登记的官方 PDF 及其已核定的印刷页/PDF 页码。

因此，本文件没有使用第三方媒体、搜索摘要、厂商排名页面或社交媒体信息。该降级不降低上述“高”置信度条目的来源级别；但对未能在本次定点浏览中逐页重验的厂商定位，已标为“中”并限定为产品路线示例。
