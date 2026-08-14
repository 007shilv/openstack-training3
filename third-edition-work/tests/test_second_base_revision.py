"""Contracts that freeze the immutable second-edition Word source."""

from __future__ import annotations

import csv
import importlib.util
import hashlib
import json
from pathlib import Path
import re
import statistics
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
FRAGMENTS_DIR = WORK_ROOT / "revision" / "fragments"
FIGURE_PLAN = WORK_ROOT / "revision" / "figures" / "figure-plan.csv"
CHAPTERS_1_2_FIGURE_MANIFEST = (
    WORK_ROOT / "revision" / "figures" / "ch01-02-figure-manifest.json"
)
TASK3_FRAGMENTS = {
    1: FRAGMENTS_DIR / "ch01.md",
    2: FRAGMENTS_DIR / "ch02.md",
    3: FRAGMENTS_DIR / "ch03.md",
}
TASK4_FRAGMENT = FRAGMENTS_DIR / "ch04.md"
TASK5_FRAGMENTS = {
    5: FRAGMENTS_DIR / "ch05.md",
    6: FRAGMENTS_DIR / "ch06.md",
}
TASK6_FRAGMENTS = {
    7: FRAGMENTS_DIR / "ch07.md",
    8: FRAGMENTS_DIR / "ch08.md",
}


def task3_fragment(chapter: int) -> str:
    return TASK3_FRAGMENTS[chapter].read_text(encoding="utf-8")


def task4_fragment() -> str:
    return TASK4_FRAGMENT.read_text(encoding="utf-8")


def task5_fragment(chapter: int) -> str:
    return TASK5_FRAGMENTS[chapter].read_text(encoding="utf-8")


def task6_fragment(chapter: int) -> str:
    return TASK6_FRAGMENTS[chapter].read_text(encoding="utf-8")


def prose_paragraphs(markdown: str) -> list[str]:
    return [
        " ".join(line.strip() for line in block.splitlines())
        for block in re.split(r"\n\s*\n", markdown)
        if block.strip() and not block.lstrip().startswith("#")
    ]


def compact_length(value: str) -> int:
    return len(re.sub(r"\s+", "", value))


def h2_sections(markdown: str) -> list[tuple[str, str]]:
    """Return each H2 and its body without turning textbook inner levels into TOC headings."""

    matches = list(re.finditer(r"(?m)^## ([^\n]+)\s*$", markdown))
    return [
        (
            match.group(1),
            markdown[match.end() : matches[index + 1].start() if index + 1 < len(matches) else None],
        )
        for index, match in enumerate(matches)
    ]


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
    body_xml = (
        '<w:jc w:val="both"/><w:ind w:firstLine="420" w:firstLineChars="200"/>'
        '<w:rPr><w:rFonts w:eastAsia="宋体"/></w:rPr>'
        if marker == "body-template"
        else ""
    )
    return (
        f'<w:p data-marker="{marker}"><w:pPr>{style_xml}'
        f'<w:spacing w:after="{len(marker)}"/>{body_xml}</w:pPr>'
        f'<w:r><w:t>{text}</w:t></w:r></w:p>'
    )


def fixture_section_break(marker: str = "section-break") -> str:
    return (
        f'<w:p data-marker="{marker}"><w:pPr><w:sectPr>'
        '<w:pgSz w:w="10432" w:h="14740"/>'
        '<w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134"/>'
        '</w:sectPr></w:pPr></w:p>'
    )


def fixture_text_section_break(
    text: str = "obsolete chapter text carrying a section break",
    marker: str = "text-section-break",
) -> str:
    return (
        f'<w:p data-marker="{marker}"><w:pPr><w:sectPr>'
        '<w:pgSz w:w="10432" w:h="14740"/>'
        '<w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134"/>'
        f'</w:sectPr></w:pPr><w:r><w:t>{text}</w:t></w:r></w:p>'
    )


def fixture_page_break(marker: str = "page-break") -> str:
    return (
        f'<w:p data-marker="{marker}"><w:pPr><w:jc w:val="left"/></w:pPr>'
        '<w:r><w:br w:type="page"/></w:r></w:p>'
    )


def fixture_part_opener(marker: str = "part-opener") -> str:
    return (
        f'<w:p data-marker="{marker}"><w:pPr><w:jc w:val="center"/>'
        '<w:rPr><w:rFonts w:eastAsia="宋体"/><w:sz w:val="52"/></w:rPr></w:pPr>'
        '<w:r><w:lastRenderedPageBreak/><w:t>第二部分 原生OpenStack云平台基础环境的构建</w:t>'
        '</w:r></w:p>'
    )


def write_bounded_fixture(
    path: Path,
    middle: list[str] | None = None,
    *,
    start_style: str | None = "1",
) -> None:
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
        + fixture_paragraph("Start   Heading", style=start_style, marker="start-heading")
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
        archive.comment = b"fixture archive comment"
        archive.writestr("[Content_Types].xml", b"<Types/>")
        archive.writestr("word/document.xml", document_xml)
        archive.writestr(
            "word/styles.xml",
            (
                '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                '<w:docDefaults><w:rPrDefault><w:rPr><w:sz w:val="21"/></w:rPr>'
                '</w:rPrDefault></w:docDefaults>'
                '<w:style w:type="paragraph" w:default="1" w:styleId="a">'
                '<w:name w:val="Normal"/><w:pPr><w:jc w:val="both"/></w:pPr></w:style>'
                '<w:style w:type="paragraph" w:styleId="1"><w:name w:val="heading 1"/>'
                '<w:pPr><w:outlineLvl w:val="0"/></w:pPr></w:style>'
                '<w:style w:type="paragraph" w:styleId="2"><w:name w:val="heading 2"/>'
                '<w:pPr><w:outlineLvl w:val="1"/></w:pPr></w:style></w:styles>'
            ).encode("utf-8"),
        )
        archive.writestr("word/_rels/document.xml.rels", relationships)
        footer = zipfile.ZipInfo("word/footer1.xml")
        footer.comment = b"fixture member comment"
        footer.extra = b"\x99\x99\x00\x00"
        archive.writestr(footer, b"<footer>frozen footer</footer>")
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
        assert after.comment == before.comment
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
        before_footer = before.getinfo("word/footer1.xml")
        after_footer = after.getinfo("word/footer1.xml")
        assert after_footer.comment == before_footer.comment
        assert after_footer.extra == before_footer.extra


def test_bounded_replace_preserves_a_trailing_section_break(tmp_path: Path) -> None:
    revision = load_bounded_revision_module()
    source = tmp_path / "source.docx"
    candidate = tmp_path / "candidate.docx"
    write_bounded_fixture(
        source,
        [
            fixture_paragraph("old chapter text", marker="old-chapter"),
            fixture_section_break(),
        ],
    )

    document = revision.load_docx(source)
    revision.replace_between_headings(
        document,
        "Start Heading",
        "End Heading",
        [revision.Block(kind="body", text="new chapter text")],
    )
    revision.save_candidate(document, candidate)

    with zipfile.ZipFile(source) as before, zipfile.ZipFile(candidate) as after:
        before_xml = before.read("word/document.xml")
        after_xml = after.read("word/document.xml")
        assert b"old chapter text" not in after_xml
        assert b"new chapter text" in after_xml
        assert before_xml.count(b"<w:sectPr") == 2
        assert after_xml.count(b"<w:sectPr") == 2
        assert raw_marked_element(after_xml, "section-break") == raw_marked_element(
            before_xml, "section-break"
        )


def test_bounded_replace_keeps_a_trailing_section_break_but_drops_its_old_text(
    tmp_path: Path,
) -> None:
    revision = load_bounded_revision_module()
    source = tmp_path / "source.docx"
    candidate = tmp_path / "candidate.docx"
    write_bounded_fixture(
        source,
        [
            fixture_paragraph("old chapter text", marker="old-chapter"),
            fixture_text_section_break(),
        ],
    )

    document = revision.load_docx(source)
    revision.replace_between_headings(
        document,
        "Start Heading",
        "End Heading",
        [revision.Block(kind="body", text="new chapter text")],
    )
    revision.save_candidate(document, candidate)

    with zipfile.ZipFile(candidate) as after:
        after_xml = after.read("word/document.xml")
        assert b"obsolete chapter text carrying a section break" not in after_xml
        assert after_xml.count(b"<w:sectPr") == 2


def test_bounded_replace_uses_a_leading_fragment_h1_to_replace_the_old_h1(
    tmp_path: Path,
) -> None:
    revision = load_bounded_revision_module()
    source = tmp_path / "source.docx"
    candidate = tmp_path / "candidate.docx"
    write_bounded_fixture(source)

    document = revision.load_docx(source)
    revision.replace_between_headings(
        document,
        "Start Heading",
        "End Heading",
        [
            revision.Block(kind="heading1", text="Replacement Heading"),
            revision.Block(kind="body", text="replacement body"),
        ],
    )
    revision.save_candidate(document, candidate)

    revised = revision.load_docx(candidate)
    _, children, _ = revision._body_parts(revised.document_xml)
    texts = [
        revision._normalize_heading(revision._child_text(revised.document_xml, child))
        for child in children
    ]
    assert "Start Heading" not in texts
    assert texts.count("Replacement Heading") == 1
    assert texts.count("End Heading") == 1


def test_task3_replace_preserves_page_break_and_retitles_the_part_opener(
    tmp_path: Path,
) -> None:
    revision = load_bounded_revision_module()
    source = tmp_path / "source.docx"
    revision_dir = tmp_path / "revision"
    fragments = revision_dir / "fragments"
    fragments.mkdir(parents=True)
    write_bounded_fixture(
        source,
        [
            fixture_paragraph("old chapter text", marker="old-chapter"),
            fixture_page_break(),
            fixture_part_opener(),
        ],
    )
    (fragments / "chapter.md").write_text("new chapter text\n", encoding="utf-8")
    revision_map = revision_dir / "revision-map.json"
    revision_map.write_text(
        json.dumps(
            [
                {
                    "op": "replace_with_part_opener",
                    "start_heading": "Start Heading",
                    "end_heading": "End Heading",
                    "fragment": "fragments/chapter.md",
                    "part_title": "第二部分 信创OpenStack云平台构建与应用",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    candidate = tmp_path / "candidate.docx"

    revision.apply_revision_map(source, revision_map, candidate)

    with zipfile.ZipFile(source) as before, zipfile.ZipFile(candidate) as after:
        before_xml = before.read("word/document.xml")
        after_xml = after.read("word/document.xml")
        assert b"old chapter text" not in after_xml
        assert b"new chapter text" in after_xml
        assert raw_marked_element(after_xml, "page-break") == raw_marked_element(
            before_xml, "page-break"
        )
        before_opener = raw_marked_element(before_xml, "part-opener")
        after_opener = raw_marked_element(after_xml, "part-opener")
        assert revision._paragraph_properties(after_opener) == revision._paragraph_properties(
            before_opener
        )
        assert "第二部分 信创OpenStack云平台构建与应用" in revision._child_text(
            after_xml, after_opener
        )
        assert "第二部分 原生OpenStack云平台基础环境的构建" not in revision._child_text(
            after_xml, after_opener
        )


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


def test_heading_boundary_rejects_an_ordinary_paragraph_with_the_same_text(tmp_path: Path) -> None:
    revision = load_bounded_revision_module()
    source = tmp_path / "ordinary-heading.docx"
    write_bounded_fixture(source, start_style=None)

    with pytest.raises(ValueError, match="heading"):
        revision.replace_between_headings(
            revision.load_docx(source),
            "Start Heading",
            "End Heading",
            [revision.Block(kind="body", text="must not be inserted")],
        )


def test_ordinary_same_named_paragraph_does_not_make_a_real_heading_ambiguous(
    tmp_path: Path,
) -> None:
    revision = load_bounded_revision_module()
    source = tmp_path / "ordinary-duplicate.docx"
    write_bounded_fixture(
        source,
        [
            fixture_paragraph("Start Heading", marker="ordinary-duplicate"),
            fixture_paragraph("old section text", marker="old"),
        ],
    )

    document = revision.load_docx(source)
    revision.replace_between_headings(
        document,
        "Start Heading",
        "End Heading",
        [revision.Block(kind="body", text="replacement")],
    )

    assert b"replacement" in document.document_xml
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


def test_nonempty_save_refuses_an_existing_output_and_preserves_its_sentinel(
    tmp_path: Path,
) -> None:
    revision = load_bounded_revision_module()
    source = tmp_path / "source.docx"
    output = tmp_path / "existing.docx"
    write_bounded_fixture(source)
    output.write_bytes(b"do not overwrite this sentinel")
    document = revision.load_docx(source)
    revision.replace_between_headings(
        document,
        "Start Heading",
        "End Heading",
        [revision.Block(kind="body", text="replacement")],
    )

    with pytest.raises(FileExistsError, match="existing"):
        revision.save_candidate(document, output)

    assert output.read_bytes() == b"do not overwrite this sentinel"


@pytest.mark.parametrize("fragment", ["../outside.md", "C:/absolute/fragment.md"])
def test_fragment_path_rejects_parent_escape_and_absolute_paths(
    tmp_path: Path, fragment: str
) -> None:
    revision = load_bounded_revision_module()
    source = tmp_path / "source.docx"
    revision_dir = tmp_path / "revision"
    revision_dir.mkdir()
    write_bounded_fixture(source)
    (tmp_path / "outside.md").write_text("outside", encoding="utf-8")
    revision_map = revision_dir / "revision-map.json"
    revision_map.write_text(
        json.dumps(
            [
                {
                    "op": "replace",
                    "start_heading": "Start Heading",
                    "end_heading": "End Heading",
                    "fragment": fragment,
                }
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="fragment"):
        revision.apply_revision_map(source, revision_map, tmp_path / "candidate.docx")


def test_fragment_path_rejects_a_symlink_even_when_its_target_is_regular(tmp_path: Path) -> None:
    revision = load_bounded_revision_module()
    source = tmp_path / "source.docx"
    revision_dir = tmp_path / "revision"
    revision_dir.mkdir()
    write_bounded_fixture(source)
    target = revision_dir / "target.md"
    target.write_text("target", encoding="utf-8")
    link = revision_dir / "fragment.md"
    try:
        link.symlink_to(target)
        fragment = link.name
    except OSError:
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "target.md").write_text("target", encoding="utf-8")
        junction = revision_dir / "fragment-link"
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(junction), str(outside)],
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            pytest.skip("neither file symlinks nor directory junctions are available")
        fragment = "fragment-link/target.md"
    revision_map = revision_dir / "revision-map.json"
    revision_map.write_text(
        json.dumps(
            [
                {
                    "op": "replace",
                    "start_heading": "Start Heading",
                    "end_heading": "End Heading",
                    "fragment": fragment,
                }
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="symlink"):
        revision.apply_revision_map(source, revision_map, tmp_path / "candidate.docx")


def test_fragment_path_accepts_only_a_regular_file_beneath_the_map_directory(
    tmp_path: Path,
) -> None:
    revision = load_bounded_revision_module()
    source = tmp_path / "source.docx"
    revision_dir = tmp_path / "revision"
    fragments = revision_dir / "fragments"
    fragments.mkdir(parents=True)
    write_bounded_fixture(source)
    (fragments / "bounded.md").write_text("safe bounded text", encoding="utf-8")
    revision_map = revision_dir / "revision-map.json"
    revision_map.write_text(
        json.dumps(
            [
                {
                    "op": "replace",
                    "start_heading": "Start Heading",
                    "end_heading": "End Heading",
                    "fragment": "fragments/bounded.md",
                }
            ]
        ),
        encoding="utf-8",
    )
    output = tmp_path / "candidate.docx"

    revision.apply_revision_map(source, revision_map, output)

    with zipfile.ZipFile(output) as archive:
        assert b"safe bounded text" in archive.read("word/document.xml")


def test_block_schema_rejects_unknown_kind_and_defers_figures_to_a_later_task(
    tmp_path: Path,
) -> None:
    revision = load_bounded_revision_module()
    with pytest.raises(ValueError, match="kind"):
        revision.Block(kind="quote", text="unsupported")
    with pytest.raises(ValueError, match="kind"):
        revision.Block(kind="figure", text="figure.png")


def test_fragment_parser_rejects_markdown_images_until_figure_support_is_implemented(
    tmp_path: Path,
) -> None:
    revision = load_bounded_revision_module()
    fragment = tmp_path / "fragment.md"
    fragment.write_text("![图1.1.1 示例](figure.png)\n", encoding="utf-8")

    with pytest.raises(ValueError, match="figure"):
        revision.parse_fragment(fragment)


def test_real_second_edition_templates_have_the_required_measured_properties() -> None:
    revision = load_bounded_revision_module()
    document = revision.load_docx(find_source_docx())
    styles = ET.fromstring(document.payloads["word/styles.xml"])
    default_run = styles.find("w:docDefaults/w:rPrDefault/w:rPr", NS)
    assert default_run is not None
    default_size = default_run.find("w:sz", NS)
    assert default_size is not None and default_size.get(f"{W}val") == "21"

    templates = {
        kind: revision._template_paragraph(document, kind)
        for kind in ("body", "command", "config", "heading1", "heading2", "caption")
    }
    elements = {
        kind: revision._parse_child(document.document_xml, paragraph)
        for kind, paragraph in templates.items()
    }

    body = elements["body"]
    body_properties = body.find("w:pPr", NS)
    assert body_properties is not None
    body_alignment = body_properties.find("w:jc", NS)
    if body_alignment is None:
        normal_style = next(
            style
            for style in styles.findall("w:style", NS)
            if style.get(f"{W}type") == "paragraph" and style.get(f"{W}default") == "1"
        )
        body_alignment = normal_style.find("w:pPr/w:jc", NS)
    assert body_alignment is not None and body_alignment.get(f"{W}val") == "both"
    indentation = body_properties.find("w:ind", NS)
    assert indentation is not None
    assert indentation.get(f"{W}firstLineChars") == "200"
    paragraph_run = body_properties.find("w:rPr", NS)
    assert paragraph_run is not None
    fonts = paragraph_run.find("w:rFonts", NS)
    assert fonts is not None and fonts.get(f"{W}eastAsia") == "宋体"
    assert paragraph_run.find("w:sz", NS) is None

    command_text = revision._child_text(document.document_xml, templates["command"]).strip()
    config_text = revision._child_text(document.document_xml, templates["config"]).strip()
    assert revision.COMMAND_PATTERN.match(command_text)
    assert not revision.COMMAND_PATTERN.match(config_text)
    assert revision.CONFIG_PATTERN.match(config_text)
    assert command_text != config_text
    command_properties = elements["command"].find("w:pPr", NS)
    config_properties = elements["config"].find("w:pPr", NS)
    assert command_properties is not None and config_properties is not None
    assert command_properties.find("w:jc", NS).get(f"{W}val") == "left"
    assert config_properties.find("w:jc", NS).get(f"{W}val") == "left"
    for properties in (command_properties, config_properties):
        fonts = properties.find("w:rPr/w:rFonts", NS)
        assert fonts is not None and fonts.get(f"{W}eastAsia") == "宋体"
    assert command_properties.find("w:ind", NS) is None
    assert config_properties.find("w:ind", NS).get(f"{W}firstLineChars") == "202"

    assert revision._paragraph_style(document.document_xml, templates["heading1"]) == "1"
    assert revision._paragraph_style(document.document_xml, templates["heading2"]) == "2"
    heading_styles = {
        style.get(f"{W}styleId"): style
        for style in styles.findall("w:style", NS)
        if style.get(f"{W}styleId") in {"1", "2"}
    }
    assert heading_styles["1"].find("w:pPr/w:outlineLvl", NS).get(f"{W}val") == "0"
    assert heading_styles["1"].find("w:rPr/w:sz", NS).get(f"{W}val") == "44"
    assert heading_styles["2"].find("w:pPr/w:outlineLvl", NS).get(f"{W}val") == "1"
    assert heading_styles["2"].find("w:rPr/w:sz", NS).get(f"{W}val") == "32"
    caption = elements["caption"]
    caption_properties = caption.find("w:pPr", NS)
    assert caption_properties is not None
    assert caption_properties.find("w:jc", NS).get(f"{W}val") == "center"
    caption_run = caption_properties.find("w:rPr", NS)
    assert caption_run is not None
    assert caption_run.find("w:b", NS) is not None
    assert caption_run.find("w:sz", NS).get(f"{W}val") == "18"


@pytest.mark.parametrize(
    "kind,template_text",
    [("command", "[root@controller ~]# true"), ("config", "[DEFAULT] enabled=true")],
)
def test_command_and_config_templates_do_not_fall_back_to_body(
    tmp_path: Path, kind: str, template_text: str
) -> None:
    revision = load_bounded_revision_module()
    source = tmp_path / "source.docx"
    without_template = tmp_path / "without-template.docx"
    write_bounded_fixture(source)

    with zipfile.ZipFile(source) as original, zipfile.ZipFile(without_template, "w") as changed:
        changed.comment = original.comment
        for member in original.infolist():
            payload = original.read(member.filename)
            if member.filename == "word/document.xml":
                needle = template_text.encode("utf-8")
                assert payload.count(needle) == 1
                payload = payload.replace(
                    needle, b"ordinary paragraph without a special template", 1
                )
            changed.writestr(member, payload)

    with pytest.raises(ValueError, match=kind):
        revision._template_paragraph(revision.load_docx(without_template), kind)


def test_task3_fragments_keep_second_edition_heading_and_narrative_density() -> None:
    expected_sections = {
        1: [
            "## 1.1 计算模式的演变",
            "## 1.2 云计算的定义",
            "## 1.3 云计算的层次以及分类",
            "## 1.4 国内外云计算产业现状",
        ],
        2: [
            "## 2.1 VMware的云计算技术及其相关产品",
            "## 2.2 Citrix的云计算技术",
            "## 2.3 微软私有云虚拟化技术Hyper-V",
            "## 2.4 国内私有云相关产品",
            "## 2.5 知名公有云平台简介",
        ],
        3: [
            "## 3.1 OpenStack技术简介",
            "## 3.2 体验原生OpenStack云平台",
        ],
    }
    minimum_characters = {1: 14_000, 2: 18_000, 3: 6_400}

    for chapter, expected in expected_sections.items():
        text = task3_fragment(chapter)
        headings = [line.strip() for line in text.splitlines() if line.startswith("#")]
        paragraphs = prose_paragraphs(text)
        narrative_paragraphs = [
            paragraph
            for paragraph in paragraphs
            if not re.match(r"^(?:[一二三四五六七八九十]+|\d+)．", paragraph)
            and not paragraph.startswith("{{FIGURE:")
        ]
        lengths = [compact_length(paragraph) for paragraph in narrative_paragraphs]

        assert headings == expected
        assert not any(line.startswith("###") for line in text.splitlines())
        assert paragraphs[0].startswith("本章导读：")
        assert "教学活动" in text
        assert sum(lengths) >= minimum_characters[chapter]
        assert max(lengths) <= 240
        assert statistics.median(lengths) >= 80
        assert sum(length < 45 for length in lengths) <= max(1, len(lengths) // 8)


def test_chapter_1_layered_outline_matches_the_approved_teaching_sequence() -> None:
    expected = {
        "1.1 计算模式的演变": [
            "一．字符终端—主机模式",
            "二．客户机—服务器模式",
            "三．集群与分布式计算",
            "四．虚拟化、资源池化与云计算",
        ],
        "1.2 云计算的定义": [
            "一．云计算定义",
            "二．五个基本特征",
            "三．云计算环境的组成",
            "四．云计算的责任边界",
        ],
        "1.3 云计算的层次以及分类": [
            "一．云服务层次",
            "二．云部署模型",
            "三．云—边—端协同",
        ],
        "1.4 国内外云计算产业现状": [
            "一．产业规模与结构",
            "二．云原生与智算云",
            "三．边缘云与分布式云",
            "四．成本、绿色与可信治理",
            "五．国产云生态",
        ],
    }
    chapter = task3_fragment(1)

    for heading, body in h2_sections(chapter):
        assert re.findall(r"(?m)^[一二三四五六七八九十]+．[^\n]+$", body) == expected[heading]
        assert re.search(r"(?m)^1．[^\n]+$", body)
        assert re.search(r"(?m)^2．[^\n]+$", body)

    for marker in ("图1.1", "图1.2", "图1.3", "图1.4", "图1.5"):
        assert chapter.count(f"{{{{FIGURE:{marker}}}}}") == 1


def test_chapters_1_2_have_second_edition_internal_levels_and_depth() -> None:
    expected_h2 = {
        1: [
            "1.1 计算模式的演变",
            "1.2 云计算的定义",
            "1.3 云计算的层次以及分类",
            "1.4 国内外云计算产业现状",
        ],
        2: [
            "2.1 VMware的云计算技术及其相关产品",
            "2.2 Citrix的云计算技术",
            "2.3 微软私有云虚拟化技术Hyper-V",
            "2.4 国内私有云相关产品",
            "2.5 知名公有云平台简介",
        ],
    }
    target_lengths = {1: (14_000, 18_000), 2: (18_000, 23_000)}

    for chapter_number in (1, 2):
        chapter = task3_fragment(chapter_number)
        sections = h2_sections(chapter)
        assert [heading for heading, _ in sections] == expected_h2[chapter_number]
        assert target_lengths[chapter_number][0] <= compact_length(chapter) <= target_lengths[chapter_number][1]
        assert not any(line.startswith("###") for line in chapter.splitlines())

        for heading, body in sections:
            chinese_levels = list(
                re.finditer(r"(?m)^([一二三四五六七八九十]+)．[^\n]+$", body)
            )
            assert len(chinese_levels) >= 2, f"{heading} lacks 一．/二． textbook levels"
            for index, level in enumerate(chinese_levels):
                nested = body[
                    level.end() : chinese_levels[index + 1].start()
                    if index + 1 < len(chinese_levels)
                    else None
                ]
                arabic_levels = re.findall(r"(?m)^\d+．[^\n]+$", nested)
                assert len(arabic_levels) >= 2, (
                    f"{heading} / {level.group(0)} lacks two Arabic-number sublevels"
                )


def test_chapters_1_2_figure_manifest_and_cross_references_are_complete() -> None:
    records = json.loads(CHAPTERS_1_2_FIGURE_MANIFEST.read_text(encoding="utf-8"))
    expected_numbers = [
        "图1.1",
        "图1.2",
        "图1.3",
        "图1.4",
        "图1.5",
        "图2.1",
        "图2.2",
        "图2.3",
        "图2.4",
        "图2.5",
        "图2.6",
        "图2.7",
    ]
    assert [record["number"] for record in records] == expected_numbers
    assert len({record["number"] for record in records}) == 12

    required = {
        "number",
        "title",
        "svg",
        "png",
        "anchor",
        "minimum_font_pt",
        "source_note",
        "width_cm",
    }
    for record in records:
        assert set(record) == required
        assert record["minimum_font_pt"] >= 9.0
        assert 11.5 <= record["width_cm"] <= 14.0
        assert record["svg"].endswith(f"/{record['number']}.svg")
        assert record["png"].endswith(f"/{record['number']}.png")
        assert record["source_note"].strip()

        chapter = task3_fragment(int(record["number"][1]))
        marker = f"{{{{FIGURE:{record['number']}}}}}"
        assert chapter.count(marker) == 1
        before, after = chapter.split(marker, 1)
        assert f"如{record['number']}所示" in before
        assert record["anchor"] in before
        following = next(
            (
                block.strip()
                for block in re.split(r"\n\s*\n", after)
                if block.strip() and not block.lstrip().startswith("#")
            ),
            "",
        )
        assert compact_length(following) >= 80


def test_chapter_1_preserves_the_recognition_sequence_and_frozen_facts() -> None:
    text = task3_fragment(1)
    evolution = text.split("## 1.1 计算模式的演变", 1)[1].split("## 1.2 云计算的定义", 1)[0]
    definition = text.split("## 1.2 云计算的定义", 1)[1].split(
        "## 1.3 云计算的层次以及分类", 1
    )[0]
    layers = text.split("## 1.3 云计算的层次以及分类", 1)[1].split(
        "## 1.4 国内外云计算产业现状", 1
    )[0]
    evolution_topics = [
        "字符哑终端—主机",
        "客户—服务器",
        "集群计算",
        "云计算",
    ]
    definition_topics = [
        "美国国家标准与技术研究院",
        "按需自助服务",
        "广泛网络访问",
        "资源池化",
        "快速弹性",
        "可计量服务",
    ]
    layer_topics = [
        "IaaS",
        "PaaS",
        "SaaS",
        "公有云",
        "私有云",
        "混合云",
    ]

    for section, ordered_topics in (
        (evolution, evolution_topics),
        (definition, definition_topics),
        (layers, layer_topics),
    ):
        positions = [section.index(topic) for topic in ordered_topics]
        assert positions == sorted(positions)
    for topic in ("云原生", "边缘云", "AI云", "FinOps", "绿色云", "主权云", "可信云"):
        assert topic in text
    for actual in (
        "8,288亿元",
        "34.4%",
        "6,216亿元",
        "36.6%",
        "2,072亿元",
        "29.3%",
        "4,201亿元",
        "682亿元",
        "23.1%",
        "突破1,000亿元",
    ):
        assert actual in text
    assert "2024年" in text
    assert "2025E" not in text
    assert "10,857" not in text
    assert "2025年实际达到10857亿元" not in text
    assert "市场份额第一" not in text


def test_chapter_2_compares_current_products_on_the_approved_dimensions() -> None:
    text = task3_fragment(2)

    for dimension in ("定位", "服务能力", "生态", "部署形态", "锁定风险", "教学场景"):
        assert dimension in text
    for product in (
        "AWS Outposts",
        "Azure Arc",
        "GKE Enterprise",
        "Apsara Stack",
        "华为云 Stack",
    ):
        assert product in text
    for stale_walkthrough in ("单击", "点击", "登录控制台", "菜单栏", "市场份额"):
        assert stale_walkthrough not in text


def test_chapter_2_restored_five_section_outline_and_product_boundaries() -> None:
    expected_internal = {
        "2.1 VMware的云计算技术及其相关产品": [
            "一．VMware虚拟化基础",
            "二．软件定义数据中心",
            "三．VMware Cloud Foundation一体化平台",
            "四．适用场景与技术边界",
        ],
        "2.2 Citrix的云计算技术": [
            "一．应用与桌面虚拟化基础",
            "二．Citrix DaaS核心架构",
            "三．用户访问与会话交付",
            "四．混合资源与技术边界",
        ],
        "2.3 微软私有云虚拟化技术Hyper-V": [
            "一．Hyper-V虚拟化架构",
            "二．虚拟网络与虚拟存储",
            "三．群集与私有云管理",
            "四．Azure Local与Azure Arc混合管理",
        ],
        "2.4 国内私有云相关产品": [
            "一．国内私有云的通用架构",
            "二．代表性私有云产品路线",
            "三．国产信创云生态",
            "四．开放平台与教学衔接",
        ],
        "2.5 知名公有云平台简介": [
            "一．公有云的稳定能力层次",
            "二．国际知名公有云平台",
            "三．国内知名公有云平台",
            "四．云产品比较与选择",
        ],
    }
    chapter = task3_fragment(2)

    assert [heading for heading, _ in h2_sections(chapter)] == list(expected_internal)
    for heading, body in h2_sections(chapter):
        assert re.findall(r"(?m)^[一二三四五六七八九十]+．[^\n]+$", body) == expected_internal[heading]

    required_by_section = {
        "2.1": ("ESXi", "vCenter", "vSphere", "vSAN", "NSX", "VMware Cloud Foundation"),
        "2.2": ("Citrix DaaS", "HDX", "Workspace", "Gateway", "Cloud Connector", "VDA", "资源位置"),
        "2.3": ("Hyper-V", "父分区", "子分区", "VMBus", "虚拟交换机", "故障转移群集", "Storage Spaces Direct", "Azure Local", "Azure Arc"),
        "2.4": ("私有云", "openEuler", "OpenStack", "华为云Stack", "Apsara Stack", "EasyStack", "ZStack", "信创"),
        "2.5": ("AWS", "Microsoft Azure", "Google Cloud", "阿里云", "华为云", "腾讯云", "区域", "可用区", "计量"),
    }
    for heading, body in h2_sections(chapter):
        prefix = heading.split()[0]
        for concept in required_by_section[prefix]:
            assert concept in body

    for marker in ("图2.1", "图2.2", "图2.3", "图2.4", "图2.5", "图2.6", "图2.7"):
        assert chapter.count(f"{{{{FIGURE:{marker}}}}}") == 1

    prohibited = (
        "市场份额第一",
        "国内排名第一",
        "全球排名第一",
        "每小时价格",
        "当前拥有100个区域",
        "产品功能大全",
    )
    assert not any(claim in chapter for claim in prohibited)


def test_chapter_3_states_governance_architecture_and_release_boundaries() -> None:
    text = task3_fragment(3)

    for topic in (
        "NASA",
        "Rackspace",
        "开放源代码",
        "开放设计",
        "开放开发",
        "开放社区",
        "OpenInfra Foundation",
        "技术委员会",
        "Keystone",
        "Glance",
        "Placement",
        "Nova",
        "Neutron",
        "Cinder",
        "Swift",
        "Horizon",
        "SLURP",
    ):
        assert topic in text
    assert re.search(
        r"2026\.1 Gazpacho.{0,80}2026年4月1日.{0,100}Maintained.{0,50}SLURP",
        text,
        re.S,
    )
    assert re.search(
        r"2026\.2 Hibiscus.{0,100}开发中.{0,100}计划于2026年9月30日",
        text,
        re.S,
    )
    assert re.search(
        r"2023\.1 Antelope.{0,80}2023年3月22日.{0,100}Unmaintained.{0,100}隔离教学环境",
        text,
        re.S,
    )
    assert re.search(r"Antelope.{0,220}不.{0,20}生产", text, re.S)


def test_task3_text_has_no_source_dump_or_command_manual_language() -> None:
    forbidden = (
        r"https?://",
        r"\[[^\]]*来源[^\]]*\]",
        r"参考文献",
        r"访问日期",
        r"置信度",
        r"```",
        r"\[(?:root|\w+)@[^\]]+\]#",
        r"\bdnf\b",
        r"\bsystemctl\b",
        r"\bpython3?\b",
        r"门禁",
        r"失败即停",
        r"验收",
        r"验证",
    )

    for path in TASK3_FRAGMENTS.values():
        text = path.read_text(encoding="utf-8")
        for pattern in forbidden:
            assert re.search(pattern, text, re.I) is None, f"{path.name}: {pattern}"


def test_task4_fragment_has_exact_structure_topology_and_manual_commands() -> None:
    text = task4_fragment()
    headings = [line.strip() for line in text.splitlines() if line.startswith("#")]

    assert headings == [
        "# 第四章 openEuler与信创OpenStack实验环境准备",
        "## 4.1 openEuler与信创云平台",
        "## 4.2 双节点实验环境与终端工具",
        "## 4.3 实训项目1 openEuler云平台基本环境配置",
    ]
    for value in (
        "192.168.234.151/24",
        "192.168.234.150/24",
        "192.168.234.2",
        "ens33",
        "ens34",
        "/dev/sda",
        "/dev/sdb",
        "/dev/sdc",
        "Cinder",
        "Swift",
        "50 GiB",
    ):
        assert value in text
    terminal_paragraphs = [
        paragraph
        for paragraph in prose_paragraphs(text)
        if any(tool in paragraph for tool in ("Xshell", "SecureCRT", "Windows PowerShell"))
    ]
    assert len(terminal_paragraphs) == 1
    assert all(tool in terminal_paragraphs[0] for tool in ("Xshell", "SecureCRT", "Windows PowerShell"))

    fenced_blocks = re.findall(r"```(?:command|config)\n(.*?)\n```", text, re.S)
    assert fenced_blocks
    for block in fenced_blocks:
        lines = [line for line in block.splitlines() if line.strip()]
        prompted = [line for line in lines if re.match(r"^\[root@(controller|compute) ~\]# ", line)]
        if prompted:
            assert len(prompted) == len(lines)
        else:
            assert not any(line.startswith("[root@") for line in lines)

    required_configuration = {
        "/etc/hosts": "192.168.234.151 controller",
        "/etc/selinux/config": "SELINUX=permissive",
        "/etc/yum.repos.d/openstack-local.repo": "[openstack-local]",
        "/etc/vsftpd/vsftpd.conf": "anonymous_enable=YES",
        "/etc/yum.repos.d/openstack-antelope.repo": "openEuler-24.03-LTS-SP2",
    }
    for path, body_line in required_configuration.items():
        vi_position = text.index(f"# vi {path}")
        body_position = text.index(body_line, vi_position)
        assert vi_position < body_position
        assert f"]# {body_line}" not in text

    assert "保留文件中原有内容，只在文件末尾追加后两行" in text
    assert "::1         localhost localhost.localdomain localhost6 localhost6.localdomain6" in text


def test_task4_fragment_rejects_forbidden_procedures_and_simple_mutations() -> None:
    text = task4_fragment()
    forbidden = (
        r"CentOS",
        r"192\.168\.100\.",
        r"\beth0\b",
        r"\bpython3?\b",
        r"\bparamiko\b",
        r"\bsed\b",
        r"\bcurl\b",
        r"systemctl is-active",
        r"chronyc (?:tracking|sources)",
        r"cat\s*>",
        r"\btee\b",
        r'<<(?:\'|")?EOF',
    )
    for pattern in forbidden:
        assert re.search(pattern, text, re.I) is None, pattern

    def require_core_contract(candidate: str) -> None:
        assert "controller管理地址为192.168.234.151/24" in candidate
        assert "compute管理地址为192.168.234.150/24" in candidate
        assert "ens34不配置IP地址" in candidate
        assert "/dev/sdb用于Cinder" in candidate
        assert "/dev/sdc用于Swift" in candidate
        assert "CentOS" not in candidate
        assert "\nsed " not in candidate
        assert "python" not in candidate.lower()
        assert "chronyc tracking" not in candidate
        assert "dnf history" not in candidate
        assert re.search(r"(?m)^\s*ss\b", candidate) is None
        assert all(
            re.match(
                r"^(?:hostnamectl|nmcli|vi|setenforce|systemctl|dnf|ss|curl)\b",
                line.strip(),
            )
            is None
            for line in candidate.splitlines()
        )
        terminal_paragraphs = [
            paragraph
            for paragraph in prose_paragraphs(candidate)
            if any(tool in paragraph for tool in ("Xshell", "SecureCRT", "Windows PowerShell"))
        ]
        assert len(terminal_paragraphs) == 1

    require_core_contract(text)
    swapped_nodes = text.replace(
        "controller管理地址为192.168.234.151/24",
        "controller管理地址为192.168.234.150/24",
        1,
    ).replace(
        "compute管理地址为192.168.234.150/24",
        "compute管理地址为192.168.234.151/24",
        1,
    )
    corruptions = (
        text.replace("192.168.234.151/24", "192.168.234.152/24"),
        swapped_nodes,
        text.replace("ens34不配置IP地址", "ens34配置IP地址", 1),
        text.replace("/dev/sdc用于Swift", "/dev/sdb用于Swift"),
        text.replace("/dev/sdb用于Cinder", "/dev/sdb用于Swift", 1),
        text + "\nCentOS\n",
        text + "\nXshell还可以独立学习。\n",
        text.replace("[root@controller ~]# nmcli", "nmcli", 1),
        text + "\nsystemctl restart chronyd\n",
        text + "\nss -lnt\n",
        text + "\ndnf history\n",
        text + "\nsed -i example\n",
        text + "\npython3 example.py\n",
        text + "\nchronyc tracking\n",
    )
    for corrupted in corruptions:
        with pytest.raises(AssertionError):
            require_core_contract(corrupted)


def test_task5_chapters_follow_second_edition_textbook_shape_and_manual_prompts() -> None:
    expected_headings = {
        5: [
            "# 第五章 MariaDB数据库及基础服务的安装与配置",
            "## 5.1 MariaDB数据库功能简介",
            "## 5.2 OpenStack基础服务功能简介",
            "## 5.3 实训项目2 MariaDB数据库及基础服务的手工安装与配置",
        ],
        6: [
            "# 第六章 Keystone的安装及其配置",
            "## 6.1 Keystone功能详解",
            "## 6.2 Keystone的令牌、密钥与Web承载",
            "## 6.3 实训项目3 Keystone的手工安装与配置",
        ],
    }
    for chapter, expected in expected_headings.items():
        text = task5_fragment(chapter)
        headings = [line for line in text.splitlines() if line.startswith("#")]
        assert headings == expected
        assert 8_500 <= compact_length(text) <= 13_000
        assert "本章导读" in text
        assert "一．实训前提环境：" in text
        assert "二．实训涉及节点：" in text
        assert "三．实训目标：" in text
        assert "四．实训步骤及其详解：" in text

        for kind, body in re.findall(r"```(command|config)\n(.*?)\n```", text, re.S):
            lines = [line for line in body.splitlines() if line.strip()]
            if kind == "command":
                assert all(
                    re.match(r"^\[root@controller ~\]# ", line)
                    or re.match(r"^MariaDB \[\(none\)\]> ", line)
                    or re.match(r"^\s+-> ", line)
                    for line in lines
                )
            else:
                assert all("]# " not in line for line in lines)


def test_task5_chapters_keep_exact_manual_order_and_configuration() -> None:
    ch5 = task5_fragment(5)
    ch6 = task5_fragment(6)
    ch5_commands = "\n".join(re.findall(r"```command\n(.*?)\n```", ch5, re.S))
    ch6_commands = "\n".join(re.findall(r"```command\n(.*?)\n```", ch6, re.S))

    ch5_steps = (
        "install mariadb-config mariadb mariadb-server python3-PyMySQL",
        "vi /etc/my.cnf.d/openstack.cnf",
        "systemctl start mariadb.service",
        "install rabbitmq-server",
        "rabbitmqctl add_user openstack qwer1234",
        "install memcached python3-memcached",
        "vi /etc/sysconfig/memcached",
        "systemctl start memcached.service",
        "install python3-openstackclient",
    )
    assert [ch5_commands.index(step) for step in ch5_steps] == sorted(
        ch5_commands.index(step) for step in ch5_steps
    )
    for value in (
        "bind-address = 0.0.0.0",
        "default-storage-engine = innodb",
        'OPTIONS="-l 127.0.0.1,::1,192.168.234.151"',
        'rabbitmqctl set_permissions -p / openstack ".*" ".*" ".*"',
    ):
        assert value in ch5

    ch6_steps = (
        "CREATE DATABASE keystone;",
        "install openstack-keystone httpd python3-mod_wsgi",
        "vi /etc/keystone/keystone.conf",
        'keystone-manage db_sync',
        "keystone-manage fernet_setup",
        "keystone-manage credential_setup",
        "keystone-manage bootstrap",
        "vi /etc/httpd/conf/httpd.conf",
        "vi /root/admin-openrc",
        "systemctl start httpd.service",
        ". /root/admin-openrc",
        "openstack project create --domain default",
    )
    assert [ch6_commands.index(step) for step in ch6_steps] == sorted(
        ch6_commands.index(step) for step in ch6_steps
    )
    for value in (
        "CREATE USER 'keystone'@'localhost' IDENTIFIED BY 'qwer1234';",
        "GRANT ALL PRIVILEGES ON keystone.*",
        "connection = mysql+pymysql://keystone:qwer1234@127.0.0.1/keystone",
        "provider = fernet",
        "--bootstrap-public-url http://controller:5000/v3/",
        "export OS_PASSWORD=qwer1234",
    ):
        assert value in ch6


def test_task5_chapters_stop_after_deployment_without_automation_or_validation() -> None:
    combined = "\n".join(task5_fragment(chapter) for chapter in (5, 6))
    forbidden = (
        r"```python",
        r"\bpython3?\s+-[cEm]",
        r"set -Eeuo",
        r"\bcurl\b",
        r"(?m)^\s*ss\b",
        r"dnf history",
        r"systemctl (?:status|is-active)",
        r"openstack token issue",
        r"openstack \S+ list",
        r"门禁",
        r"验收",
        r"自动化部署",
        r"一键安装",
    )
    for pattern in forbidden:
        assert re.search(pattern, combined, re.I) is None, pattern
    assert "qwer1234" in combined
    assert "隔离" in combined and "生产环境" in combined
    assert "第二版" not in combined and "第三版" not in combined


def test_task6_chapters_are_textbook_shaped_manual_deployment_records() -> None:
    expected_headings = {
        7: [
            "# 第七章 Glance的安装及其配置",
            "## 7.1 Glance功能简介",
            "## 7.2 Glance后端与调用过程",
            "## 7.3 实训项目4 Glance的手工安装与配置",
        ],
        8: [
            "# 第八章 Placement的安装及其配置",
            "## 8.1 Placement功能简介",
            "## 8.2 Allocation、Consumer与调度协作",
            "## 8.3 实训项目5 Placement的手工安装与配置",
        ],
    }
    for chapter, expected in expected_headings.items():
        text = task6_fragment(chapter)
        assert [line for line in text.splitlines() if line.startswith("#")] == expected
        assert 9_000 <= compact_length(text) <= 13_500
        assert "本章导读" in text
        for heading in (
            "一．实训前提环境：",
            "二．实训涉及节点：",
            "三．实训目标：",
            "四．实训步骤及其详解：",
        ):
            assert heading in text
        for kind, body in re.findall(r"```(command|config)\n(.*?)\n```", text, re.S):
            lines = [line for line in body.splitlines() if line.strip()]
            if kind == "command":
                assert all(
                    re.match(r"^\[root@controller ~\]# ", line)
                    or re.match(r"^MariaDB \[\(none\)\]> ", line)
                    or re.match(r"^\s+-> ", line)
                    for line in lines
                )
            else:
                assert all("]# " not in line for line in lines)


def test_task6_chapters_keep_component_objects_configuration_and_order() -> None:
    ch7 = task6_fragment(7)
    ch8 = task6_fragment(8)
    ch7_commands = "\n".join(re.findall(r"```command\n(.*?)\n```", ch7, re.S))
    ch8_commands = "\n".join(re.findall(r"```command\n(.*?)\n```", ch8, re.S))

    glance_steps = (
        "CREATE DATABASE glance;",
        "openstack user create --domain default --password qwer1234 glance",
        "openstack role add --project service --user glance admin",
        'openstack service create --name glance --description "OpenStack Image" image',
        "openstack endpoint create --region RegionOne image public http://controller:9292",
        "install openstack-glance",
        "vi /etc/glance/glance-api.conf",
        "glance-manage db_sync",
        "systemctl start openstack-glance-api.service",
    )
    assert [ch7_commands.index(step) for step in glance_steps] == sorted(
        ch7_commands.index(step) for step in glance_steps
    )
    for value in (
        "enabled_backends = file:file",
        "connection = mysql+pymysql://glance:qwer1234@127.0.0.1/glance",
        "default_backend = file",
        "filesystem_store_datadir = /var/lib/glance/images/",
        "queued",
        "active",
        "qcow2",
    ):
        assert value in ch7

    placement_steps = (
        "CREATE DATABASE placement;",
        "openstack user create --domain default --password qwer1234 placement",
        "openstack role add --project service --user placement admin",
        'openstack service create --name placement --description "Placement API" placement',
        "openstack endpoint create --region RegionOne placement public http://controller:8778",
        "install openstack-placement-api",
        "vi /etc/placement/placement.conf",
        "oslopolicy-convert-json-to-yaml",
        "placement-manage db sync",
        "vi /etc/httpd/conf.d/00-placement-api.conf",
        "systemctl restart httpd.service",
    )
    assert [ch8_commands.index(step) for step in placement_steps] == sorted(
        ch8_commands.index(step) for step in placement_steps
    )
    for value in (
        "Resource Provider",
        "Resource Class",
        "Inventory",
        "Trait",
        "Allocation",
        "Consumer",
        "Allocation Candidate",
        "connection = mysql+pymysql://placement:qwer1234@127.0.0.1/placement",
        "policy_file = policy.yaml",
        "Listen 8778",
        "WSGIScriptAlias / /usr/bin/placement-api",
    ):
        assert value in ch8


def test_task6_chapters_have_no_editor_voice_automation_or_post_install_validation() -> None:
    combined = "\n".join(task6_fragment(chapter) for chapter in (7, 8))
    forbidden = (
        r"第二版",
        r"第三版",
        r"```python",
        r"\bpython3?\s+-[cEm]",
        r"\bcurl\b",
        r"(?m)^\s*ss\b",
        r"dnf history",
        r"systemctl (?:status|is-active)",
        r"openstack image (?:create|list|show)",
        r"openstack resource provider",
        r"门禁",
        r"验收",
        r"自动化部署",
        r"一键安装",
    )
    for pattern in forbidden:
        assert re.search(pattern, combined, re.I) is None, pattern
    assert "qwer1234" in combined
    assert "隔离" in combined and "生产" in combined


def test_task3_revision_map_uses_the_real_second_edition_h1_boundaries() -> None:
    mapping = json.loads((WORK_ROOT / "revision" / "revision-map.json").read_text(encoding="utf-8"))

    assert mapping == [
        {
            "op": "replace",
            "start_heading": "第一章 云计算基本概念",
            "end_heading": "第二章 云计算知名厂商及其产品",
            "fragment": "fragments/ch01.md",
        },
        {
            "op": "replace",
            "start_heading": "第二章 云计算知名厂商及其产品",
            "end_heading": "第三章 原生OpenStack云平台",
            "fragment": "fragments/ch02.md",
        },
        {
            "op": "replace_with_part_opener",
            "start_heading": "第三章 原生OpenStack云平台",
            "end_heading": "第四章 原生OpenStack云平台的环境准备",
            "fragment": "fragments/ch03.md",
            "part_title": "第二部分 信创OpenStack云平台构建与应用",
        },
        {
            "op": "replace",
            "start_heading": "第四章 原生OpenStack云平台的环境准备",
            "end_heading": "第五章 MySQL数据库的安装及其配置",
            "fragment": "fragments/ch04.md",
        },
        {
            "op": "replace",
            "start_heading": "第五章 MySQL数据库的安装及其配置",
            "end_heading": "第六章 Keystone的安装及其配置",
            "fragment": "fragments/ch05.md",
        },
        {
            "op": "replace",
            "start_heading": "第六章 Keystone的安装及其配置",
            "end_heading": "第七章 Glance的安装及其配置",
            "fragment": "fragments/ch06.md",
        },
        {
            "op": "replace",
            "start_heading": "第七章 Glance的安装及其配置",
            "end_heading": "第八章 Placement的安装及其配置",
            "fragment": "fragments/ch07.md",
        },
        {
            "op": "replace",
            "start_heading": "第八章 Placement的安装及其配置",
            "end_heading": "第九章 Nova的安装及其配置",
            "fragment": "fragments/ch08.md",
        },
    ]


def test_task3_figure_plan_resolves_each_old_figure_without_placeholders() -> None:
    with FIGURE_PLAN.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))

    expected_columns = {
        "chapter",
        "second_edition_figure",
        "decision",
        "target_number",
        "proposed_title",
        "width_cm",
        "source_or_capture",
        "placement_anchor",
        "reason",
        "owner",
    }
    assert rows and set(rows[0]) == expected_columns
    assert {row["chapter"] for row in rows} == {"1", "2", "3", "4"}
    assert len({row["second_edition_figure"] for row in rows if row["second_edition_figure"]}) >= 36
    assert {row["decision"] for row in rows} <= {"保留", "删除", "重绘", "重拍"}
    assert all(
        not row["target_number"] or re.fullmatch(r"图[1234]\.\d+", row["target_number"])
        for row in rows
    )
    assert all(row["target_number"] for row in rows if row["decision"] != "删除")
    assert all(not row["target_number"] for row in rows if row["decision"] == "删除")
    joined = "\n".join("|".join(row.values()) for row in rows)
    assert "占位" not in joined
    assert "假截图" not in joined

    chapter_targets = {
        chapter: sorted(
            [
                row["target_number"]
                for row in rows
                if row["chapter"] == str(chapter) and row["target_number"]
            ],
            key=lambda number: int(number.split(".")[1]),
        )
        for chapter in (1, 2)
    }
    assert chapter_targets == {
        1: [f"图1.{number}" for number in range(1, 6)],
        2: [f"图2.{number}" for number in range(1, 8)],
    }

    chapter4 = [row for row in rows if row["chapter"] == "4"]
    chapter4_sources = {row["second_edition_figure"] for row in chapter4}
    assert "图4.1.3—图4.1.26、图4.1.46 旧虚拟机创建与系统安装截图" in chapter4_sources
    assert "图4.3.2—图4.3.7、图4.3.10、图4.3.13—图4.3.14 旧基础配置与检查截图" in chapter4_sources
    assert "图4.1.3—图4.1.46 旧虚拟机创建与系统安装截图" not in chapter4_sources
    assert "图4.3.2—图4.3.14 旧基础配置与检查截图" not in chapter4_sources
    target_numbers = [row["target_number"] for row in chapter4 if row["target_number"]]
    assert target_numbers == [f"图4.{number}" for number in range(1, len(target_numbers) + 1)]
    for title in (
        "openEuler LTS与SP生命周期",
        "双节点实验拓扑与存储分工",
        "openEuler虚拟机创建与系统登录",
        "固定管理网络配置",
        "hosts文件配置",
        "本地软件仓配置",
        "Antelope SP2兼容仓配置",
        "基础服务启动",
    ):
        assert any(row["proposed_title"] == title for row in chapter4)
