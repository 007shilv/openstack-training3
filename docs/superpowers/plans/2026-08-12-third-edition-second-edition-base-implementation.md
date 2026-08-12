# Third Edition Second-Edition-Base Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce the third-edition textbook by editing a copy of the second-edition DOCX in place, retaining its teaching voice, chapter flow, typography, page geometry, and figure rhythm while updating facts, commands, configurations, screenshots, and new chapters.

**Architecture:** The original second-edition DOCX remains immutable. A revision tool copies it to a working DOCX and applies heading-bounded replacement fragments, cloning paragraph properties from the original Word document instead of generating a new book. Content fragments are chapter-scoped; each batch can be reviewed independently, and the final assembly updates the Word table of contents and pagination without rebuilding the document from Markdown.

**Tech Stack:** Microsoft Word DOCX/Open XML, Python 3.14, `python-docx`, `lxml`, Microsoft Word COM for pagination/PDF rendering, PyMuPDF for visual QA, PowerShell, pytest, Git.

## Global Constraints

- Source DOCX: `D:\codex\云计算教材更新\云计算基础架构平台构建与应用（第二版初稿）.docx`; SHA-256 must remain `96bcad5246cc56574f5f38f4b210b8f0ed71363a1794fac9beb877332d2ae5d6`.
- Working DOCX: `D:\codex\云计算教材更新\云计算基础架构平台构建与应用（第三版工作母稿）.docx`.
- Final DOCX: `D:\codex\云计算教材更新\云计算基础架构平台构建与应用（第三版初稿-第二版底板）.docx`.
- Page size 18.4 cm × 26 cm; all four margins 2 cm; header 1.5 cm; footer 1.75 cm.
- Body font is SimSun 10.5 pt, justified, with approximately two-character first-line indent; Heading 1 is 22 pt bold; Heading 2/3 is 16 pt bold; figure captions are SimSun 9 pt bold centered.
- Every executable Linux command includes its native prompt, such as `[root@controller ~]#`, `[root@compute ~]#`, or `$`.
- MariaDB commands use `MariaDB [(none)]>`, `MariaDB [database]>`, and actual continuation prompt `->`.
- Configuration file contents do not receive a shell prompt; the preceding `vi` command does.
- Controller is `192.168.234.151`; compute is `192.168.234.150`; ens33 is management; ens34 is Provider with no IP; compute `/dev/sdb` is Cinder and `/dev/sdc` is Swift, each 50 GiB.
- Teaching passwords are uniformly `qwer1234`, with an explicit isolated-lab-only warning.
- OpenStack overview is updated through 2026-07-31 and 2026.1 Gazpacho; the lab version remains 2023.1 Antelope on openEuler 24.03 LTS SP3.
- Part II installation is manual only: DNF, Linux commands, `vi`, database sync, identity/service/endpoint creation, and service start.
- Part II installation contains no Python execution, Python heredoc, Paramiko, validators, tests, gates, audits, acceptance reports, rollback programs, Shell functions, loops, or conditional orchestration.
- Installation chapters stop after enabling and starting services; API, port, state, database-table, and synthetic-resource verification is excluded.
- Operations chapters retain teaching queries and resource lifecycle commands because those are the subject being taught, not installation verification.
- Figure numbering is `图1.1`; table numbering is `表1-1`; final images live under `D:\codex\云计算教材更新\第三版教材图片` and use their figure number as filename.
- The final Part III is approximately 50 pages; the full book is approximately 380 pages.

---

## File Structure

- `third-edition-work/revision/second-edition-style-baseline.json`: immutable measured page/style/figure invariants from the source DOCX.
- `third-edition-work/revision/revision-map.json`: ordered heading-bounded replacements, deletions, insertions, and chapter renumbering.
- `third-edition-work/revision/fragments/ch01.md` … `ch17.md`: teaching prose and manual commands for each final chapter; these are editorial fragments, not a whole-book generator.
- `third-edition-work/revision/figures/figure-plan.csv`: source/reuse/redraw/recapture decision and target number for every figure.
- `third-edition-work/tools/revise_second_edition.py`: copies the source DOCX and applies revision fragments while cloning second-edition Word paragraph properties.
- `third-edition-work/tools/audit_second_base_docx.py`: checks source hash, page geometry, fonts, prompt use, forbidden content, heading structure, image/caption adjacency, and output integrity.
- `third-edition-work/tests/test_second_base_revision.py`: executable contracts for base preservation and fragment insertion.
- `third-edition-work/validation/second-base-revision-qa.md`: final content, style, page, image, and secret-scan evidence.

---

### Task 1: Freeze the Second-Edition Base and Style Contracts

**Files:**
- Create: `third-edition-work/revision/second-edition-style-baseline.json`
- Create: `third-edition-work/tools/audit_second_base_docx.py`
- Create: `third-edition-work/tests/test_second_base_revision.py`

**Interfaces:**
- Consumes: the immutable second-edition DOCX.
- Produces: `load_baseline(path: Path) -> dict`, `audit_docx(source: Path, candidate: Path) -> list[str]`, and machine-readable style invariants used by every later task.

- [ ] **Step 1: Write failing source-hash and geometry tests**

```python
def test_source_hash_and_geometry():
    baseline = revision.load_baseline(BASELINE_JSON)
    assert revision.sha256(SOURCE_DOCX) == baseline["source_sha256"]
    result = revision.measure_docx(SOURCE_DOCX)
    assert result["page_cm"] == [18.4, 26.0]
    assert result["margins_cm"] == [2.0, 2.0, 2.0, 2.0]
```

- [ ] **Step 2: Run the focused test and record the expected RED state**

Run: `python -m pytest third-edition-work/tests/test_second_base_revision.py -k source_hash -v`

Expected: FAIL because the baseline loader and measurement tool do not exist.

- [ ] **Step 3: Implement the baseline and audit primitives**

The JSON must contain the exact source SHA-256, page dimensions, margins, header/footer distances, body font/size, heading sizes, caption format, paragraph count, image count, and table count measured from the second edition.

The audit command must be:

```powershell
python third-edition-work/tools/audit_second_base_docx.py `
  --source "D:\codex\云计算教材更新\云计算基础架构平台构建与应用（第二版初稿）.docx" `
  --candidate "D:\codex\云计算教材更新\云计算基础架构平台构建与应用（第三版工作母稿）.docx"
```

- [ ] **Step 4: Run tests and baseline audit**

Expected: source hash PASS; all five sections report 18.4×26 cm and 2 cm margins; 522 inline shapes; no source mutation.

- [ ] **Step 5: Commit**

```powershell
git add third-edition-work/revision/second-edition-style-baseline.json third-edition-work/tools/audit_second_base_docx.py third-edition-work/tests/test_second_base_revision.py
git commit -m "test: freeze second edition textbook baseline"
```

### Task 2: Build the Heading-Bounded DOCX Revision Tool

**Files:**
- Create: `third-edition-work/tools/revise_second_edition.py`
- Create: `third-edition-work/revision/revision-map.json`
- Modify: `third-edition-work/tests/test_second_base_revision.py`

**Interfaces:**
- Consumes: source DOCX, revision map, chapter fragments, figure files.
- Produces: `copy_source(source: Path, output: Path)`, `replace_between_headings(doc, start: str, end: str, blocks: list[Block])`, `delete_between_headings(...)`, `insert_before_heading(...)`, and `save_candidate(...)`.

- [ ] **Step 1: Write a failing fixture replacement test**

The test creates a two-heading DOCX fixture, replaces only the text between those headings, and asserts the section settings, heading XML, footer, and an unrelated image relationship are byte-equivalent.

- [ ] **Step 2: Run the focused test**

Run: `python -m pytest third-edition-work/tests/test_second_base_revision.py -k bounded_replace -v`

Expected: FAIL because the revision tool does not exist.

- [ ] **Step 3: Implement clone-based paragraph insertion**

Use cloned `w:pPr` from second-edition templates for body, command, configuration, Heading 1, Heading 2, and caption paragraphs. Do not synthesize a new document or new global styles. Commands receive the same body properties as second-edition commands; captions receive 9 pt bold centered runs.

- [ ] **Step 4: Define the revision-map schema and validate it**

Each operation is one of:

```json
{"op":"replace","start_heading":"第一章 云计算基本概念","end_heading":"第二章 云计算知名厂商及其产品","fragment":"fragments/ch01.md"}
```

```json
{"op":"delete","start_heading":"4.2  终端软件的使用","end_heading":"4.3  实训项目1 原生OpenStack云平台基本环境配置"}
```

```json
{"op":"insert_before","heading":"第十三章 原生OpenStack云平台各组件运维","fragment":"fragments/ch12.md"}
```

- [ ] **Step 5: Copy the source to the working DOCX without content changes**

Run the tool with an empty revision map. Expected: output SHA differs only if Word metadata is updated; audit reports equal sections, styles, headings, paragraph count, image count, and image relationships.

- [ ] **Step 6: Commit**

```powershell
git add third-edition-work/tools/revise_second_edition.py third-edition-work/revision/revision-map.json third-edition-work/tests/test_second_base_revision.py
git commit -m "feat: add second edition bounded revision tool"
```

### Task 3: Revise Chapters 1–3 Without Compressing the Teaching Narrative

**Files:**
- Create: `third-edition-work/revision/fragments/ch01.md`
- Create: `third-edition-work/revision/fragments/ch02.md`
- Create: `third-edition-work/revision/fragments/ch03.md`
- Modify: `third-edition-work/revision/revision-map.json`
- Create: `third-edition-work/revision/figures/figure-plan.csv`
- Modify: `third-edition-work/tests/test_second_base_revision.py`

**Interfaces:**
- Consumes: official-source manuscript and source register already present in the repository.
- Produces: three teaching-style replacement fragments and figure decisions for the theory section.

- [ ] **Step 1: Write failing narrative-density and heading tests**

Tests require chapter guides, only chapter/section headings, no dense third-level outline, at least the second-edition core topics, and no source-list dump in body text.

- [ ] **Step 2: Rewrite Chapter 1 in the second-edition recognition sequence**

Retain the flow: computing-model evolution → cloud definitions → characteristics → IaaS/PaaS/SaaS → public/private/hybrid cloud → industry. Update the final industry section through 2026-07-31 and integrate cloud native, edge cloud, AI cloud, FinOps, green cloud, sovereign cloud, and trusted cloud as explanatory prose.

- [ ] **Step 3: Rewrite Chapter 2 using the original product-comparison frame**

Update domestic and international cloud products and remove dead product-interface walkthroughs. Preserve comparison by technical position, service capability, ecosystem, deployment form, lock-in risk, and teaching scenario.

- [ ] **Step 4: Expand Chapter 3 from official OpenStack material**

Retain origin, open governance, logical architecture, core components, component collaboration, and platform experience. Add OpenInfra governance, current projects, release cadence, 2026.1 Gazpacho, and a clear statement that the lab remains Antelope.

- [ ] **Step 5: Apply the three replacements and render sample pages**

Render the chapter openers, one continuous-theory page, and each new architecture figure. Expected: teaching prose dominates; no command-manual layout.

- [ ] **Step 6: Commit**

```powershell
git add third-edition-work/revision/fragments/ch01.md third-edition-work/revision/fragments/ch02.md third-edition-work/revision/fragments/ch03.md third-edition-work/revision/revision-map.json third-edition-work/revision/figures/figure-plan.csv third-edition-work/tests/test_second_base_revision.py
git commit -m "docs: update cloud and OpenStack foundations on second edition base"
```

### Task 4: Replace the Environment Chapter with openEuler and the Fixed Lab Topology

**Files:**
- Create: `third-edition-work/revision/fragments/ch04.md`
- Modify: `third-edition-work/revision/revision-map.json`
- Modify: `third-edition-work/revision/figures/figure-plan.csv`
- Modify: `third-edition-work/tests/test_second_base_revision.py`

**Interfaces:**
- Produces: the openEuler introduction and manual two-node environment preparation chapter.

- [ ] **Step 1: Write failing environment contracts**

Require openEuler 24.03 LTS SP3, controller/compute addresses, ens33/ens34 roles, `/dev/sdb` and `/dev/sdc`, and exactly one short terminal-tool paragraph. Reject CentOS, the old addresses, and standalone Xshell/SecureCRT tutorials.

- [ ] **Step 2: Write the openEuler teaching section**

Explain project origin, LTS/SP lifecycle, Linux 6.6 base, package management, hardware/software ecosystem, open-source collaboration, and its role in a trusted domestic cloud platform before starting the lab.

- [ ] **Step 3: Rewrite the environment lab in the original four-part structure**

Keep VM preparation, hostname, network, hosts, time, SELinux/firewall teaching configuration, local repository, and base services. Every executable line includes `[root@controller ~]#` or `[root@compute ~]#`.

- [ ] **Step 4: Apply, render, and inspect**

Expected: second-edition page style and image rhythm; no validation loops or Python; configuration bodies visually distinct from prompt-bearing commands.

- [ ] **Step 5: Commit**

```powershell
git add third-edition-work/revision/fragments/ch04.md third-edition-work/revision/revision-map.json third-edition-work/revision/figures/figure-plan.csv third-edition-work/tests/test_second_base_revision.py
git commit -m "docs: migrate environment chapter to openEuler SP3"
```

### Task 5: Revise MariaDB, Infrastructure, and Keystone

**Files:**
- Create: `third-edition-work/revision/fragments/ch05.md`
- Create: `third-edition-work/revision/fragments/ch06.md`
- Modify: `third-edition-work/revision/revision-map.json`
- Modify: `third-edition-work/tests/test_second_base_revision.py`

**Interfaces:**
- Produces: Part II foundation and Keystone chapters with manual prompts and no post-install verification.

- [ ] **Step 1: Write failing prompt, password, and forbidden-content tests**

Require `[root@controller ~]#`, `MariaDB [(none)]>`, `qwer1234`, database creation, grants, `vi`, `keystone-manage db_sync`, Fernet/credential setup, bootstrap, admin environment, and service start. Reject `python`, `set -Eeuo`, `curl`, validators, API tests, and script interpretation sections.

- [ ] **Step 2: Rewrite Chapter 5**

Retain MariaDB explanation and manual installation. Add RabbitMQ, Memcached, chrony, and OpenStack client as supporting foundation services, each with purpose, package command, necessary configuration, and service start.

- [ ] **Step 3: Rewrite Chapter 6**

Retain the “Keystone is the door” teaching analogy and explain domain, project, user, group, role, token, service, endpoint, catalog, and policy. The lab follows database → package → `vi keystone.conf` → sync → keys → bootstrap → Apache → service start → admin environment.

- [ ] **Step 4: Apply, render, and inspect the MariaDB and Keystone samples**

Check that MariaDB prompts and continuation lines match the client; configuration text is prompt-free; the final installation action is service enable/start.

- [ ] **Step 5: Commit**

```powershell
git add third-edition-work/revision/fragments/ch05.md third-edition-work/revision/fragments/ch06.md third-edition-work/revision/revision-map.json third-edition-work/tests/test_second_base_revision.py
git commit -m "docs: revise infrastructure and Keystone chapters"
```

### Task 6: Revise Glance and Placement

**Files:**
- Create: `third-edition-work/revision/fragments/ch07.md`
- Create: `third-edition-work/revision/fragments/ch08.md`
- Modify: `third-edition-work/revision/revision-map.json`
- Modify: `third-edition-work/tests/test_second_base_revision.py`

**Interfaces:**
- Produces: Glance and Placement theory plus manual installation chapters.

- [ ] **Step 1: Write failing component-content tests**

Require Glance stores/status/formats, file backend, user/admin role/image service/three endpoints, `vi glance-api.conf`, sync, and service start. Require Placement resource providers/inventories/allocations, exact user/service/endpoints, `vi placement.conf`, sync, policy conversion if needed, Apache configuration, and start/restart. Reject API and synthetic-image/provider validation.

- [ ] **Step 2: Author both chapters in second-edition cadence**

Each step contains purpose, node, prompt-bearing command, configuration, key parameter explanation, and transition to the next dependency.

- [ ] **Step 3: Apply and visually inspect**

Expected: theory and explanation exceed raw command/configuration volume; critical architecture figures are redrawn, not placeholders.

- [ ] **Step 4: Commit**

```powershell
git add third-edition-work/revision/fragments/ch07.md third-edition-work/revision/fragments/ch08.md third-edition-work/revision/revision-map.json third-edition-work/tests/test_second_base_revision.py
git commit -m "docs: revise Glance and Placement chapters"
```

### Task 7: Revise Nova in Controller-Then-Compute Order

**Files:**
- Create: `third-edition-work/revision/fragments/ch09.md`
- Modify: `third-edition-work/revision/revision-map.json`
- Modify: `third-edition-work/revision/figures/figure-plan.csv`
- Modify: `third-edition-work/tests/test_second_base_revision.py`

**Interfaces:**
- Produces: a single Nova chapter whose manual installation sequence is controller services before compute services.

- [ ] **Step 1: Write failing order and content tests**

Require Nova API, Scheduler, Conductor, Compute, libvirt, VNC, cells, Placement interaction, three databases, identity service/endpoints, `vi nova.conf`, API DB sync → cell0 → cell1 → main DB sync, controller service start, compute package/config, libvirt start, nova-compute start, and host discovery. Reject post-install service/API/hypervisor/provider validation.

- [ ] **Step 2: Restore the full Nova theory narrative**

Explain services and the instance creation flow before the lab, using the second-edition transition “下面以创建虚拟机为例” or equivalent teaching prose.

- [ ] **Step 3: Write the manual two-node lab**

Every node switch is explicit. Every command includes the correct prompt. Explain why controller must finish before compute and why host discovery is last.

- [ ] **Step 4: Apply, render, and inspect controller/compute transition pages**

- [ ] **Step 5: Commit**

```powershell
git add third-edition-work/revision/fragments/ch09.md third-edition-work/revision/revision-map.json third-edition-work/revision/figures/figure-plan.csv third-edition-work/tests/test_second_base_revision.py
git commit -m "docs: revise manual Nova chapter"
```

### Task 8: Revise Neutron Without Converting It to a Checklist

**Files:**
- Create: `third-edition-work/revision/fragments/ch10.md`
- Modify: `third-edition-work/revision/revision-map.json`
- Modify: `third-edition-work/revision/figures/figure-plan.csv`
- Modify: `third-edition-work/tests/test_second_base_revision.py`

**Interfaces:**
- Produces: Neutron theory, external-network preparation, controller service configuration, compute agent configuration, and service start.

- [ ] **Step 1: Write failing Neutron contracts**

Require SDN introduction, network objects, Linux bridge/ML2, Provider interface ens34 without IP, controller-before-compute, database/identity/three endpoints, `vi` configuration for neutron/ML2/Linux bridge/DHCP/metadata/L3, Nova integration configuration, and service starts. Reject network creation as installation verification; it belongs to operations.

- [ ] **Step 2: Author theory and the two original-style lab sections**

Retain the second edition’s separation between external-environment setup and core services. Explain the purpose of every agent and every node transition.

- [ ] **Step 3: Apply and inspect**

- [ ] **Step 4: Commit**

```powershell
git add third-edition-work/revision/fragments/ch10.md third-edition-work/revision/revision-map.json third-edition-work/revision/figures/figure-plan.csv third-edition-work/tests/test_second_base_revision.py
git commit -m "docs: revise manual Neutron chapter"
```

### Task 9: Revise Cinder and Add Swift as a Full Textbook Chapter

**Files:**
- Create: `third-edition-work/revision/fragments/ch11.md`
- Create: `third-edition-work/revision/fragments/ch12.md`
- Modify: `third-edition-work/revision/revision-map.json`
- Modify: `third-edition-work/revision/figures/figure-plan.csv`
- Modify: `third-edition-work/tests/test_second_base_revision.py`

**Interfaces:**
- Produces: Cinder and Swift theory/manual-install chapters and chapter insertion before Dashboard.

- [ ] **Step 1: Write failing storage safety and sequence tests**

Require `/dev/sdb` only for Cinder, `/dev/sdc` only for Swift, both 50 GiB, explicit student-facing confirmation before destructive initialization, and prohibition of `/dev/sda`. Require Cinder database/identity/endpoints/config/sync/controller services then LVM/LIO volume service. Require Swift identity/endpoints/config, XFS `swift-data`, mount, rsync, account/container/object services, rings, ring transfer, and proxy service. Reject post-install volume/object lifecycle tests.

- [ ] **Step 2: Rewrite Cinder theory and manual lab**

Explain block storage, backend/driver, volume service, LVM thin pool, iSCSI/LIO, and attachment relationship before the lab.

- [ ] **Step 3: Author Swift as a new full chapter in second-edition style**

Explain object/container/account, replica/ring/partition/zone, proxy/storage services, and consistency before the lab. Use the same four-part lab structure and teaching transitions.

- [ ] **Step 4: Apply, render, and inspect destructive-disk pages**

Expected: visible human confirmation language, correct prompts, no guard programs or Shell control-flow code.

- [ ] **Step 5: Commit**

```powershell
git add third-edition-work/revision/fragments/ch11.md third-edition-work/revision/fragments/ch12.md third-edition-work/revision/revision-map.json third-edition-work/revision/figures/figure-plan.csv third-edition-work/tests/test_second_base_revision.py
git commit -m "docs: revise Cinder and add Swift textbook chapter"
```

### Task 10: Revise Horizon and Migrate the Complete Manual Operations Chapter

**Files:**
- Create: `third-edition-work/revision/fragments/ch13.md`
- Create: `third-edition-work/revision/fragments/ch14.md`
- Modify: `third-edition-work/revision/revision-map.json`
- Modify: `third-edition-work/revision/figures/figure-plan.csv`
- Modify: `third-edition-work/tests/test_second_base_revision.py`

**Interfaces:**
- Produces: Dashboard install/config chapter and the full manual operations curriculum migrated to Antelope.

- [ ] **Step 1: Write failing Horizon and operations-flow tests**

Require DNF install, backup explanation, `vi local_settings`, Keystone v3, `/dashboard/`, Default domain, member role, Memcached, Asia/Shanghai, Apache configuration, and service restart. Require operations sections for Keystone, Glance, Nova, Neutron, Cinder, Swift, and Horizon. Reject installation verification language from Chapter 13 but allow teaching queries and lifecycle commands in Chapter 14.

- [ ] **Step 2: Rewrite Horizon in the original installation style**

Finish after Apache enable/restart. Browser login instructions move to the operations chapter.

- [ ] **Step 3: Migrate the second-edition operations task chain**

Preserve explain → command → field explanation → Dashboard counterpart. Update legacy clients to current `openstack` commands and use `qwer1234` for teaching users. Add Swift container/object management without collapsing the existing operations material into tables.

- [ ] **Step 4: Apply and render representative command/Dashboard pages**

- [ ] **Step 5: Commit**

```powershell
git add third-edition-work/revision/fragments/ch13.md third-edition-work/revision/fragments/ch14.md third-edition-work/revision/revision-map.json third-edition-work/revision/figures/figure-plan.csv third-edition-work/tests/test_second_base_revision.py
git commit -m "docs: revise Horizon and migrate manual operations"
```

### Task 11: Update the Image-Creation Chapter Without Removing Its Teaching Detail

**Files:**
- Create: `third-edition-work/revision/fragments/ch15.md`
- Modify: `third-edition-work/revision/revision-map.json`
- Modify: `third-edition-work/revision/figures/figure-plan.csv`
- Modify: `third-edition-work/tests/test_second_base_revision.py`

**Interfaces:**
- Produces: updated manual QCOW2 image construction chapter.

- [ ] **Step 1: Write failing image-chapter tests**

Require image-format explanation, KVM/libvirt preparation, `qemu-img`, `virt-install`, cloud-init/Cloudbase-Init context, and stepwise GUI/VNC captures where applicable. Reject CentOS 7 and obsolete OpenStack references.

- [ ] **Step 2: Preserve the original explanation and step rhythm**

Update guest versions, package commands, tool versions, and screenshots; do not reduce the chapter to a command list.

- [ ] **Step 3: Apply and inspect multi-screenshot pages**

- [ ] **Step 4: Commit**

```powershell
git add third-edition-work/revision/fragments/ch15.md third-edition-work/revision/revision-map.json third-edition-work/revision/figures/figure-plan.csv third-edition-work/tests/test_second_base_revision.py
git commit -m "docs: update virtual machine image construction chapter"
```

### Task 12: Add the Two Agent Chapters in Second-Edition Teaching Style

**Files:**
- Create: `third-edition-work/revision/fragments/ch16.md`
- Create: `third-edition-work/revision/fragments/ch17.md`
- Modify: `third-edition-work/revision/revision-map.json`
- Modify: `third-edition-work/revision/figures/figure-plan.csv`
- Modify: `third-edition-work/tests/test_second_base_revision.py`

**Interfaces:**
- Produces: an approximately 50-page Part III appended after the image chapter.

- [ ] **Step 1: Write failing Part III structure tests**

Require exact title `第十六章 智能体的部署和应用`, TRAE installation, DeepSeek connection, Claude Code, OpenAI Codex, OpenClaw, Hermes, dedicated OpenStack agent, one-shot deployment, and multiple operations tasks. Reject any suggestion that Part II uses agent automation.

- [ ] **Step 2: Rewrite Chapter 16 as concept → ecosystem → lab**

Use chapter guide, explanatory comparisons, installation preconditions, involved device, objectives, and step-by-step details. Avoid product-feature bullet dumping.

- [ ] **Step 3: Rewrite Chapter 17 as a complete project-based lab**

Explain why agent deployment follows manual learning, then present project preparation, one-shot build, human approval points, and operations tasks with teaching context and explanations.

- [ ] **Step 4: Insert real approved captures or omit unavailable UI figures**

Do not insert fictional placeholder UI. Keep a separate capture plan for images that require a safe API-key/account session.

- [ ] **Step 5: Apply and measure Part III page range**

Expected: 45–55 pages using second-edition geometry and styles.

- [ ] **Step 6: Commit**

```powershell
git add third-edition-work/revision/fragments/ch16.md third-edition-work/revision/fragments/ch17.md third-edition-work/revision/revision-map.json third-edition-work/revision/figures/figure-plan.csv third-edition-work/tests/test_second_base_revision.py
git commit -m "docs: add agent chapters on second edition base"
```

### Task 13: Complete Figures, Renumbering, TOC, and Final Acceptance

**Files:**
- Modify: `third-edition-work/revision/figures/figure-plan.csv`
- Modify: `third-edition-work/tools/revise_second_edition.py`
- Modify: `third-edition-work/tools/audit_second_base_docx.py`
- Modify: `third-edition-work/tests/test_second_base_revision.py`
- Create: `third-edition-work/validation/second-base-revision-qa.md`

**Interfaces:**
- Produces: final DOCX, PDF proof, figure folder, environment package, and QA report.

- [ ] **Step 1: Resolve every figure-plan row**

Each row must be one of `reuse-reviewed`, `redrawn`, `recaptured`, or `omitted-by-design`; no `planned`, `placeholder`, or `pending` status enters the final DOCX.

- [ ] **Step 2: Renumber all headings, figures, tables, and cross-references**

Figures use `图章.序号`; tables use `表章-序号`; chapter numbers reflect the final 17-chapter structure. Commands and configurations are not converted into screenshots.

- [ ] **Step 3: Run the full textual audit**

The audit rejects unprompted executable commands, old IPs, old passwords, CentOS, Python execution, validation/manual words in install chapters, script interpretation sections, placeholder images, and secret material.

- [ ] **Step 4: Update Word fields, repaginate, and export PDF**

Use Microsoft Word COM to update the TOC and fields, save the final DOCX, and export a PDF proof. Record total pages and Part III range.

- [ ] **Step 5: Render and inspect representative pages**

Inspect cover, TOC, theory page, openEuler page, each component opener, command/configuration page, disk initialization page, operations page, image-creation page, Chapter 16 opener, Chapter 17 operations page, and final page.

- [ ] **Step 6: Run full tests and scans**

Run: `python -m pytest -q`

Expected: all tests pass.

Run: `git diff --check`

Expected: no whitespace errors.

Run a targeted secret scan over tracked changes, final DOCX extracted XML, figure metadata, and the environment package. Expected: no SSH password, API Key, token, private key, cookie, or personal account information.

- [ ] **Step 7: Write the final QA report**

Record source hash unchanged, page geometry, paragraph/image/table counts, chapter/Part III pages, forbidden-content count zero, prompt coverage, real-figure status, environment checksum count, and visual inspection results.

- [ ] **Step 8: Commit and push**

```powershell
git add third-edition-work/revision third-edition-work/tools/revise_second_edition.py third-edition-work/tools/audit_second_base_docx.py third-edition-work/tests/test_second_base_revision.py third-edition-work/validation/second-base-revision-qa.md
git commit -m "feat: complete third edition from second edition base"
git push origin third-edition
```

---

## Plan Self-Review

- Spec coverage: all design sections map to at least one task, including typography, chapter flow, prompt-bearing commands, openEuler, Antelope, operations migration, Swift, image construction, agent chapters, ideology integration, figures, environment package, and final QA.
- Placeholder scan: no `TBD`, `TODO`, or implementation-later instruction is present. Unavailable real agent screenshots are explicitly omitted from the final DOCX rather than represented by placeholders.
- Interface consistency: all chapter tasks consume the same revision tool, revision map, fragment format, figure plan, and audit contracts established in Tasks 1–2.
- Scope control: each content batch is independently reviewable and commits before the next chapter group. The source DOCX remains immutable throughout.
