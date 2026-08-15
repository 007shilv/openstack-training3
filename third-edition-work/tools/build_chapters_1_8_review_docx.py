"""Build the bounded textbook chapters in the current Word manuscript.

The source is a DOCX that already contains figure and table markers.  This
module preserves the second-edition package and paragraph templates, converts
all table markers to native Word tables, and uses an isolated Word instance to
insert high-resolution PNG figures and export a PDF for visual review.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pythoncom
import win32com.client
from lxml import etree


TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from build_chapters_1_2_review_docx import (  # noqa: E402
    MSO_TRUE,
    WD_ALIGN_PARAGRAPH_CENTER,
    WD_COLLAPSE_END,
    WD_EXPORT_FORMAT_PDF,
    WD_FORMAT_DOCUMENT_DEFAULT,
    WD_FIND_STOP,
    W,
    W_NS,
    _ensure_run_format,
    _find_exact_paragraphs,
    _new_table,
    _new_text_paragraph,
    _set_simsun,
)


CHAPTER_ONE = "第一章 云计算基本概念"
CHAPTER_AFTER_SCOPE = "第十四章 虚拟机镜像文件的制作"
CHAPTER_RE = re.compile(r"^第[一二三四五六七八九十]+章")
INTERNAL_HEADING_RE = re.compile(r"^(?:[一二三四五六七八九十]+|\d+)．")


def normalize_table_record(record: dict) -> dict:
    """Return the table schema expected by the native Word table renderer."""

    normalized = dict(record)
    columns = normalized.get("columns", normalized.get("headers"))
    if not isinstance(columns, list) or not columns:
        raise ValueError(f"{record.get('number', 'table')} has no columns")
    rows = normalized.get("rows")
    if not isinstance(rows, list):
        raise ValueError(f"{record.get('number', 'table')} has no rows")
    if any(not isinstance(row, list) or len(row) != len(columns) for row in rows):
        raise ValueError(f"{record.get('number', 'table')} row width mismatch")
    normalized["columns"] = columns
    normalized["font_pt"] = float(normalized.get("font_pt", 9.0))
    widths = normalized.get("column_widths_cm")
    if widths is None:
        width = 14.5 / len(columns)
        widths = [width for _ in columns]
    if not isinstance(widths, list) or len(widths) != len(columns):
        raise ValueError(f"{record.get('number', 'table')} column width mismatch")
    normalized["column_widths_cm"] = [float(value) for value in widths]
    return normalized


def _load_records(paths: list[Path], *, table: bool) -> list[dict]:
    records: list[dict] = []
    numbers: set[str] = set()
    for manifest in paths:
        if not manifest.is_file():
            raise FileNotFoundError(manifest)
        values = json.loads(manifest.read_text(encoding="utf-8"))
        if not isinstance(values, list):
            raise ValueError(f"manifest must be a list: {manifest}")
        for value in values:
            record = normalize_table_record(value) if table else dict(value)
            number = record.get("number")
            if not isinstance(number, str) or number in numbers:
                raise ValueError(f"duplicate or missing number in {manifest}: {number!r}")
            numbers.add(number)
            if not table:
                png = (manifest.parent.parent / record["png"]).resolve()
                try:
                    png.relative_to(manifest.parent.parent.resolve())
                except ValueError as exc:
                    raise ValueError(f"figure path escapes revision root: {record['png']}") from exc
                if not png.is_file():
                    raise FileNotFoundError(png)
                record["_png_path"] = str(png)
            records.append(record)
    return records


def _set_left_no_indent(properties: etree._Element) -> None:
    indent = properties.find(f"{W}ind")
    if indent is not None:
        properties.remove(indent)
    alignment = properties.find(f"{W}jc")
    if alignment is None:
        alignment = etree.Element(f"{W}jc")
        run_properties = properties.find(f"{W}rPr")
        if run_properties is None:
            properties.append(alignment)
        else:
            properties.insert(properties.index(run_properties), alignment)
    alignment.set(f"{W}val", "left")


def _normalize_styles_xml(styles_xml: bytes) -> bytes:
    """Use Song typeface for Chinese and Times New Roman for Latin text."""

    root = etree.fromstring(styles_xml)
    for owner in root.xpath(
        ".//w:docDefaults/w:rPrDefault/w:rPr | .//w:style/w:rPr",
        namespaces={"w": W_NS},
    ):
        fonts = owner.find(f"{W}rFonts")
        if fonts is None:
            fonts = etree.Element(f"{W}rFonts")
            owner.insert(0, fonts)
        fonts.set(f"{W}ascii", "Times New Roman")
        fonts.set(f"{W}hAnsi", "Times New Roman")
        fonts.set(f"{W}eastAsia", "宋体")
        fonts.set(f"{W}cs", "Times New Roman")

    for style in root.findall(f"{W}style"):
        style_id = style.get(f"{W}styleId", "")
        size_half_points = None
        if style_id in {"1", "Heading1", "heading1"}:
            size_half_points = 44
        elif style_id in {"2", "3", "Heading2", "Heading3", "heading2", "heading3"}:
            size_half_points = 32
        if size_half_points is None:
            continue
        properties = style.find(f"{W}rPr")
        if properties is None:
            properties = etree.SubElement(style, f"{W}rPr")
        for tag in ("sz", "szCs"):
            size = properties.find(f"{W}{tag}")
            if size is None:
                size = etree.SubElement(properties, f"{W}{tag}")
            size.set(f"{W}val", str(size_half_points))

    return etree.tostring(
        root,
        encoding="UTF-8",
        xml_declaration=True,
        standalone=True,
    )


def _rewrite_styles_in_place(docx_path: Path) -> None:
    """Reassert bilingual style fonts after Word has normalized the package."""

    with tempfile.TemporaryDirectory(prefix="textbook-font-style-") as directory:
        replacement = Path(directory) / docx_path.name
        with ZipFile(docx_path, "r") as source, ZipFile(
            replacement, "w", compression=ZIP_DEFLATED
        ) as target:
            target.comment = source.comment
            for info in source.infolist():
                payload = source.read(info)
                if info.filename == "word/styles.xml":
                    payload = _normalize_styles_xml(payload)
                target.writestr(info, payload)
        os.replace(replacement, docx_path)


def _prepare_document(input_docx: Path, output_docx: Path, tables: list[dict]) -> None:
    """Format the bounded deployment chapters and replace table markers."""

    namespace = {"w": W_NS}
    with ZipFile(input_docx, "r") as source:
        document_xml = source.read("word/document.xml")
        root = etree.fromstring(document_xml)
        body = root.find(f".//{W}body")
        if body is None:
            raise ValueError("DOCX has no body")

        # Apply the book-wide typeface rule to actual runs, including text that
        # predates the bounded chapter replacement.  Sizes are changed only for
        # the three heading styles; all other direct sizes remain intact.
        for paragraph in body.findall(f".//{W}p"):
            style = paragraph.find(f"{W}pPr/{W}pStyle")
            style_id = style.get(f"{W}val") if style is not None else ""
            heading_size = None
            if style_id in {"1", "Heading1", "heading1"}:
                heading_size = 44
            elif style_id in {"2", "3", "Heading2", "Heading3", "heading2", "heading3"}:
                heading_size = 32
            for run in paragraph.findall(f".//{W}r"):
                _ensure_run_format(run, size_half_points=heading_size)

        in_scope = False
        start_count = 0
        end_count = 0
        scoped: list[etree._Element] = []
        for child in list(body):
            if child.tag != f"{W}p":
                if in_scope:
                    scoped.append(child)
                continue
            text = "".join(child.xpath(".//w:t/text()", namespaces=namespace)).strip()
            if text == CHAPTER_ONE:
                start_count += 1
                in_scope = True
            elif text == CHAPTER_AFTER_SCOPE:
                end_count += 1
                in_scope = False
            if in_scope:
                scoped.append(child)

        if start_count != 1 or end_count != 1 or not scoped:
            raise ValueError(
                f"chapter bounds are not unique: start={start_count} end={end_count}"
            )

        caption_texts = {
            f"{record['number']} {record['title']}" for record in tables
        }
        marker_paragraphs: dict[str, etree._Element] = {}
        for paragraph in scoped:
            if paragraph.tag != f"{W}p":
                continue
            text = "".join(paragraph.xpath(".//w:t/text()", namespaces=namespace)).strip()
            if text.startswith("{{TABLE:"):
                if text in marker_paragraphs:
                    raise ValueError(f"duplicate table marker: {text}")
                marker_paragraphs[text] = paragraph
                continue

            style = paragraph.find(f"{W}pPr/{W}pStyle")
            style_id = style.get(f"{W}val") if style is not None else ""
            is_chapter_heading = bool(CHAPTER_RE.match(text))
            is_section_heading = style_id in {"1", "2", "Heading1", "Heading2"} or bool(
                re.match(r"^\d+\.\d+\s", text)
            )
            is_internal_heading = bool(INTERNAL_HEADING_RE.match(text))
            if is_chapter_heading:
                properties = paragraph.find(f"{W}pPr")
                if properties is None:
                    properties = etree.Element(f"{W}pPr")
                    paragraph.insert(0, properties)
                page_break = properties.find(f"{W}pageBreakBefore")
                if page_break is None:
                    page_break = etree.Element(f"{W}pageBreakBefore")
                    properties.append(page_break)
                page_break.set(f"{W}val", "1")
            if is_internal_heading:
                properties = paragraph.find(f"{W}pPr")
                if properties is None:
                    properties = etree.Element(f"{W}pPr")
                    paragraph.insert(0, properties)
                _set_left_no_indent(properties)
            if not text or is_chapter_heading or is_section_heading or text in caption_texts:
                continue
            for run in paragraph.findall(f".//{W}r"):
                _ensure_run_format(
                    run,
                    size_half_points=21,
                    bold=is_internal_heading,
                )

        expected_markers = {f"{{{{TABLE:{record['number']}}}}}" for record in tables}
        if set(marker_paragraphs) != expected_markers:
            raise ValueError(
                "table marker mismatch: "
                f"missing={sorted(expected_markers - set(marker_paragraphs))} "
                f"unexpected={sorted(set(marker_paragraphs) - expected_markers)}"
            )
        for record in tables:
            marker = f"{{{{TABLE:{record['number']}}}}}"
            paragraph = marker_paragraphs[marker]
            parent = paragraph.getparent()
            position = parent.index(paragraph)
            parent.remove(paragraph)
            title = _new_text_paragraph(
                f"{record['number']} {record['title']}",
                align="center",
                size_half_points=18,
                bold=True,
                page_break_before=bool(record.get("page_break_before", False)),
            )
            parent.insert(position, title)
            parent.insert(position + 1, _new_table(record))

        updated_xml = etree.tostring(
            root,
            encoding="UTF-8",
            xml_declaration=True,
            standalone=True,
        )
        styles_xml = _normalize_styles_xml(source.read("word/styles.xml"))
        with ZipFile(output_docx, "w", compression=ZIP_DEFLATED) as target:
            target.comment = source.comment
            for info in source.infolist():
                if info.filename == "word/document.xml":
                    payload = updated_xml
                elif info.filename == "word/styles.xml":
                    payload = styles_xml
                else:
                    payload = source.read(info)
                target.writestr(info, payload)


def build_review_docx(
    input_docx: Path,
    output_docx: Path,
    output_pdf: Path,
    figure_manifests: list[Path],
    table_manifests: list[Path],
) -> None:
    if not input_docx.is_file():
        raise FileNotFoundError(input_docx)
    for path in (output_docx, output_pdf):
        if path.exists():
            raise FileExistsError(f"refusing to overwrite existing output: {path}")
    figures = _load_records(figure_manifests, table=False)
    tables = _load_records(table_manifests, table=True)

    pythoncom.CoInitialize()
    temporary = tempfile.TemporaryDirectory(prefix="textbook-review-")
    word = None
    document = None
    try:
        prepared = Path(temporary.name) / "prepared.docx"
        _prepare_document(input_docx, prepared, tables)
        word = win32com.client.DispatchEx("Word.Application")
        word.Visible = False
        word.DisplayAlerts = 0
        word.ScreenUpdating = False
        document = word.Documents.Open(
            str(prepared.resolve()),
            ReadOnly=True,
            AddToRecentFiles=False,
        )

        placements: list[tuple[int, int, dict, Path]] = []
        for record in figures:
            marker = "{{FIGURE:" + record["number"] + "}}"
            matches = _find_exact_paragraphs(document, marker)
            if len(matches) != 1:
                raise RuntimeError(f"marker {marker!r} occurs {len(matches)} times")
            placements.append((*matches[0], record, Path(record["_png_path"])))

        for start, end, record, png_path in sorted(placements, reverse=True):
            selection = word.Selection
            selection.SetRange(start, end - 1)
            if selection.Text.strip() != "{{FIGURE:" + record["number"] + "}}":
                raise RuntimeError(f"marker changed before placement: {record['number']}")
            selection.Text = ""
            selection.SetRange(start, start)
            shape = selection.InlineShapes.AddPicture(
                FileName=str(png_path),
                LinkToFile=False,
                SaveWithDocument=True,
            )
            shape.LockAspectRatio = MSO_TRUE
            shape.Width = float(record["width_cm"]) * 28.3464566929
            selection.ParagraphFormat.Alignment = WD_ALIGN_PARAGRAPH_CENTER
            selection.ParagraphFormat.LeftIndent = 0
            selection.ParagraphFormat.FirstLineIndent = 0
            selection.Collapse(WD_COLLAPSE_END)
            selection.TypeParagraph()
            selection.TypeText(f"{record['number']} {record['title']}")
            _set_simsun(selection.Font, 9.0)
            selection.Font.Bold = MSO_TRUE
            selection.ParagraphFormat.Alignment = WD_ALIGN_PARAGRAPH_CENTER
            selection.ParagraphFormat.LeftIndent = 0
            selection.ParagraphFormat.FirstLineIndent = 0

        # Word may simplify run properties during SaveAs.  Apply the bilingual
        # typeface rule through the Word object model so the saved document and
        # the PDF use the same explicit fonts throughout the main story.
        document.Content.Font.NameFarEast = "宋体"
        document.Content.Font.NameAscii = "Times New Roman"
        document.Content.Font.NameOther = "Times New Roman"

        document.SaveAs2(
            str(output_docx.resolve()),
            FileFormat=WD_FORMAT_DOCUMENT_DEFAULT,
            AddToRecentFiles=False,
        )
        document.ExportAsFixedFormat(
            str(output_pdf.resolve()),
            WD_EXPORT_FORMAT_PDF,
            OpenAfterExport=False,
            OptimizeFor=0,
            Range=0,
            Item=0,
            IncludeDocProps=True,
            KeepIRM=True,
            CreateBookmarks=1,
            DocStructureTags=True,
            BitmapMissingFonts=True,
            UseISO19005_1=False,
        )
    finally:
        if document is not None:
            document.Close(SaveChanges=False)
        if word is not None:
            word.Quit(SaveChanges=False)
        temporary.cleanup()
        pythoncom.CoUninitialize()
    _rewrite_styles_in_place(output_docx)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-docx", type=Path, required=True)
    parser.add_argument("--output-pdf", type=Path, required=True)
    parser.add_argument("--figures", action="append", type=Path, required=True)
    parser.add_argument("--tables", action="append", type=Path, required=True)
    args = parser.parse_args()
    build_review_docx(
        args.input.resolve(),
        args.output_docx.resolve(),
        args.output_pdf.resolve(),
        [path.resolve() for path in args.figures],
        [path.resolve() for path in args.tables],
    )
    print(f"PASS DOCX: {args.output_docx.resolve()}")
    print(f"PASS PDF: {args.output_pdf.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
