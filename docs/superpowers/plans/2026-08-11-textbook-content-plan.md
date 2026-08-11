# Third-Edition Textbook Content Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce complete, source-backed manuscript files for all thirteen chapters within the approved page budget.

**Architecture:** Author modular Markdown chapter sources with a uniform pedagogical schema, then assemble them later into Word. Official-source research is separated from prose so facts, dates, URLs, figures, and access dates remain auditable.

**Tech Stack:** Markdown, official web/PDF sources, local DOCX extraction, verified OpenStack lab records.

## Global Constraints

- Facts freeze at 2026-07-31.
- Use primary/official sources for software, standards, policies, market data, and screenshots whenever available.
- Part II commands/configuration must come from the verified manual run, not untested recollection.
- Chapter sources must not contain real credentials.
- Figure callouts use `图N.M`; table callouts use `表N-M`.
- Page budgets are 90 pages for Part I, 232 for Part II, and 50 for Part III.

---

### Task 1: Build the source register and extract reusable second-edition material

**Files:**
- Create: `third-edition-work/research/source-register.md`
- Create: `third-edition-work/research/second-edition-content-map.md`
- Create: `third-edition-work/research/reuse-decisions.csv`

**Interfaces:**
- Consumes: original DOCX and approved design.
- Produces: traceable source/reuse decisions used by all chapters.

- [ ] List every second-edition Heading 1/2 range, paragraph count, image count, and disposition: retain, rewrite, merge, or delete.
- [ ] Mark the old terminal-tools section for deletion and the old Stein/CentOS procedures for replacement.
- [ ] Add official source entries for OpenStack releases/docs, openEuler SP3, CAICT cloud reports, NIST/ISO cloud definitions, TRAE, DeepSeek, Claude Code, Codex, OpenClaw, and Hermes Agent.
- [ ] For every source record title, publisher, publication/update date, URL, access date `2026-08-11`, intended chapter, and allowable figure use.
- [ ] Run `rg -n -S "TBD|TODO|待补|待查" third-edition-work/research`; expected result is no match.

### Task 2: Author Part I, Chapters 1–4

**Files:**
- Create: `third-edition-work/chapters/ch01.md`
- Create: `third-edition-work/chapters/ch02.md`
- Create: `third-edition-work/chapters/ch03.md`
- Create: `third-edition-work/chapters/ch04.md`

**Interfaces:**
- Consumes: source register and approved 90-page structure.
- Produces: cloud-industry, ecosystem, OpenStack overview, and openEuler/environment chapters.

- [ ] Write Chapter 1 with cloud definitions, evolution, service/deployment models, cloud native, edge/AI cloud, sovereign cloud, FinOps, and 2026-cutoff industry evidence.
- [ ] Write Chapter 2 as comparative platform/ecosystem analysis; remove stale revenue/product counts and avoid vendor advertising language.
- [ ] Write Chapter 3 with corrected OpenStack origin, core/optional services, release cadence, SLURP, 2026.1 Gazpacho, and an explicit Gazpacho-versus-Antelope table.
- [ ] Write Chapter 4 with openEuler history/features, SP3/Linux 6.6, two-VM topology, VMware resources, two NICs, compute `/dev/sdb` and `/dev/sdc`, OS installation, and one-page terminal choice.
- [ ] Add literacy boxes after Chapters 2 and 4 using the approved themes.
- [ ] Add chapter objectives, summaries, practice questions, and figure/table callouts.

### Task 3: Author Part II foundational and identity/image/resource chapters

**Files:**
- Create: `third-edition-work/chapters/ch05.md`
- Create: `third-edition-work/chapters/ch06.md`
- Create: `third-edition-work/chapters/ch07.md`

**Interfaces:**
- Consumes: verified manual-install records for base services, Keystone, Glance, and Placement.
- Produces: complete hand-edited installation chapters.

- [ ] Write Chapter 5 with hostname/network/time, local repository, MariaDB, RabbitMQ, Memcached, client packages, and verification.
- [ ] Write Chapter 6 with Keystone DB/grants, service user/role/entity/endpoints, config edits, Fernet/bootstrap/OpenRC, and verification.
- [ ] Write Chapter 7 with separate complete Glance and Placement procedures; include all DB, identity, endpoint, config, sync, service, and check steps.
- [ ] Explain configuration keys adjacent to the exact INI blocks instead of appending a disconnected option glossary.
- [ ] Add the approved permission/security literacy box after Chapter 6.

### Task 4: Author Part II compute, network, and storage chapters

**Files:**
- Create: `third-edition-work/chapters/ch08.md`
- Create: `third-edition-work/chapters/ch09.md`
- Create: `third-edition-work/chapters/ch10.md`

**Interfaces:**
- Consumes: verified Nova, Neutron, Cinder, and Swift records.
- Produces: exact two-node manual procedures with safety warnings.

- [ ] Write Chapter 8 with Nova DBs/cells, endpoints, config on both nodes, VNC, libvirt/QEMU, `compute_id`, discovery, and scheduling checks.
- [ ] Write Chapter 9 with ML2/Linux Bridge/VXLAN/Provider mappings, agents, namespaces, tenant/external networks, router, and network troubleshooting.
- [ ] Write Chapter 10 with an explicit preflight showing `/dev/sda` is root, `/dev/sdb` is Cinder, and `/dev/sdc` is Swift before any destructive command.
- [ ] Explain Cinder LVM/iSCSI and Swift one-device/one-replica teaching limitations.
- [ ] Add craftsmanship after Chapter 8 and data-responsibility after Chapter 10.

### Task 5: Author Part II Horizon, initialization, operations, and image material

**Files:**
- Create: `third-edition-work/chapters/ch11.md`

**Interfaces:**
- Consumes: verified Horizon and end-to-end records.
- Produces: a complete platform-use and operations chapter.

- [ ] Write Horizon installation/configuration and `/dashboard/` access.
- [ ] Write CLI and Horizon workflows for images, flavors, projects/users/quotas, networks/subnets/router, security groups/key pairs, instances, floating IPs, volumes, Swift containers/objects, snapshots, and resource cleanup.
- [ ] Replace obsolete CentOS 7.1/Windows Server 2012 focus with CirrOS quick verification and openEuler 24.03 LTS SP3 cloud image as the primary guest.
- [ ] Include the proven RabbitMQ permission, time-drift, compute discovery, Linux Bridge experimental flag, and Horizon WEBROOT cases.

### Task 6: Author Part III draft chapters

**Files:**
- Create: `third-edition-work/chapters/ch12.md`
- Create: `third-edition-work/chapters/ch13.md`

**Interfaces:**
- Consumes: official agent sources and safe deployment facts.
- Produces: text slots ready for real screenshots from the agent-labs plan.

- [ ] Write Chapter 12 sections for agent concepts/ecosystem, four domestic products, Claude Code, Codex, OpenClaw, Hermes Agent, TRAE installation, DeepSeek access, custom agent, and security.
- [ ] Write Chapter 13 installation task and all sixteen approved operations tasks.
- [ ] For every screenshot slot, add a unique proposed caption using chapter-only numbering and record it in the figure registry; do not invent screenshot results.
- [ ] Add the responsible-AI/human-oversight literacy box across Chapters 11–13.

### Task 7: Perform manuscript consistency and scope QA

**Files:**
- Create: `third-edition-work/validation/content-qa.md`
- Create: `third-edition-work/checkpoints/chapter-sources.sha256`

**Interfaces:**
- Consumes: all thirteen chapter files.
- Produces: approved manuscript sources ready for layout.

- [ ] Search for banned active-procedure terms: `CentOS_7.1`, `Stein版本`, `192.168.234.152`, Cinder `/dev/sda`, and unmasked `guosai@205`; explain historical mentions or remove them.
- [ ] Confirm every component includes DB/user/service/endpoint steps where applicable.
- [ ] Confirm exactly six literacy boxes occur at the approved chapter intervals.
- [ ] Confirm all figure captions match `^图([1-9]|1[0-3])\.[1-9][0-9]*` and all tables match `^表([1-9]|1[0-3])-[1-9][0-9]*`.
- [ ] Record estimated page allocation per chapter and rebalance prose/figures to the 372-page body target.
- [ ] Hash all chapter files and save the sorted results in `chapter-sources.sha256`.

