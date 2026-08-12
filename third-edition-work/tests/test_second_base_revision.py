"""Contracts that freeze the immutable second-edition Word source."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from xml.etree import ElementTree as ET
import zipfile


WORK_ROOT = Path(__file__).resolve().parents[1]
BASELINE_JSON = WORK_ROOT / "revision" / "second-edition-style-baseline.json"
AUDIT_TOOL = WORK_ROOT / "tools" / "audit_second_base_docx.py"
SOURCE_FILENAME = "云计算基础架构平台构建与应用（第二版初稿）.docx"


def find_source_docx() -> Path:
    for directory in (WORK_ROOT, *WORK_ROOT.parents):
        candidate = directory / SOURCE_FILENAME
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"cannot locate {SOURCE_FILENAME}")


def load_revision_module():
    spec = importlib.util.spec_from_file_location("second_base_revision", AUDIT_TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_source_hash_and_geometry() -> None:
    revision = load_revision_module()
    source = find_source_docx()

    baseline = revision.load_baseline(BASELINE_JSON)

    assert revision.sha256(source) == baseline["source_sha256"]
    result = revision.measure_docx(source)
    assert result["page_cm"] == [18.4, 26.0]
    assert result["margins_cm"] == [2.0, 2.0, 2.0, 2.0]


def test_baseline_captures_measured_style_invariants() -> None:
    revision = load_revision_module()
    baseline = revision.load_baseline(BASELINE_JSON)
    result = revision.measure_docx(find_source_docx())

    for field in (
        "section_count",
        "header_cm",
        "footer_cm",
        "body_font",
        "body_size_pt",
        "heading_sizes_pt",
        "caption_format",
        "paragraph_count",
        "inline_shape_count",
        "table_count",
    ):
        assert result[field] == baseline[field]


def test_audit_accepts_the_frozen_source() -> None:
    revision = load_revision_module()
    source = find_source_docx()

    assert revision.audit_docx(source, source) == []


def test_audit_reports_a_candidate_with_changed_margins(tmp_path: Path) -> None:
    revision = load_revision_module()
    source = find_source_docx()
    candidate = tmp_path / "changed-margin.docx"
    namespace = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

    with zipfile.ZipFile(source) as original, zipfile.ZipFile(candidate, "w") as changed:
        for member in original.infolist():
            payload = original.read(member.filename)
            if member.filename == "word/document.xml":
                document = ET.fromstring(payload)
                margin = document.find(f".//{{{namespace}}}pgMar")
                assert margin is not None
                margin.set(f"{{{namespace}}}top", "1200")
                payload = ET.tostring(document, encoding="utf-8", xml_declaration=True)
            changed.writestr(member, payload)

    assert any("margins_cm" in error for error in revision.audit_docx(source, candidate))
