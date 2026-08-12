# OpenStack Third-Edition Textbook Master Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a verified, approximately 380-page third-edition Word textbook, all numbered high-resolution figures, and a reproducible teaching-environment package.

**Architecture:** Work is split into four independently reviewable streams: safe OpenStack lab validation, source-backed chapter authoring, TRAE/DeepSeek agent labs and screenshots, and deterministic Word/assets/environment assembly. Each stream produces files consumed by the next stream; the original second-edition DOCX and original `openstack-ts` directory remain unchanged.

**Tech Stack:** openEuler 24.03 LTS SP3, OpenStack 2023.1 Antelope RPMs, PowerShell, Python 3, Paramiko, python-docx/lxml, Microsoft Word or LibreOffice rendering, TRAE IDE domestic edition, DeepSeek API.

## Global Constraints

- External facts are frozen at 2026-07-31.
- Overview uses OpenStack 2026.1 Gazpacho; hands-on deployment uses OpenStack 2023.1 Antelope.
- Lab hosts are controller `192.168.234.151` and compute `192.168.234.150`.
- Management NIC is `ens33`; Provider NIC is `ens34` without an IP address.
- Compute system disk `/dev/sda` must never be initialized by Cinder or Swift.
- Cinder uses blank 50 GB `/dev/sdb`; Swift uses blank 50 GB `/dev/sdc`.
- Part II teaches manual package installation, database/service registration, and manual configuration editing.
- Every Part II deployment and operations command is typed manually, step by step. Each component must show manual configuration-file editing, manual database synchronization, manual database grants and identity/service/endpoint creation, and manual service enable/start/verification; scripts, agents, and orchestration models may validate these steps but must not replace them in the textbook procedure.
- Chapter 13 is the explicit exception authorized for agent-driven one-shot script installation; it must remain clearly separated from the manual Part II method.
- Component acceptance is intentionally lightweight: verify active/enabled services, a healthy API response, and one representative CLI/basic operation. Reserve complex fail-closed checks for destructive disk, overwrite, delete, or repository operations.
- Subagent concurrency is capped at three; normally use one implementer at a time, finish it, then use one independent reviewer and release completed agents before starting the next component.
- Chapter 13 lets TRAE call the verified scripts once to install OpenStack, then emphasizes multiple operations tasks.
- Total target is approximately 380 pages; Part III target is approximately 50 pages.
- Figures are numbered per chapter as `图1.1`; tables as `表1-1`.
- Every 2–3 chapters contains one integrated ideological/professional-literacy point.
- No final artifact stores plaintext passwords, API keys, cookies, or tokens.
- The workspace is not a Git repository; tasks create SHA-256 checkpoint files instead of Git commits.

---

## File Map

- Source of truth: `docs/superpowers/specs/2026-08-11-openstack-third-edition-textbook-design.md`
- Work root: `third-edition-work/`
- Safe script copy: `third-edition-work/deployment/openstack-ts/`
- Research register: `third-edition-work/research/source-register.md`
- Chapter sources: `third-edition-work/chapters/ch01.md` through `ch13.md`
- Figure registry: `third-edition-work/assets/figure-registry.csv`
- Validation records: `third-edition-work/validation/`
- Final DOCX: `云计算基础架构平台构建与应用（第三版初稿）.docx`
- Final figures: `第三版教材图片/`
- Final environment: `第三版教材配套环境/`

### Task 1: Validate the OpenStack laboratory and safe deployment copy

**Files:**
- Follow: `docs/superpowers/plans/2026-08-11-openstack-lab-validation-plan.md`
- Produce: `third-edition-work/deployment/openstack-ts/`
- Produce: `third-edition-work/validation/openstack-install/`

**Interfaces:**
- Consumes: original `openstack-ts/`, `openstack_repo.zip`, two clean virtual machines.
- Produces: safe scripts, exact version matrix, sanitized logs, verified manual command/configuration facts.

- [ ] Execute every task in the lab-validation plan.
- [ ] Stop unless both VM clean snapshots exist and the disk guard accepts `/dev/sdb` and `/dev/sdc`.
- [ ] Approve the stream only after Keystone, Glance, Placement, Nova, Neutron, Cinder, Swift, and Horizon pass end-to-end checks.

### Task 2: Rewrite and source-check all thirteen chapters

**Files:**
- Follow: `docs/superpowers/plans/2026-08-11-textbook-content-plan.md`
- Produce: `third-edition-work/chapters/ch01.md` through `ch13.md`
- Produce: `third-edition-work/research/source-register.md`

**Interfaces:**
- Consumes: approved design and verified facts/logs from Task 1.
- Produces: complete chapter text with figure/table callouts and citations.

- [ ] Execute every task in the textbook-content plan.
- [ ] Verify all thirteen chapter files contain learning objectives, content, practice, verification, summary, exercises, and required literacy point where scheduled.
- [ ] Approve the stream only when no Stein/CentOS-era command remains in active Antelope procedures.

### Task 3: Build the TRAE/DeepSeek labs and capture agent screenshots

**Files:**
- Follow: `docs/superpowers/plans/2026-08-11-agent-labs-plan.md`
- Modify: `third-edition-work/chapters/ch12.md`
- Modify: `third-edition-work/chapters/ch13.md`
- Produce: Chapter 12–13 images in `第三版教材图片/`

**Interfaces:**
- Consumes: safe script copy from Task 1 and Chapter 12–13 drafts from Task 2.
- Produces: real TRAE installation, DeepSeek access, one-shot deployment, operations-task screenshots, and sanitized result records.

- [ ] Execute every task in the agent-labs plan.
- [ ] Require the user to enter the DeepSeek API key interactively; never request or save it in a file.
- [ ] Approve the stream only when Chapter 13 independently reproduces installation and the defined operations tasks.

### Task 4: Assemble, render, verify, and package the third edition

**Files:**
- Follow: `docs/superpowers/plans/2026-08-11-docx-assets-environment-plan.md`
- Produce: `云计算基础架构平台构建与应用（第三版初稿）.docx`
- Produce: `第三版教材图片/`
- Produce: `第三版教材配套环境/`

**Interfaces:**
- Consumes: all chapter sources, figure registry, verified images/logs, and safe scripts.
- Produces: final deliverables and QA records.

- [ ] Execute every task in the DOCX/assets/environment plan.
- [ ] Confirm the original second-edition DOCX hash is unchanged.
- [ ] Approve the stream only after DOCX validation, PDF rendering, representative-page visual inspection, figure/table numbering checks, and environment SHA-256 checks pass.

### Task 5: Final cross-stream acceptance

**Files:**
- Create: `third-edition-work/validation/final-acceptance.md`
- Create: `third-edition-work/checkpoints/final.sha256`

**Interfaces:**
- Consumes: Tasks 1–4 deliverables.
- Produces: one acceptance record referencing all evidence.

- [ ] Record the final page count, chapter count, figure count, table count, and Part III page count in `final-acceptance.md`.
- [ ] Record successful service, network, instance, Cinder, and Swift end-to-end tests with timestamps.
- [ ] Run a credential scan: `rg -n -S "sk-[A-Za-z0-9_-]{16,}|guosai@205|OS_PASSWORD=." "云计算基础架构平台构建与应用（第三版初稿）.docx" "第三版教材图片" "第三版教材配套环境"` using extracted DOCX XML for the DOCX check; expected result is no unmasked secret.
- [ ] Generate hashes: `Get-FileHash -Algorithm SHA256 '云计算基础架构平台构建与应用（第三版初稿）.docx','第三版教材配套环境\09_官方来源与下载校验\SHA256SUMS.txt' | Format-List` and save them in `third-edition-work/checkpoints/final.sha256`.
- [ ] Compare deliverables against every acceptance bullet in the approved design; document each as PASS or FAIL.
