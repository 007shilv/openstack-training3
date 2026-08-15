#!/usr/bin/env python3
"""Insert Chapter 3 figures and tables into a bounded-review DOCX.

The builder uses only the Python standard library.  Existing package members are
copied with their ZipInfo metadata and payloads intact unless the member is one
of the three Open XML parts that must be updated for embedded images.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import struct
import tempfile
from copy import copy
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
PIC = "http://schemas.openxmlformats.org/drawingml/2006/picture"
PR = "http://schemas.openxmlformats.org/package/2006/relationships"
CT = "http://schemas.openxmlformats.org/package/2006/content-types"
IMAGE_REL = f"{R}/image"
PNG_CONTENT_TYPE = "image/png"


for prefix, namespace in (
    ("w", W),
    ("r", R),
    ("wp", WP),
    ("a", A),
    ("pic", PIC),
    ("", PR),
):
    ET.register_namespace(prefix, namespace)


def q(namespace: str, local: str) -> str:
    return f"{{{namespace}}}{local}"


def _paragraph_text(paragraph: ET.Element) -> str:
    return "".join(node.text or "" for node in paragraph.iter(q(W, "t")))


def _ensure_child(parent: ET.Element, tag: str, first: bool = False) -> ET.Element:
    child = parent.find(tag)
    if child is None:
        child = ET.Element(tag)
        if first:
            parent.insert(0, child)
        else:
            parent.append(child)
    return child


def _run_properties(run: ET.Element) -> ET.Element:
    return _ensure_child(run, q(W, "rPr"), first=True)


def _set_run_font(run: ET.Element, size_half_points: int, bold: bool = False) -> None:
    properties = _run_properties(run)
    fonts = _ensure_child(properties, q(W, "rFonts"))
    fonts.set(q(W, "ascii"), "Times New Roman")
    fonts.set(q(W, "hAnsi"), "Times New Roman")
    fonts.set(q(W, "eastAsia"), "宋体")
    fonts.set(q(W, "cs"), "Times New Roman")
    size = _ensure_child(properties, q(W, "sz"))
    size.set(q(W, "val"), str(size_half_points))
    size_cs = _ensure_child(properties, q(W, "szCs"))
    size_cs.set(q(W, "val"), str(size_half_points))
    existing_bold = properties.find(q(W, "b"))
    if bold and existing_bold is None:
        ET.SubElement(properties, q(W, "b"))


def _paragraph_properties(paragraph: ET.Element) -> ET.Element:
    return _ensure_child(paragraph, q(W, "pPr"), first=True)


def _new_text_paragraph(
    text: str,
    *,
    size_half_points: int = 18,
    bold: bool = False,
    alignment: str = "center",
) -> ET.Element:
    paragraph = ET.Element(q(W, "p"))
    properties = ET.SubElement(paragraph, q(W, "pPr"))
    justification = ET.SubElement(properties, q(W, "jc"))
    justification.set(q(W, "val"), alignment)
    spacing = ET.SubElement(properties, q(W, "spacing"))
    spacing.set(q(W, "before"), "0")
    spacing.set(q(W, "after"), "0")
    spacing.set(q(W, "line"), "240")
    spacing.set(q(W, "lineRule"), "auto")
    run = ET.SubElement(paragraph, q(W, "r"))
    _set_run_font(run, size_half_points, bold)
    node = ET.SubElement(run, q(W, "t"))
    node.text = text
    return paragraph


def _new_caption(number: str, title: str) -> ET.Element:
    """Build a caption while keeping its number as a distinct text run."""
    paragraph = _new_text_paragraph(number, bold=True)
    run = ET.SubElement(paragraph, q(W, "r"))
    _set_run_font(run, 18, True)
    node = ET.SubElement(run, q(W, "t"))
    node.set(q("http://www.w3.org/XML/1998/namespace", "space"), "preserve")
    node.text = f" {title}"
    return paragraph


def _png_size(path: Path) -> tuple[int, int]:
    payload = path.read_bytes()
    if payload[:8] != b"\x89PNG\r\n\x1a\n" or payload[12:16] != b"IHDR":
        raise ValueError(f"not a PNG file: {path}")
    return struct.unpack(">II", payload[16:24])


def _emu_from_cm(value: float) -> int:
    return round(value / 2.54 * 914400)


def _new_drawing_paragraph(
    relationship_id: str,
    name: str,
    width_emu: int,
    height_emu: int,
    doc_property_id: int,
) -> ET.Element:
    paragraph = ET.Element(q(W, "p"))
    ppr = ET.SubElement(paragraph, q(W, "pPr"))
    jc = ET.SubElement(ppr, q(W, "jc"))
    jc.set(q(W, "val"), "center")
    spacing = ET.SubElement(ppr, q(W, "spacing"))
    spacing.set(q(W, "before"), "120")
    spacing.set(q(W, "after"), "0")

    run = ET.SubElement(paragraph, q(W, "r"))
    drawing = ET.SubElement(run, q(W, "drawing"))
    inline = ET.SubElement(drawing, q(WP, "inline"), {"distT": "0", "distB": "0", "distL": "0", "distR": "0"})
    ET.SubElement(inline, q(WP, "extent"), {"cx": str(width_emu), "cy": str(height_emu)})
    ET.SubElement(inline, q(WP, "effectExtent"), {"l": "0", "t": "0", "r": "0", "b": "0"})
    ET.SubElement(inline, q(WP, "docPr"), {"id": str(doc_property_id), "name": name})
    frame = ET.SubElement(inline, q(WP, "cNvGraphicFramePr"))
    ET.SubElement(frame, q(A, "graphicFrameLocks"), {"noChangeAspect": "1"})

    graphic = ET.SubElement(inline, q(A, "graphic"))
    data = ET.SubElement(graphic, q(A, "graphicData"), {"uri": "http://schemas.openxmlformats.org/drawingml/2006/picture"})
    picture = ET.SubElement(data, q(PIC, "pic"))
    nonvisual = ET.SubElement(picture, q(PIC, "nvPicPr"))
    ET.SubElement(nonvisual, q(PIC, "cNvPr"), {"id": "0", "name": name})
    ET.SubElement(nonvisual, q(PIC, "cNvPicPr"))
    fill = ET.SubElement(picture, q(PIC, "blipFill"))
    ET.SubElement(fill, q(A, "blip"), {q(R, "embed"): relationship_id})
    stretch = ET.SubElement(fill, q(A, "stretch"))
    ET.SubElement(stretch, q(A, "fillRect"))
    shape = ET.SubElement(picture, q(PIC, "spPr"))
    transform = ET.SubElement(shape, q(A, "xfrm"))
    ET.SubElement(transform, q(A, "off"), {"x": "0", "y": "0"})
    ET.SubElement(transform, q(A, "ext"), {"cx": str(width_emu), "cy": str(height_emu)})
    geometry = ET.SubElement(shape, q(A, "prstGeom"), {"prst": "rect"})
    ET.SubElement(geometry, q(A, "avLst"))
    return paragraph


def _set_cell_width(cell: ET.Element, width_cm: float) -> None:
    properties = ET.SubElement(cell, q(W, "tcPr"))
    width = ET.SubElement(properties, q(W, "tcW"))
    width.set(q(W, "w"), str(round(width_cm / 2.54 * 1440)))
    width.set(q(W, "type"), "dxa")


def _new_table(record: dict) -> ET.Element:
    columns = record["columns"]
    rows = record["rows"]
    widths = record["column_widths_cm"]
    if not columns or len(columns) != len(widths):
        raise ValueError(f"invalid columns for {record['number']}")
    if any(len(row) != len(columns) for row in rows):
        raise ValueError(f"invalid row width for {record['number']}")
    half_points = round(float(record.get("font_pt", 9.0)) * 2)

    table = ET.Element(q(W, "tbl"))
    properties = ET.SubElement(table, q(W, "tblPr"))
    width = ET.SubElement(properties, q(W, "tblW"))
    width.set(q(W, "w"), "0")
    width.set(q(W, "type"), "auto")
    layout = ET.SubElement(properties, q(W, "tblLayout"))
    layout.set(q(W, "type"), "fixed")
    borders = ET.SubElement(properties, q(W, "tblBorders"))
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        ET.SubElement(borders, q(W, edge), {q(W, "val"): "single", q(W, "sz"): "4", q(W, "space"): "0", q(W, "color"): "808080"})
    grid = ET.SubElement(table, q(W, "tblGrid"))
    for value in widths:
        ET.SubElement(grid, q(W, "gridCol"), {q(W, "w"): str(round(float(value) / 2.54 * 1440))})

    for row_index, values in enumerate([columns, *rows]):
        row = ET.SubElement(table, q(W, "tr"))
        for column_index, value in enumerate(values):
            cell = ET.SubElement(row, q(W, "tc"))
            _set_cell_width(cell, float(widths[column_index]))
            cell_properties = cell.find(q(W, "tcPr"))
            if row_index == 0:
                shading = ET.SubElement(cell_properties, q(W, "shd"))
                shading.set(q(W, "fill"), "D9EAF7")
            paragraph = ET.SubElement(cell, q(W, "p"))
            ppr = ET.SubElement(paragraph, q(W, "pPr"))
            jc = ET.SubElement(ppr, q(W, "jc"))
            jc.set(q(W, "val"), "center" if row_index == 0 else "left")
            run = ET.SubElement(paragraph, q(W, "r"))
            _set_run_font(run, half_points, row_index == 0)
            text = ET.SubElement(run, q(W, "t"))
            text.text = str(value)
    return table


def _next_relationship_number(relationships: ET.Element) -> int:
    numbers = []
    for relationship in relationships:
        match = re.fullmatch(r"rId(\d+)", relationship.attrib.get("Id", ""))
        if match:
            numbers.append(int(match.group(1)))
    return max(numbers, default=0) + 1


def _next_doc_property_id(document: ET.Element) -> int:
    values = []
    for node in document.iter(q(WP, "docPr")):
        try:
            values.append(int(node.attrib.get("id", "0")))
        except ValueError:
            continue
    return max(values, default=0) + 1


def _replace_direct_child(body: ET.Element, old: ET.Element, replacements: list[ET.Element]) -> None:
    children = list(body)
    try:
        index = children.index(old)
    except ValueError as exc:
        raise ValueError("marker is not a direct body child") from exc
    body.remove(old)
    for offset, replacement in enumerate(replacements):
        body.insert(index + offset, replacement)


def _find_unique_marker(body: ET.Element, marker: str) -> ET.Element:
    matches = [child for child in list(body) if child.tag == q(W, "p") and _paragraph_text(child).strip() == marker]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one marker {marker!r}, found {len(matches)}")
    return matches[0]


def _normalize_chapter_fonts(body: ET.Element, caption_texts: set[str]) -> None:
    children = list(body)
    chapter_start = next((i for i, child in enumerate(children) if child.tag == q(W, "p") and _paragraph_text(child).strip().startswith("第三章 ")), None)
    chapter_end = next((i for i, child in enumerate(children) if child.tag == q(W, "p") and _paragraph_text(child).strip().startswith("第四章 ")), None)
    if chapter_start is None or chapter_end is None or chapter_start >= chapter_end:
        raise ValueError("could not locate the Chapter 3 bounded range")
    internal_heading = re.compile(r"^(?:[一二三四五六七八九十]+|\d+)．")
    for child in children[chapter_start + 1 : chapter_end]:
        if child.tag != q(W, "p"):
            continue
        text = _paragraph_text(child).strip()
        if not text or text.startswith(("3.1 ", "3.2 ")) or text in caption_texts:
            continue
        bold = bool(internal_heading.match(text))
        for run in child.findall(q(W, "r")):
            _set_run_font(run, 21, bold)


def _xml_bytes(root: ET.Element) -> bytes:
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _copy_zip_info(info: ZipInfo) -> ZipInfo:
    # ZipFile accepts a copied ZipInfo and thereby preserves timestamps,
    # compression, permissions, comments and extra fields.
    return copy(info)


def build_review_docx(
    source_docx: str | Path,
    output_docx: str | Path,
    figure_manifest: str | Path,
    table_manifest: str | Path,
) -> None:
    source = Path(source_docx).resolve()
    output = Path(output_docx).resolve()
    figure_manifest_path = Path(figure_manifest).resolve()
    table_manifest_path = Path(table_manifest).resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if output.exists():
        raise FileExistsError(output)
    if source == output:
        raise ValueError("source and output paths must differ")

    figures = json.loads(figure_manifest_path.read_text(encoding="utf-8"))
    tables = json.loads(table_manifest_path.read_text(encoding="utf-8"))
    expected_figures = [f"图3.{number}" for number in range(1, 10)]
    expected_tables = [f"表3-{number}" for number in range(1, 6)]
    if [row.get("number") for row in figures] != expected_figures:
        raise ValueError("figure manifest must contain 图3.1 through 图3.9 exactly once and in order")
    if [row.get("number") for row in tables] != expected_tables:
        raise ValueError("table manifest must contain 表3-1 through 表3-5 exactly once and in order")

    media: list[tuple[str, Path]] = []
    with ZipFile(source, "r") as package:
        infos = package.infolist()
        names = [info.filename for info in infos]
        required = {"[Content_Types].xml", "word/document.xml", "word/_rels/document.xml.rels"}
        missing = sorted(required.difference(names))
        if missing:
            raise ValueError(f"source DOCX is missing required members: {missing}")
        payloads = {info.filename: package.read(info.filename) for info in infos}
        archive_comment = package.comment

    document = ET.fromstring(payloads["word/document.xml"])
    relationships = ET.fromstring(payloads["word/_rels/document.xml.rels"])
    content_types = ET.fromstring(payloads["[Content_Types].xml"])
    body = document.find(q(W, "body"))
    if body is None:
        raise ValueError("word/document.xml has no w:body")

    relationship_number = _next_relationship_number(relationships)
    document_property_id = _next_doc_property_id(document)
    revision_root = figure_manifest_path.parent.parent
    for index, record in enumerate(figures, start=1):
        marker = f"{{{{FIGURE:{record['number']}}}}}"
        marker_paragraph = _find_unique_marker(body, marker)
        image_path = (revision_root / record["png"]).resolve()
        try:
            image_path.relative_to(revision_root.resolve())
        except ValueError as exc:
            raise ValueError(f"figure path escapes revision root: {record['png']}") from exc
        if not image_path.is_file():
            raise FileNotFoundError(image_path)
        pixel_width, pixel_height = _png_size(image_path)
        width_emu = _emu_from_cm(float(record["width_cm"]))
        height_emu = round(width_emu * pixel_height / pixel_width)
        relationship_id = f"rId{relationship_number}"
        relationship_number += 1
        media_name = f"word/media/ch03-figure-{index}.png"
        if media_name in payloads:
            raise ValueError(f"source already contains reserved media name: {media_name}")
        ET.SubElement(
            relationships,
            q(PR, "Relationship"),
            {"Id": relationship_id, "Type": IMAGE_REL, "Target": f"media/ch03-figure-{index}.png"},
        )
        drawing = _new_drawing_paragraph(
            relationship_id,
            f"Chapter 3 Figure {index}",
            width_emu,
            height_emu,
            document_property_id,
        )
        document_property_id += 1
        caption = _new_caption(record["number"], record["title"])
        _replace_direct_child(body, marker_paragraph, [drawing, caption])
        media.append((media_name, image_path))

    for record in tables:
        marker = f"{{{{TABLE:{record['number']}}}}}"
        marker_paragraph = _find_unique_marker(body, marker)
        caption = _new_caption(record["number"], record["title"])
        _replace_direct_child(body, marker_paragraph, [caption, _new_table(record)])

    caption_texts = {
        f"{record['number']} {record['title']}" for record in [*figures, *tables]
    }
    _normalize_chapter_fonts(body, caption_texts)
    if not any(node.attrib.get("Extension", "").lower() == "png" for node in content_types.findall(q(CT, "Default"))):
        ET.SubElement(content_types, q(CT, "Default"), {"Extension": "png", "ContentType": PNG_CONTENT_TYPE})
    payloads["word/document.xml"] = _xml_bytes(document)
    payloads["word/_rels/document.xml.rels"] = _xml_bytes(relationships)
    payloads["[Content_Types].xml"] = _xml_bytes(content_types)

    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{output.stem}-", suffix=".tmp", dir=output.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with ZipFile(temporary, "w") as package:
            package.comment = archive_comment
            for info in infos:
                package.writestr(_copy_zip_info(info), payloads[info.filename])
            for media_name, image_path in media:
                package.writestr(media_name, image_path.read_bytes(), compress_type=ZIP_DEFLATED)
        with ZipFile(temporary, "r") as package:
            bad_member = package.testzip()
            if bad_member is not None:
                raise ValueError(f"generated DOCX failed ZIP integrity at {bad_member}")
        os.replace(temporary, output)
    finally:
        if temporary.exists():
            temporary.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--figures", required=True, type=Path)
    parser.add_argument("--tables", required=True, type=Path)
    args = parser.parse_args()
    build_review_docx(args.source, args.output, args.figures, args.tables)
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
