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


def _prepare_inner_headings(input_docx: Path, prepared_docx: Path) -> None:
    """Remove body indents from inner headings without a slow Word COM loop."""

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
        for paragraph in root.xpath(".//w:body/w:p", namespaces=namespace):
            text = "".join(
                paragraph.xpath(".//w:t/text()", namespaces=namespace)
            ).strip()
            if text == CHAPTER_ONE:
                chapter_one_count += 1
                in_scope = True
            elif text == CHAPTER_THREE:
                chapter_three_count += 1
                in_scope = False
            elif in_scope and (
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
) -> None:
    for path in (input_docx, manifest_path):
        if not path.is_file():
            raise FileNotFoundError(path)
    for path in (output_docx, output_pdf):
        if path.exists():
            raise FileExistsError(f"refusing to overwrite existing output: {path}")

    records = json.loads(manifest_path.read_text(encoding="utf-8"))
    revision_root = manifest_path.parent.parent
    expected_numbers = [
        *(f"图1.{index}" for index in range(1, 8)),
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
        _prepare_inner_headings(input_docx, prepared_docx)
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
    args = parser.parse_args()
    build_review_docx(args.input, args.output_docx, args.output_pdf, args.manifest)
    print(f"PASS DOCX: {args.output_docx}")
    print(f"PASS PDF: {args.output_pdf}")


if __name__ == "__main__":
    main()
