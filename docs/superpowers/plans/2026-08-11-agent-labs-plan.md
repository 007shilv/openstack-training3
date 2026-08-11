# TRAE and DeepSeek Agent Labs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce reproducible Chapter 12–13 procedures and real, sanitized screenshots for TRAE installation, DeepSeek access, one-shot OpenStack deployment, and multi-task operations.

**Architecture:** Capture a clean Windows/Trae workflow, then use one custom OpenStack agent to invoke the safe script copy on restored VMs. After installation, issue isolated natural-language operations tasks and verify each result independently with OpenStack CLI/API evidence.

**Tech Stack:** Windows 11, TRAE IDE domestic edition, DeepSeek official API, Python/Paramiko remote runner, openEuler/OpenStack lab, PNG/SVG asset pipeline.

## Global Constraints

- User enters the DeepSeek API key interactively; it is never pasted into chat, a script, a screenshot, or a deliverable.
- All account identifiers are cropped or blurred.
- Screenshots are PNG, ideally 1920×1080 or greater, with readable UI/terminal text.
- Chapter 13 may execute only the safe script copy that passed the lab-validation contract tests.
- Each destructive or privileged action requires a visible plan/confirmation step in the teaching narrative.

---

### Task 1: Establish the figure registry and capture standard

**Files:**
- Create: `third-edition-work/assets/figure-registry.csv`
- Create: `third-edition-work/assets/screenshot-standard.md`
- Create: `第三版教材图片/`

**Interfaces:**
- Consumes: Chapter 12–13 screenshot slots.
- Produces: unique numbers, captions, paths, sources, and status for every image.

- [ ] Define CSV columns: `figure_no,chapter,caption,type,source_url,access_date,local_path,width,height,status`.
- [ ] Reserve sequential Chapter 12 and 13 figure numbers without section numbers.
- [ ] Record requirements: terminal 16 px minimum, browser 100–125%, no secrets, no unrelated desktop content, and lossless PNG.
- [ ] Add an automated duplicate check that fails when two rows share `figure_no` or `local_path`.

### Task 2: Capture agent ecosystem figures

**Files:**
- Create: Chapter 12 ecosystem PNGs in `第三版教材图片/`
- Modify: `third-edition-work/assets/figure-registry.csv`

**Interfaces:**
- Consumes: official pages for TRAE, Lingma, CodeBuddy, Comate, Claude Code, Codex, OpenClaw, and Hermes Agent.
- Produces: eight source-attributed interface figures.

- [ ] Capture or obtain official interface views for the four domestic products.
- [ ] Capture official interface views for Claude Code and OpenAI Codex only; do not include GitHub Copilot, Cursor, or Windsurf.
- [ ] Capture official OpenClaw and Nous Research Hermes Agent interface/project views.
- [ ] Add source URL and 2026-08-11 access date to the registry for every external figure.
- [ ] Verify all text is readable at the planned Word width of approximately 14.4 cm.

### Task 3: Install TRAE and connect DeepSeek

**Files:**
- Create: Chapter 12 installation/configuration PNGs in `第三版教材图片/`
- Create: `third-edition-work/validation/agent-labs/deepseek-connectivity.md`

**Interfaces:**
- Consumes: TRAE official installer and user-entered DeepSeek key.
- Produces: complete, reproducible Chapter 12 sequence.

- [ ] Record TRAE installer version, official URL, SHA-256, Windows version, and installation date.
- [ ] Capture download, installer, first launch, login, project open, and settings/model entry screens.
- [ ] Have the user create or select a DeepSeek API key and enter it directly into TRAE while capture is paused.
- [ ] Capture provider/model/Base URL fields with the key field fully masked.
- [ ] Send a non-destructive connectivity prompt and capture the response/model indicator.
- [ ] Record the exact model ID and API endpoint in `deepseek-connectivity.md`, but never the key.

### Task 4: Create the OpenStack deployment and operations agent

**Files:**
- Create: `third-edition-work/agent/openstack-agent-prompt.md`
- Create: `third-edition-work/agent/task-prompts.md`
- Create: Chapter 12 custom-agent PNGs in `第三版教材图片/`

**Interfaces:**
- Consumes: safe scripts and design constraints.
- Produces: reusable, sanitized agent instructions and operations prompts.

- [ ] Write the agent role with exact hosts, NICs, data disks, service order, approval boundaries, and required post-checks.
- [ ] Prohibit use of `/dev/sda`, credential disclosure, firewall/network changes beyond the scripts, and destructive cleanup outside named OpenStack resources.
- [ ] Add a required preflight response schema: environment facts, risk list, planned stages, rollback point, and approval request.
- [ ] Write sixteen operations prompts matching Chapter 13 tasks, each with expected verification commands.
- [ ] Capture custom-agent creation, model binding, tools, prompt, and confirmation-policy screens.

### Task 5: Run one-shot OpenStack installation through TRAE

**Files:**
- Create: `third-edition-work/validation/agent-labs/install-session.md`
- Create: Chapter 13 installation PNGs in `第三版教材图片/`

**Interfaces:**
- Consumes: restored VM snapshots and safe scripts.
- Produces: one complete installation session and agent-generated acceptance report.

- [ ] Restore both clean VM snapshots and reconfirm `/dev/sdb` and `/dev/sdc` are blank.
- [ ] Open the safe script project in TRAE and issue one installation request.
- [ ] Capture agent analysis of Antelope versions, `.151/.150` addresses, `/dev/sdb`, `/dev/sdc`, and the 17-stage order.
- [ ] Approve the plan only after the disk safety checks are shown.
- [ ] Let TRAE execute the full staged installation, capturing milestone rather than every repeated command.
- [ ] Capture final service/endpoint/agent/storage/Horizon checks and the generated acceptance report.
- [ ] Sanitize exported session text and save it in `install-session.md`.

### Task 6: Execute and verify the sixteen operations tasks

**Files:**
- Create: `third-edition-work/validation/agent-labs/operations/01.md` through `16.md`
- Create: Chapter 13 operations PNGs in `第三版教材图片/`

**Interfaces:**
- Consumes: working platform, task prompts, CirrOS and openEuler cloud images.
- Produces: verified evidence for every Chapter 13 task.

- [ ] Run each task separately: services, identity/quota, images, flavors, Provider network, tenant network/router, security/key pair, boot, floating IP, Cinder, Swift, snapshot/rebuild, resource change/delete, inspection report, fault diagnosis, cleanup.
- [ ] For each task, save the user prompt, agent plan, commands/actions, CLI/API verification, screenshot numbers, and PASS/FAIL.
- [ ] Use unique resource names prefixed `book-` so cleanup is safely scoped.
- [ ] Do not mark a task PASS solely from agent prose; require independent OpenStack CLI/API output.
- [ ] After cleanup, verify no `book-` resources remain.

### Task 7: QA Chapter 12–13 visuals and security

**Files:**
- Create: `third-edition-work/validation/agent-labs/visual-security-qa.md`
- Create: `third-edition-work/checkpoints/agent-assets.sha256`

**Interfaces:**
- Consumes: all Chapter 12–13 images and records.
- Produces: approved, sanitized visual set.

- [ ] Scan OCR-visible and text records for passwords, API keys, usernames, email addresses, and tokens; redact and recapture any failure.
- [ ] Verify every registered figure exists, opens, is at least the required resolution, and has a unique chapter-only number.
- [ ] Inspect all figures at approximately 14.4 cm display width for legibility.
- [ ] Verify Chapter 12 shows the complete install/DeepSeek path and Chapter 13 shows installation plus all sixteen tasks.
- [ ] Hash all approved images and save results in `agent-assets.sha256`.

