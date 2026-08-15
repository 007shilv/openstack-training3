# Chapters 7-13 Theory Enrichment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand Chapters 7-13 with component theory, branching and looping logic diagrams, summary tables, and three integrated ideological-education points so Chapters 1-13 occupy about 180 Word pages.

**Architecture:** Keep the existing Markdown fragments, figure/table manifests, bounded DOCX builder, and the single current formal DOCX. Research evidence is stored separately from narrative text; each chapter receives one new theory section, one decision/loop diagram, and one comparison/status table before its manual practicum.

**Tech Stack:** Markdown, JSON manifests, SVG/PNG, Open XML, Microsoft Word COM, PDF rendering, pytest.

## Global Constraints

- Keep the second-edition DOCX immutable and edit only the current third-edition DOCX in place after temporary validation.
- Chinese narrative uses Songti 10.5 pt; Latin letters and digits use Times New Roman; captions use Songti 9 pt bold.
- Commands remain manual, carry their real prompts, and contain no Python deployment or one-click scripts.
- Passwords remain `qwer1234`; controller is `192.168.234.151`; compute is `192.168.234.150`.
- Figures use chapter-local numbering, contain no notes, and must have no text overflow or arrow-node collision.
- Tables use chapter-local `表N-N` numbering.
- Narrative contains definitions, facts, mechanisms, examples and analysis, not author rules, teaching activities, review questions, gates or validation reports.
- Every 2-3 chapters include one naturally integrated ideological-education point.

---

### Task 1: Establish the second-edition and current-theory gap

**Files:**
- Create: `third-edition-work/revision/research/ch07-13-second-edition-gap-20260815.md`
- Read: `云计算基础架构平台构建与应用（第二版初稿）.docx`
- Read: `third-edition-work/revision/fragments/ch07.md` through `ch13.md`

- [ ] Extract the second-edition theory paragraphs and original figure captions for Chapters 7-13.
- [ ] Measure current pre-practicum narrative length, figures, tables and actual Word page spans.
- [ ] Record retain, update, remove and add decisions for every chapter.
- [ ] Confirm that the planned additions total 26-32 pages.

### Task 2: Register official OpenStack evidence

**Files:**
- Create: `third-edition-work/revision/research/ch07-13-official-research-20260815.md`
- Create: `third-edition-work/revision/research/ch07-13-sources-20260815.json`

- [ ] Research Glance image lifecycle/import, Placement candidates/generations, Nova scheduling/retries, Neutron ML2 binding, Cinder scheduling/attachments, Swift rings/quorum/background processes, and Horizon catalog/session/policy using official OpenStack sources.
- [ ] Record the official URL, page title, retrieval date, applicable component and supported textbook claims.
- [ ] Separate stable architecture concepts from post-Antelope version-specific configuration.

### Task 3: Add focused content and diagram contracts

**Files:**
- Create: `third-edition-work/tests/test_chapters_7_13_theory.py`

- [ ] Assert one new theory H2, one new figure marker and one new table marker per chapter.
- [ ] Assert the new figures contain decision diamonds, a feedback/loop path and readable font metadata.
- [ ] Assert figures are cited before insertion and explained after insertion.
- [ ] Assert ideological-education passages exist in Chapters 8, 10 and 13 and contain no teaching-activity language.
- [ ] Run the focused test and observe failures before implementation.

### Task 4: Expand Chapters 7-10

**Files:**
- Modify: `third-edition-work/revision/fragments/ch07.md`
- Modify: `third-edition-work/revision/fragments/ch08.md`
- Modify: `third-edition-work/revision/fragments/ch09.md`
- Modify: `third-edition-work/revision/fragments/ch10.md`
- Modify: `third-edition-work/revision/tables/ch07-table-manifest.json` through `ch10-table-manifest.json`

- [ ] Add image import and lifecycle branching to Chapter 7 and renumber the practicum to 7.4.
- [ ] Add candidate generation and generation-conflict retry to Chapter 8 and renumber the practicum to 8.4.
- [ ] Add scheduling claim, alternate-host retry and instance states to Chapter 9 and renumber the practicum to 9.4.
- [ ] Add ML2 port binding and agent reconciliation loops to Chapter 10 and renumber the practicum to 10.4.
- [ ] Add the first two ideological-education passages to Chapters 8 and 10.

### Task 5: Expand Chapters 11-13

**Files:**
- Modify: `third-edition-work/revision/fragments/ch11.md`
- Modify: `third-edition-work/revision/fragments/ch12.md`
- Modify: `third-edition-work/revision/fragments/ch13.md`
- Modify: `third-edition-work/revision/tables/ch11-table-manifest.json` through `ch13-table-manifest.json`

- [ ] Add volume scheduling, attachment objects and state transitions to Chapter 11 and renumber the practicum to 11.4.
- [ ] Add Swift quorum, handoff, replication, auditing and updater loops to Chapter 12 and renumber the practicum to 12.4.
- [ ] Add Horizon catalog, session and policy request branching to Chapter 13 and renumber the practicum to 13.4.
- [ ] Add the third ideological-education passage to Chapter 13.

### Task 6: Draw and validate seven logic diagrams

**Files:**
- Modify: `third-edition-work/tools/build_ch04_08_figures.py`
- Modify: `third-edition-work/revision/figures/ch07-figure-manifest.json` through `ch13-figure-manifest.json`
- Create: `third-edition-work/revision/figures/ch7/图7.3.svg` and `.png` through `ch13/图13.3.svg` and `.png`

- [ ] Add shared process, decision, branch-label and loop-arrow primitives.
- [ ] Generate one component-specific decision/loop diagram per chapter.
- [ ] Parse every SVG as XML, render every PNG at high resolution and inspect each image visually.
- [ ] Reject any text overflow, arrow-node collision, inconsistent font size or clipped shape.

### Task 7: Build, paginate and update the current DOCX in place

**Files:**
- Modify in place: `D:/codex/云计算教材更新/云计算基础架构平台构建与应用（第三版第1-3章审阅稿-20260815-04修复版）.docx`

- [ ] Build a same-volume temporary DOCX from the bounded Chapter 1-13 revision map.
- [ ] Validate the DOCX package and confirm Chapter 14 and later content remains unchanged.
- [ ] Reopen in Microsoft Word, repaginate, export PDF and confirm Chapter 14 begins on page 181-187.
- [ ] Inspect all new figure pages and all chapter transitions; revise any overflow or blank-page issue.
- [ ] Atomically replace the current formal DOCX only after all checks pass.
- [ ] Run focused and full tests, source hash checks, `git diff --check`, commit and push the source changes.
