# DOCX, Figures, and Teaching Environment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Assemble the approved chapter sources and images into a visually verified third-edition DOCX and a complete teaching-environment directory.

**Architecture:** A deterministic Python builder loads chapter Markdown and a figure registry, starts from the second-edition Word style package, generates the new body, and runs structural and visual QA. Environment packaging is manifest-driven so large/open files are included when legally distributable and restricted software is represented by official links and checksums.

**Tech Stack:** Python 3, python-docx, lxml, Pillow, zipfile, Microsoft Word COM or LibreOffice, Poppler, PowerShell.

## Global Constraints

- Never overwrite `云计算基础架构平台构建与应用（第二版初稿）.docx`.
- Output is `云计算基础架构平台构建与应用（第三版初稿）.docx`.
- Preserve A4 page size, approximately 1.27 cm margins, Heading 1 at 22 pt, Heading 2 at 16 pt, and body/caption visual continuity unless visual QA shows a defect.
- Figure captions use Song typeface and chapter-only `图N.M`; table captions use `表N-M`.
- All images are also saved independently in `第三版教材图片/`.
- No environment bundle contains credentials or unlawfully redistributed commercial installers.

---

### Task 1: Define the book manifest and builder interfaces

**Files:**
- Create: `third-edition-work/book/manifest.json`
- Create: `third-edition-work/tools/book_builder.py`
- Create: `third-edition-work/tests/test_book_builder.py`

**Interfaces:**
- Consumes: `manifest.json`, chapter Markdown, figure registry, original DOCX template.
- Produces: `build_book(manifest_path: Path, output_path: Path) -> None`.

- [ ] Define manifest fields: title, subtitle, source_template, output, chapters, figure_registry, page_target, styles, and section settings.
- [ ] Write failing tests for thirteen ordered chapters, output-not-equal-to-template, figure lookup, `图N.M` validation, `表N-M` validation, and rejection of missing assets.
- [ ] Run `python -m pytest third-edition-work/tests/test_book_builder.py -v`; expected result is FAIL because `book_builder.py` is not implemented.
- [ ] Implement `load_manifest`, `load_figure_registry`, `validate_numbering`, `new_from_template`, `append_chapter`, and `build_book` with explicit type hints.
- [ ] Preserve style/theme/header/footer parts from the original package while replacing the document body in a new output file.
- [ ] Run the tests again; expected result is all PASS.

### Task 2: Implement paragraphs, code blocks, tables, figures, and captions

**Files:**
- Modify: `third-edition-work/tools/book_builder.py`
- Modify: `third-edition-work/tests/test_book_builder.py`

**Interfaces:**
- Consumes: normalized Markdown blocks.
- Produces: correctly styled Word elements and relationships.

- [ ] Add tests for Heading 1/2/3, body text, ordered steps, command/code blocks, warning boxes, literacy boxes, tables, images, captions, page breaks, and source notes.
- [ ] Implement each renderer as a focused function; code blocks use a legible monospaced font and paragraph shading, not screenshots of plain text.
- [ ] Insert figures at up to approximately 14.4 cm wide while preserving aspect ratio.
- [ ] Insert captions and table captions with their exact registered numbers.
- [ ] Add built-in heading outline levels so the Word TOC can update correctly.
- [ ] Run the builder tests; expected result is all PASS.

### Task 3: Normalize and validate the complete figure set

**Files:**
- Modify/Create: `第三版教材图片/*`
- Create: `third-edition-work/tools/figure_qa.py`
- Create: `third-edition-work/validation/figure-qa.md`

**Interfaces:**
- Consumes: figure registry and all old/new images.
- Produces: normalized image files and QA report.

- [ ] Export reusable original figures from the second-edition DOCX and map only approved figures to new chapter numbers.
- [ ] Redraw outdated architecture/flow diagrams rather than enlarging low-resolution bitmaps.
- [ ] Implement checks for missing files, duplicate numbers, unreadable dimensions, incorrect extensions, and registry/path mismatches.
- [ ] Run `python third-edition-work/tools/figure_qa.py`; expected result is exit code 0 and every registry row marked PASS.
- [ ] Save editable SVGs beside corresponding PNGs for newly drawn technical diagrams.

### Task 4: Build and structurally validate the DOCX

**Files:**
- Create: `云计算基础架构平台构建与应用（第三版初稿）.docx`
- Create: `third-edition-work/validation/docx-structure.md`

**Interfaces:**
- Consumes: all approved chapter sources and images.
- Produces: complete Word manuscript.

- [ ] Run the builder with the approved manifest.
- [ ] Validate the DOCX ZIP/package and XML relationships using the DOCX skill validator.
- [ ] Count Heading 1 elements; expected result is 13 chapter headings plus part headings handled by their designated style.
- [ ] Check all referenced image relationships resolve and all captions are sequential within each chapter.
- [ ] Check the original second-edition SHA-256 still matches `original-inputs.sha256`.
- [ ] Record results in `docx-structure.md`.

### Task 5: Render and visually QA the manuscript

**Files:**
- Create: `third-edition-work/render/third-edition.pdf`
- Create: `third-edition-work/render/pages/`
- Create: `third-edition-work/validation/visual-qa.md`

**Interfaces:**
- Consumes: final DOCX.
- Produces: PDF/page previews and visual defect log.

- [ ] Render with the DOCX skill's LibreOffice helper; if LibreOffice is unavailable, use installed Microsoft Word COM `SaveAs2` to PDF.
- [ ] Convert PDF pages to JPEG previews at 100–150 dpi.
- [ ] Inspect title/TOC, first/last page of every chapter, all full-page figures/tables, chapter transitions, Chapter 12 model setup, and Chapter 13 deployment/operations pages.
- [ ] Check clipping, blank pages, orphan captions, tiny text, distorted figures, table overflow, and inconsistent spacing.
- [ ] Fix defects in sources/builder, rebuild, and rerender until `visual-qa.md` contains no unresolved high- or medium-severity item.
- [ ] Record final total page count and Part III page count; rebalance only if total materially exceeds approximately 380 or Part III materially differs from approximately 50.

### Task 6: Assemble the teaching environment directory

**Files:**
- Create: `第三版教材配套环境/01_环境与版本清单/README.md`
- Create: `第三版教材配套环境/02_openEuler安装与云镜像/`
- Create: `第三版教材配套环境/03_OpenStack离线源/`
- Create: `第三版教材配套环境/04_OpenStack部署脚本/`
- Create: `第三版教材配套环境/05_手工配置文件模板/`
- Create: `第三版教材配套环境/06_Trae与DeepSeek接入资料/`
- Create: `第三版教材配套环境/07_实验网络与虚拟机说明/`
- Create: `第三版教材配套环境/08_检查验收与运维工具/`
- Create: `第三版教材配套环境/09_官方来源与下载校验/SHA256SUMS.txt`

**Interfaces:**
- Consumes: safe scripts, repo ZIP, templates, images/ISOs allowed for redistribution, source register, and verification tools.
- Produces: reproducible, credential-free environment bundle.

- [ ] Copy `openstack_repo.zip` without modification and verify its hash.
- [ ] Copy the safe script directory, manual configuration templates, sanitized OpenRC sample, checks, task prompts, network/VM guide, and version matrix.
- [ ] Include CirrOS and openEuler ISO/cloud image when their official distribution terms allow; otherwise include an exact official URL, version, size, SHA-256, and download instructions.
- [ ] For VMware, Xshell, SecureCRT, TRAE, and other restricted software, include official download links/version/checksums and screenshots, not unauthorized installers.
- [ ] Add a root README explaining directory order, minimum host resources, VM configuration, credentials the teacher must set, and complete lab sequence.
- [ ] Generate `SHA256SUMS.txt` for every bundled file except the checksum file itself.

### Task 7: Final DOCX/environment verification

**Files:**
- Create: `third-edition-work/validation/package-qa.md`
- Create: `third-edition-work/checkpoints/final-docx-assets-env.sha256`

**Interfaces:**
- Consumes: DOCX, figures, environment bundle.
- Produces: final QA evidence.

- [ ] Open the DOCX in Microsoft Word and update fields/TOC; save only the third-edition output.
- [ ] Re-run DOCX structural validation after Word saves it.
- [ ] Re-run figure registry QA and environment checksum verification.
- [ ] Extract DOCX XML and scan DOCX, images metadata/OCR records, scripts, templates, and docs for real credentials.
- [ ] Verify every final deliverable path exists and is readable.
- [ ] Hash the final DOCX, all figure files, and environment manifest; save sorted hashes in `final-docx-assets-env.sha256`.

