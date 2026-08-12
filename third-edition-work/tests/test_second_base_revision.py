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
TASK3_FRAGMENTS = {
    1: FRAGMENTS_DIR / "ch01.md",
    2: FRAGMENTS_DIR / "ch02.md",
    3: FRAGMENTS_DIR / "ch03.md",
}


def task3_fragment(chapter: int) -> str:
    return TASK3_FRAGMENTS[chapter].read_text(encoding="utf-8")


def prose_paragraphs(markdown: str) -> list[str]:
    return [
        " ".join(line.strip() for line in block.splitlines())
        for block in re.split(r"\n\s*\n", markdown)
        if block.strip() and not block.lstrip().startswith("#")
    ]


def compact_length(value: str) -> int:
    return len(re.sub(r"\s+", "", value))


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
            "## 2.1 云产品的比较方法",
            "## 2.2 国际代表性云产品",
            "## 2.3 国内代表性云产品",
            "## 2.4 产品选择与教学活动",
        ],
        3: [
            "## 3.1 OpenStack技术简介",
            "## 3.2 体验原生OpenStack云平台",
        ],
    }
    minimum_characters = {1: 6_500, 2: 5_500, 3: 6_400}

    for chapter, expected in expected_sections.items():
        text = task3_fragment(chapter)
        headings = [line.strip() for line in text.splitlines() if line.startswith("#")]
        paragraphs = prose_paragraphs(text)
        lengths = [compact_length(paragraph) for paragraph in paragraphs]

        assert headings == expected
        assert not any(line.startswith("###") for line in text.splitlines())
        assert paragraphs[0].startswith("本章导读：")
        assert "教学活动" in text
        assert sum(lengths) >= minimum_characters[chapter]
        assert max(lengths) <= 240
        assert statistics.median(lengths) >= 80
        assert sum(length < 45 for length in lengths) <= max(1, len(lengths) // 8)


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
    for actual in ("8,288亿元", "34.4%", "6,216亿元", "36.6%", "2,072亿元", "29.3%"):
        assert actual in text
    assert "2024年" in text
    assert "2025E" not in text
    assert "10,857" not in text


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
            "op": "replace",
            "start_heading": "第三章 原生OpenStack云平台",
            "end_heading": "第四章 原生OpenStack云平台的环境准备",
            "fragment": "fragments/ch03.md",
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
    assert {row["chapter"] for row in rows} == {"1", "2", "3"}
    assert len({row["second_edition_figure"] for row in rows if row["second_edition_figure"]}) == 36
    assert {row["decision"] for row in rows} <= {"保留", "删除", "重绘", "重拍"}
    assert all(
        not row["target_number"] or re.fullmatch(r"图[123]\.\d+", row["target_number"])
        for row in rows
    )
    assert all(row["target_number"] for row in rows if row["decision"] != "删除")
    assert all(not row["target_number"] for row in rows if row["decision"] == "删除")
    joined = "\n".join("|".join(row.values()) for row in rows)
    assert "占位" not in joined
    assert "假截图" not in joined
