"""Insert the approved chapter figures into a bounded Word review candidate.

The script opens the input through an isolated Microsoft Word instance, writes a
new DOCX, and exports the same layout as PDF.  It never overwrites its input or
an existing output artifact.
"""

from __future__ import annotations

import argparse
import json
import re
import tempfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pythoncom
import win32com.client
from lxml import etree


WD_ALIGN_PARAGRAPH_LEFT = 0
WD_ALIGN_PARAGRAPH_CENTER = 1
WD_COLLAPSE_END = 0
WD_FIND_STOP = 0
WD_FORMAT_DOCUMENT_DEFAULT = 16
WD_EXPORT_FORMAT_PDF = 17
MSO_TRUE = -1

CHAPTER_ONE = "第一章 云计算基本概念"
CHAPTER_THREE = "第三章 原生OpenStack云平台"
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{W_NS}}}"


def _find_exact_paragraphs(document, text: str) -> list[tuple[int, int]]:
    matches: list[tuple[int, int]] = []
    search = document.Content.Duplicate
    while search.Find.Execute(
        FindText=text,
        Forward=True,
        Wrap=WD_FIND_STOP,
        Format=False,
        MatchCase=True,
        MatchWholeWord=False,
    ):
        paragraph = search.Paragraphs(1)
        actual = paragraph.Range.Text.rstrip("\r\x07").strip()
        if actual == text:
            matches.append((paragraph.Range.Start, paragraph.Range.End))
        next_start = search.End
        if next_start >= document.Content.End:
            break
        search.SetRange(next_start, document.Content.End)
    return matches


def _set_simsun(font, size: float) -> None:
    font.NameFarEast = "宋体"
    font.NameAscii = "Times New Roman"
    font.NameOther = "Times New Roman"
    font.Size = size


def _ensure_run_format(
    run: etree._Element,
    *,
    size_half_points: int | None = None,
    bold: bool = False,
) -> None:
    properties = run.find(f"{W}rPr")
    if properties is None:
        properties = etree.Element(f"{W}rPr")
        run.insert(0, properties)
    fonts = properties.find(f"{W}rFonts")
    if fonts is None:
        fonts = etree.Element(f"{W}rFonts")
        properties.insert(0, fonts)
    fonts.set(f"{W}ascii", "Times New Roman")
    fonts.set(f"{W}hAnsi", "Times New Roman")
    fonts.set(f"{W}eastAsia", "宋体")
    fonts.set(f"{W}cs", "Times New Roman")
    if size_half_points is not None:
        for tag in ("sz", "szCs"):
            size = properties.find(f"{W}{tag}")
            if size is None:
                size = etree.SubElement(properties, f"{W}{tag}")
            size.set(f"{W}val", str(size_half_points))
    if bold and properties.find(f"{W}b") is None:
        etree.SubElement(properties, f"{W}b")


def _new_text_paragraph(
    text: str,
    *,
    align: str,
    size_half_points: int,
    bold: bool = False,
    page_break_before: bool = False,
) -> etree._Element:
    paragraph = etree.Element(f"{W}p")
    properties = etree.SubElement(paragraph, f"{W}pPr")
    justification = etree.SubElement(properties, f"{W}jc")
    justification.set(f"{W}val", align)
    spacing = etree.SubElement(properties, f"{W}spacing")
    spacing.set(f"{W}before", "0")
    spacing.set(f"{W}after", "0")
    if page_break_before:
        page_break = etree.SubElement(properties, f"{W}pageBreakBefore")
        page_break.set(f"{W}val", "1")
    run = etree.SubElement(paragraph, f"{W}r")
    _ensure_run_format(run, size_half_points=size_half_points, bold=bold)
    lines = text.split("\n")
    for index, line in enumerate(lines):
        if index:
            etree.SubElement(run, f"{W}br")
        value = etree.SubElement(run, f"{W}t")
        if line[:1].isspace() or line[-1:].isspace():
            value.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        value.text = line
    return paragraph


def _new_table(record: dict) -> etree._Element:
    columns = record["columns"]
    rows = [columns, *record["rows"]]
    widths_twips = [round(float(width) / 2.54 * 1440) for width in record["column_widths_cm"]]
    size_half_points = round(float(record["font_pt"]) * 2)

    table = etree.Element(f"{W}tbl")
    properties = etree.SubElement(table, f"{W}tblPr")
    layout = etree.SubElement(properties, f"{W}tblLayout")
    layout.set(f"{W}type", "fixed")
    width = etree.SubElement(properties, f"{W}tblW")
    width.set(f"{W}type", "dxa")
    width.set(f"{W}w", str(sum(widths_twips)))
    borders = etree.SubElement(properties, f"{W}tblBorders")
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        border = etree.SubElement(borders, f"{W}{side}")
        border.set(f"{W}val", "single")
        border.set(f"{W}sz", "4")
        border.set(f"{W}color", "808080")
    grid = etree.SubElement(table, f"{W}tblGrid")
    for column_width in widths_twips:
        column = etree.SubElement(grid, f"{W}gridCol")
        column.set(f"{W}w", str(column_width))

    for row_index, row_values in enumerate(rows):
        row = etree.SubElement(table, f"{W}tr")
        row_properties = etree.SubElement(row, f"{W}trPr")
        if row_index == 0:
            repeat = etree.SubElement(row_properties, f"{W}tblHeader")
            repeat.set(f"{W}val", "1")
        cannot_split = etree.SubElement(row_properties, f"{W}cantSplit")
        cannot_split.set(f"{W}val", "1")
        for cell_index, value in enumerate(row_values):
            cell = etree.SubElement(row, f"{W}tc")
            cell_properties = etree.SubElement(cell, f"{W}tcPr")
            cell_width = etree.SubElement(cell_properties, f"{W}tcW")
            cell_width.set(f"{W}type", "dxa")
            cell_width.set(f"{W}w", str(widths_twips[cell_index]))
            vertical = etree.SubElement(cell_properties, f"{W}vAlign")
            vertical.set(f"{W}val", "center")
            if row_index == 0:
                shading = etree.SubElement(cell_properties, f"{W}shd")
                shading.set(f"{W}val", "clear")
                shading.set(f"{W}fill", "D9EAF7")
            cell.append(
                _new_text_paragraph(
                    str(value),
                    align="center" if row_index == 0 else "left",
                    size_half_points=size_half_points,
                    bold=row_index == 0,
                )
            )
    return table


def _prepare_inner_headings(
    input_docx: Path,
    prepared_docx: Path,
    table_manifest_path: Path | None = None,
) -> None:
    """Normalize the bounded chapter layout and insert native Word tables."""

    chinese_heading = re.compile(r"^[一二三四五六七八九十]+．")
    arabic_heading = re.compile(r"^\d+．")
    namespace = {"w": W_NS}

    with ZipFile(input_docx, "r") as source:
        document_xml = source.read("word/document.xml")
        root = etree.fromstring(document_xml)
        in_scope = False
        chapter_one_count = 0
        chapter_three_count = 0
        changed = 0
        scoped_paragraphs: list[etree._Element] = []
        for paragraph in root.xpath(".//w:body/w:p", namespaces=namespace):
            text = "".join(
                paragraph.xpath(".//w:t/text()", namespaces=namespace)
            ).strip()
            if text == CHAPTER_ONE:
                chapter_one_count += 1
                in_scope = True
                scoped_paragraphs.append(paragraph)
            elif text == CHAPTER_THREE:
                chapter_three_count += 1
                in_scope = False
            elif in_scope:
                scoped_paragraphs.append(paragraph)

            if in_scope and (
                chinese_heading.match(text) or arabic_heading.match(text)
            ):
                properties = paragraph.find(f"{W}pPr")
                if properties is None:
                    properties = etree.Element(f"{W}pPr")
                    paragraph.insert(0, properties)
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
                changed += 1

        for paragraph in scoped_paragraphs:
            text = "".join(paragraph.xpath(".//w:t/text()", namespaces=namespace)).strip()
            style = paragraph.find(f"{W}pPr/{W}pStyle")
            style_id = style.get(f"{W}val") if style is not None else ""
            is_heading = (
                text == CHAPTER_ONE
                or style_id in {"1", "2"}
                or bool(re.match(r"^\d+\.\d+\s", text))
                or bool(chinese_heading.match(text))
                or bool(arabic_heading.match(text))
            )
            if text.startswith("{{TABLE:"):
                continue
            for run in paragraph.findall(f".//{W}r"):
                _ensure_run_format(
                    run,
                    size_half_points=None if is_heading else 21,
                )

        if table_manifest_path is not None:
            table_records = json.loads(table_manifest_path.read_text(encoding="utf-8"))
            scoped_markers = {
                "".join(paragraph.xpath(".//w:t/text()", namespaces=namespace)).strip(): paragraph
                for paragraph in scoped_paragraphs
                if "".join(paragraph.xpath(".//w:t/text()", namespaces=namespace)).strip().startswith(
                    "{{TABLE:"
                )
            }
            expected_markers = {f"{{{{TABLE:{record['number']}}}}}" for record in table_records}
            if set(scoped_markers) != expected_markers:
                raise RuntimeError(
                    "table marker mismatch: "
                    f"expected={sorted(expected_markers)} actual={sorted(scoped_markers)}"
                )
            for record in table_records:
                marker = f"{{{{TABLE:{record['number']}}}}}"
                paragraph = scoped_markers[marker]
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
                table = _new_table(record)
                note = _new_text_paragraph(
                    f"注：{record['note']}",
                    align="left",
                    size_half_points=18,
                )
                parent.insert(position, title)
                parent.insert(position + 1, table)
                parent.insert(position + 2, note)

        if chapter_one_count != 1 or chapter_three_count != 1 or not changed:
            raise RuntimeError(
                "inner-heading preparation failed: "
                f"chapter_one={chapter_one_count} "
                f"chapter_three={chapter_three_count} changed={changed}"
            )

        updated_xml = etree.tostring(
            root,
            encoding="UTF-8",
            xml_declaration=True,
            standalone=True,
        )
        with ZipFile(prepared_docx, "w", compression=ZIP_DEFLATED) as target:
            target.comment = source.comment
            for info in source.infolist():
                payload = updated_xml if info.filename == "word/document.xml" else source.read(info)
                target.writestr(info, payload)


def build_review_docx(
    input_docx: Path,
    output_docx: Path,
    output_pdf: Path,
    manifest_path: Path,
    table_manifest_path: Path,
) -> None:
    for path in (input_docx, manifest_path, table_manifest_path):
        if not path.is_file():
            raise FileNotFoundError(path)
    for path in (output_docx, output_pdf):
        if path.exists():
            raise FileExistsError(f"refusing to overwrite existing output: {path}")

    records = json.loads(manifest_path.read_text(encoding="utf-8"))
    revision_root = manifest_path.parent.parent
    expected_numbers = [
        *(f"图1.{index}" for index in range(1, 10)),
        *(f"图2.{index}" for index in range(1, 15)),
    ]
    actual_numbers = [record["number"] for record in records]
    if actual_numbers != expected_numbers:
        raise ValueError(f"unexpected figure order: {actual_numbers}")

    pythoncom.CoInitialize()
    temporary = tempfile.TemporaryDirectory(prefix="chapters-1-2-review-")
    word = None
    document = None
    try:
        prepared_docx = Path(temporary.name) / "prepared.docx"
        _prepare_inner_headings(input_docx, prepared_docx, table_manifest_path)
        word = win32com.client.DispatchEx("Word.Application")
        word.Visible = False
        word.DisplayAlerts = 0
        word.ScreenUpdating = False
        document = word.Documents.Open(
            str(prepared_docx.resolve()),
            ReadOnly=True,
            AddToRecentFiles=False,
        )

        placements: list[tuple[int, int, dict, Path]] = []
        for record in records:
            marker = "{{FIGURE:" + record["number"] + "}}"
            matches = _find_exact_paragraphs(document, marker)
            if len(matches) != 1:
                raise RuntimeError(f"marker {marker!r} occurs {len(matches)} times")
            png_path = (revision_root / record["png"]).resolve()
            if not png_path.is_file():
                raise FileNotFoundError(png_path)
            placements.append((*matches[0], record, png_path))

        # Work from the end so earlier Word ranges do not move.
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-docx", type=Path, required=True)
    parser.add_argument("--output-pdf", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--tables", type=Path, required=True)
    args = parser.parse_args()
    build_review_docx(
        args.input,
        args.output_docx,
        args.output_pdf,
        args.manifest,
        args.tables,
    )
    print(f"PASS DOCX: {args.output_docx}")
    print(f"PASS PDF: {args.output_pdf}")


if __name__ == "__main__":
    main()
