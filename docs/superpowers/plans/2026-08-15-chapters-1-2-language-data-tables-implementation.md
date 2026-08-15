# 第1—2章语言、数据、图片与表格统一修订实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将第1—2章修订为纯叙事、宋体排版、具有历史图片、国际产业数据和原生Word比较表格的教材审阅稿。

**Architecture:** Markdown正文只保存教材叙述、图片标记和表格标记；图片清单与表格清单分别保存资源和结构化数据；Word构建工具在第二版边界稿中插入图片与原生表格，并统一第一章至第三章之间的有效东亚字体。所有动态数据及图片来源保存在独立登记文件中，不把作者工作说明写进正文。

**Tech Stack:** Markdown、JSON、CSV、Python、Open XML、Microsoft Word COM、PyMuPDF、pytest、官方网页与PDF资料。

## Global Constraints

- 只修改第1—2章及其资源、构建工具和测试。
- 不覆盖`云计算基础架构平台构建与应用（第三版工作母稿）.docx`。
- 新输出文件名使用`第三版第1-2章审阅稿-20260815-05`。
- 第3章及后续正文与输入边界稿逐段一致。
- 正文只讲定义、事实、因果、对象关系和案例，不出现作者写作规则。
- 表格编号使用`表1-1`、`表2-1`的分章编号。
- 价格比较口径为2核4GB Linux按需实例、同一中国内地或邻近区域、按小时计费、查询日期2026年8月15日。
- 第1—2章正文有效东亚字体为宋体10.5磅；图注宋体9磅加粗；表内文字不小于9磅。

---

### Task 1: 建立语言、数据、图片、表格与字体合同

**Files:**
- Modify: `third-edition-work/tests/test_second_base_revision.py`
- Create: `third-edition-work/revision/tables/ch01-02-table-manifest.json`

**Interfaces:**
- Consumes: 当前`ch01.md`、`ch02.md`、图片清单和Word构建工具。
- Produces: 规则性语言拒绝合同、图1.1—图1.9合同、表1-1—表1-3与表2-1—表2-2合同、国际数据合同和DOCX有效字体合同。

- [ ] **Step 1: 添加失败测试**

测试拒绝“每个数字都必须说明”“教材”“本文只”“使用时核对”“资料筛选”等作者说明式短语；要求1.1节出现两幅历史图片；要求第1章9幅图、第2章14幅图；要求5个表格标记唯一且清单字段完整；要求全球产业数据包含机构、年份、币种、实际或预测属性。

- [ ] **Step 2: 添加Word字体与表格失败测试**

对最终候选的第一章起点到第三章起点遍历正文段落和表格单元格，计算有效东亚字体；正文必须为宋体，表格必须为原生`w:tbl`，表题与表格相邻。

- [ ] **Step 3: 运行定向测试确认RED**

Run: `python -m pytest third-edition-work/tests/test_second_base_revision.py -k "editorial or historic or table_manifest or international_market or effective_font" -q`

Expected: 因历史图片、表格清单、国际数据和统一字体尚未实现而失败。

---

### Task 2: 调研并冻结权威来源

**Files:**
- Create: `third-edition-work/revision/research/ch01-02-sources-20260815.json`
- Create: `third-edition-work/revision/figures/ch01/raw/图1.1-original.*`
- Create: `third-edition-work/revision/figures/ch01/raw/图1.2-original.*`

**Interfaces:**
- Consumes: 权威统计机构、博物馆或档案馆、六个以上云厂商官方页面和价格页。
- Produces: 可追溯来源登记、两幅历史原图、全球产业数据和公有云平台比较字段。

- [ ] **Step 1: 收集国际产业数据**

从Gartner、IDC、Synergy Research或同等权威一手公开资料中选择全球公有云总规模/支出与服务结构数据。每条记录包含机构、标题、统计对象、年份、actual_or_forecast、数值、币种、发布日期、页面URL和访问日期。

- [ ] **Step 2: 收集历史图片**

选择大型主机/字符终端和客户机—服务器时代各1幅高清开放许可图片，保存原始文件、权利人、许可、来源页、直接图片地址和SHA-256。

- [ ] **Step 3: 收集公有云比较资料**

至少登记AWS、Microsoft Azure、Google Cloud、阿里云、华为云、腾讯云的官网、主要服务方式、计费方式、价格页或计算器。可补充百度智能云、火山引擎或天翼云；所有信息来自厂商官方页面。

- [ ] **Step 4: 校验来源一致性**

检查所有URL可访问、时间和币种明确、预测与实际未混写、同一价格单位未误换算；计算两幅原图哈希并写入登记文件。

---

### Task 3: 重写正文并加入表格标记

**Files:**
- Modify: `third-edition-work/revision/fragments/ch01.md`
- Modify: `third-edition-work/revision/fragments/ch02.md`
- Create: `third-edition-work/revision/tables/ch01-02-table-manifest.json`

**Interfaces:**
- Consumes: Task 2来源登记和已批准表格字段。
- Produces: 纯叙事正文、五个唯一表格标记和结构化表格数据。

- [ ] **Step 1: 全文清除作者规则语言**

逐段重写第1—2章，将统计口径说明、资料筛选、教材取舍、动态信息核对等作者说明改为产业事实、对象关系或适用条件。保留定义、技术限制、共同责任、教学活动和思政内容。

- [ ] **Step 2: 补充国际产业事实**

在1.4节加入全球云计算总体规模和服务结构，明确实际值与预测值属性；与中国信通院2024年数据形成国内外两条并列叙事，不直接相加。

- [ ] **Step 3: 插入五个表格标记**

加入`{{TABLE:表1-1}}`计算模式比较、`{{TABLE:表1-2}}`部署模式比较、`{{TABLE:表1-3}}`国内外产业数据、`{{TABLE:表2-1}}`产品路线比较、`{{TABLE:表2-2}}`知名公有云平台比较。每个标记前有正文引用，表后有分析段。

- [ ] **Step 4: 填写结构化表格清单**

每张表包含number、title、anchor、columns、rows、column_widths_cm、font_pt和note字段。表2-2不少于6行，列出官网、服务方式、计费/价格口径及适用场景。

---

### Task 4: 加入历史图片并重新编号

**Files:**
- Modify: `third-edition-work/revision/figures/ch01-02-figure-manifest.json`
- Modify: `third-edition-work/revision/figures/figure-plan.csv`
- Modify: `third-edition-work/revision/figures/real-image-sources.json`
- Create/rename: `third-edition-work/revision/figures/ch01/图1.1.*` through `图1.9.*`

**Interfaces:**
- Consumes: 两幅历史原图与现有第1章7幅图。
- Produces: 第1章图1.1—图1.9连续序列和更新后的来源登记。

- [ ] **Step 1: 生成书稿用历史图片**

按不变形原则裁剪为高分辨率PNG，不在图片内部增加规则说明或来源文字；图片文字若存在，应在14厘米插入宽度下可读。

- [ ] **Step 2: 调整图号**

历史图片作为图1.1、图1.2；现有计算模式图顺延为图1.3，后续第1章图片依次顺延到图1.9。第2章图号不变。

- [ ] **Step 3: 更新正文引用与来源清单**

每幅图片在正文中先出现“如图X所示”，图片后首段不少于80个汉字并分析硬件形态或架构关系；来源登记哈希与文件逐项一致。

- [ ] **Step 4: 运行图片验证**

Run: `python third-edition-work/tools/validate_textbook_figures.py third-edition-work/revision/figures/ch01-02-figure-manifest.json`

Expected: 23幅图片全部存在，图号连续，原图哈希和尺寸通过。

---

### Task 5: 扩展Word构建工具并统一宋体

**Files:**
- Modify: `third-edition-work/tools/build_chapters_1_2_review_docx.py`
- Modify: `third-edition-work/tools/validate_textbook_figures.py`
- Modify: `third-edition-work/tests/test_second_base_revision.py`

**Interfaces:**
- Consumes: 23条图片清单、5张表格清单和边界候选DOCX。
- Produces: 含原生表格、统一字体、图片和PDF导出的最终审阅稿。

- [ ] **Step 1: 实现表格标记替换**

构建工具读取表格清单，要求每个标记恰好出现一次；由后向前将标记替换为Word原生表格，设置固定列宽、表头底纹、边框、单元格垂直居中、宋体9磅和表题。

- [ ] **Step 2: 实现章节范围字体规范化**

在第一章起点到第三章起点的Word范围内，正文样式和直接格式有效东亚字体统一为宋体；正文10.5磅，章节和小节标题保留原字号与加粗；图注与表题使用宋体9磅加粗。

- [ ] **Step 3: 更新图片连续性检查**

构建工具和验证器要求第1章图1.1—图1.9、第2章图2.1—图2.14，共23幅图。

- [ ] **Step 4: 运行测试确认GREEN**

Run: `python -m pytest third-edition-work/tests/test_second_base_revision.py -q`

Expected: 全部通过。

---

### Task 6: 生成和目视检查审阅稿

**Files:**
- Create: `D:/codex/云计算教材更新/云计算基础架构平台构建与应用（第三版第1-2章审阅稿-20260815-05-base）.docx`
- Create: `D:/codex/云计算教材更新/云计算基础架构平台构建与应用（第三版第1-2章审阅稿-20260815-05）.docx`
- Create: `D:/codex/云计算教材更新/云计算基础架构平台构建与应用（第三版第1-2章审阅稿-20260815-05）.pdf`

**Interfaces:**
- Consumes: 更新后的正文、图片、表格和构建工具。
- Produces: 供教师审阅的Word/PDF和独立图片资源。

- [ ] **Step 1: 生成边界候选**

使用`revise_second_edition.py`从第三版工作母稿生成新的`-05-base.docx`，拒绝覆盖现有文件。

- [ ] **Step 2: 插入图片、表格并导出PDF**

使用更新后的Word构建工具生成`-05.docx`和`-05.pdf`。

- [ ] **Step 3: 结构检查**

检查23幅图片、23条图注、5个原生表格、5条表题、正文宋体和第三章后逐段一致。

- [ ] **Step 4: 逐页视觉检查**

渲染第1—2章全部页面，检查表格不溢出、跨页表头合理、图片清晰、图注相邻、正文无等线、页面层级与第二版一致。

---

### Task 7: 回归、提交和交付

**Files:**
- Verify: 本计划全部文件和`-05`审阅稿。

**Interfaces:**
- Consumes: Tasks 1—6全部产物。
- Produces: 已验证提交、远程同步和用户审阅链接。

- [ ] **Step 1: 运行全部正文与版式测试**

Run: `python -m pytest third-edition-work/tests/test_second_base_revision.py -q`

- [ ] **Step 2: 运行部署合同回归**

Run: `python -m pytest third-edition-work/tests/test_deployment_contract.py -q`

- [ ] **Step 3: 检查差异与敏感信息**

运行`git diff --check`，扫描真实账号、密码、令牌、Cookie、私钥和截图中的个人信息；确认未提交临时目录。

- [ ] **Step 4: 提交并同步**

只暂存本任务文件，提交到`third-edition`分支并推送远程仓库。

- [ ] **Step 5: 交付并停止**

向用户提供`-05.docx`、`-05.pdf`、图片文件夹和表格来源登记链接，停在第1—2章等待反馈。
