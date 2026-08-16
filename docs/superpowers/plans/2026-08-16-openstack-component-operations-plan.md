# OpenStack Component Operations Chapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a new Chapter 14 covering manual OpenStack component operations with real isolated-lab terminal and Horizon screenshots, and update the current third-edition Word file in place without developing Chapter 15 or later content.

**Architecture:** Keep Chapter 13 unchanged. Extend the bounded Open XML revision pipeline with one strict chapter-renumber operation, insert `ch14.md` before the renamed Chapter 15, and reuse the current figure/table manifest builder. Capture cloud operations in a dedicated `bookops` project, store only sanitized evidence and images, then delete task-owned resources by exact ID.

**Tech Stack:** Python 3, pytest, `zipfile`/Open XML, Paramiko with reviewed `known_hosts` and `RejectPolicy`, OpenStackClient on the controller node, Playwright headless Chromium for Horizon, Pillow for terminal-image rendering, Microsoft Word/PDF visual QA.

## Global Constraints

- Modify the current formal Word file in place; do not create another formal review DOCX.
- Chapter 13 remains `第十三章 Horizon的安装及云平台初始化`.
- Add `第十四章 OpenStack云平台各组件运维` and focus all content work on this chapter. The old `第十四章 虚拟机镜像文件的制作` receives only the minimum mechanical renumbering required to avoid a duplicate chapter number; its prose, illustrations, procedures, and later chapter planning are outside this task.
- Textbook commands are manually typed shell commands with second-edition prompts; no Python source or one-click deployment scripts appear in the textbook.
- All writable cloud resources live in project `bookops` and use the `bookops-` prefix; pre-existing resources are never adopted or deleted.
- Example textbook passwords are `qwer1234`; passwords, tokens, cookies, secret hashes, private keys, and session data are never stored in tracked files or screenshots.
- Controller is `192.168.234.151`; compute is `192.168.234.150`; strict reviewed host keys and Paramiko `RejectPolicy` are mandatory.
- Existing `admin`, `service`, `demo`, service configuration, databases, `/dev/sdb`, `/dev/sdc`, Cinder backends, Swift storage, and Placement inventories are read-only.
- Terminal screenshots use actual output, white background, black text, and no reconstructed rows; Horizon screenshots use a new headless browser profile and are deleted/recreated only inside the task image folder.
- Chinese text uses SimSun; English and numbers use Times New Roman; commands use the second-edition command style.
- Figures are numbered `图14.1` onward and tables `表14-1` onward; every figure/table is cited before insertion and explained afterward; no image notes are added.
- Do not create or restore VM snapshots.
- Preserve the existing untracked `.playwright-cli/` and `tmp/` directories and never stage them.

---

### Task 1: Chapter 14 insertion boundary and duplicate-number prevention

**Files:**
- Modify: `third-edition-work/tools/revise_second_edition.py`
- Modify: `third-edition-work/revision/revision-map-ch01-08.json`
- Create: `third-edition-work/tests/test_chapter14_operations.py`

**Interfaces:**
- Consumes: `DocxDocument`, `_normalized_text`, and strict revision-map processing from `revise_second_edition.py`.
- Produces: `renumber_chapter(doc: DocxDocument, heading: str, old_number: int, new_number: int) -> None` and revision-map operation `{"op":"renumber_chapter","heading":...,"old_number":"14","new_number":"15"}`.

- [ ] **Step 1: Write the failing bounded-renumber tests**

```python
def test_renumber_chapter_changes_only_target_chapter(doc_with_two_chapters):
    before = doc_with_two_chapters.parts.copy()
    revise.renumber_chapter(doc_with_two_chapters, "第十四章 虚拟机镜像文件的制作", 14, 15)
    text = revise.visible_paragraph_texts(doc_with_two_chapters)
    assert "第十五章 虚拟机镜像文件的制作" in text
    assert "15.1 镜像制作" in text
    assert "图15.1" in text and "表15-1" in text
    assert "第十三章 Horizon的安装及云平台初始化" in text
    assert doc_with_two_chapters.non_document_payloads == before.non_document_payloads

def test_renumber_chapter_rejects_missing_or_duplicate_heading(...): ...
def test_chapter14_inserted_once_before_chapter15(...): ...
```

- [ ] **Step 2: Run the tests and observe RED**

Run: `python -m pytest third-edition-work/tests/test_chapter14_operations.py -q`

Expected: failures because `renumber_chapter` and the new map operation do not exist.

- [ ] **Step 3: Implement the strict operation**

Add `renumber_chapter` that finds exactly one top-level heading, selects elements until the next same-level chapter heading or `sectPr`, and performs only the mechanical number changes required to keep the book structurally valid: `第十四章`→`第十五章`, heading/reference prefix `14.`→`15.`, `图14.`→`图15.`, and `表14-`→`表15-`. Do not rewrite or enrich any downstream prose. Reject a missing/duplicate heading and reject a requested number that does not match the chapter heading. Add the exact fields to `OPERATION_FIELDS` and dispatch before `insert_before`.

- [ ] **Step 4: Update the revision map**

Append, in this order:

```json
{
  "op": "renumber_chapter",
  "heading": "第十四章 虚拟机镜像文件的制作",
  "old_number": "14",
  "new_number": "15"
},
{
  "op": "insert_before",
  "heading": "第十五章 虚拟机镜像文件的制作",
  "fragment": "fragments/ch14.md"
}
```

- [ ] **Step 5: Run focused and full regression tests**

Run: `python -m pytest third-edition-work/tests/test_chapter14_operations.py third-edition-work/tests/test_second_base_revision.py -q`

Expected: all tests pass and non-document DOCX parts remain byte-identical in the synthetic mutation test.

- [ ] **Step 6: Commit**

```powershell
git add third-edition-work/tools/revise_second_edition.py third-edition-work/revision/revision-map-ch01-08.json third-edition-work/tests/test_chapter14_operations.py
git commit -m "feat: add bounded chapter fourteen insertion"
```

### Task 2: Safe capture and terminal rendering tools

**Files:**
- Create: `third-edition-work/tools/capture_ch14_operations.py`
- Create: `third-edition-work/tools/render_terminal_capture.py`
- Modify: `third-edition-work/tests/test_chapter14_operations.py`

**Interfaces:**
- Consumes: reviewed controller `known_hosts`, an in-memory SSH password from `getpass`, and controller-side `/root/admin-openrc`.
- Produces: `CaptureRecord(command: str, stdout: str, stderr: str, returncode: int)`, sanitized JSON under `third-edition-work/validation/ch14/`, and `render_capture(record, output_png, title) -> None`.

- [ ] **Step 1: Write RED tests for sanitization and rendering**

```python
def test_sanitize_rejects_tokens_passwords_cookies_and_private_keys(): ...
def test_renderer_produces_white_background_black_text(tmp_path): ...
def test_cleanup_accepts_only_owned_exact_ids(): ...
def test_strict_ssh_uses_reject_policy_and_reviewed_known_hosts(): ...
```

- [ ] **Step 2: Run RED**

Run: `python -m pytest third-edition-work/tests/test_chapter14_operations.py -k 'sanitize or renderer or owned or strict_ssh' -q`

Expected: failures because capture/rendering functions are absent.

- [ ] **Step 3: Implement minimal capture and renderer**

Implement a read/execute adapter that never prints the SSH password, loads only the reviewed host-key file, uses `RejectPolicy`, and records command output after blocking `OS_TOKEN`, `OS_PASSWORD`, `X-Auth-Token`, cookies, PEM material, and password-bearing URLs. Render actual text with Pillow on a white canvas using a bundled/available clear monospace font, dark text, 1.5 px gray border, and no line editing other than wrapping at whitespace.

- [ ] **Step 4: Add exact ownership manifest**

The runtime JSON must contain only type/name/project_id/object_id and creation order. Cleanup accepts an object only when its exact ID appears in the same run's manifest and its current project/name still match; otherwise it stops.

- [ ] **Step 5: Run tests**

Run: `python -m pytest third-edition-work/tests/test_chapter14_operations.py -q`

Expected: all chapter-14 tool tests pass.

- [ ] **Step 6: Commit**

```powershell
git add third-edition-work/tools/capture_ch14_operations.py third-edition-work/tools/render_terminal_capture.py third-edition-work/tests/test_chapter14_operations.py
git commit -m "feat: add safe operations capture tools"
```

### Task 3: Environment precheck and identity/image evidence

**Files:**
- Create: `third-edition-work/validation/ch14/precheck.txt`
- Create: `third-edition-work/validation/ch14/keystone.json`
- Create: `third-edition-work/validation/ch14/glance.json`
- Create: `third-edition-work/revision/figures/ch14/terminal-keystone.png`
- Create: `third-edition-work/revision/figures/ch14/terminal-glance.png`

**Interfaces:**
- Consumes: Task 2 capture tool.
- Produces: task-owned `bookops` project/user/group/role assignment and `bookops-image`, plus exact IDs held only in the runtime ownership manifest until cleanup.

- [ ] **Step 1: Run strict read-only precheck**

Verify controller/compute identity, OpenStack APIs, service status, no collision for `bookops` and every `bookops-*` object, no failed services, no task artifacts, and no change to the two compute data disks. Stop before any mutation on any unexpected result.

- [ ] **Step 2: Create identity sandbox manually through OpenStack CLI**

Create project `bookops`, user `bookops-user`, group `bookops-group`, add the user to the group, grant `member` on `bookops`, and query domain/project/user/group/role/service/endpoint output. Record exact IDs.

- [ ] **Step 3: Exercise Glance inside the sandbox**

Upload a small existing lab image as `bookops-image`, show/list it, change description and protected property, compare admin/task-user visibility, remove protection, and retain the image until Nova screenshots are complete.

- [ ] **Step 4: Render terminal captures**

Render only actual selected outputs. Confirm images contain no token, password, cookie, UUID belonging to infrastructure secrets, or private key.

- [ ] **Step 5: Verify scope**

Run the capture tool's read-only audit and expect exactly one task project, one task user, one task group, one task role assignment, and one task image; existing admin/service/demo objects are unchanged.

### Task 4: Placement, Nova, and Neutron evidence

**Files:**
- Create: `third-edition-work/validation/ch14/placement.json`
- Create: `third-edition-work/validation/ch14/nova.json`
- Create: `third-edition-work/validation/ch14/neutron.json`
- Create: `third-edition-work/revision/figures/ch14/terminal-placement.png`
- Create: `third-edition-work/revision/figures/ch14/terminal-nova.png`
- Create: `third-edition-work/revision/figures/ch14/terminal-neutron.png`

**Interfaces:**
- Consumes: Task 3 project/user/image and Task 2 ownership manifest.
- Produces: read-only Placement evidence and task-owned flavor, network, subnet, router, security group, port, floating IP if available, and one instance.

- [ ] **Step 1: Collect Placement read-only evidence**

Use the authenticated Placement API when the OSC plugin is unavailable. Capture resource provider, inventories `VCPU`, `MEMORY_MB`, `DISK_GB`, traits, usage, generation, and allocations without writing provider data.

- [ ] **Step 2: Create isolated Neutron resources**

Create `bookops-net`, `bookops-subnet`, `bookops-router`, task security group and rules. Attach the router only when an existing external network is available; otherwise document the isolated path and do not fabricate floating-IP output.

- [ ] **Step 3: Create Nova resources**

Create `bookops-flavor`, boot `bookops-server`, wait for `ACTIVE`, and perform stop/start, soft reboot, pause/unpause or shelve/unshelve only when the platform reports support. Capture actual state transitions and create `bookops-server-snapshot` only after the instance is stable.

- [ ] **Step 4: Verify exact resource graph**

Confirm the server belongs to `bookops`, uses the task image/flavor/network, and each port/security-group/router reference resolves to a task-owned ID. Stop if any relation points outside the sandbox except the read-only external network.

- [ ] **Step 5: Render terminal captures**

Produce selected actual-output images with readable text and no dynamic credentials.

### Task 5: Cinder and Swift evidence

**Files:**
- Create: `third-edition-work/validation/ch14/cinder.json`
- Create: `third-edition-work/validation/ch14/swift.json`
- Create: `third-edition-work/revision/figures/ch14/terminal-cinder.png`
- Create: `third-edition-work/revision/figures/ch14/terminal-swift.png`

**Interfaces:**
- Consumes: task project/server and the ownership manifest.
- Produces: task-owned volume/snapshot/derived volume and container/object, all deleted in Task 8.

- [ ] **Step 1: Exercise Cinder**

Create `bookops-volume`, wait for `available`, attach it to the exact task server, verify `in-use`, detach, create snapshot `bookops-volume-snapshot`, create a derived volume, and capture state/relationship output. Do not mount or format the volume inside the guest.

- [ ] **Step 2: Exercise Swift**

Create `bookops-container`, upload a small non-secret text object, list/show metadata, download and compare content in memory, update metadata, then retain until Dashboard capture.

- [ ] **Step 3: Verify backend boundaries**

Confirm Cinder services and Swift services remain active, `/dev/sdb` remains the Cinder PV, `/dev/sdc` remains the Swift XFS mount, and no service configuration changed.

- [ ] **Step 4: Render terminal captures**

Render actual results and ensure object content, hashes, tokens, passwords, and storage UUIDs are not shown.

### Task 6: Headless Horizon screenshots

**Files:**
- Create: `third-edition-work/tools/capture_ch14_horizon.py`
- Create: `third-edition-work/revision/figures/ch14/dashboard-login.png`
- Create: `third-edition-work/revision/figures/ch14/dashboard-project.png`
- Create: `third-edition-work/revision/figures/ch14/dashboard-images.png`
- Create: `third-edition-work/revision/figures/ch14/dashboard-instances.png`
- Create: `third-edition-work/revision/figures/ch14/dashboard-networks.png`
- Create: `third-edition-work/revision/figures/ch14/dashboard-volumes.png`
- Modify: `third-edition-work/tests/test_chapter14_operations.py`

**Interfaces:**
- Consumes: Horizon URL, `bookops-user`, password from in-memory prompt, and task resources from Tasks 3–5.
- Produces: cropped headless-browser PNG screenshots and no persistent browser profile.

- [ ] **Step 1: Write RED browser-isolation tests**

```python
def test_horizon_capture_uses_headless_new_context_and_closes_it(): ...
def test_horizon_capture_never_logs_password_cookie_or_token(): ...
def test_dashboard_images_have_expected_minimum_dimensions(): ...
```

- [ ] **Step 2: Run RED**

Run: `python -m pytest third-edition-work/tests/test_chapter14_operations.py -k horizon -q`

Expected: failures because the Horizon capture tool does not exist.

- [ ] **Step 3: Implement isolated capture**

Launch Playwright Chromium headless with a fresh temporary user-data directory, enter domain/user/password without logging input, wait for the project overview, capture only the page viewport, visit image/instance/network/volume pages, log out, close browser/context, and delete the exact temporary profile after verifying ownership.

- [ ] **Step 4: Capture and visually inspect**

Confirm each screenshot shows the `bookops` project and expected task objects, contains no password/token/cookie, is not clipped, and uses consistent scale.

- [ ] **Step 5: Run tests**

Run: `python -m pytest third-edition-work/tests/test_chapter14_operations.py -q`

Expected: all focused tests pass.

### Task 7: Chapter 14 manuscript, sources, figures, and tables

**Files:**
- Create: `third-edition-work/revision/fragments/ch14.md`
- Create: `third-edition-work/revision/research/ch14-sources-20260816.json`
- Create: `third-edition-work/revision/figures/ch14-figure-manifest.json`
- Create: `third-edition-work/revision/tables/ch14-table-manifest.json`
- Modify: `third-edition-work/tests/test_chapter14_operations.py`

**Interfaces:**
- Consumes: actual outputs/screenshots from Tasks 3–6 and second-edition Chapter 13 structure.
- Produces: one complete textbook chapter with eight H2 sections, 24–32 figure markers, and chapter-local tables; no Chapter 15 or later manuscript is authored in this task.

- [ ] **Step 1: Write RED manuscript-contract tests**

Test exact H1/H2 order, H2→Chinese-number→Arabic-number hierarchy, no empty leaf heading, no `Python`/`脚本`/`教学活动`/`复习思考`, all shell lines containing `[root@controller ~]#`, `[root@compute ~]#`, or a MariaDB prompt, all figures/tables cited before marker, and all required cleanup commands present.

- [ ] **Step 2: Run RED**

Run: `python -m pytest third-edition-work/tests/test_chapter14_operations.py -k manuscript -q`

Expected: failures because `ch14.md` and manifests are absent.

- [ ] **Step 3: Write Chapter 14**

Write continuous textbook narration for Keystone, Glance, Placement, Nova, Neutron, Cinder, Swift, and Horizon. Each section explains the object model and state transitions before commands, includes manual command prompts, cites real screenshots, explains output fields, and gives exact cleanup operations. First-use terms include English full name and Chinese explanation.

- [ ] **Step 4: Create figure and table manifests**

Map `图14.1` onward to real PNG files with widths that preserve readable text; create tables covering sandbox objects, common states, cross-component relationships, and cleanup order. Use no image notes.

- [ ] **Step 5: Run focused tests and prose scans**

Run: `python -m pytest third-edition-work/tests/test_chapter14_operations.py -q`

Run: `rg -n '教学活动|复习思考|作者建议|不宜把|教学云|TODO|TBD' third-edition-work/revision/fragments/ch14.md`

Expected: tests pass; the scan prints no matches.

- [ ] **Step 6: Commit chapter assets**

```powershell
git add third-edition-work/revision/fragments/ch14.md third-edition-work/revision/research/ch14-sources-20260816.json third-edition-work/revision/figures/ch14 third-edition-work/revision/figures/ch14-figure-manifest.json third-edition-work/revision/tables/ch14-table-manifest.json third-edition-work/tests/test_chapter14_operations.py
git commit -m "docs: add manual OpenStack operations chapter"
```

### Task 8: Exact cleanup and final cloud audit

**Files:**
- Create: `third-edition-work/validation/ch14/final-audit.txt`
- Modify: `third-edition-work/validation/ch14/*.json`

**Interfaces:**
- Consumes: exact ownership manifest from Tasks 3–5.
- Produces: zero task-owned cloud resources and a sanitized final audit.

- [ ] **Step 1: Delete task resources by exact dependency order**

Delete exact task server/snapshot, detach/delete exact volumes/snapshots, delete Swift object/container, floating IP/ports/router interfaces/router/subnet/network/security group, flavor/image, role assignment/group/user/project. Before each delete, re-query exact ID, name, and project.

- [ ] **Step 2: Confirm zero task residue**

Search every supported service for names prefixed `bookops-` and the exact `bookops` identity objects. Expect zero results; any collision or query error is a failure rather than an empty result.

- [ ] **Step 3: Confirm platform health and storage boundaries**

Check controller/compute OpenStack services active, component APIs responsive, existing admin/service/demo objects present, compute services up, Cinder/Swift backend status unchanged, and `/dev/sdb`/`/dev/sdc` unchanged.

- [ ] **Step 4: Remove exact temporary evidence containing raw runtime data**

Delete only task-owned runtime ownership JSON, browser profile, downloaded image/object/volume test payloads, and SSH temporary files after matching their ownership marker. Retain sanitized tracked evidence and screenshots.

### Task 9: In-place Word integration and visual verification

**Files:**
- Modify in place: `D:/codex/云计算教材更新/云计算基础架构平台构建与应用（第三版第1-3章审阅稿-20260815-04修复版）.docx`
- Create: `.superpowers/sdd/ch14-operations-report.md` (ignored local report)

**Interfaces:**
- Consumes: revised maps, `ch14.md`, figure/table manifests, current formal DOCX.
- Produces: one updated formal DOCX with Chapter 14 inserted and old Chapter 14 renumbered to Chapter 15.

- [ ] **Step 1: Build to a task-owned temporary DOCX**

Run the existing two-stage bounded revision and manifest builder against the current formal Word file, adding the Chapter 14 figure/table manifests. The temporary output must be outside the project root formal-file set.

- [ ] **Step 2: Run structural checks before replacement**

Verify ZIP/XML integrity, exactly one Chapter 13/14/15 H1 in order, no old `第十四章 虚拟机镜像文件的制作`, no `图14.*`/`表14-*` left inside the image-production chapter, all 24–32 Chapter 14 images embedded once, and package media/relationships resolve.

- [ ] **Step 3: Open with Word and export PDF**

Open the temporary DOCX with Word, update fields/TOC, save, export PDF, close only the Word instance started by this task, and reopen both DOCX and PDF. Do not terminate unrelated Word processes.

- [ ] **Step 4: Visual QA every Chapter 14 page**

Render Chapter 14 PDF pages and inspect every page for SimSun/Times New Roman usage, heading hierarchy, table numbering, readable terminal text, unclipped Dashboard screenshots, arrows/boxes without overlap, figure width, captions, blank pages, and Chapter 15 transition.

- [ ] **Step 5: Replace the current formal Word atomically**

After structural and visual checks pass, copy the temporary DOCX to a same-directory exclusive temporary name, verify SHA-256 and openability, then atomically replace only the current formal Word file. Confirm the project root still contains exactly the second-edition source and this current third-edition DOCX.

- [ ] **Step 6: Run complete verification**

Run:

```powershell
python -m pytest third-edition-work/tests/test_chapter14_operations.py -q
python -m pytest third-edition-work/tests -q
git diff --check
```

Expected: zero failures and no whitespace errors. Reopen the final DOCX once more and record page count, Chapter 14/15 start pages, figure/table counts, final SHA-256, cloud cleanup result, and Word/PDF visual result in the ignored report.

- [ ] **Step 7: Commit and push**

```powershell
git add docs/superpowers/plans/2026-08-16-openstack-component-operations-plan.md third-edition-work
git commit -m "docs: complete OpenStack operations chapter"
git push origin third-edition
```

Do not stage `.playwright-cli/`, `tmp/`, runtime ownership manifests, browser profiles, secrets, or the formal DOCX outside the repository.

## Self-Review

- Spec coverage: Chapter 13 preservation, new Chapter 14, old Chapter 15 renumbering, eight components, sandboxed operations, actual terminal results, headless Horizon screenshots, exact cleanup, no Python in textbook, in-place Word update, figure/table numbering, and visual QA are each assigned to a task.
- Placeholder scan: the plan contains no `TODO`, `TBD`, “implement later”, or undefined “similar to” steps.
- Type consistency: `CaptureRecord`, `render_capture`, the ownership manifest, `renumber_chapter`, and Horizon capture outputs have a single name and role throughout the plan.
- Safety boundary: no step authorizes snapshots, service reconfiguration, database mutation, disk initialization, deletion by fuzzy name, or reuse of pre-existing `bookops` objects.
