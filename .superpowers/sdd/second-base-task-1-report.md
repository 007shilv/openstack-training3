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
python third-edition-work/tools/audit_second_base_docx.py --source "D:\codex\云计算教材更新\云计算基础架构平台构建与应用（第二版初稿）.docx" --candidate "D:\codex\云计算教材更新\云计算基础架构平台构建与应用（第二版初稿）.docx"
git diff --check
```

Results:

- Focused baseline tests: 4 passed.
- Existing deployment-contract suite: 192 passed.
- The source hash remains `96bcad5246cc56574f5f38f4b210b8f0ed71363a1794fac9beb877332d2ae5d6`.
- All five source sections measure 18.4 × 26.0 cm with 2.0 cm page margins.
- Open XML totals are 5,202 main-body paragraphs, 522 inline shapes, and 3 tables.
- `git diff --check` passed.

## Files

- `third-edition-work/revision/second-edition-style-baseline.json`
- `third-edition-work/tools/audit_second_base_docx.py`
- `third-edition-work/tests/test_second_base_revision.py`

## Commit

`a3795f73b531deeaaadf1f82eada6481dd7900f2` — `test: freeze second edition textbook baseline`

## Risks and follow-up

The existing Markdown-generated third-edition draft fails the audit, as
intended: it has a different section count, Letter-sized page geometry,
different margins and missing frozen style details.  It is reference material,
not an approved third-edition base.  Future work should copy the second-edition
source before making targeted edits and use the audit tool against that copy.
