# 云计算产业、OpenStack与openEuler更新稿

> **资料冻结声明**　本稿反映截至 **2026年7月31日** 已经发生并可由官方资料确认的事实。网页访问与复核日期为 **2026年8月12日**。冻结日以后发生的版本发布、政策变化和统计修订不纳入正文。动态网页中的“最新”“当前”等表述，均按冻结日重新核定。本稿可拆分进入第三版教材第1章、第3章和第4章；正文中的图表号为建议号，合入总书稿时按所在章独立连续编号。

## 一、云计算：从资源服务走向智能算力底座

### （一）经典定义没有失效，技术边界已经扩展

美国国家标准与技术研究院（NIST）在SP 800-145中将云计算定义为：通过网络，以便捷、按需的方式访问可配置计算资源共享池，并能够以较少的管理工作或服务商交互快速获取和释放资源。该定义归纳了五项基本特征——按需自助服务、广泛网络访问、资源池化、快速弹性和可计量服务；三类服务模型——IaaS、PaaS和SaaS；四类部署模型——私有云、社区云、公有云和混合云。到2026年，这一框架仍然是识别“什么是云”的基础，但它不再足以完整描述云计算产业的全部形态。[来源：NIST SP 800-145](https://csrc.nist.gov/pubs/sp/800/145/final)

理解今天的云计算，需要把“资源服务”与“技术融合”同时纳入视野：

1. **资源对象从CPU、内存和磁盘扩展为多元异构算力。** 云平台既管理通用CPU，也管理GPU、NPU、DPU、FPGA、高性能网络和分层存储，并按训练、推理、高性能计算和通用业务的差异进行组合与调度。
2. **交付对象从虚拟机扩展为应用全生命周期。** 除虚拟机外，容器、Kubernetes、函数、模型服务、数据服务、智能体和行业应用都可以成为云服务的交付对象。
3. **部署空间从中心数据中心扩展为“云—边—端”连续体。** 核心云承担集中管理和大规模处理，边缘节点承接低时延、数据就近和断网自治场景，终端产生数据并执行部分实时任务。
4. **运营目标从“能用”扩展为安全、稳定、成本、性能和绿色的综合最优。** AIOps、FinOps、可观测性、软件供应链安全、可信计算和算电协同逐步进入云平台的日常治理体系。

因此，云计算不能简单等同于虚拟化。虚拟化是资源抽象的重要技术，但只有当系统同时具备按需、自助、池化、弹性和计量等服务能力时，才能形成完整的云服务。云原生也不等同于“只在公有云上运行”，它强调的是适合动态环境的架构与工程方法。

### （二）2021—2026年云计算认知的主要变化

| 观察维度 | 2021年前后教材常见表述 | 截至2026年7月应采用的表述 |
|---|---|---|
| 产业角色 | 为企业信息系统提供低成本、弹性资源 | 数字基础设施与智能基础设施的共同底座，连接算力、网络、数据、模型和应用 |
| 核心资源 | 以CPU虚拟机、云硬盘和虚拟网络为主 | 通用算力、智能算力和高性能算力协同，GPU/NPU/DPU等异构资源进入统一管理 |
| 应用形态 | 虚拟机、传统Web应用、数据库 | 虚拟机与容器并存，叠加大模型训练推理、智能体、数据智能和行业云应用 |
| 技术主线 | 虚拟化、分布式存储、软件定义网络 | 云原生、平台工程、GitOps、可观测性、AI云、算力互联网、机密计算和软件供应链安全 |
| 部署形态 | 公有云、私有云、混合云分类 | 混合多云常态化，中心云、边缘云、行业云和本地基础设施协同 |
| 运维方式 | 自动化脚本、监控告警、人工处置 | 声明式交付、全链路可观测、AIOps辅助诊断、FinOps成本治理与智能体协同运维 |
| 安全重点 | 边界防护、账号权限、数据加密 | 身份成为新边界，强调零信任、工作负载身份、供应链溯源、运行时安全、数据主权和在用数据保护 |
| 产业要求 | 上云、用云和规模增长 | 用云成效、智能化转型、可信合规、自主可控、开放生态和绿色低碳并重 |

### （三）我国云计算市场进入“云智融合”阶段

中国信息通信研究院《云计算蓝皮书（2025年）》统计，2024年我国云计算市场规模达到 **8288亿元**，比2023年增长34.4%；其中公有云6216亿元、私有云2072亿元。公有云IaaS市场规模为4201亿元，智能算力服务成为主要增量；SaaS增长则受到企业级智能应用和智能体发展的推动。这些数据表明，云计算的增长动力已经由一般资源上云，进一步转向智能算力供给、AI开发平台和智能应用落地。[来源：中国信通院《云计算蓝皮书（2025年）》第21—22页](https://www.caict.ac.cn/kxyj/qwfb/bps/202507/P020250722583603558109.pdf)

需要注意，市场规模不能单独代表云计算发展质量。对一个地区、行业或企业来说，更有价值的评价维度还包括资源利用率、业务连续性、服务时延、数据治理、研发效率、单位业务成本、单位计算能耗和安全合规水平。教学中应引导学生从“采购了多少云资源”转向“云平台是否持续创造业务价值”。

### （四）云原生成为现代应用的通用工程方法

CNCF将云原生概括为：在公有云、私有云和混合云等现代动态环境中构建和运行可扩展应用的一组技术与方法，容器、服务网格、微服务、不可变基础设施和声明式API是其典型实践；这些方法配合自动化，使松耦合系统更具韧性、可管理性和可观测性。[来源：CNCF云原生定义](https://github.com/cncf/toc/blob/main/DEFINITION.md)

2025年度CNCF云原生调查显示，在受访组织中，98%已经采用云原生技术；在容器用户中，82%已在生产环境运行Kubernetes；在托管生成式AI模型的组织中，66%使用Kubernetes管理部分或全部推理工作负载。该调查是行业样本调查，不能机械外推为所有组织的普及率，但足以说明云原生已从“新兴技术选项”转变为现代基础设施的重要通用层。[来源：CNCF 2025年度云原生调查发布说明](https://www.cncf.io/announcements/2026/01/20/kubernetes-established-as-the-de-facto-operating-system-for-ai-as-production-use-hits-82-in-2025-cncf-annual-cloud-native-survey/)

云原生阶段的关键变化包括：

- **容器编排平台化。** Kubernetes不再只是调度容器，还承载策略、网络、存储、弹性、设备插件和AI工作负载管理。
- **交付方式声明化。** 基础设施即代码、配置即代码和GitOps使期望状态可版本化、可审查、可回滚。
- **平台工程兴起。** 组织通过内部开发者平台封装基础设施复杂度，以标准化模板、服务目录和自助接口提高交付效率。
- **可观测性统一。** 指标、日志、链路、事件和性能剖析逐步关联，运维从“看到告警”走向“理解业务影响”。
- **虚拟机与容器协同。** 大量核心系统仍运行在虚拟机中，新应用更多采用容器；二者并不是替代关系，而是由统一云基础设施承载的不同工作负载形态。

### （五）AI云与智算：云平台成为模型生产系统

人工智能使云平台的资源、网络、存储和运维方式发生系统性变化。中国信通院将“一云多算”概括为：以云的弹性和服务化能力，把通用算力、智能算力和高性能算力等资源池进行融合，提供统一调度、管理、运维和运营能力。[来源：中国信通院《云计算蓝皮书（2025年）》第12—13页](https://www.caict.ac.cn/kxyj/qwfb/bps/202507/P020250722583603558109.pdf)

AI云可以按以下三层理解：

1. **AI基础设施即服务（AIIaaS）。** 提供GPU/NPU等加速资源、高性能互联、并行文件系统、对象存储、裸金属和虚拟化隔离，解决算力供给、资源切分和集群调度问题。
2. **AI平台即服务（AIPaaS）。** 提供数据处理、模型开发、分布式训练、微调、评测、模型仓库、推理部署和监控能力，降低模型工程门槛。中国信通院指出，AIPaaS通过异构智能算力调度，为模型开发、训练、部署和推理提供云化服务。[来源：中国信通院《云计算蓝皮书（2025年）》第34—36页](https://www.caict.ac.cn/kxyj/qwfb/bps/202507/P020250722583603558109.pdf)
3. **AI应用与智能体服务。** 行业模型、知识库、智能体和业务系统在上层组合，通过API调用底层模型与工具。此时，云平台还要管理提示词、知识、模型版本、工具权限、调用成本和安全审计。

智算并不是“把GPU装进服务器”这么简单。训练与推理对网络带宽、存储吞吐、拓扑感知调度、故障恢复和能耗管理提出了更高要求。云平台需要把计算、网络、存储、数据和模型作为一个整体优化。OpenStack中的Nova、Placement、Neutron、Cinder、Ironic和Cyborg等组件，正可从不同层面支撑虚拟机、裸金属和加速设备资源的管理。

### （六）混合多云、边缘云与算力互联网

混合云解决本地基础设施与公有云协同问题，多云强调使用多个云服务提供方，边缘云则把计算能力下沉到接近数据源和用户的位置。三者在实际系统中常常同时出现。NIST专门设立多云安全公共工作组，指出现代多云系统连接多个云服务商及第三方实体，会增加安全与隐私实施的复杂度。[来源：NIST多云安全公共工作组章程](https://csrc.nist.gov/projects/mcspwg/mcspw-charter)

主要云厂商也以不同方式把云能力延伸到本地或其他云环境。例如，AWS Outposts把AWS基础设施、API和运维模式延伸到客户本地设施；Google Anthos以Kubernetes为基础，为本地、Google Cloud和其他云上的应用提供较一致的管理方式。这些产品路径共同说明，企业需要的不只是“使用多个云”，而是跨环境的身份、策略、可观测性、交付和成本治理。[来源：AWS Outposts官方文档](https://docs.aws.amazon.com/whitepapers/latest/hybrid-cloud-with-aws/aws-hybrid-cloud-solutions.html)；[Google Cloud Anthos官方说明](https://cloud.google.com/solutions/hybrid-and-multicloud-application-platform)

我国政策进一步把云的互联扩展为算力互联。工业和信息化部《算力互联互通行动计划》提出，实现不同主体、不同架构公共算力资源的标准化互联，并面向大模型训练与推理、科学计算等场景发展灵活的算力调度和服务模式。[来源：工业和信息化部《算力互联互通行动计划》](https://fjca.miit.gov.cn/zwgk/zcwj/wjfb/art/2025/art_25eea57dd6f840e680184fffb086883d.html)

对学习者而言，应把“多云”理解为治理问题，而不是简单的资源数量问题。一个成熟的混合多云体系至少需要解决：统一身份与最小权限、网络互联与隔离、数据位置与迁移、配置一致性、服务可观测、故障切换、成本归集以及供应商退出路径。

### （七）主权云、可信云与安全体系

随着数据成为关键生产要素，云平台的评价维度从传统机密性、完整性、可用性扩展到数据位置、司法管辖、技术自主、供应链透明、运营控制和可迁移性。欧盟委员会在2026年发布的云主权框架中，将主权目标分为战略、法律与司法管辖、数据与AI、运营、供应链、技术、安全与合规、环境可持续八类。主权云因而不是一个单一产品名称，而是一组可评估、可审计的控制要求。[来源：欧盟委员会云主权框架说明](https://commission.europa.eu/news-and-media/news/sovereign-cloud-framework-explained-2026-06-01_en)

云原生环境的安全边界也在变化。CNCF安全资料把零信任、DevSecOps和安全软件供应链列为重要目标，强调源代码、依赖、构建流水线、制品和部署全过程的身份验证、完整性校验、签名、SBOM与持续扫描。[来源：CNCF云原生安全白皮书v2](https://tag-security.cncf.io/community/resources/security-whitepaper/v2/cloud-native-security-whitepaper/) 到2026年，身份进一步成为动态、短生命周期工作负载的关键安全边界。[来源：CNCF云原生IAM白皮书说明](https://www.cncf.io/blog/2026/06/04/identity-and-access-management-whitepaper/)

教材中应把云安全组织为五个相互衔接的层次：

- **身份与权限：** 用户身份、服务身份、工作负载身份、最小权限和短期凭据；
- **数据安全：** 静态数据、传输数据和使用中数据保护，密钥全生命周期与备份恢复；
- **平台安全：** 主机加固、网络微隔离、API保护、漏洞管理和运行时检测；
- **供应链安全：** 可信软件源、包与镜像签名、SBOM、构建证明、依赖治理和可追溯发布；
- **运营安全：** 全链路监控、审计留痕、事件响应、灾难恢复和云服务商与用户的责任共担。

### （八）绿色云：从数据中心节能走向算力效能治理

工业和信息化部等六部门发布的《算力基础设施高质量发展行动计划》把算力基础设施概括为多元泛在、智能敏捷、安全可靠、绿色低碳，并从计算力、运载力、存储力和应用赋能统筹建设。该计划还提出提升算力碳效、增加绿色能源使用、推进算电协同和赋能行业低碳转型。[来源：工业和信息化部政策解读](https://www.miit.gov.cn/zwgk/zcjd/art/2023/art_916261bbfa6d4e1eb9483e843c5a4fd5.html)

绿色云不能只看机房制冷效率。面向AI负载，还应关注资源利用率、任务完成能耗、闲置加速卡比例、数据搬移开销、软件算法效率和可再生能源匹配。平台工程实践中，可将容量规划、弹性伸缩、实例规格优化、冷热数据分层、任务错峰和能耗监测纳入统一的GreenOps与FinOps治理。

### （九）信创化平台：自主创新与开放协作相统一

在本书语境中，“信创化云平台”不是简单替换品牌，也不能只凭“国产”标签判断。它应体现以下工程能力：

1. 基础软件源代码开放、治理透明，关键技术路线可持续演进；
2. 能适配x86、Arm、LoongArch、RISC-V等多种计算架构，降低单一技术路线依赖；
3. 软件包、镜像、配置和构建过程可验证、可追溯，形成可信供应链；
4. 核心组件具备替换、迁移和二次开发能力，接口尽可能采用开放标准；
5. 通过真实业务和实验验证兼容性、性能、稳定性和安全性，而不是以宣传材料代替工程证据；
6. 形成社区、企业、高校和产业用户共同参与的人才与生态体系。

openEuler与OpenStack均采用开放社区协作方式。将openEuler作为操作系统底座、OpenStack作为云基础设施平台，能够让学生在理解国际开源协作规则的同时，掌握面向我国数字基础设施的适配、验证和运维能力。这种路线体现的是在开放合作中增强自主创新能力。

## 二、OpenStack：面向开放基础设施的云操作系统

### （一）OpenStack的定位与应用价值

OpenStack官方文档将其描述为一种“云操作系统”：它控制数据中心内大规模的计算、存储和网络资源，并通过API、命令行和Web界面向管理员与用户提供自助服务。[来源：OpenStack 2026.1官方文档首页](https://docs.openstack.org/2026.1/)

“云操作系统”是一种功能类比，而不是说OpenStack替代Linux。Linux负责单台服务器的进程、内存、设备和文件系统，OpenStack则把多台服务器、存储和网络设备组织成资源池，并以租户、项目、配额、镜像、实例、卷和网络等对象对外提供服务。

OpenStack适合建设私有云、公有云、行业云、电信云、边缘云、科研云和AI基础设施。OpenInfra官方资料显示，截至2025年10月，公开统计的OpenStack全球部署规模已超过5500万计算核心。2026.1发布周期约有500名贡献者、100个组织参与，完成超过9000项代码变更，说明OpenStack仍是活跃演进的大规模开放基础设施项目。[来源：OpenInfra关于Gazpacho的官方发布文章](https://www.openstack.org/blog/openstack-gazpacho-built-by-a-global-community-designed-for-real-world-infrastructure/)

OpenStack的主要价值包括：

- 以开放API实现计算、网络、存储等基础设施能力的服务化；
- 支持多厂商硬件、虚拟化、网络和存储后端，避免把整个云平台绑定在单一专有技术栈；
- 通过模块化组件按需组合，既可建设两节点教学云，也可扩展到大规模生产云；
- 与Kubernetes、裸金属、加速器和边缘部署协同，承载传统应用与现代应用；
- 允许组织掌握平台数据、配置、升级节奏和运维流程，为私有云与主权云提供开放底座。

### （二）核心组件与逻辑架构

OpenStack不是一个单体程序，而是一组通过REST API、消息队列、数据库和认证机制协作的服务。官方2026.1安装指南给出的最小安装顺序为Keystone、Glance、Placement、Nova、Neutron；完成最小服务后，可继续安装Horizon和Cinder。Swift对象存储也可独立部署。[来源：OpenStack官方安装服务顺序](https://docs.openstack.org/install-guide/openstack-services.html)

| 能力域 | 组件 | 主要职责 | 与本书实训的关系 |
|---|---|---|---|
| 身份 | Keystone | 用户、项目、角色、令牌、服务目录与端点 | 必装；其他服务统一使用其认证与服务发现能力 |
| 镜像 | Glance | 云镜像注册、元数据管理、镜像获取与后端存储 | 必装；为实例提供启动镜像 |
| 资源跟踪 | Placement | 记录资源提供者、资源库存、特征和分配 | 必装；Nova调度计算资源时使用 |
| 计算 | Nova | 实例生命周期、调度、计算节点管理和控制台 | 必装；负责虚拟机计算服务 |
| 网络 | Neutron | 网络、子网、端口、路由、安全组和多种网络后端 | 必装；本书使用ML2/Linux bridge教学架构 |
| 块存储 | Cinder | 云硬盘、快照、卷类型和存储后端 | 扩展安装；本书使用计算节点附加盘构建LVM后端 |
| 对象存储 | Swift | 分布式对象存储、账户、容器和对象管理 | 扩展安装；本书使用另一块附加盘完成教学部署 |
| 控制面板 | Horizon | 基于Web的管理与用户自助界面 | 扩展安装；用于观察和辅助管理，不替代命令行学习 |
| 编排 | Heat | 通过模板创建和管理资源栈 | 作为扩展生态介绍 |
| 裸金属 | Ironic | 物理服务器发现、部署和生命周期管理 | 连接高性能计算、AI与边缘场景 |
| 负载均衡 | Octavia | 负载均衡即服务 | 作为网络扩展服务介绍 |
| 密钥管理 | Barbican | 密钥、证书和机密信息管理 | 连接TLS、加密卷和可信云场景 |
| 加速器 | Cyborg | GPU、FPGA等加速设备生命周期与资源对接 | 连接AI与异构算力场景 |
| 容器基础设施 | Magnum | 通过OpenStack资源提供容器编排集群 | 连接OpenStack与Kubernetes生态 |

一次典型的实例创建请求可概括为：用户通过CLI或Horizon提交请求，Keystone完成身份验证；Nova API接收请求并把持久数据写入数据库；调度器查询Placement选择计算节点；计算服务从Glance取得镜像，通过Neutron创建端口和网络连接，并可通过Cinder连接云硬盘；组件之间使用消息队列传递异步任务。由此可见，数据库、消息队列和缓存虽然不是面向租户的OpenStack云服务，却是控制面的重要基础依赖。

### （三）发布节奏、版本命名与SLURP

OpenStack按大约六个月一个周期进行协调发布，通常每年发布两个版本；初始版本发布后，各项目还会发布稳定修订版本。Zed之后，版本以“年份.当年序号”为主标识，同时保留代号，例如2023.1 Antelope、2026.1 Gazpacho。[来源：OpenStack版本命名规则](https://governance.openstack.org/tc/reference/release-naming.html)

从2023.1开始，OpenStack每隔一个版本标记一个SLURP（Skip Level Upgrade Release Process）版本。相邻大版本升级仍被支持；在满足项目要求时，还支持从一个SLURP版本跨过中间的非SLURP版本升级到下一个SLURP版本。这样，运营者既可以保持六个月升级节奏，也可以围绕SLURP形成约一年的升级节奏。[来源：OpenStack发布列表与SLURP说明](https://releases.openstack.org/)；[TC发布节奏决议](https://governance.openstack.org/tc/resolutions/20220210-release-cadence-adjustment.html)

需要特别强调：SLURP表示社区规定并测试的跨级升级路径，不等于“长期支持版”，也不意味着可以跨过任意多个版本直接升级。生产升级仍需逐项目阅读升级说明、完成数据库在线迁移、处理废弃配置并进行备份和回退演练。

### （四）开放治理与社区协作

OpenStack延续“四个开放”原则：开放源代码、开放设计、开放开发和开放社区。源代码采用Apache License 2.0；设计、代码评审、路线图、会议和邮件讨论公开进行；社区贡献者选举项目负责人和技术委员会成员。[来源：OpenStack“四个开放”](https://governance.openstack.org/tc/reference/opens.html)

OpenStack技术委员会（TC）是项目的技术治理机构，由贡献者选举产生，对跨项目技术事务进行监督。官方项目团队负责生产具体软件与协调发布，SIG、工作组和临时团队处理跨项目或专题工作。[来源：OpenStack技术委员会](https://governance.openstack.org/tc/) 这种治理结构把“谁使用软件”和“谁参与定义软件”连接起来，是开源基础设施长期演进的重要机制。

### （五）2026.1 Gazpacho：截至冻结日的最新受支持版本

OpenStack 2026.1 Gazpacho已于 **2026年4月1日** 正式发布，是OpenStack第33个版本，也是SLURP版本。截至2026年7月31日，官方发布站点将其标记为Maintained，官方文档将其标记为当前受支持版本；同期2026.2 Hibiscus仍处于开发阶段。因此，本书概论部分应以Gazpacho介绍OpenStack社区与技术现状，不能再把它写成计划版本。[来源：Gazpacho官方发布页](https://releases.openstack.org/gazpacho/index.html)；[OpenStack 2026.1文档首页](https://docs.openstack.org/2026.1/)

Gazpacho协调发布时部分核心服务的初始版本如下：

| 服务 | 2026.1初始版本 | 服务 | 2026.1初始版本 |
|---|---:|---|---:|
| Keystone | 29.0.0 | Glance | 32.0.0 |
| Placement | 15.0.0 | Nova | 33.0.0 |
| Neutron | 28.0.0 | Cinder | 28.0.0 |
| Swift | 2.37.0 | Heat | 26.0.0 |
| Ironic | 33.0.0 | Horizon | 25.6.0 |

Gazpacho的重要改进集中在真实生产环境的迁移、运营和硬件适配：

- Nova支持并行实时迁移、默认每个QEMU实例使用IOThread、带vTPM实例的特定模式实时迁移，以及异步卷挂载API；
- Neutron的OVN驱动增强BGP、外部端口南北向路由、虚拟MAC允许地址对和可扩展性配置；
- Ironic增强部署接口自动探测、Redfish虚拟介质协议探测、端口特征调度和现有裸金属纳管；
- Manila增加QoS类型与规格，提升共享文件服务的性能策略管理；
- Cyborg、Ironic和Nova等持续扩展GPU、FPGA、NIC及其他加速硬件适配；
- 多个服务推进从eventlet向原生线程迁移，其中标记为实验或技术预览的功能仍不应直接作为生产默认配置。

以上内容应以官方发布说明中的成熟度标记为准，不能把“实验功能”“技术预览”和“未来计划”写成稳定能力。[来源：Gazpacho官方特性说明](https://www.openstack.org/software/openstack-gazpacho)；[Gazpacho各项目发布亮点](https://releases.openstack.org/gazpacho/highlights.html)

### （六）为什么概论讲Gazpacho，实训固定Antelope

| 比较项 | OpenStack 2026.1 Gazpacho | OpenStack 2023.1 Antelope |
|---|---|---|
| 官方初始发布日期 | 2026年4月1日 | 2023年3月22日 |
| 冻结日官方状态 | Maintained，当前受支持版本 | Unmaintained，旧版本 |
| 是否为SLURP | 是 | 是 |
| 本书用途 | 用于概论、产业现状、组件生态和版本演进 | 用于两节点手工安装与运维实训 |
| 选择原因 | 反映截至2026年7月的社区最新事实 | 已有完整本地软件仓和脚本参考，便于固定环境、逐项拆解配置并复现实验 |
| 使用边界 | 可作为理解当前OpenStack的基线，生产选型仍需评估发行版支持 | 仅限隔离教学环境，不作为新建互联网生产云的版本建议 |

Antelope官方发布页显示其于2023年3月22日发布；截至冻结日已处于Unmaintained状态。[来源：Antelope官方发布页](https://releases.openstack.org/antelope/index.html) 本书保留Antelope实训，不是因为它比Gazpacho更新，而是为了在已经验证的软件包组合上，让学生完整理解数据库、消息队列、身份、服务用户、服务目录、端点、配置文件、数据库同步和systemd服务之间的关系。

教材必须在概论和实训开头同时提示这一边界：**概论版本用于认识当前技术，实验版本用于掌握原理和过程。** 学生不能把书中的Antelope安装步骤直接照搬到面向互联网的生产环境；生产平台应选用仍在维护且由所采用操作系统或商业发行版明确支持的版本。

## 三、openEuler：面向数字基础设施的开放操作系统底座

### （一）openEuler的定位与生态

openEuler是由开放原子开源基金会孵化和运营的开源操作系统项目。其定位已经从服务器操作系统扩展为数字基础设施操作系统，覆盖服务器、云计算、边缘计算和嵌入式场景，并支持x86、Arm、RISC-V、LoongArch、PowerPC、SW-64等多种指令集架构。[来源：openEuler官方文档中心](https://docs.openeuler.org/zh/)；[openEuler常见问题](https://docs.openeuler.org/zh/docs/common/faq/general/general_faq.html)

openEuler采用社区化治理，由不同SIG围绕内核、虚拟化、云原生、安全、编译器、AI和多样性计算等方向协作。对云计算教学而言，openEuler的价值不只是“更换Linux发行版”，而在于：

- 以开放社区和开放代码支撑操作系统关键能力的学习、适配和二次开发；
- 覆盖多种处理器架构，为异构计算与国产软硬件生态适配提供统一基础；
- 同时面向服务器、云、边缘和嵌入式，便于理解“云—边—端”数字基础设施；
- 提供虚拟化、容器、机密计算、系统安全、故障诊断和性能调优能力；
- 通过兼容性清单、软件包规范、构建与签名基础设施推进生态协作和供应链治理。[来源：openEuler操作系统技术白皮书](https://www.openeuler.org/whitepaper/en/openEuler%20OS%20Technical%20Whitepaper%28Innovation%20Projects%29.pdf)

### （二）openEuler 24.03 LTS SP3的版本事实

openEuler社区版本分为长期支持版本和创新版本。openEuler 24.03 LTS SP3于 **2025年12月** 发布，基于Linux Kernel 6.6，面向服务器、云和AI工作负载，并支持UnifiedBus SuperPoD相关能力。官方社区下载页列出的架构包括x86_64、AArch64、ARM32、LoongArch64和RISC-V，计划生命周期终点为2027年12月。[来源：openEuler社区版本下载页](https://www.openeuler.org/zh/download/)

截至2026年7月31日，24.03 LTS系列已有SP4于2026年6月发布。因此，教材不应把SP3表述为“当前最新服务包”；准确说法是：**本书实训选定的长期支持系列固定版本为openEuler 24.03 LTS SP3。** 固定SP3有利于保持软件包依赖、配置文件路径、内核和实验截图一致，而概论部分仍应说明同系列已继续演进。

SP3的代表性技术方向包括：

- **多样性算力与SuperPoD。** UnifiedBus相关组件扩展设备、内存、通信和虚拟化管理，面向资源池化和高性能互联；
- **虚拟化与机密计算。** 提供虚拟机、设备直通、可信执行环境、远程证明和机密虚拟机迁移相关能力；
- **云原生与编译优化。** 围绕容器、微服务、Go和JDK等运行时进行性能与生态适配；
- **系统运维。** 通过故障巡检、慢I/O检测、性能感知和调优框架提高可维护性；
- **安全能力。** 提供安全基线、漏洞扫描、根套件检测、证书签名和可信计算相关工具。

这些能力并非都要在两节点OpenStack基础实验中启用。教材应先让学生掌握稳定的最小云平台，再在拓展阅读中说明多架构、机密计算和SuperPoD等方向，避免用新名词掩盖基础原理。[来源：openEuler 24.03 LTS SP3关键特性](https://docs.openeuler.org/zh/docs/24.03_LTS_SP3/server/releasenotes/releasenotes/key_features.html)

### （三）openEuler与信创化云平台

openEuler可作为信创化云平台的操作系统底座，但“使用openEuler”不自动等于整个平台已经完成自主可控与安全可信建设。还应继续验证处理器、服务器、网卡、存储、虚拟化、数据库、中间件、OpenStack组件、管理工具和业务应用之间的兼容性，并建立软件源、签名、漏洞、补丁和升级管理制度。

建议在教材中用以下四个维度评价信创化平台：

| 维度 | 教学观察点 | 可形成的证据 |
|---|---|---|
| 技术可控 | 源代码、接口、配置和数据格式是否开放，是否具备迁移与替换路径 | 源码仓、开放API、配置文件、导入导出与迁移测试 |
| 生态兼容 | 多架构硬件、驱动、软件包和上层应用是否经过验证 | 兼容清单、安装记录、功能与性能测试结果 |
| 供应链可信 | 软件来自何处，是否有签名、校验、版本锁定和漏洞响应 | 仓库清单、RPM签名、哈希、SBOM、补丁记录 |
| 运维自主 | 团队能否独立部署、诊断、升级、备份和恢复 | 手工部署文档、监控审计、故障演练与恢复报告 |

这种评价方式把“自主可控”落实为可检查的工程活动，也能培养学生严谨求证、精益操作和对系统全生命周期负责的职业素养。

### （四）本书实验的软件组合与兼容边界

本书实验使用以下固定组合：

| 层次 | 固定选择 | 说明 |
|---|---|---|
| 宿主操作系统 | openEuler 24.03 LTS SP3，Linux 6.6 | 两台教学虚拟机统一版本 |
| 云平台 | OpenStack 2023.1 Antelope | 按组件手工部署，便于讲清服务依赖和配置过程 |
| OpenStack软件包 | 来自openEuler 24.03 LTS SP2对应Antelope仓的软件包，并整理为本地仓 | 用户已实测SP2软件包可在SP3系统安装运行，项目还将按组件进行API与服务验证 |
| 部署方法 | 学生手工输入命令、编辑配置、同步数据库、创建服务用户与端点、启动服务 | 自动化脚本只作为配置与顺序参考，不替代第二篇手工操作 |

需要明确：**“SP3操作系统＋SP2仓Antelope软件包”是本教材项目的教学兼容组合，不是openEuler社区对该跨服务包组合的官方支持承诺。** 它成立的依据是软件包依赖解析、RPM签名与来源检查，以及在指定两节点环境中的逐组件实测。教材应保留本地仓版本清单和验证记录，使结论可复核。

采用这一组合时还要遵守三项边界：

1. 不把SP2软件源整体替换为系统基础源。操作系统基础包仍以SP3及经过审核的补充包为准，Antelope组件从固定本地仓安装；
2. 不在实验中无控制地执行系统全量升级，以免改变已验证依赖；需要补丁时先在副本环境验证；
3. 不把实验组合用于面向互联网的生产系统。生产部署必须依据仍受维护的OpenStack版本、操作系统支持矩阵和组织安全要求重新设计。

## 四、面向教学的知识组织建议

### （一）三条贯穿主线

第三版可用三条主线串联概论、平台构建与智能体运维：

- **资源主线：** 物理资源 → 操作系统 → 虚拟化 → OpenStack资源池 → 虚拟机/卷/网络 → 容器与AI工作负载；
- **服务主线：** 手工配置单个组件 → API与身份目录协同 → 云资源自助服务 → 智能体调用标准工具完成组合任务；
- **可信主线：** 官方来源与版本冻结 → 本地软件仓与签名校验 → 最小权限与审计 → 可复现部署 → 智能体操作的授权、验证和回退。

这样安排可避免把“传统OpenStack”和“智能体运维”写成彼此割裂的两本书。智能体能够执行任务，是因为前文已经建立了清晰的对象模型、命令边界、服务依赖和验收规则。

### （二）课程思政与职业素养融入点

**主题：开放协作中的自主创新与工程报国。** OpenStack体现全球开源社区的开放协作，openEuler体现我国数字基础设施开源生态的持续建设。二者结合说明，自主创新并不是拒绝交流，而是在理解开放规则、尊重知识产权和参与共同治理的基础上，形成可掌握、可验证、可演进的核心能力。可组织学生讨论：为什么“能安装”不等于“自主可控”？如何用软件来源、签名、测试记录、故障复盘和社区贡献证明工程责任？由此融入爱国情怀、开放精神、工匠精神、诚信意识和安全责任。

## 五、建议图表清单

以下编号按建议落入的章节独立编号，不采用小节编号。

### 第1章建议

- **图1.1　2021—2026年云计算技术边界演进图**：从虚拟机资源池扩展到云原生、AI云、云边端、可信与绿色治理。
- **图1.2　AI云三层架构图**：AIIaaS、AIPaaS、AI应用/智能体，上下贯通算力、网络、存储、数据、模型和运营。
- **图1.3　云—边—端与算力互联网协同示意图**：中心云、区域节点、边缘节点、终端和跨域算力调度。
- **图1.4　可信云全生命周期安全图**：开发、构建、分发、部署、运行五阶段及身份、签名、SBOM、审计。
- **表1-1　2021年前后与2026年云计算认知对照表**：可直接采用本文对应表格。
- **表1-2　IaaS、PaaS、SaaS与AI云服务映射表**：在传统三层模型上增加异构算力、模型平台和智能体实例。
- **表1-3　混合云、多云、边缘云和主权云比较表**：比较目标、部署位置、治理重点和典型场景。

### 第3章建议

- **图3.1　OpenStack 2026.1组件全景图**：按计算、网络、存储、共享服务、编排和运维分类。
- **图3.2　OpenStack两节点教学架构与服务调用关系图**：controller、compute、管理网、提供者网及数据库/消息队列。
- **图3.3　创建虚拟机的跨组件请求流程图**：Keystone、Nova、Placement、Glance、Neutron、Cinder和计算节点。
- **图3.4　OpenStack六个月发布与SLURP升级节奏图**：相邻升级与SLURP跨一级升级路径。
- **表3-1　OpenStack主要组件及职责表**：可直接采用本文对应表格。
- **表3-2　Gazpacho核心服务初始版本表**：可直接采用本文对应表格。
- **表3-3　Gazpacho与Antelope教学定位对照表**：突出“概论最新、实训固定、生产勿照搬”。

### 第4章建议

- **图4.1　openEuler数字基础设施场景图**：服务器、云、边缘、嵌入式与多架构硬件生态。
- **图4.2　openEuler SP3与OpenStack Antelope教学软件栈图**：硬件/虚拟机、SP3、SP2仓Antelope包、OpenStack服务、云资源。
- **图4.3　本地软件仓可信链示意图**：官方来源、下载、签名与哈希、版本清单、本地发布、实验验证。
- **表4-1　openEuler 24.03 LTS SP3版本信息表**：内核、架构、场景、发布时间和冻结日生命周期。
- **表4-2　信创化云平台四维评价表**：可直接采用本文对应表格。
- **表4-3　教材实验固定软件组合表**：可直接采用本文对应表格。

图片制作要求：架构图优先采用矢量SVG或可编辑源文件，导出300 dpi以上PNG用于排版；官方页面截图须保留页面标题、版本、发布日期或状态等证据区域，同时裁去无关导航和隐私信息；正文中的最小字号不低于原稿同类图片字号减一号。每幅图的高清文件按书稿最终图号命名并单独保存。

## 六、官方来源注释

以下资料均为官方或一手来源。统一访问日期：**2026年8月12日**；统一内容冻结日期：**2026年7月31日**。

1. NIST，《The NIST Definition of Cloud Computing》，SP 800-145。https://csrc.nist.gov/pubs/sp/800/145/final
2. 中国信息通信研究院，《云计算蓝皮书（2025年）》，2025年7月。https://www.caict.ac.cn/kxyj/qwfb/bps/202507/P020250722583603558109.pdf
3. 工业和信息化部，《算力基础设施高质量发展行动计划》配套解读，2023年10月9日。https://www.miit.gov.cn/zwgk/zcjd/art/2023/art_916261bbfa6d4e1eb9483e843c5a4fd5.html
4. 工业和信息化部，《算力互联互通行动计划》，2025年发布。https://fjca.miit.gov.cn/zwgk/zcwj/wjfb/art/2025/art_25eea57dd6f840e680184fffb086883d.html
5. CNCF，Cloud Native Definition。https://github.com/cncf/toc/blob/main/DEFINITION.md
6. CNCF，2025 Annual Cloud Native Survey发布说明，2026年1月20日。https://www.cncf.io/announcements/2026/01/20/kubernetes-established-as-the-de-facto-operating-system-for-ai-as-production-use-hits-82-in-2025-cncf-annual-cloud-native-survey/
7. CNCF TAG Security，Cloud Native Security Whitepaper v2。https://tag-security.cncf.io/community/resources/security-whitepaper/v2/cloud-native-security-whitepaper/
8. CNCF TAG Security and Compliance，Identity and Access Management Whitepaper发布说明，2026年6月4日。https://www.cncf.io/blog/2026/06/04/identity-and-access-management-whitepaper/
9. NIST，Multi-Cloud Security Public Working Group Charter。https://csrc.nist.gov/projects/mcspwg/mcspw-charter
10. 欧盟委员会，Sovereign Cloud Framework Explained，2026年6月1日。https://commission.europa.eu/news-and-media/news/sovereign-cloud-framework-explained-2026-06-01_en
11. AWS，Hybrid Cloud with AWS—AWS hybrid cloud solutions。https://docs.aws.amazon.com/whitepapers/latest/hybrid-cloud-with-aws/aws-hybrid-cloud-solutions.html
12. Google Cloud，Hybrid and multicloud application platform。https://cloud.google.com/solutions/hybrid-and-multicloud-application-platform
13. OpenStack，2026.1 Documentation。https://docs.openstack.org/2026.1/
14. OpenStack，2026.1 Installation Guides。https://docs.openstack.org/2026.1/install/index.html
15. OpenStack，Install OpenStack services。https://docs.openstack.org/install-guide/openstack-services.html
16. OpenStack Release Team，OpenStack Releases及SLURP说明。https://releases.openstack.org/
17. OpenStack Release Team，2026.1 Gazpacho。https://releases.openstack.org/gazpacho/index.html
18. OpenStack/OpenInfra，Gazpacho官方特性页。https://www.openstack.org/software/openstack-gazpacho
19. OpenStack Release Team，Gazpacho Release Highlights。https://releases.openstack.org/gazpacho/highlights.html
20. OpenStack/OpenInfra，OpenStack Gazpacho: Built by a Global Community, Designed for Real-World Infrastructure，2026年4月1日。https://www.openstack.org/blog/openstack-gazpacho-built-by-a-global-community-designed-for-real-world-infrastructure/
21. OpenStack Technical Committee，The Four Opens。https://governance.openstack.org/tc/reference/opens.html
22. OpenStack Technical Committee，OpenStack Technical Committee。https://governance.openstack.org/tc/
23. OpenStack Technical Committee，Release Cadence Adjustment（SLURP决议）。https://governance.openstack.org/tc/resolutions/20220210-release-cadence-adjustment.html
24. OpenStack Technical Committee，Release Identification/Name。https://governance.openstack.org/tc/reference/release-naming.html
25. OpenStack Release Team，2023.1 Antelope。https://releases.openstack.org/antelope/index.html
26. openEuler，社区版本下载页。https://www.openeuler.org/zh/download/
27. openEuler，文档中心。https://docs.openeuler.org/zh/
28. openEuler，常见问题—什么是openEuler。https://docs.openeuler.org/zh/docs/common/faq/general/general_faq.html
29. openEuler，openEuler 24.03 LTS SP3关键特性。https://docs.openeuler.org/zh/docs/24.03_LTS_SP3/server/releasenotes/releasenotes/key_features.html
30. openEuler，openEuler OS Technical White Paper。https://www.openeuler.org/whitepaper/en/openEuler%20OS%20Technical%20Whitepaper%28Innovation%20Projects%29.pdf

### 出版前复核提示

本稿已按2026年7月31日冻结。进入终稿排版时，如果出版社要求继续滚动更新，只需重新核对三类动态事实：OpenStack当前受支持版本与状态、openEuler 24.03 LTS各服务包生命周期、云计算市场年度统计。若仍执行本次冻结规则，则不得用冻结日后的版本替换正文事实。
