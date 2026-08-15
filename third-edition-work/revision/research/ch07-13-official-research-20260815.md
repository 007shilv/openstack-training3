# 第7—13章组件原理资料底稿

资料于2026-08-15检索。组件职责、状态和接口语义优先以OpenStack官方文档为准；OpenInfra Superuser、Red Hat等技术文章只用于借鉴案例、图示层次和通俗说明，写入教材前与官方资料交叉核对。

## Glance

官方架构将Glance描述为客户端—服务器结构。REST API之后包含认证与授权中间件、领域控制逻辑、数据库访问层和glance_store。数据库保存镜像元数据，glance_store为文件系统、Swift、Ceph RBD等后端提供统一访问接口。教材可把请求拆成“认证与策略—元数据—镜像数据”三条相关路径。

镜像可以走直接上传，也可以走可互操作导入。导入过程先把数据写入暂存区，再执行导入插件链并写入目标后端。成功进入active，失败进入相应错误状态。镜像缓存包含incomplete、invalid和queue等区域；预取器按队列处理，失败项目保留供后续重试，清理器和裁剪器周期性回收不完整或过期内容。教材流程图应显示上传方式判断、暂存/后端写入、成功/失败分支以及缓存周期任务。

## Placement

Placement通过资源提供者、资源类别、清单、特征、聚合、消费者和分配描述资源供给与占用。分配候选请求先验证资源数量，再结合提供者树、共享提供者、聚合成员和required/forbidden traits形成候选组合。

资源提供者和消费者都有generation。修改请求必须携带调用者已知的generation；若并发请求已经改变对象，服务返回409 `placement.concurrent_update`。正确处理不是盲目重复原请求，而是重新读取对象、重新判断容量和约束，再用新generation提交。这个机制适合用带回环的流程图解释乐观并发控制。

## Nova

当前Nova调度由请求规格、Placement候选、Nova过滤和称重、Placement资源声明以及Cell conductor构建共同完成。Scheduler从Placement取得满足资源要求的候选和对应AllocationRequest，形成HostState，再进行过滤和称重。对首选主机声明资源失败时，Scheduler继续尝试排序列表中的下一主机。

首选主机和若干备用主机会被传给目标Cell的Conductor。若nova-compute在首选主机构建失败，Conductor释放原主机声明，并依次对备用主机声明资源和重试构建。候选耗尽或达到最大尝试次数后，实例进入ERROR。教材应把“调度阶段的资源声明重试”和“构建阶段的备用主机重试”区分开。

第二版对Libvirt和控制台代理的解释仍有教材价值，但Nova Cert和nova-consoleauth不再作为现行服务。Libvirt继续作为nova-compute与KVM/QEMU之间的统一管理接口；noVNC代理把浏览器访问与计算节点上的虚拟机控制台连接起来。

## Neutron

ML2把网络类型与后端实现分离。网络、子网和端口的创建或更新包括precommit和postcommit阶段：数据库状态在事务中持久化，随后机制驱动把变化传递给外部网络后端。端口绑定可以跨多层基础设施形成有顺序的binding levels，删除时按相反顺序拆除。

在Linux Bridge参考实现中，Neutron Server保存期望状态，二层代理通过RPC或周期检查取得端口信息，在计算节点建立桥、虚拟接口、VXLAN设备和安全组规则。端口可能经历DOWN、BUILD、ACTIVE；绑定无法完成时出现binding_failed。代理重启或消息丢失后需要重新同步，因此图中应表现“发现设备—查询期望状态—配置—上报—周期复查”的循环。

## Cinder

Cinder API接收请求、验证输入与策略并建立初始数据库记录；Scheduler依据后端能力、过滤器和称重器选择后端；Volume服务通过驱动操作真实存储。若没有后端同时满足可用区、容量、卷类型和能力要求，请求不能进入后端创建。

卷连接不是单一步骤。Attachment对象先预留卷与实例关系，再根据计算节点连接器信息初始化连接，最后完成连接并把卷状态置为in-use。分离时先进入detaching，再终止后端连接，最后删除Attachment并恢复available。状态更新和连接操作必须保持顺序，否则可能留下宿主机设备并造成数据泄漏或损坏。

## Swift

Swift为账户、容器和每种对象存储策略分别维护Ring。Ring把对象路径哈希映射到分区，再把分区副本分配到不同region、zone、server和device。Proxy根据Ring找到主设备；主设备不可用时可以选择handoff设备继续处理。

Swift副本相互独立，写入请求达到配置要求的成功响应后即可向客户端返回。短时间不一致由后台进程修复：Replicator比较并同步副本，Auditor读取数据和元数据检查损坏，Account/Container Updater补齐列表信息，Expirer处理到期对象。Ring变更后，复制进程循环把分区移动到新位置。教材应强调这是最终一致性和持续修复机制，不等于每次请求都等待全部副本完成。

## Horizon

Horizon使用Keystone服务目录定位其他OpenStack API。用户登录后取得作用域令牌，角色和项目范围进入会话。Dashboard、PanelGroup和Panel构成可扩展界面；面板通过统一API封装访问Nova、Glance、Neutron、Cinder和Swift。

Horizon的策略检查利用作用域令牌中的角色和资源所有权决定按钮或面板是否显示，但后端服务仍会再次执行自己的策略规则。前端允许不代表后端一定允许。令牌过期时需要刷新或重新登录；无权限、服务端点不可达和API错误应分成不同分支呈现。

## 课程思政连接点

OpenStack接口协作体现开放标准、分工协作和持续贡献。将开源成果适配国产操作系统，需要理解规范、验证兼容并回馈社区，不能把简单复制等同于自主创新。Neutron的隔离与Cinder/Swift的数据完整性说明工程师必须对配置边界和业务数据负责。Horizon的权限处理说明便利界面不能削弱最小权限、数据保护和操作留痕。
