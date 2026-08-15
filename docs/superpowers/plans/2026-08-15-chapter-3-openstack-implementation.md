# 第三章 OpenStack技术与生态体系 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 以第二版Word书稿为版式底板，完成第三章“OpenStack技术简介”和“OpenStack生态体系”的教材正文、9幅图、4张表及独立DOCX/PDF审阅稿。

**Architecture:** 内容层以官方资料登记、章节Markdown、图表清单三个独立接口组织；构建层沿用第一、二章已经验证的OpenXML局部替换和Word插图/表格流程。第三章候选稿以第1—2章审阅稿08为输入，只替换第三章范围，第四章以后不得漂移。

**Tech Stack:** OpenStack/OpenInfra官方资料、Markdown、JSON/CSV、SVG/PNG、Python pytest、Open XML、Microsoft Word COM、PDF视觉抽查。

## Global Constraints

- 3.2标题必须为“OpenStack生态体系”。
- 资料截止日期为2026年7月31日；Gazpacho写为已发布，Hibiscus写为开发中，Antelope写为教材实验版本。
- 正文采用第二版宋体、字号、行距、首行缩进和两端对齐，不使用等线。
- 节内层级依次使用“一．二．”和“1．2．”。
- 图按“图3.1”连续编号，表按“表3-1”连续编号；图片、表格后均不得设置“注：”。
- 正文不得出现“教学活动”“不宜把”“编写规则”“产品名称还原”等编辑性语言。
- 不加入Python程序、部署脚本、验证报告、测试日志、Windows Server 2012及远程桌面操作。
- 不安装、重装或修改OpenStack；Horizon截图只读采集，隐藏账号、令牌、资源UUID和浏览器会话信息。

---

### Task 1: 冻结官方资料与章节事实边界

**Files:**
- Create: `third-edition-work/revision/research/ch03-official-research-20260815.md`
- Create: `third-edition-work/revision/research/ch03-sources-20260815.json`

**Interfaces:**
- Consumes: OpenStack release、install guide、project navigator、governance和OpenInfra官方页面。
- Produces: 可供正文逐项引用的版本、架构、治理和项目事实，以及来源URL、页面标题、访问日期和用途字段。

- [ ] **Step 1: 汇总已经完成的官方资料研究**

研究文件按“事实—教材表述—来源”三列组织，至少覆盖逻辑架构、核心服务、常用扩展项目、发布周期、SLURP、Gazpacho、Hibiscus和Antelope。

- [ ] **Step 2: 写入机器可核对的来源登记**

`ch03-sources-20260815.json` 使用以下字段：

```json
{
  "cutoff_date": "2026-07-31",
  "sources": [
    {
      "id": "openstack-logical-architecture",
      "title": "Logical architecture",
      "publisher": "OpenStack",
      "url": "https://docs.openstack.org/install-guide/get-started-logical-architecture.html",
      "accessed": "2026-08-15",
      "supports": ["图3.3", "3.1 OpenStack的逻辑架构"]
    }
  ]
}
```

- [ ] **Step 3: 验证来源登记**

Run:

```powershell
python -m json.tool third-edition-work/revision/research/ch03-sources-20260815.json > $null
rg -n "Gazpacho|Hibiscus|Antelope|SLURP|logical architecture" third-edition-work/revision/research/ch03-official-research-20260815.md
```

Expected: JSON退出码为0；研究文件中五类事实均有官方来源。

- [ ] **Step 4: Commit**

```powershell
git add third-edition-work/revision/research/ch03-official-research-20260815.md third-edition-work/revision/research/ch03-sources-20260815.json
git commit -m "docs: research OpenStack chapter sources"
```

### Task 2: 先建立第三章内容和图表契约

**Files:**
- Create: `third-edition-work/tests/test_chapter3_revision.py`
- Modify: `third-edition-work/revision/fragments/ch03.md`

**Interfaces:**
- Consumes: 已批准设计说明和第二版第三章边界。
- Produces: 对章节标题、层级、事实、禁用语言、图表引用和正文篇幅的可执行约束。

- [ ] **Step 1: 写结构和语言的失败测试**

```python
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHAPTER = ROOT / "third-edition-work" / "revision" / "fragments" / "ch03.md"


def chapter_text() -> str:
    return CHAPTER.read_text(encoding="utf-8")


def test_chapter3_has_approved_two_section_structure():
    text = chapter_text()
    assert text.count("## 3.1 OpenStack技术简介") == 1
    assert text.count("## 3.2 OpenStack生态体系") == 1
    assert "体验原生OpenStack云平台" not in text


def test_chapter3_uses_textbook_levels_and_avoids_editorial_language():
    text = chapter_text()
    for heading in ("一．", "二．", "1．", "2．"):
        assert heading in text
    for banned in ("教学活动", "不宜把", "编写规则", "产品名称还原", "学生应当"):
        assert banned not in text


def test_chapter3_has_continuous_figure_and_table_references():
    text = chapter_text()
    for number in range(1, 10):
        assert f"图3.{number}" in text
    for number in range(1, 5):
        assert f"表3-{number}" in text
    assert "注：" not in text
```

- [ ] **Step 2: 运行测试并确认RED**

Run:

```powershell
python -m pytest third-edition-work/tests/test_chapter3_revision.py -v
```

Expected: 因旧3.2标题、缺少图表引用或禁用内容而失败，不得因导入错误失败。

- [ ] **Step 3: 增加版本和内容完整性测试**

```python
def test_chapter3_keeps_version_boundaries_precise():
    text = chapter_text()
    assert "2026.1 Gazpacho" in text
    assert "2026年4月1日" in text
    assert "2026.2 Hibiscus" in text
    assert "开发" in text
    assert "Antelope" in text
    assert "教学" in text


def test_chapter3_has_textbook_scale_and_no_deployment_code():
    text = chapter_text()
    assert len("".join(text.split())) >= 14000
    for banned in ("```python", "paramiko", "pytest", "audit", "Windows Server 2012", "远程桌面"):
        assert banned not in text
```

- [ ] **Step 4: 再次运行并保留RED证据**

Run: `python -m pytest third-edition-work/tests/test_chapter3_revision.py -v`

Expected: 篇幅和事实边界测试失败，证明测试能够识别当前旧稿。

### Task 3: 重写第三章正文并制作4张原生表格

**Files:**
- Modify: `third-edition-work/revision/fragments/ch03.md`
- Create: `third-edition-work/revision/tables/ch03-table-manifest.json`

**Interfaces:**
- Consumes: Task 1事实登记和Task 2测试。
- Produces: 14,000—18,000汉字的连续教材正文，正文内含9个插图标记和4个表格标记。

- [ ] **Step 1: 写3.1正文**

按“产生与发展—逻辑架构—核心服务—版本演进—信创基础设施”顺序写作。核心服务逐项解释资源对象和服务关系，扩展内容不得提前进入3.2。

- [ ] **Step 2: 写3.2正文**

按“项目生态—访问生态—资源对象—部署形态—Antelope教学云”顺序写作。只解释Horizon、CLI、API、SDK和资源页面的关系，不写逐步点击说明。

- [ ] **Step 3: 插入图表标记并在正文引用**

正文标记精确使用：

```text
{{FIGURE:图3.1}}
{{TABLE:表3-1}}
```

每个标记前的段落必须出现同一编号并分析图表信息；不得在标记后添加“注：”。

- [ ] **Step 4: 定义4张Word原生表格**

`ch03-table-manifest.json` 依次登记：

```json
[
  {"number": "表3-1", "title": "OpenStack核心服务及其主要资源对象"},
  {"number": "表3-2", "title": "OpenStack常用扩展项目及典型应用场景"},
  {"number": "表3-3", "title": "Antelope、Gazpacho与Hibiscus版本状态比较"},
  {"number": "表3-4", "title": "OpenStack访问方式比较"}
]
```

每条记录补充`columns`和`rows`，表内不写网址、访问日期或备注段。

- [ ] **Step 5: 运行GREEN和语言扫描**

Run:

```powershell
python -m pytest third-edition-work/tests/test_chapter3_revision.py -v
rg -n "教学活动|不宜把|编写规则|产品名称还原|学生应当|^注：|Windows Server 2012|远程桌面" third-edition-work/revision/fragments/ch03.md
```

Expected: 测试全部通过；`rg`无输出。

- [ ] **Step 6: Commit**

```powershell
git add third-edition-work/revision/fragments/ch03.md third-edition-work/revision/tables/ch03-table-manifest.json third-edition-work/tests/test_chapter3_revision.py
git commit -m "docs: rewrite OpenStack ecosystem chapter"
```

### Task 4: 制作9幅第三章图片

**Files:**
- Modify: `third-edition-work/revision/figures/figure-plan.csv`
- Create: `third-edition-work/revision/figures/ch03/图3.1.svg`
- Create: `third-edition-work/revision/figures/ch03/图3.1.png`
- Create: `third-edition-work/revision/figures/ch03/图3.2.svg`
- Create: `third-edition-work/revision/figures/ch03/图3.2.png`
- Create: `third-edition-work/revision/figures/ch03/图3.3.svg`
- Create: `third-edition-work/revision/figures/ch03/图3.3.png`
- Create: `third-edition-work/revision/figures/ch03/图3.4.svg`
- Create: `third-edition-work/revision/figures/ch03/图3.4.png`
- Create: `third-edition-work/revision/figures/ch03/图3.5.svg`
- Create: `third-edition-work/revision/figures/ch03/图3.5.png`
- Create: `third-edition-work/revision/figures/ch03/图3.6.svg`
- Create: `third-edition-work/revision/figures/ch03/图3.6.png`
- Create: `third-edition-work/revision/figures/ch03/图3.7.svg`
- Create: `third-edition-work/revision/figures/ch03/图3.7.png`
- Create: `third-edition-work/revision/figures/ch03/图3.8.png`
- Create: `third-edition-work/revision/figures/ch03/图3.9.png`
- Create: `third-edition-work/revision/figures/ch03-figure-manifest.json`

**Interfaces:**
- Consumes: 正文图号、官方架构事实、本地Horizon只读页面。
- Produces: 7幅重新绘制的高清图和2幅脱敏真实截图，供Word构建器按图号插入。

- [ ] **Step 1: 先写图片清单失败测试**

```python
import json


def test_chapter3_figure_manifest_is_complete():
    path = ROOT / "third-edition-work" / "revision" / "figures" / "ch03-figure-manifest.json"
    records = json.loads(path.read_text(encoding="utf-8"))
    assert [row["number"] for row in records] == [f"图3.{n}" for n in range(1, 10)]
    for row in records:
        image = ROOT / row["path"]
        assert image.is_file()
        assert image.stat().st_size >= 50_000
        assert "note" not in row
```

- [ ] **Step 2: 运行并确认RED**

Run: `python -m pytest third-edition-work/tests/test_chapter3_revision.py -k figure -v`

Expected: 清单或图片缺失而失败。

- [ ] **Step 3: 绘制图3.1—图3.7**

使用16:9或适合书稿版心的横向构图，导出至少2000像素宽的PNG。每图只保留标题所需的技术元素，不在图内写资料来源、编写规则、阅读提示或“注：”。

- [ ] **Step 4: 只读采集图3.8和图3.9**

通过已核验主机地址打开Horizon，登录后仅查看项目概览及资源列表；不创建、修改或删除资源。截图裁去浏览器密码、cookie、token、UUID和无关桌面区域；若平台不可达，改用OpenStack官方Horizon演示素材并在来源登记中说明。

- [ ] **Step 5: 运行图片质量验证**

Run:

```powershell
python -m pytest third-edition-work/tests/test_chapter3_revision.py -k figure -v
python third-edition-work/tools/validate_textbook_figures.py --manifest third-edition-work/revision/figures/ch03-figure-manifest.json
```

Expected: 图号连续、文件存在、像素和清晰度检查通过。

- [ ] **Step 6: Commit**

```powershell
git add third-edition-work/revision/figures/figure-plan.csv third-edition-work/revision/figures/ch03 third-edition-work/revision/figures/ch03-figure-manifest.json third-edition-work/tests/test_chapter3_revision.py
git commit -m "docs: add OpenStack chapter figures"
```

### Task 5: 合成第三章Word审阅稿并进行视觉检查

**Files:**
- Create: `third-edition-work/tools/build_chapter_3_review_docx.py`
- Create: `D:/codex/云计算教材更新/云计算基础架构平台构建与应用（第三版第1-3章审阅稿-20260815-01）.docx`
- Create: `D:/codex/云计算教材更新/云计算基础架构平台构建与应用（第三版第1-3章审阅稿-20260815-01）.pdf`

**Interfaces:**
- Consumes: 第1—2章审阅稿08、ch03.md、第三章图表清单和第二版样式模板。
- Produces: 第1—3章独立DOCX/PDF审阅稿；第四章以后保持输入文件内容不变。

- [ ] **Step 1: 写候选稿边界测试**

测试必须验证：3.2标题唯一、图表编号连续、新增正文有效字体为宋体、第四章以后XML不漂移、图片均有题注且题注后无“注：”。

- [ ] **Step 2: 运行并确认RED**

Run: `python -m pytest third-edition-work/tests/test_chapter3_revision.py -k docx -v`

Expected: 构建器或候选稿缺失而失败。

- [ ] **Step 3: 实现局部构建器**

输入文件固定为：

```text
D:/codex/云计算教材更新/云计算基础架构平台构建与应用（第三版第1-2章审阅稿-20260815-08）.docx
```

构建器先在第三章边界内替换正文，再按清单插入9幅图片和4张Word原生表格，复制第二版正文、题注和表格样式；保存到全新路径，不覆盖输入文件。

- [ ] **Step 4: 生成DOCX和PDF**

Run:

```powershell
python third-edition-work/tools/build_chapter_3_review_docx.py --input "D:/codex/云计算教材更新/云计算基础架构平台构建与应用（第三版第1-2章审阅稿-20260815-08）.docx" --output-docx "D:/codex/云计算教材更新/云计算基础架构平台构建与应用（第三版第1-3章审阅稿-20260815-01）.docx" --output-pdf "D:/codex/云计算教材更新/云计算基础架构平台构建与应用（第三版第1-3章审阅稿-20260815-01）.pdf"
```

Expected: 两个输出文件存在且非空，构建器退出码为0。

- [ ] **Step 5: 运行完整验证**

Run:

```powershell
python -m pytest third-edition-work/tests/test_chapter3_revision.py -v
python -m pytest third-edition-work/tests/test_second_base_revision.py -v
git diff --check
```

Expected: 第三章focused和既有第二版母稿测试全部通过，diff检查无错误。

- [ ] **Step 6: 视觉抽查**

从PDF渲染第三章章首页、每张表、每幅架构图和两幅Horizon截图所在页，逐页检查宋体、字号、图题、表题、分页、裁切、重叠和空白页。发现视觉问题时先增加可复现检查，再修改构建器并重新生成。

- [ ] **Step 7: Commit**

```powershell
git add third-edition-work/tools/build_chapter_3_review_docx.py third-edition-work/tests/test_chapter3_revision.py
git commit -m "feat: build chapter 3 Word review draft"
```

### Task 6: 最终范围审计与交付

**Files:**
- Modify only if verification identifies a defect: files listed in Tasks 1—5.

**Interfaces:**
- Consumes: 全部第三章正文、图表、构建器及审阅稿。
- Produces: 可供用户直接打开审阅的DOCX/PDF及准确的版本记录。

- [ ] **Step 1: 核对Git范围**

Run: `git status --short`

Expected: `.playwright-cli/`和`tmp/`保持未跟踪且不提交；其余只包含本计划列出的第三章文件。

- [ ] **Step 2: 核对禁用内容与秘密信息**

Run:

```powershell
rg -n "教学活动|不宜把|编写规则|产品名称还原|^注：|qwer1234|OS_PASSWORD|token|cookie|[0-9a-fA-F]{32,}" third-edition-work/revision/fragments/ch03.md third-edition-work/revision/figures/ch03-figure-manifest.json
```

Expected: 无禁用语言和真实凭据、令牌、cookie、UUID或摘要输出。

- [ ] **Step 3: 记录文件哈希与页数**

计算DOCX/PDF SHA-256、文件大小和PDF页数，写入本任务报告；报告不得把测试过程写进教材正文。

- [ ] **Step 4: 提交最后修正并交付**

只有在Step 1—3全部通过后才报告完成，并向用户提供DOCX和PDF的绝对路径链接。
