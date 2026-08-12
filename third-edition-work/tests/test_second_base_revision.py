"""Contracts that freeze the immutable second-edition Word source."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import re
import subprocess
import sys
from xml.etree import ElementTree as ET
import zipfile


WORK_ROOT = Path(__file__).resolve().parents[1]
BASELINE_JSON = WORK_ROOT / "revision" / "second-edition-style-baseline.json"
AUDIT_TOOL = WORK_ROOT / "tools" / "audit_second_base_docx.py"
SOURCE_FILENAME = "云计算基础架构平台构建与应用（第二版初稿）.docx"
WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
DRAWING_NS = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
NS = {"w": WORD_NS, "wp": DRAWING_NS}
W = f"{{{WORD_NS}}}"
FIGURE_CAPTION = re.compile(r"^图\d+\.\d+\.\d+")


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


def write_mutated_docx(source: Path, candidate: Path, mutate) -> None:
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(candidate, "w") as changed:
        for member in original.infolist():
            payload = original.read(member.filename)
            if member.filename == "word/document.xml":
                document = ET.fromstring(payload)
                mutate(document)
                payload = ET.tostring(document, encoding="utf-8", xml_declaration=True)
            changed.writestr(member, payload)


def figure_caption_paragraphs(document: ET.Element) -> list[ET.Element]:
    body = document.find("w:body", NS)
    assert body is not None
    captions: list[ET.Element] = []
    paragraphs = body.findall("w:p", NS)
    for index, paragraph in enumerate(paragraphs[:-1]):
        if paragraph.findall(".//wp:inline", NS):
            next_text = "".join(node.text or "" for node in paragraphs[index + 1].findall(".//w:t", NS)).strip()
            if FIGURE_CAPTION.match(next_text):
                captions.append(paragraphs[index + 1])
    return captions


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
    def mutate(document: ET.Element) -> None:
        margin = document.find(f".//{{{WORD_NS}}}pgMar")
        assert margin is not None
        margin.set(f"{{{WORD_NS}}}top", "1200")

    write_mutated_docx(source, candidate, mutate)

    assert any("margins_cm" in error for error in revision.audit_docx(source, candidate))


def test_audit_rejects_any_source_other_than_the_frozen_hash() -> None:
    revision = load_revision_module()
    non_frozen_source = next(
        path for directory in (WORK_ROOT, *WORK_ROOT.parents)
        for path in directory.glob("*.docx")
        if path != find_source_docx() and path.stat().st_size > 1_000_000
    )

    assert any("source_sha256" in error for error in revision.audit_docx(non_frozen_source, non_frozen_source))


def test_audit_reports_a_second_section_geometry_change(tmp_path: Path) -> None:
    revision = load_revision_module()
    source = find_source_docx()
    candidate = tmp_path / "changed-second-section.docx"

    def mutate(document: ET.Element) -> None:
        sections = document.findall(".//w:sectPr", NS)
        assert len(sections) == 5
        margins = sections[1].find("w:pgMar", NS)
        assert margins is not None
        margins.set(f"{W}left", "1200")

    write_mutated_docx(source, candidate, mutate)

    assert any("sections[1].margins_cm" in error for error in revision.audit_docx(source, candidate))


def test_audit_reports_later_caption_style_and_numbering_mutations(tmp_path: Path) -> None:
    revision = load_revision_module()
    source = find_source_docx()
    candidate = tmp_path / "changed-later-caption.docx"

    def mutate(document: ET.Element) -> None:
        captions = figure_caption_paragraphs(document)
        assert len(captions) > 2
        second_caption = captions[1]
        text = second_caption.find(".//w:t", NS)
        properties = second_caption.find(".//w:rPr", NS)
        assert text is not None and text.text is not None and properties is not None
        text.text = text.text.replace(".", "-", 1)
        fonts = properties.find("w:rFonts", NS)
        assert fonts is not None
        fonts.set(f"{W}eastAsia", "Arial")

    write_mutated_docx(source, candidate, mutate)

    errors = revision.audit_docx(source, candidate)
    assert any("caption[1].numbering" in error for error in errors)
    assert any("caption[1].font" in error for error in errors)


def test_audit_reports_inline_width_and_body_run_direct_format_mutations(tmp_path: Path) -> None:
    revision = load_revision_module()
    source = find_source_docx()
    candidate = tmp_path / "changed-image-and-body-run.docx"

    def mutate(document: ET.Element) -> None:
        extent = document.find(".//wp:inline/wp:extent", NS)
        assert extent is not None
        extent.set("cx", str(int(extent.attrib["cx"]) + 1))
        for paragraph in document.findall(".//w:body/w:p", NS):
            text = "".join(node.text or "" for node in paragraph.findall(".//w:t", NS)).strip()
            if text and not FIGURE_CAPTION.match(text):
                run = paragraph.find("w:r", NS)
                assert run is not None
                properties = run.find("w:rPr", NS)
                if properties is None:
                    properties = ET.SubElement(run, f"{W}rPr")
                fonts = properties.find("w:rFonts", NS)
                if fonts is None:
                    fonts = ET.SubElement(properties, f"{W}rFonts")
                fonts.set(f"{W}eastAsia", "Arial")
                break
        else:
            raise AssertionError("no body run found")

    write_mutated_docx(source, candidate, mutate)

    errors = revision.audit_docx(source, candidate)
    assert any("inline_widths_emu" in error for error in errors)
    assert any("body_run_direct_format" in error for error in errors)


def test_cli_rejects_non_frozen_source_from_an_arbitrary_cwd(tmp_path: Path) -> None:
    non_frozen_source = next(
        path for directory in (WORK_ROOT, *WORK_ROOT.parents)
        for path in directory.glob("*.docx")
        if path != find_source_docx() and path.stat().st_size > 1_000_000
    )

    result = subprocess.run(
        [sys.executable, str(AUDIT_TOOL), "--source", str(non_frozen_source), "--candidate", str(non_frozen_source)],
        cwd=tmp_path,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "source_sha256" in result.stderr.decode("utf-8", errors="replace")


def test_cli_checks_source_hash_before_opening_an_untrusted_docx(tmp_path: Path) -> None:
    not_a_docx = tmp_path / "not-a-docx.docx"
    not_a_docx.write_bytes(b"not a ZIP archive")

    result = subprocess.run(
        [sys.executable, str(AUDIT_TOOL), "--source", str(not_a_docx), "--candidate", str(not_a_docx)],
        cwd=tmp_path,
        capture_output=True,
        check=False,
    )

    stderr = result.stderr.decode("utf-8", errors="replace")
    assert result.returncode == 1
    assert "source_sha256" in stderr
    assert "Traceback" not in stderr
