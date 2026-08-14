# 第1—2章叙事化正文与真实图片增强实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 清除第1—2章正文和图片中的编写规则性表述，并在保持第二版版式的前提下加入2幅数据中心实景图和7幅官方产品截图。

**Architecture:** 书稿正文、图片清单、来源登记和Word构建工具彼此分离。正文只保留知识叙述；图片清单控制图号、文件和插入宽度；来源登记保存网址、权利人和获取日期；Word工具只按清单插图和生成图注。

**Tech Stack:** Markdown、JSON、SVG、PNG、Python、Pillow、Microsoft Word COM、PyMuPDF、pytest。

## Global Constraints

- 只修改第1—2章，不覆盖第三版工作母稿。
- 正文和图片均不得出现教材编写规则、免责声明、资料筛选过程或作者工作说明。
- 第1章最终7幅图，第2章最终14幅图，均按“图1.1”“图2.1”连续编号。
- 正文宋体10.5磅；图注宋体9磅、加粗、居中；图片文字保持可读。
- 每幅图片必须先由正文引用，图片后必须有对象或功能分析。
- 第3章及后续正文必须与当前工作母稿一致。
- 图片原始文件与书稿裁剪文件分开保存，来源信息不写入叙事正文。

---

### Task 1: 建立叙事正文和真实图片合同

**Files:**
- Modify: `third-edition-work/tests/test_second_base_revision.py`
- Modify: `third-edition-work/revision/figures/ch01-02-figure-manifest.json`

**Interfaces:**
- Consumes: `ch01.md`、`ch02.md`、当前12幅图清单。
- Produces: 规则性表述拒绝列表、7/14图号合同、真实图片来源字段合同。

- [ ] **Step 1: 添加正文规则性表述拒绝测试**

测试同时扫描两个Markdown片段及所有SVG可见文字，拒绝“教材不能”“本章保留”“图中不”“使用时核对”“仅供参考”“不作为结论”等作者说明式语句。

- [ ] **Step 2: 添加图号、引用与来源测试**

断言第1章图号精确为图1.1—图1.7，第2章精确为图2.1—图2.14；每个标记恰好出现一次；标记前有“如图X.X所示”等引用；标记后存在解释段。真实图片记录必须包含`kind`、`source_page`、`rights_owner`、`accessed_on`、`raw`和`png`。

- [ ] **Step 3: 运行测试并确认RED**

Run: `python -m pytest third-edition-work/tests/test_second_base_revision.py -k "narrative_only or real_image" -q`

Expected: 因现有规则性语句、图号数量和真实图片记录缺失而失败。

- [ ] **Step 4: 提交测试合同**

```powershell
git add third-edition-work/tests/test_second_base_revision.py
git commit -m "test: require narrative prose and real images"
```

---

### Task 2: 收集并登记真实图片

**Files:**
- Create: `third-edition-work/revision/figures/real-image-sources.json`
- Create: `third-edition-work/revision/figures/ch01/raw/`
- Create: `third-edition-work/revision/figures/ch02/raw/`
- Create: `third-edition-work/revision/figures/ch01/图1.2.png`
- Create: `third-edition-work/revision/figures/ch01/图1.4.png`
- Create: `third-edition-work/revision/figures/ch02/图2.2.png`
- Create: `third-edition-work/revision/figures/ch02/图2.4.png`
- Create: `third-edition-work/revision/figures/ch02/图2.6.png`
- Create: `third-edition-work/revision/figures/ch02/图2.8.png`
- Create: `third-edition-work/revision/figures/ch02/图2.9.png`
- Create: `third-edition-work/revision/figures/ch02/图2.12.png`
- Create: `third-edition-work/revision/figures/ch02/图2.13.png`

**Interfaces:**
- Consumes: 官方文档或开放许可图片页面。
- Produces: 2幅数据中心实景图、7幅产品截图及机器可读来源登记。

- [ ] **Step 1: 搜索并筛选来源**

数据中心图片选择两幅具有明确开放许可的高清实景；产品截图分别覆盖VMware Cloud Foundation、Citrix DaaS、Windows Admin Center或Azure Local、华为云Stack、ZStack、阿里云控制台和AWS管理控制台。产品图片只使用厂商官网、官方文档或官方公开演示资料。

- [ ] **Step 2: 保存原始文件与来源登记**

每条记录保存图号、标题、原始页面、直接图片地址、权利人、访问日期`2026-08-14`、原始文件相对路径、书稿PNG相对路径和裁剪说明。原始文件不得覆盖或二次压缩。

- [ ] **Step 3: 生成书稿裁剪图**

保持界面核心区域，删除网页导航、Cookie提示和无关空白，不重绘产品界面；只允许增加不遮挡界面的编号框。输出至少1600像素宽的PNG，确保按13.5—14厘米插入后文字可读。

- [ ] **Step 4: 逐图视觉检查**

检查截图没有模糊、拉伸、裁切文字、私人账号信息、真实密钥、Cookie或登录信息；图片内部没有免责声明或教材规则性说明。

- [ ] **Step 5: 提交真实图片资源**

```powershell
git add third-edition-work/revision/figures/real-image-sources.json third-edition-work/revision/figures/ch01 third-edition-work/revision/figures/ch02
git commit -m "docs: add real cloud infrastructure images"
```

---

### Task 3: 重写叙事正文并重新编号

**Files:**
- Modify: `third-edition-work/revision/fragments/ch01.md`
- Modify: `third-edition-work/revision/fragments/ch02.md`
- Modify: `third-edition-work/revision/figures/ch01-02-figure-manifest.json`
- Modify: `third-edition-work/revision/figures/figure-plan.csv`
- Rename: 原12幅架构图的SVG和PNG，使其与7/14连续图号一致。

**Interfaces:**
- Consumes: Task 1合同和Task 2图片资源。
- Produces: 纯叙事正文、连续图号、21幅图的统一清单。

- [ ] **Step 1: 清除正文中的作者说明**

逐段改写导读、产业数据、厂商比较和本章小结，把“教材如何选择信息”的句子改成对技术对象、产业事实或用户责任的直接叙述。

- [ ] **Step 2: 插入数据中心实景图引用与分析**

在云计算环境组成与资源池化相关段落中加入图1.2和图1.4。图后分别解释机柜、服务器、网络与供电环境，以及监控、运维和资源管理场景。

- [ ] **Step 3: 插入产品截图引用与分析**

在五个厂商与产品小节中加入7幅截图。图后解释控制台导航、资源对象、集群或资源位置、项目与区域、监控与服务目录，不写按钮操作步骤和版本免责声明。

- [ ] **Step 4: 更新架构图图号和清单**

第1章最终顺序为：计算模式、数据中心实景、云环境组成、运行环境实景、责任边界、市场结构、趋势。第2章最终顺序为：VMware架构/界面、Citrix架构/界面、Hyper-V架构/界面、国内私有云架构/两种界面、信创生态、公有云层次/两种界面、选择框架。

- [ ] **Step 5: 运行合同并确认GREEN**

Run: `python -m pytest third-edition-work/tests/test_second_base_revision.py -q`

Expected: 全部测试通过。

- [ ] **Step 6: 提交正文和清单**

```powershell
git add third-edition-work/revision/fragments/ch01.md third-edition-work/revision/fragments/ch02.md third-edition-work/revision/figures
git commit -m "docs: integrate real images into chapters 1 and 2"
```

---

### Task 4: 更新Word构建并生成审阅稿

**Files:**
- Modify: `third-edition-work/tools/build_chapters_1_2_review_docx.py`
- Create: `D:/codex/云计算教材更新/云计算基础架构平台构建与应用（第三版第1-2章审阅稿-20260814-04）.docx`
- Create: `D:/codex/云计算教材更新/云计算基础架构平台构建与应用（第三版第1-2章审阅稿-20260814-04）.pdf`

**Interfaces:**
- Consumes: 21条统一图片清单和更新后的第1—2章Markdown。
- Produces: 基于第二版样式的Word与PDF审阅稿。

- [ ] **Step 1: 让构建工具按清单验证连续图号**

将固定的5/7图号检查改为根据清单验证第1章1—7、第2章1—14；继续要求每个图片标记唯一、输出文件不存在、图片文件可读。

- [ ] **Step 2: 生成新的边界候选稿**

Run: `python third-edition-work/tools/revise_second_edition.py --source "D:/codex/云计算教材更新/云计算基础架构平台构建与应用（第三版工作母稿）.docx" --map third-edition-work/revision/revision-map-ch01-02.json --output "D:/codex/云计算教材更新/云计算基础架构平台构建与应用（第三版第1-2章审阅稿-20260814-04-base）.docx"`

- [ ] **Step 3: 插图并导出Word/PDF**

Run: `python third-edition-work/tools/build_chapters_1_2_review_docx.py --input "D:/codex/云计算教材更新/云计算基础架构平台构建与应用（第三版第1-2章审阅稿-20260814-04-base）.docx" --output-docx "D:/codex/云计算教材更新/云计算基础架构平台构建与应用（第三版第1-2章审阅稿-20260814-04）.docx" --output-pdf "D:/codex/云计算教材更新/云计算基础架构平台构建与应用（第三版第1-2章审阅稿-20260814-04）.pdf" --manifest third-edition-work/revision/figures/ch01-02-figure-manifest.json`

- [ ] **Step 4: 检查Word结构和PDF页面**

确认21幅图片、21条相邻图注、正文宋体10.5磅、图注宋体9磅加粗、内部层级无正文缩进、第3章以后文字与输入候选完全一致；渲染所有含图页面并检查图片清晰度和裁切。

- [ ] **Step 5: 提交构建工具**

```powershell
git add third-edition-work/tools/build_chapters_1_2_review_docx.py
git commit -m "tools: build illustrated chapters 1 and 2 review"
```

---

### Task 5: 最终回归与交付

**Files:**
- Verify: 第1—2章Markdown、21幅图、来源登记、Word和PDF。

**Interfaces:**
- Consumes: Tasks 1—4全部产物。
- Produces: 可供教师审阅的第1—2章最终审阅稿。

- [ ] **Step 1: 运行全部正文与图片测试**

Run: `python -m pytest third-edition-work/tests/test_second_base_revision.py -q`

- [ ] **Step 2: 运行既有部署合同回归**

Run: `python -m pytest third-edition-work/tests/test_deployment_contract.py -q`

- [ ] **Step 3: 检查差异和敏感信息**

Run: `git diff --check`

扫描正文、来源登记和截图文件名，确认无密码、令牌、Cookie、个人账号和登录信息。

- [ ] **Step 4: 输出审阅链接并停止**

只向用户提供`-04.docx`、`-04.pdf`和两章图片文件夹，明确停在第1—2章等待反馈，不进入第3章。
