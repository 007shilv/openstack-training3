"""Contracts that freeze the immutable second-edition Word source."""

from __future__ import annotations

import importlib.util
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from xml.etree import ElementTree as ET
import zipfile

import pytest


WORK_ROOT = Path(__file__).resolve().parents[1]
BASELINE_JSON = WORK_ROOT / "revision" / "second-edition-style-baseline.json"
AUDIT_TOOL = WORK_ROOT / "tools" / "audit_second_base_docx.py"
REVISION_TOOL = WORK_ROOT / "tools" / "revise_second_edition.py"
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


def load_bounded_revision_module():
    spec = importlib.util.spec_from_file_location("bounded_second_base_revision", REVISION_TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def sha256_bytes(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixture_paragraph(text: str, style: str | None = None, marker: str = "body") -> str:
    style_xml = f'<w:pStyle w:val="{style}"/>' if style else ""
    return (
        f'<w:p data-marker="{marker}"><w:pPr>{style_xml}'
        f'<w:spacing w:after="{len(marker)}"/></w:pPr><w:r><w:t>{text}</w:t></w:r></w:p>'
    )


def write_bounded_fixture(path: Path, middle: list[str] | None = None) -> None:
    middle = middle or [fixture_paragraph("old section text", marker="old")]
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<w:body>'
        + fixture_paragraph("ordinary template", marker="body-template")
        + fixture_paragraph("[root@controller ~]# true", marker="command-template")
        + fixture_paragraph("[DEFAULT] enabled=true", marker="config-template")
        + fixture_paragraph("图1.1.1 示例", marker="caption-template")
        + fixture_paragraph("Start   Heading", style="1", marker="start-heading")
        + "".join(middle)
        + fixture_paragraph("End Heading", style="1", marker="end-heading")
        + fixture_paragraph("outside untouched", marker="outside")
        + '<w:p data-marker="image"><w:pPr/><w:r><w:drawing><w:object r:id="rIdImage1"/>'
          '</w:drawing></w:r></w:p>'
        + '<w:sectPr data-marker="section"><w:pgSz w:w="10432" w:h="14740"/>'
          '<w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134"/>'
          '</w:sectPr></w:body></w:document>'
    ).encode("utf-8")
    relationships = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rIdImage1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
        'Target="media/image1.png"/></Relationships>'
    ).encode("utf-8")
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", b"<Types/>")
        archive.writestr("word/document.xml", document_xml)
        archive.writestr("word/_rels/document.xml.rels", relationships)
        archive.writestr("word/footer1.xml", b"<footer>frozen footer</footer>")
        archive.writestr("word/media/image1.png", b"not-a-real-png-but-byte-stable")


def raw_marked_element(xml: bytes, marker: str) -> bytes:
    match = re.search(
        rb'<w:(?:p|sectPr) data-marker="' + re.escape(marker.encode()) + rb'".*?</w:(?:p|sectPr)>',
        xml,
    )
    assert match is not None
    return match.group(0)


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


def test_audit_reports_the_second_text_run_of_a_later_multi_run_caption(tmp_path: Path) -> None:
    revision = load_revision_module()
    source = find_source_docx()
    candidate = tmp_path / "changed-second-caption-text-run.docx"

    def mutate(document: ET.Element) -> None:
        multi_run_captions = []
        for caption in figure_caption_paragraphs(document):
            text_runs = [run for run in caption.findall("w:r", NS) if run.findall(".//w:t", NS)]
            if len(text_runs) > 1:
                multi_run_captions.append(text_runs)
        assert len(multi_run_captions) >= 2
        second_text_run = multi_run_captions[1][1]
        properties = second_text_run.find("w:rPr", NS)
        if properties is None:
            properties = ET.SubElement(second_text_run, f"{W}rPr")
        fonts = properties.find("w:rFonts", NS)
        if fonts is None:
            fonts = ET.SubElement(properties, f"{W}rFonts")
        fonts.set(f"{W}eastAsia", "Arial")

    write_mutated_docx(source, candidate, mutate)

    assert any("caption[1].text_runs[1].font" in error for error in revision.audit_docx(source, candidate))


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


def test_bounded_replace_preserves_everything_outside_heading_range(tmp_path: Path) -> None:
    revision = load_bounded_revision_module()
    source = tmp_path / "source.docx"
    candidate = tmp_path / "candidate.docx"
    write_bounded_fixture(source)

    document = revision.load_docx(source)
    revision.replace_between_headings(
        document,
        "  Start Heading ",
        "End\tHeading",
        [revision.Block(kind="body", text="new bounded text")],
    )
    revision.save_candidate(document, candidate)

    with zipfile.ZipFile(source) as before, zipfile.ZipFile(candidate) as after:
        before_xml = before.read("word/document.xml")
        after_xml = after.read("word/document.xml")
        assert b"old section text" not in after_xml
        assert b"new bounded text" in after_xml
        for marker in ("start-heading", "end-heading", "outside", "image", "section"):
            assert raw_marked_element(after_xml, marker) == raw_marked_element(before_xml, marker)
        for member in (
            "word/_rels/document.xml.rels",
            "word/footer1.xml",
            "word/media/image1.png",
        ):
            assert after.read(member) == before.read(member)


def test_bounded_replace_fails_closed_for_duplicate_normalized_heading(tmp_path: Path) -> None:
    revision = load_bounded_revision_module()
    source = tmp_path / "duplicate.docx"
    write_bounded_fixture(
        source,
        [
            fixture_paragraph("inside", marker="inside"),
            fixture_paragraph("Start Heading", style="2", marker="duplicate-start"),
        ],
    )

    document = revision.load_docx(source)
    with pytest.raises(ValueError, match="unique"):
        revision.replace_between_headings(
            document,
            "Start Heading",
            "End Heading",
            [revision.Block(kind="body", text="replacement")],
        )


def test_heading_mutations_fail_for_missing_or_reverse_ranges(tmp_path: Path) -> None:
    revision = load_bounded_revision_module()
    source = tmp_path / "source.docx"
    write_bounded_fixture(source)

    with pytest.raises(ValueError, match="unique"):
        revision.delete_between_headings(
            revision.load_docx(source), "Missing Heading", "End Heading"
        )
    with pytest.raises(ValueError, match="order"):
        revision.delete_between_headings(
            revision.load_docx(source), "End Heading", "Start Heading"
        )
    with pytest.raises(ValueError, match="unique"):
        revision.insert_before_heading(
            revision.load_docx(source),
            "Missing Heading",
            [revision.Block(kind="body", text="never inserted")],
        )


@pytest.mark.parametrize(
    "mapping,error",
    [
        ([{"op": "rename", "heading": "End Heading"}], "unknown op"),
        (
            [{"op": "delete", "start_heading": "Start Heading", "end_heading": "End Heading", "extra": 1}],
            "unknown fields",
        ),
        (
            [{"op": "replace", "start_heading": "Start Heading", "end_heading": "End Heading"}],
            "missing fields",
        ),
        ([{"op": "insert_before", "heading": "End Heading"}], "missing fields"),
    ],
)
def test_revision_map_schema_rejects_unknown_or_incomplete_operations(
    tmp_path: Path, mapping: object, error: str
) -> None:
    revision = load_bounded_revision_module()
    path = tmp_path / "revision-map.json"
    path.write_text(json.dumps(mapping), encoding="utf-8")

    with pytest.raises(ValueError, match=error):
        revision.load_revision_map(path)


def test_empty_revision_map_is_an_exact_byte_copy(tmp_path: Path) -> None:
    revision = load_bounded_revision_module()
    source = tmp_path / "source.docx"
    output = tmp_path / "copy.docx"
    mapping = tmp_path / "revision-map.json"
    write_bounded_fixture(source)
    mapping.write_text("[]\n", encoding="utf-8")

    revision.apply_revision_map(source, mapping, output)

    assert output.read_bytes() == source.read_bytes()
    assert sha256_bytes(output) == sha256_bytes(source)


def test_block_schema_rejects_unknown_kind_and_invalid_figure_payload(tmp_path: Path) -> None:
    revision = load_bounded_revision_module()
    with pytest.raises(ValueError, match="kind"):
        revision.Block(kind="quote", text="unsupported")
    with pytest.raises(ValueError, match="image"):
        revision.Block(kind="figure", text="not a path")
