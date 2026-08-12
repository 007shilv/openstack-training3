# Task 1 Report: Second-Edition Base and Style Contract

## Result

The immutable second-edition DOCX is frozen as a UTF-8 JSON contract.  The
audit tool reads DOCX Open XML directly; it does not launch or paginate Word.

## RED

Command:

```powershell
python -m pytest third-edition-work/tests/test_second_base_revision.py -k source_hash -v
```

Result: failed as expected because
`third-edition-work/tools/audit_second_base_docx.py` did not yet exist.

## GREEN and verification

Commands:

```powershell
python -m pytest third-edition-work/tests/test_second_base_revision.py -v
python -m pytest third-edition-work/tests/test_deployment_contract.py -q
python third-edition-work/tools/audit_second_base_docx.py --source "D:\codex\云计算教材更新\云计算基础架构平台构建与应用（第二版初稿）.docx" --candidate "D:\codex\云计算教材更新\云计算基础架构平台构建与应用（第三版初稿）.docx"
git diff --check
```

Results:

- Focused baseline tests: 4 passed.
- Existing deployment-contract suite: 192 passed.
- The source hash remains `96bcad5246cc56574f5f38f4b210b8f0ed71363a1794fac9beb877332d2ae5d6`.
- All five source sections measure 18.4 × 26.0 cm with 2.0 cm page margins.
- Open XML totals are 5,202 main-body paragraphs, 522 inline shapes, and 3 tables.
- `git diff --check` passed.
- The real old third-edition candidate audit exited 1, confirming it is not an
  eligible second-edition-based source.

## Files

- `third-edition-work/revision/second-edition-style-baseline.json`
- `third-edition-work/tools/audit_second_base_docx.py`
- `third-edition-work/tests/test_second_base_revision.py`

## Commit

Initial freeze: `b0727960b66e6184d63967055b10f8af0666fa0e` — `test: freeze second edition textbook baseline`.

## Risks and follow-up

The existing Markdown-generated third-edition draft fails the audit, as
intended: it has a different section count, Letter-sized page geometry,
different margins and missing frozen style details.  It is reference material,
not an approved third-edition base.  Future work should copy the second-edition
source before making targeted edits and use the audit tool against that copy.

## Review remediation: frozen-source and complete style audit

Review mutations exposed that the original audit compared a caller-provided
source against itself, checked only the first section, and did not freeze
per-caption, image-width, or direct-run formatting invariants.  The repair
now loads the committed baseline internally and fails before opening the DOCX
when the supplied source SHA-256 is not the frozen value.

### RED

```powershell
python -m pytest third-edition-work/tests/test_second_base_revision.py -v
```

Result before the repair: 5 new mutation cases failed.  They covered a
non-frozen source hash, a second-section margin change, a later caption's
delimiter/font change, an inline-image width change, a body run's direct font
change, and CLI behavior from an arbitrary current directory.

### GREEN and verification

```powershell
python -m pytest third-edition-work/tests/test_second_base_revision.py -v
python -m pytest third-edition-work/tests/test_deployment_contract.py -q
git diff --check
```

The repaired audit freezes all five section records; parses every caption that
is immediately adjacent to an inline picture; compares its real numbering
separators, font, size, boldness, and alignment; freezes the complete inline
width sequence via a UTF-8 canonical SHA-256; and freezes direct body-run
font/size formatting via a canonical signature.  It also validates the
effective Normal and Heading 1–3 style values.

The CLI was executed from a separate temporary working directory.  It passed
for the frozen second edition (exit 0) and rejected the old third-edition draft
(exit 1) before parsing it, reporting its actual non-frozen source hash
`51112be7edb3bf190be8cece9f7d1911b781d317be1403cc5c81c5f47b5e0c4e`.

The follow-up commit covers this review remediation and the evidence above;
its immutable Git hash is supplied after commit creation rather than being
prewritten here.

## Final review remediation: all figure-caption text runs

The caption auditor initially inspected only the first run properties.  A
further RED mutation changed the second visible text run of the second
multi-run, image-adjacent caption to Arial; the focused test failed because
the change was invisible to the auditor.  The repair resolves each visible
caption run through direct properties, run/paragraph styles, style inheritance,
and document defaults, then compares every run's effective font, size, and
bold value at its caption/run index.  The source has 475 multi-run captions.
The new focused mutation test passes after the repair.
