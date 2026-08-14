# Chapters 1–2 Structure and Visual Revision Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild Chapters 1 and 2 as layered, appropriately detailed, image-rich textbook chapters while preserving the second-edition Word typography and page design.

**Architecture:** Markdown fragments remain the authoritative text source. A figure manifest binds numbered SVG/PNG assets to explicit in-text anchors, and a Word automation step inserts the reviewed figures and captions into a heading-bounded candidate derived from the current work mother. Automated contracts check hierarchy, length, citations, font metadata, figure cross-references, and chapter boundaries; final acceptance includes Word-to-PDF rendering and visual inspection.

**Tech Stack:** UTF-8 Markdown, Python 3, pytest, Open XML, Microsoft Word COM automation, SVG, PNG, headless Chromium/Puppeteer or CairoSVG for export, PyMuPDF/Poppler for rendered-page inspection.

## Global Constraints

- Modify only Chapters 1 and 2; Chapter 3 and later content must remain outside the edited heading ranges.
- Preserve the second-edition page geometry, headings, headers, footers, body rhythm, and caption treatment.
- Body text is 宋体 10.5 pt; captions are 宋体 9 pt bold and centered.
- Figure text is 宋体 10.5 pt by default and never smaller than 9 pt.
- Internal levels use `一．……` and `1．……`, remain body paragraphs, and do not enter the table of contents.
- Figure numbering is chapter-local: `图1.1` through `图1.5`, and `图2.1` through `图2.7`.
- Every figure must be cited before it appears and followed by prose explaining its elements and relationships.
- Chapter 1 target length is 14,000–18,000 non-whitespace characters; Chapter 2 target length is 18,000–23,000.
- Chapter 2 retains the five-section skeleton of the second edition while updating product names and architectures through July 2026.
- Use only verified 2024 actual CAICT market figures; do not present 2025E values as actuals.
- Keep the work mother unchanged until the user approves the independent Chapters 1–2 review copy.

---

### Task 1: Add Chapter Structure and Figure Contracts

**Files:**
- Modify: `third-edition-work/tests/test_second_base_revision.py`
- Modify: `third-edition-work/revision/figures/figure-plan.csv`
- Create: `third-edition-work/revision/figures/ch01-02-figure-manifest.json`

**Interfaces:**
- Consumes: current `ch01.md`, `ch02.md`, `revision-map.json`, and the second-edition style baseline.
- Produces: a machine-readable manifest with `number`, `title`, `svg`, `png`, `anchor`, `minimum_font_pt`, and `source_note` fields; focused tests used by Tasks 2–5.

- [x] **Step 1: Write failing hierarchy and length tests**

Add tests that require all four Chapter 1 H2 headings, the five restored Chapter 2 H2 headings, at least two `一．` paragraphs per section, nested `1．` paragraphs under the major concepts, and the approved target lengths.

```python
def test_chapters_1_2_have_second_edition_internal_levels_and_depth():
    ch1 = task3_fragment(1)
    ch2 = task3_fragment(2)
    assert 14_000 <= compact_length(ch1) <= 18_000
    assert 18_000 <= compact_length(ch2) <= 23_000
    assert [line for line in ch2.splitlines() if line.startswith("## ")] == [
        "## 2.1 VMware的云计算技术及其相关产品",
        "## 2.2 Citrix的云计算技术",
        "## 2.3 微软私有云虚拟化技术Hyper-V",
        "## 2.4 国内私有云相关产品",
        "## 2.5 知名公有云平台简介",
    ]
    for chapter in (ch1, ch2):
        assert len(re.findall(r"(?m)^一．", chapter)) >= 1
        assert len(re.findall(r"(?m)^1．", chapter)) >= 1
```

- [x] **Step 2: Write failing figure-contract tests**

Require exactly 12 manifest records, unique chapter-local numbers, SVG and PNG paths, a minimum text size of 9 pt, an in-text forward reference, a caption, and explanatory prose after each figure marker.

```python
def test_chapters_1_2_figure_manifest_and_cross_references_are_complete():
    records = load_chapter_figure_manifest()
    assert [item["number"] for item in records] == [
        "图1.1", "图1.2", "图1.3", "图1.4", "图1.5",
        "图2.1", "图2.2", "图2.3", "图2.4", "图2.5", "图2.6", "图2.7",
    ]
    for item in records:
        assert item["minimum_font_pt"] >= 9
        chapter = task3_fragment(int(item["number"][1]))
        assert f"如{item['number']}所示" in chapter
        assert f"{{{{FIGURE:{item['number']}}}}}" in chapter
```

- [x] **Step 3: Run focused tests and confirm RED**

Run: `python -m pytest third-edition-work/tests/test_second_base_revision.py -k "chapters_1_2" -q`

Expected: failures for the old Chapter 2 headings, insufficient length, absent hierarchy, and absent manifest/assets.

- [x] **Step 4: Create the exact 12-record manifest**

Use these titles and file paths:

```json
[
  {"number":"图1.1","title":"计算模式演变与资源服务化","svg":"figures/ch01/图1.1.svg","png":"figures/ch01/图1.1.png","minimum_font_pt":10.5},
  {"number":"图1.2","title":"云计算环境的组成","svg":"figures/ch01/图1.2.svg","png":"figures/ch01/图1.2.png","minimum_font_pt":10.5},
  {"number":"图1.3","title":"云服务层次与责任边界","svg":"figures/ch01/图1.3.svg","png":"figures/ch01/图1.3.png","minimum_font_pt":9.0},
  {"number":"图1.4","title":"2024年我国云计算市场结构","svg":"figures/ch01/图1.4.svg","png":"figures/ch01/图1.4.png","minimum_font_pt":10.5},
  {"number":"图1.5","title":"云计算技术与治理趋势","svg":"figures/ch01/图1.5.svg","png":"figures/ch01/图1.5.png","minimum_font_pt":9.0},
  {"number":"图2.1","title":"VMware Cloud Foundation私有云逻辑架构","svg":"figures/ch02/图2.1.svg","png":"figures/ch02/图2.1.png","minimum_font_pt":9.0},
  {"number":"图2.2","title":"Citrix DaaS应用与桌面交付架构","svg":"figures/ch02/图2.2.svg","png":"figures/ch02/图2.2.png","minimum_font_pt":9.0},
  {"number":"图2.3","title":"Hyper-V与Azure Local混合基础设施架构","svg":"figures/ch02/图2.3.svg","png":"figures/ch02/图2.3.png","minimum_font_pt":9.0},
  {"number":"图2.4","title":"国内私有云通用技术架构","svg":"figures/ch02/图2.4.svg","png":"figures/ch02/图2.4.png","minimum_font_pt":9.0},
  {"number":"图2.5","title":"国产信创云生态架构","svg":"figures/ch02/图2.5.svg","png":"figures/ch02/图2.5.png","minimum_font_pt":9.0},
  {"number":"图2.6","title":"国内外公有云稳定能力层次","svg":"figures/ch02/图2.6.svg","png":"figures/ch02/图2.6.png","minimum_font_pt":9.0},
  {"number":"图2.7","title":"云产品比较与选择框架","svg":"figures/ch02/图2.7.svg","png":"figures/ch02/图2.7.png","minimum_font_pt":9.0}
]
```

Update the Chapter 1 and Chapter 2 rows in `figure-plan.csv` to the same five-plus-seven target figures. Keep the historical second-edition figure disposition rows, but remove the superseded four-plus-two target plan so that the CSV and manifest have one consistent numbering contract.

- [x] **Step 5: Commit the RED contracts and manifest**

```powershell
git add third-edition-work/tests/test_second_base_revision.py third-edition-work/revision/figures/ch01-02-figure-manifest.json
git commit -m "test: define chapters 1 and 2 visual contracts"
```

---

### Task 2: Rewrite Chapter 1 with Layered Explanations

**Files:**
- Modify: `third-edition-work/revision/fragments/ch01.md`
- Modify: `third-edition-work/tests/test_second_base_revision.py`

**Interfaces:**
- Consumes: the five Chapter 1 manifest records and `third-edition-work/research/part1-official-research-2026-07.md`.
- Produces: a 14,000–18,000-character Chapter 1 fragment with five figure markers and complete forward references/explanations.

- [ ] **Step 1: Lock the exact internal outline in a failing test**

Require these first-level internal headings, with Arabic-number subheads beneath the detailed topics:

```text
1.1 一．字符终端—主机模式；二．客户机—服务器模式；三．集群与分布式计算；四．虚拟化、资源池化与云计算
1.2 一．云计算定义；二．五个基本特征；三．云计算环境的组成；四．云计算的责任边界
1.3 一．云服务层次；二．云部署模型；三．云—边—端协同
1.4 一．产业规模与结构；二．云原生与智算云；三．边缘云与分布式云；四．成本、绿色与可信治理；五．国产云生态
```

- [ ] **Step 2: Run the Chapter 1 outline test and confirm RED**

Run: `python -m pytest third-edition-work/tests/test_second_base_revision.py -k "chapter_1_layered_outline" -q`

Expected: FAIL because the existing text has no internal numbered hierarchy or figure markers.

- [ ] **Step 3: Rewrite `ch01.md`**

Use continuous textbook prose around the approved hierarchy. Expand the definition, five characteristics, cloud environment, responsibility boundary, service/deployment models, and 2026 technology/governance trends. Keep historical computing modes and volatile product examples concise. Insert all five markers only after forward references, for example:

```markdown
计算模式的变化不是简单的设备替换，而是资源组织和服务交付方式的连续演变，如图1.1所示。

{{FIGURE:图1.1}}

图1.1从左到右给出四个阶段。字符终端—主机模式强调集中共享……
```

- [ ] **Step 4: Verify CAICT facts and prohibited claims**

Require the verified values `8288亿元`, `34.4%`, `6216亿元`, `2072亿元`, and `4201亿元`; reject `2025年实际达到10857亿元`, unsupported rankings, and market-share claims.

- [ ] **Step 5: Run Chapter 1 focused tests and confirm GREEN**

Run: `python -m pytest third-edition-work/tests/test_second_base_revision.py -k "chapter_1 or chapters_1_2" -q`

Expected: all Chapter 1 structure, length, fact-boundary, and cross-reference tests pass; Chapter 2 asset tests may remain RED.

- [ ] **Step 6: Commit Chapter 1**

```powershell
git add third-edition-work/revision/fragments/ch01.md third-edition-work/tests/test_second_base_revision.py
git commit -m "docs: deepen cloud computing fundamentals"
```

---

### Task 3: Restore and Modernize the Five-Section Chapter 2

**Files:**
- Modify: `third-edition-work/revision/fragments/ch02.md`
- Modify: `third-edition-work/tests/test_second_base_revision.py`
- Modify: `third-edition-work/research/part1-official-research-2026-07.md`

**Interfaces:**
- Consumes: seven Chapter 2 manifest records and official VMware, Citrix, Microsoft, openEuler/OpenStack, domestic private-cloud, and public-cloud product boundaries.
- Produces: an 18,000–23,000-character Chapter 2 fragment with exactly five H2 sections and seven figure markers.

- [ ] **Step 1: Add RED tests for the restored five-section outline**

Require the exact H2 headings and these concepts:

```python
required = {
    "2.1": ("ESXi", "vCenter", "vSphere", "vSAN", "NSX", "VMware Cloud Foundation"),
    "2.2": ("Citrix DaaS", "HDX", "Workspace", "Gateway", "Cloud Connector", "VDA", "资源位置"),
    "2.3": ("Hyper-V", "父分区", "子分区", "VMBus", "虚拟交换机", "故障转移群集", "Storage Spaces Direct", "Azure Local", "Azure Arc"),
    "2.4": ("私有云", "openEuler", "OpenStack", "华为云Stack", "Apsara Stack", "EasyStack", "ZStack", "信创"),
    "2.5": ("AWS", "Microsoft Azure", "Google Cloud", "阿里云", "华为云", "腾讯云", "区域", "可用区", "计量"),
}
```

Reject vendor rankings, unverified market shares, detailed pricing, transient region counts, and long product catalogs.

- [ ] **Step 2: Run the Chapter 2 tests and confirm RED**

Run: `python -m pytest third-edition-work/tests/test_second_base_revision.py -k "chapter_2_restored" -q`

Expected: FAIL because the current Chapter 2 has four different sections and insufficient depth.

- [ ] **Step 3: Update the official research register**

Record the official July-2026 boundaries used in the chapter, including:

- VMware Cloud Foundation: vSphere compute, vSAN storage, NSX networking, operations/automation/lifecycle.
- Citrix DaaS: Citrix-managed control plane plus customer resource locations, Cloud Connectors, VDAs, and supported on-prem/public-cloud hosts.
- Microsoft: Hyper-V and Failover Clustering/Storage Spaces Direct under Azure Local, with Azure Arc management.
- Domestic and public-cloud products: only official technical positioning and stable architectural roles.

- [ ] **Step 4: Rewrite `ch02.md` to the five-section structure**

Each section must contain `一．` and `1．` levels. Explain the architecture before naming representative products, distinguish virtualization from cloud service delivery, and connect the domestic private-cloud section to the later openEuler/OpenStack lab without turning it into installation guidance.

- [ ] **Step 5: Run Chapter 2 focused tests and confirm GREEN**

Run: `python -m pytest third-edition-work/tests/test_second_base_revision.py -k "chapter_2 or chapters_1_2" -q`

Expected: all Chapter 2 structure, length, concept-boundary, and cross-reference tests pass; missing asset tests may remain RED.

- [ ] **Step 6: Commit Chapter 2**

```powershell
git add third-edition-work/revision/fragments/ch02.md third-edition-work/research/part1-official-research-2026-07.md third-edition-work/tests/test_second_base_revision.py
git commit -m "docs: restore cloud vendor and product chapter"
```

---

### Task 4: Draw and Export the 12 Figures

**Files:**
- Create: `third-edition-work/revision/figures/ch01/图1.1.svg` through `图1.5.svg`
- Create: `third-edition-work/revision/figures/ch01/图1.1.png` through `图1.5.png`
- Create: `third-edition-work/revision/figures/ch02/图2.1.svg` through `图2.7.svg`
- Create: `third-edition-work/revision/figures/ch02/图2.1.png` through `图2.7.png`
- Create: `third-edition-work/tools/validate_textbook_figures.py`
- Modify: `third-edition-work/tests/test_second_base_revision.py`

**Interfaces:**
- Consumes: the figure manifest and finalized prose/anchors from Tasks 2–3.
- Produces: 12 editable SVGs, 12 high-resolution PNGs, and a validator that confirms dimensions, fonts, minimum text size, file identity, and readable raster output.

- [ ] **Step 1: Add failing SVG/PNG asset tests**

```python
def test_chapter_figures_exist_and_use_readable_song_font():
    for item in load_chapter_figure_manifest():
        svg = REVISION_DIR / item["svg"]
        png = REVISION_DIR / item["png"]
        assert svg.is_file() and png.is_file()
        root = ET.fromstring(svg.read_text(encoding="utf-8"))
        assert all(float(node.attrib["font-size"]) >= 9 for node in root.findall(".//{*}text"))
        assert all("SimSun" in node.attrib.get("font-family", "") or "宋体" in node.attrib.get("font-family", "") for node in root.findall(".//{*}text"))
```

- [ ] **Step 2: Run asset tests and confirm RED**

Run: `python -m pytest third-edition-work/tests/test_second_base_revision.py -k "chapter_figures" -q`

Expected: FAIL because the 24 SVG/PNG deliverables do not yet exist.

- [ ] **Step 3: Create neutral textbook diagrams**

Use a white background, restrained blue/teal/gray palette, 1.2–1.8 pt strokes, no gradients that reduce print contrast, no company logos, and no copied vendor marketing art. Use the prose-defined architecture and official component relationships. Each SVG must define a fixed viewBox and explicit text sizes in points.

- [ ] **Step 4: Export PNG files at print resolution**

Use headless Chromium/Puppeteer for CJK fidelity. Export at no less than 2400 px width for 13.5–14 cm Word placement. Do not use a converter that replaces Chinese characters with boxes.

- [ ] **Step 5: Run the validator and visually inspect all figures**

Run: `python third-edition-work/tools/validate_textbook_figures.py third-edition-work/revision/figures/ch01-02-figure-manifest.json`

Expected: 12/12 SVG and 12/12 PNG pass; minimum font size is at least 9 pt; raster dimensions and hashes are reported.

Open every PNG with image inspection. Reject clipping, overlapping labels, tiny text, low contrast, broken arrows, or unsupported glyphs.

- [ ] **Step 6: Commit figures and validation**

```powershell
git add third-edition-work/revision/figures third-edition-work/tools/validate_textbook_figures.py third-edition-work/tests/test_second_base_revision.py
git commit -m "docs: add chapters 1 and 2 textbook figures"
```

---

### Task 5: Build a Font-Faithful Chapters 1–2 Word Review Copy

**Files:**
- Create: `third-edition-work/tools/insert_textbook_figures_word.py`
- Modify: `third-edition-work/tests/test_second_base_revision.py`
- Create outside Git: `D:\codex\云计算教材更新\云计算基础架构平台构建与应用（第三版第1-2章层次图文审阅稿-20260814）.docx`
- Create outside Git: `D:\codex\云计算教材更新\云计算基础架构平台构建与应用（第三版第1-2章层次图文审阅稿-20260814）.pdf`

**Interfaces:**
- Consumes: current work mother hash `1904c62ec7344b4af410fde1f404721db2988a7a53445b7ebf46e86c294ad039`, the two revised fragments, revision map, figure manifest, and 12 PNG assets.
- Produces: a separate Word/PDF review pair; does not overwrite the work mother.

- [ ] **Step 1: Add failing Word figure/style tests**

Require exact Chapter 1/2 figure numbers, captions, image relationships, body font/size, internal-level paragraphs, and unchanged Chapter 3+ boundary.

```python
def test_review_docx_has_second_edition_fonts_and_all_chapter_figures(review_docx):
    audit = inspect_review_docx(review_docx)
    assert audit.body_font == "宋体"
    assert audit.body_size_pt == 10.5
    assert audit.caption_font == "宋体"
    assert audit.caption_size_pt == 9.0
    assert audit.figure_numbers == [f"图1.{n}" for n in range(1, 6)] + [f"图2.{n}" for n in range(1, 8)]
    assert audit.minimum_embedded_figure_font_pt >= 9.0
```

- [ ] **Step 2: Run the Word tests and confirm RED**

Run: `python -m pytest third-edition-work/tests/test_second_base_revision.py -k "review_docx_chapters_1_2" -q`

Expected: FAIL because the new review copy and image relationships do not exist.

- [ ] **Step 3: Generate a heading-bounded text candidate**

Use `revise_second_edition.py` against the unchanged work mother and a Task-specific map that replaces only Chapter 1 and Chapter 2. Refuse to overwrite an existing output and confirm the current mother hash before processing.

- [ ] **Step 4: Insert figures and captions with Word automation**

`insert_textbook_figures_word.py` must find each unique `{{FIGURE:图X.Y}}` marker, replace it with the corresponding PNG as an inline shape at the manifest width, insert a caption paragraph immediately below, set the caption to 宋体 9 pt bold centered, and remove the marker. It must set Chapter 1/2 body runs to effective 宋体 10.5 pt while preserving Heading 1/2 and code/config styles outside the target chapters.

- [ ] **Step 5: Update the table of contents and save as a new review copy**

Use the already-running Word instance only through a dedicated automation session; do not close unrelated user documents or kill Word processes. Save to the exact Task-specific output path.

- [ ] **Step 6: Run Word/Open XML audits and confirm GREEN**

Run the focused tests plus a package validation that confirms five sections, unchanged page geometry, 12 images/captions, no markers, valid relationships, and a byte-stable/semantic-stable Chapter 3+ boundary as defined by the existing tool contracts.

- [ ] **Step 7: Convert to PDF and inspect layout**

Render the Word review copy to PDF. Inspect the table of contents, both chapter openers, all 12 figure pages, multiple dense-prose pages, and the Chapter 3 transition. Reject clipped images, orphan captions, figures separated from their references, wrong fonts, broken glyphs, excessive white space, or paragraph overlap.

- [ ] **Step 8: Commit tooling/tests but not review binaries**

```powershell
git add third-edition-work/tools/insert_textbook_figures_word.py third-edition-work/tests/test_second_base_revision.py
git commit -m "feat: build illustrated chapters 1 and 2 review copy"
```

---

### Task 6: Final Verification and User Handoff

**Files:**
- Create ignored report: `.superpowers/sdd/second-base-task-7-report.md`
- Modify ignored progress ledger: `.superpowers/sdd/progress.md`

**Interfaces:**
- Consumes: all Task 1–5 outputs.
- Produces: fresh evidence, a clean/pushed branch, clickable Word/PDF review links, and an explicit stop before further chapters.

- [ ] **Step 1: Run fresh complete tests**

```powershell
python -m pytest third-edition-work/tests/test_second_base_revision.py -q
python -m pytest third-edition-work/tests/test_deployment_contract.py -q
python -m py_compile third-edition-work/tools/revise_second_edition.py third-edition-work/tools/validate_textbook_figures.py third-edition-work/tools/insert_textbook_figures_word.py
git diff --check
```

Expected: zero failures and zero syntax/diff errors.

- [ ] **Step 2: Run content and artifact audits**

Confirm exact H1/H2/internal headings, target lengths, 12 forward references/markers resolved, 12 captions, 12 SVG/PNG source pairs, effective Word fonts, five sections, no broken bookmarks, no unsupported predictions, and unchanged source/work-mother hashes.

- [ ] **Step 3: Record exact hashes and visual findings**

Write the Word/PDF/SVG/PNG hashes, page/section counts, test counts, source facts, and any remaining figure or pagination risks to the Task report.

- [ ] **Step 4: Obtain independent lightweight review**

Review only the two chapters and review artifacts for textbook voice, hierarchy, detail balance, source fidelity, figure readability, body/caption fonts, and Chapter 3 boundary. Fix all Critical and Important findings before handoff.

- [ ] **Step 5: Push the branch and stop**

Push `third-edition` only after verification and review pass. Provide the user the Word and PDF review links and explicitly state that the workflow is paused for Chapter 1/2 feedback.

## Plan Self-Review

- Spec coverage: all hierarchy, detail balance, five-section Chapter 2, 12 figures, font sizes, numbering, source limits, Word/PDF review, and stop boundary are assigned to concrete tasks.
- Placeholder scan: no TODO/TBD or unspecified figure/title paths remain.
- Interface consistency: manifest fields are consumed by tests, figure validation, Word insertion, and final audits using the same names and paths.
- Scope: Chapters 1 and 2 are one coherent review unit because they share the concept/product transition, figure numbering rules, and one bounded Word candidate; later chapters are explicitly excluded.
