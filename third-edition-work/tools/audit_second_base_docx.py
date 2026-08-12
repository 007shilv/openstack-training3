"""Measure and audit the frozen second-edition DOCX style contract.

This module intentionally reads DOCX Open XML directly.  It does not automate
Word, so its measurements are repeatable in CI and on systems without Office.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET


WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
DRAWING_NS = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
NS = {"w": WORD_NS, "wp": DRAWING_NS}
W = f"{{{WORD_NS}}}"
CAPTION_PATTERN = re.compile(r"^图\d+\.\d+\.\d+")


def sha256(path: Path) -> str:
    """Return the SHA-256 digest of a file without modifying it."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_baseline(path: Path) -> dict[str, Any]:
    """Load the UTF-8 machine-readable second-edition style contract."""
    with path.open(encoding="utf-8") as stream:
        baseline = json.load(stream)
    if not isinstance(baseline, dict):
        raise ValueError(f"baseline must be a JSON object: {path}")
    return baseline


def _attribute(element: ET.Element | None, name: str, default: str | None = None) -> str | None:
    return default if element is None else element.get(f"{W}{name}", default)


def _centimeters(twips: str | None) -> float:
    if twips is None:
        raise ValueError("DOCX page setting is missing a required twip value")
    return round(int(twips) * 2.54 / 1440, 2)


def _points(half_points: str | None) -> float | str:
    if half_points is None:
        return "<missing>"
    return int(half_points) / 2


def _text(paragraph: ET.Element) -> str:
    return "".join(node.text or "" for node in paragraph.findall(".//w:t", NS)).strip()


def _run_properties(paragraph: ET.Element) -> ET.Element:
    properties = paragraph.find(".//w:rPr", NS)
    if properties is None:
        raise ValueError("caption has no direct run properties")
    return properties


def _font_name(properties: ET.Element) -> str:
    fonts = properties.find("w:rFonts", NS)
    if fonts is None:
        return "<missing>"
    return _attribute(fonts, "eastAsia") or _attribute(fonts, "ascii") or "<missing>"


def _body_paragraph_count(body: ET.Element) -> int:
    """Count top-level body paragraphs, matching Word's main-text structure."""
    return len(body.findall("w:p", NS))


def _style_properties(styles: ET.Element, style_id: str) -> ET.Element:
    for style in styles.findall("w:style", NS):
        if _attribute(style, "styleId") == style_id:
            properties = style.find("w:rPr", NS)
            if properties is None:
                return ET.Element(f"{W}rPr")
            return properties
    return ET.Element(f"{W}rPr")


def measure_docx(path: Path) -> dict[str, Any]:
    """Return style and structural measurements from DOCX Open XML."""
    with zipfile.ZipFile(path) as archive:
        document = ET.fromstring(archive.read("word/document.xml"))
        styles = ET.fromstring(archive.read("word/styles.xml"))

    sections: list[dict[str, Any]] = []
    for section in document.findall(".//w:sectPr", NS):
        page = section.find("w:pgSz", NS)
        margins = section.find("w:pgMar", NS)
        if page is None or margins is None:
            raise ValueError("DOCX section is missing page size or margins")
        sections.append(
            {
                "page_cm": [_centimeters(_attribute(page, "w")), _centimeters(_attribute(page, "h"))],
                "margins_cm": [
                    _centimeters(_attribute(margins, side))
                    for side in ("top", "right", "bottom", "left")
                ],
                "header_cm": _centimeters(_attribute(margins, "header")),
                "footer_cm": _centimeters(_attribute(margins, "footer")),
            }
        )
    if not sections:
        raise ValueError("DOCX has no section settings")

    defaults = styles.find("w:docDefaults/w:rPrDefault/w:rPr", NS)
    if defaults is None:
        raise ValueError("DOCX has no default run properties")
    default_size = defaults.find("w:sz", NS)
    normal = _style_properties(styles, "a")
    heading_sizes = {
        f"heading_{number}": _points(_attribute(_style_properties(styles, str(number)).find("w:sz", NS), "val"))
        for number in (1, 2, 3)
    }

    caption: ET.Element | None = None
    for paragraph in document.findall(".//w:p", NS):
        if CAPTION_PATTERN.match(_text(paragraph)):
            caption = paragraph
            break
    if caption is None:
        caption_format: dict[str, Any] = {
            "font": "<missing>", "size_pt": "<missing>", "bold": False,
            "alignment": "<missing>", "numbering": "<missing>",
        }
    else:
        caption_properties = _run_properties(caption)
        caption_size = caption_properties.find("w:sz", NS)
        caption_alignment = caption.find("w:pPr/w:jc", NS)
        caption_format = {
            "font": _font_name(caption_properties),
            "size_pt": _points(_attribute(caption_size, "val")),
            "bold": caption_properties.find("w:b", NS) is not None,
            "alignment": _attribute(caption_alignment, "val", "<missing>"),
            "numbering": "图<chapter>.<section>.<sequence>",
        }

    body = document.find("w:body", NS)
    if body is None:
        raise ValueError("DOCX has no document body")
    first = sections[0]
    return {
        "section_count": len(sections),
        "sections": sections,
        "page_cm": first["page_cm"],
        "margins_cm": first["margins_cm"],
        "header_cm": first["header_cm"],
        "footer_cm": first["footer_cm"],
        "body_font": _font_name(normal),
        "body_size_pt": _points(_attribute(default_size, "val")),
        "heading_sizes_pt": heading_sizes,
        "caption_format": caption_format,
        "paragraph_count": _body_paragraph_count(body),
        "inline_shape_count": len(document.findall(".//wp:inline", NS)),
        "table_count": len(document.findall(".//w:tbl", NS)),
    }


def audit_docx(source: Path, candidate: Path) -> list[str]:
    """Return style-contract violations between a reference and candidate DOCX.

    Text, table, and picture totals are reported by ``measure_docx`` but are not
    enforced here: targeted textbook edits are expected to change them.
    """
    reference = measure_docx(source)
    measured = measure_docx(candidate)
    errors: list[str] = []
    for field in (
        "section_count",
        "page_cm",
        "margins_cm",
        "header_cm",
        "footer_cm",
        "body_font",
        "body_size_pt",
        "heading_sizes_pt",
        "caption_format",
    ):
        if measured[field] != reference[field]:
            errors.append(f"{field} differs: source={reference[field]!r}, candidate={measured[field]!r}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="immutable second-edition DOCX")
    parser.add_argument("--candidate", type=Path, required=True, help="DOCX to audit")
    arguments = parser.parse_args(argv)

    source_measurement = measure_docx(arguments.source)
    print(f"source SHA-256: {sha256(arguments.source)}")
    for index, section in enumerate(source_measurement["sections"], start=1):
        print(
            f"section {index}: {section['page_cm'][0]}×{section['page_cm'][1]} cm; "
            f"margins {section['margins_cm']} cm"
        )
    print(
        "source totals: "
        f"paragraphs={source_measurement['paragraph_count']}, "
        f"inline_shapes={source_measurement['inline_shape_count']}, "
        f"tables={source_measurement['table_count']}"
    )
    errors = audit_docx(arguments.source, arguments.candidate)
    if errors:
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print("PASS: candidate preserves the source style contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
