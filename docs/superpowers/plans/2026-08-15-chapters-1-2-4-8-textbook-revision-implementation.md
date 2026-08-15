# 第1—2章与第4—8章教材化修订 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按第二版内容组织与版式完成第1、2、4—8章教材化修订，并输出一个可由Word稳定打开的当前审阅稿。

**Architecture:** 以章节Markdown作为可审查内容源，以图表清单和独立高清图片作为视觉资产源，再通过现有第二版边界替换工具写入当前DOCX。内容检查、Open XML检查、Word重开、PDF渲染和视觉抽查构成逐层验收。

**Tech Stack:** Markdown、SVG/PNG、Open XML DOCX、Microsoft Word、PDF渲染、pytest。

## Global Constraints

- 以第二版书稿为内容组织和Word版式底板。
- 第1—2章与第4—8章为本轮正文范围；第3章只做统一术语中文化。
- 只写教材叙事和手工Linux命令，不写Python、自动化脚本、门禁、审计或验证报告。
- 命令必须带真实系统提示符；配置文件必须通过`vi`手工编辑；实训目标必须按数字分点。
- 实验环境口令统一为`qwer1234`。
- 正文宋体10.5磅；图中文字原则上9磅且不小于正文以下1.5磅。
- 图号使用“图N.N”，表号使用“表N-N”，每章独立连续编号；正文先引用再出现图表，图后解释元素。
- 不出现“教学云”“教学活动”“不宜把”“产品名称还原”及复习思考内容。
- 只保留第二版源文件和当前第三版审阅稿作为最终Word文档。

---

### Task 1: 建立批量修订内容合同

**Files:**
- Modify: `third-edition-work/tests/test_second_base_revision.py`
- Modify: `third-edition-work/tests/test_chapter3_revision.py`
- Create: `third-edition-work/tests/test_chapters_4_8_revision.py`

**Interfaces:**
- Consumes: `revision/fragments/ch01.md`至`ch08.md`、图表清单和当前DOCX。
- Produces: 章节层级、禁用语言、实训目标、提示符、图表编号、字体与Word可打开性的可执行检查。

- [ ] **Step 1: 写入章节结构和禁用语言的失败测试**
- [ ] **Step 2: 运行定向测试，确认当前第4—8章因层级、图表和实训目标不足而失败**
- [ ] **Step 3: 写入图表引用、提示符、纯手工操作和密码统一检查**
- [ ] **Step 4: 运行定向测试并保存失败基线**

### Task 2: 修订第1—2章与第三章术语

**Files:**
- Modify: `third-edition-work/revision/fragments/ch01.md`
- Modify: `third-edition-work/revision/fragments/ch02.md`
- Modify: `third-edition-work/revision/fragments/ch03.md`
- Modify: `third-edition-work/revision/figures/ch01-02-figure-manifest.json`

**Interfaces:**
- Consumes: 已审阅的第1—2章正文、真实截图和产业资料。
- Produces: 语言统一、层级完整、重点详略合理且图表引用闭合的第1—2章；第三章通用英文状态中文化。

- [ ] **Step 1: 按节梳理定义、事实、原因和重点内容顺序**
- [ ] **Step 2: 删除编辑性语言、教学活动和复习思考**
- [ ] **Step 3: 把节内标题统一为中文序号与阿拉伯数字两级**
- [ ] **Step 4: 检查每幅图和每张表均先引用、后解释且无独立注释**
- [ ] **Step 5: 运行第1—3章定向测试并修正到通过**
- [ ] **Step 6: 提交第1—3章内容修订**

### Task 3: 重写第4章环境准备与双节点实训

**Files:**
- Modify: `third-edition-work/revision/fragments/ch04.md`
- Create: `third-edition-work/revision/figures/ch04/图4.1.svg`
- Create: `third-edition-work/revision/figures/ch04/图4.1.png`
- Create: `third-edition-work/revision/figures/ch04/图4.2.svg`
- Create: `third-edition-work/revision/figures/ch04/图4.2.png`
- Create: `third-edition-work/revision/figures/ch04/图4.3.svg`
- Create: `third-edition-work/revision/figures/ch04/图4.3.png`
- Create: `third-edition-work/revision/figures/ch04/图4.4.svg`
- Create: `third-edition-work/revision/figures/ch04/图4.4.png`
- Create: `third-edition-work/revision/figures/ch04-figure-manifest.json`

**Interfaces:**
- Consumes: openEuler 24.03 LTS SP3、Antelope、controller/compute地址、网卡和磁盘分工。
- Produces: 第4章完整原理、4图4表和纯手工基础环境实训。

- [ ] **Step 1: 用第二版章节节奏重组4.1—4.3**
- [ ] **Step 2: 写出openEuler、信创技术栈和版本组合的叙事正文**
- [ ] **Step 3: 写出双节点、双网卡、磁盘和组件分工的4张表**
- [ ] **Step 4: 绘制并渲染图4.1—图4.4，检查9磅中文文字清晰度**
- [ ] **Step 5: 将实训目标改为编号列表并整理全部手工命令顺序**
- [ ] **Step 6: 运行第4章定向测试并修正到通过**
- [ ] **Step 7: 提交第4章内容和图表**

### Task 4: 修订第5—6章基础服务与Keystone

**Files:**
- Modify: `third-edition-work/revision/fragments/ch05.md`
- Modify: `third-edition-work/revision/fragments/ch06.md`
- Create: `third-edition-work/revision/figures/ch05/*`
- Create: `third-edition-work/revision/figures/ch06/*`
- Create: `third-edition-work/revision/figures/ch05-figure-manifest.json`
- Create: `third-edition-work/revision/figures/ch06-figure-manifest.json`

**Interfaces:**
- Consumes: 第4章已完成的节点、软件仓和时间服务环境。
- Produces: MariaDB/RabbitMQ/Memcached/客户端与Keystone的原理、图表和手工部署正文。

- [ ] **Step 1: 重组第5章原理、依赖关系和实训层级**
- [ ] **Step 2: 补充第5章服务关系图、流程图和比较表**
- [ ] **Step 3: 重组第6章身份对象、令牌、服务目录和实训层级**
- [ ] **Step 4: 补充第6章对象关系图、请求流程图和配置表**
- [ ] **Step 5: 核对数据库、用户、服务、端点、配置、同步、启动的手工顺序**
- [ ] **Step 6: 运行第5—6章定向测试并修正到通过**
- [ ] **Step 7: 提交第5—6章内容和图表**

### Task 5: 修订第7—8章Glance与Placement

**Files:**
- Modify: `third-edition-work/revision/fragments/ch07.md`
- Modify: `third-edition-work/revision/fragments/ch08.md`
- Create: `third-edition-work/revision/figures/ch07/*`
- Create: `third-edition-work/revision/figures/ch08/*`
- Create: `third-edition-work/revision/figures/ch07-figure-manifest.json`
- Create: `third-edition-work/revision/figures/ch08-figure-manifest.json`

**Interfaces:**
- Consumes: 第6章Keystone服务目录与认证环境。
- Produces: Glance和Placement原理、图表及纯手工部署正文。

- [ ] **Step 1: 重组第7章镜像对象、后端、调用关系和实训层级**
- [ ] **Step 2: 补充第7章架构图、调用图和配置/对象表**
- [ ] **Step 3: 重组第8章资源提供者、清单、分配、调度协作和实训层级**
- [ ] **Step 4: 补充第8章资源模型图、调度协作图和对象/接口表**
- [ ] **Step 5: 核对身份对象、配置文件、数据库同步、Apache承载和服务启动顺序**
- [ ] **Step 6: 运行第7—8章定向测试并修正到通过**
- [ ] **Step 7: 提交第7—8章内容和图表**

### Task 6: 合并当前Word并统一版式

**Files:**
- Modify in place: `D:/codex/云计算教材更新/云计算基础架构平台构建与应用（第三版第1-3章审阅稿-20260815-04修复版）.docx`
- Preserve: `D:/codex/云计算教材更新/云计算基础架构平台构建与应用（第二版初稿）.docx`

**Interfaces:**
- Consumes: ch01—ch08章节片段及图表资产。
- Produces: 第1—8章内容和版式完整的当前第三版审阅稿。

- [ ] **Step 1: 检查Word未被用户占用并记录源文件哈希**
- [ ] **Step 2: 在临时文件中按真实章节边界替换第1、2、4—8章并更新第三章术语**
- [ ] **Step 3: 插入图表并套用第二版标题、正文、题注、表格和命令样式**
- [ ] **Step 4: 检查正文宋体10.5磅、图片文字9磅、图表编号和提示符**
- [ ] **Step 5: 用Word打开临时文件并另存，成功后原子替换当前审阅稿**

### Task 7: 完整验收并交付集中审阅

**Files:**
- Create: `third-edition-work/validation/revision/ch01-08-content-check.txt`
- Create: `third-edition-work/validation/revision/ch01-08-layout-check.txt`

**Interfaces:**
- Consumes: 当前第三版审阅稿。
- Produces: 内容、结构、Word稳定性和视觉质量证据。

- [ ] **Step 1: 运行全部章节内容合同和既有回归测试**
- [ ] **Step 2: 解包检查DOCX关系、媒体、图表编号和样式引用**
- [ ] **Step 3: 用Word重新打开并转换为PDF**
- [ ] **Step 4: 渲染第1、2、4、5、6、7、8章代表页并逐页检查**
- [ ] **Step 5: 修正裁切、重叠、空白、字号、表格断裂和图文引用问题**
- [ ] **Step 6: 重新运行全套验收并记录最终哈希、页数和图表数量**
- [ ] **Step 7: 提交最终审阅稿相关源文件并停止后续章节写作**

### Task 8: 按集中反馈统一术语、产品结构、图形和编号

**Files:**
- Modify: `third-edition-work/revision/fragments/ch01.md`
- Modify: `third-edition-work/revision/fragments/ch02.md`
- Modify: `third-edition-work/revision/fragments/ch03.md`
- Modify: `third-edition-work/revision/fragments/ch04.md`
- Modify: `third-edition-work/revision/fragments/ch05.md` 至 `ch08.md`
- Modify: `third-edition-work/revision/figures/ch01` 至 `ch8` 中现有图形资产
- Modify: `third-edition-work/tests/test_chapters_4_8_revision.py`
- Modify in place: `D:/codex/云计算教材更新/云计算基础架构平台构建与应用（第三版第1-3章审阅稿-20260815-04修复版）.docx`

**Interfaces:**
- Consumes: 用户八幅截图、已批准的术语首现格式和当前第1—8章图文内容。
- Produces: 术语首次出现即释义、国内产品详写、国外产品简写、图形无重叠溢出、表格连续编号且只使用本地软件源的当前审阅稿。

- [x] **Step 1: 写入术语首现、第二章结构、第四章表号和本地源流程的失败测试**
- [x] **Step 2: 运行定向测试，确认上述问题在当前稿中真实存在**
- [x] **Step 3: 重组第二章为国外私有云简介、国内私有云、国内公有云、国外公有云简介和产品选择五节**
- [x] **Step 4: 按正文阅读顺序统一第1—8章专业术语的首次解释，命令、路径、网址和环境变量保持原样**
- [x] **Step 5: 把第四章表号按出现顺序改为表4-1至表4-4，删除远程Antelope仓配置，仅保留教材配套本地仓**
- [x] **Step 6: 逐张检查第1—8章44幅图片；示意图修正箭头、字号、模块尺寸和文字溢出，截图检查清晰度与裁切**
- [x] **Step 7: 运行定向和全量测试并修正到通过**
- [x] **Step 8: 在临时文件中生成当前Word，完成打开、页数和代表页视觉检查后原子覆盖原文件**
- [x] **Step 9: 提交本轮源文件和检查项，不提交临时文件或另建正式书稿**

### Task 9: 统一全稿结构、字体和现有图形

**Files:**
- Modify: `third-edition-work/revision/fragments/ch02.md`
- Modify: `third-edition-work/revision/figures/ch02/图2.11.svg`
- Modify: `third-edition-work/revision/figures/ch7/图7.2.svg`
- Modify: `third-edition-work/tools/revise_second_edition.py`
- Modify: `third-edition-work/tools/build_ch04_08_figures.py`
- Modify: `third-edition-work/tests/test_chapters_4_8_revision.py`

**Interfaces:**
- Consumes: 当前第1—8章正文、图形资产和第二版字体字号基线。
- Produces: 第二章无重复标题、公有云通用结构独立成节、图形文字不溢出、中文宋体且英文数字为Times New Roman的当前稿。

- [ ] **Step 1: 写入第二章结构、图7.2文字边界和中英文字体合同并运行失败基线**
- [ ] **Step 2: 把第二章重排为公有云服务体系、国内产品、国外产品和选择比较四个连续层次**
- [ ] **Step 3: 重绘图7.2并统一现有SVG字体栈、字号、模块内边距和箭头走向**
- [ ] **Step 4: 在Open XML生成层统一中文、英文数字字体并保持第二版标题字号**
- [ ] **Step 5: 运行定向测试和全量回归测试**

### Task 10: 完成Nova至Horizon部署部分

**Files:**
- Create: `third-edition-work/revision/fragments/ch09.md` 至 `ch13.md`
- Create: `third-edition-work/revision/figures/ch9` 至 `ch13` 中的教材示意图
- Create: `third-edition-work/revision/figures/ch09-figure-manifest.json` 至 `ch13-figure-manifest.json`
- Create: `third-edition-work/revision/tables/ch09-table-manifest.json` 至 `ch13-table-manifest.json`
- Modify: `third-edition-work/revision/revision-map-ch01-08.json`
- Modify: `third-edition-work/tools/build_chapters_1_8_review_docx.py`
- Modify in place: `D:/codex/云计算教材更新/云计算基础架构平台构建与应用（第三版第1-3章审阅稿-20260815-04修复版）.docx`

**Interfaces:**
- Consumes: 第二版第9—13章可借鉴叙事、本地手工部署记录、当前第1—8章环境和配置参数。
- Produces: Nova、Neutron、Cinder、Swift、Horizon及平台初始化的纯手工教材正文，并回写唯一当前正式稿。

- [ ] **Step 1: 从第二版与已验证记录提取每章原理、组件、配置和严格先后关系**
- [ ] **Step 2: 先写章节层级、禁用语言、提示符、密码和手工步骤的失败合同**
- [ ] **Step 3: 完成第9章Nova与第10章Neutron正文、图表和配置**
- [ ] **Step 4: 完成第11章Cinder、第12章Swift和第13章Horizon正文、图表和配置**
- [ ] **Step 5: 确保命令均带系统提示符，数据库、身份、端点、配置、同步和启服均为逐条手工操作**
- [ ] **Step 6: 生成全章图表，逐图渲染检查文字溢出、箭头覆盖和字号**
- [ ] **Step 7: 在临时副本中替换第9—13章，Word打开及PDF视觉检查通过后原子覆盖当前稿**
- [ ] **Step 8: 运行全量测试、包结构检查和最终字体图表审计**
