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
BASELINE_PATH = Path(__file__).resolve().parents[1] / "revision" / "second-edition-style-baseline.json"
CAPTION_PATTERN = re.compile(r"^图(?P<chapter>\d+)(?P<separator_1>[^\d])(?P<section>\d+)(?P<separator_2>[^\d])(?P<sequence>\d+)")


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


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _font_name(properties: ET.Element) -> str:
    fonts = properties.find("w:rFonts", NS)
    if fonts is None:
        return "<missing>"
    return _attribute(fonts, "eastAsia") or _attribute(fonts, "ascii") or "<missing>"


def _body_paragraph_count(body: ET.Element) -> int:
    """Count top-level body paragraphs, matching Word's main-text structure."""
    return len(body.findall("w:p", NS))


def _style_run_properties(styles: ET.Element, style_id: str, seen: set[str] | None = None) -> list[ET.Element]:
    """Return inherited-to-local run properties for a named paragraph/run style."""
    seen = set() if seen is None else seen
    if style_id in seen:
        return []
    seen.add(style_id)
    for style in styles.findall("w:style", NS):
        if _attribute(style, "styleId") != style_id:
            continue
        inherited: list[ET.Element] = []
        based_on = style.find("w:basedOn", NS)
        parent_id = _attribute(based_on, "val")
        if parent_id:
            inherited.extend(_style_run_properties(styles, parent_id, seen))
        properties = style.find("w:rPr", NS)
        if properties is not None:
            inherited.append(properties)
        return inherited
    return []


def _bold_value(properties: ET.Element) -> bool:
    value = _attribute(properties.find("w:b", NS), "val")
    return value not in {"0", "false", "off"}


def _effective_text_run_format(
    paragraph: ET.Element,
    run: ET.Element,
    styles: ET.Element,
    defaults: ET.Element,
) -> dict[str, Any]:
    """Resolve the font/size/bold chain for one visible text run."""
    properties_chain = [defaults]
    paragraph_style = _attribute(paragraph.find("w:pPr/w:pStyle", NS), "val")
    if paragraph_style:
        properties_chain.extend(_style_run_properties(styles, paragraph_style))
    paragraph_properties = paragraph.find("w:pPr/w:rPr", NS)
    if paragraph_properties is not None:
        properties_chain.append(paragraph_properties)
    run_properties = run.find("w:rPr", NS)
    run_style = _attribute(run_properties.find("w:rStyle", NS) if run_properties is not None else None, "val")
    if run_style:
        properties_chain.extend(_style_run_properties(styles, run_style))
    if run_properties is not None:
        properties_chain.append(run_properties)

    east_asia: str | None = None
    ascii_font: str | None = None
    size: str | None = None
    bold = False
    for properties in properties_chain:
        fonts = properties.find("w:rFonts", NS)
        if fonts is not None:
            east_asia = _attribute(fonts, "eastAsia", east_asia)
            ascii_font = _attribute(fonts, "ascii", ascii_font)
        size = _attribute(properties.find("w:sz", NS), "val", size)
        if properties.find("w:b", NS) is not None:
            bold = _bold_value(properties)
    return {
        "font": east_asia or ascii_font or "<missing>",
        "size_pt": _points(size),
        "bold": bold,
    }


def _caption_record(paragraph: ET.Element, styles: ET.Element, defaults: ET.Element) -> dict[str, Any] | None:
    """Parse an adjacent figure caption and every visible text run's effective format."""
    match = CAPTION_PATTERN.match(_text(paragraph))
    if match is None:
        return None
    alignment = paragraph.find("w:pPr/w:jc", NS)
    text_runs = [run for run in paragraph.findall(".//w:r", NS) if _text(run)]
    if not text_runs:
        raise ValueError("caption has no visible text runs")
    effective_runs = [
        _effective_text_run_format(paragraph, run, styles, defaults)
        for run in text_runs
    ]
    return {
        "numbering": {
            "prefix": "图",
            "separators": [match.group("separator_1"), match.group("separator_2")],
        },
        "font": effective_runs[0]["font"],
        "size_pt": effective_runs[0]["size_pt"],
        "bold": effective_runs[0]["bold"],
        "alignment": _attribute(alignment, "val", "<missing>"),
        "text_runs": effective_runs,
    }


def _figure_caption_records(body: ET.Element, styles: ET.Element, defaults: ET.Element) -> list[dict[str, Any] | None]:
    """Return one adjacency-aware caption record for each inline picture paragraph."""
    paragraphs = body.findall("w:p", NS)
    records: list[dict[str, Any] | None] = []
    for index, paragraph in enumerate(paragraphs):
        inline_count = len(paragraph.findall(".//wp:inline", NS))
        if not inline_count:
            continue
        if inline_count != 1:
            raise ValueError("source has an inline-picture paragraph with more than one image")
        records.append(_caption_record(paragraphs[index + 1], styles, defaults) if index + 1 < len(paragraphs) else None)
    return records


def _inline_widths_emu(document: ET.Element) -> list[int]:
    widths: list[int] = []
    for inline in document.findall(".//wp:inline", NS):
        extent = inline.find("wp:extent", NS)
        if extent is None or "cx" not in extent.attrib:
            raise ValueError("inline picture is missing an extent width")
        widths.append(int(extent.attrib["cx"]))
    return widths


def _figure_caption_records_from_docx(path: Path) -> list[dict[str, Any] | None]:
    with zipfile.ZipFile(path) as archive:
        document = ET.fromstring(archive.read("word/document.xml"))
        styles = ET.fromstring(archive.read("word/styles.xml"))
    body = document.find("w:body", NS)
    defaults = styles.find("w:docDefaults/w:rPrDefault/w:rPr", NS)
    if body is None or defaults is None:
        raise ValueError("DOCX has no document body")
    return _figure_caption_records(body, styles, defaults)


def _body_direct_run_formats(body: ET.Element) -> list[dict[str, Any]]:
    """Capture direct font/size formatting on body text runs, excluding figure captions."""
    records: list[dict[str, Any]] = []
    for paragraph_index, paragraph in enumerate(body.findall("w:p", NS)):
        if CAPTION_PATTERN.match(_text(paragraph)):
            continue
        for run_index, run in enumerate(paragraph.findall("w:r", NS)):
            if not _text(run):
                continue
            properties = run.find("w:rPr", NS)
            if properties is None:
                continue
            fonts = properties.find("w:rFonts", NS)
            size = properties.find("w:sz", NS)
            if fonts is None and size is None:
                continue
            records.append(
                {
                    "paragraph": paragraph_index,
                    "run": run_index,
                    "font": _font_name(properties),
                    "size_pt": _points(_attribute(size, "val")),
                }
            )
    return records


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

    caption: ET.Element | None = next(
        (paragraph for paragraph in document.findall(".//w:p", NS) if CAPTION_PATTERN.match(_text(paragraph))),
        None,
    )
    if caption is None:
        caption_format: dict[str, Any] = {
            "font": "<missing>", "size_pt": "<missing>", "bold": False,
            "alignment": "<missing>", "numbering": "<missing>",
        }
    else:
        caption_format = _caption_record(caption, styles, defaults)
        assert caption_format is not None

    body = document.find("w:body", NS)
    if body is None:
        raise ValueError("DOCX has no document body")
    first = sections[0]
    caption_records = _figure_caption_records(body, styles, defaults)
    inline_widths = _inline_widths_emu(document)
    direct_run_formats = _body_direct_run_formats(body)
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
        "caption_count": sum(record is not None for record in caption_records),
        "caption_records_sha256": _canonical_sha256(caption_records),
        "inline_widths_emu": {
            "count": len(inline_widths),
            "min": min(inline_widths),
            "max": max(inline_widths),
            "sequence_sha256": _canonical_sha256(inline_widths),
        },
        "body_run_direct_format_sha256": _canonical_sha256(direct_run_formats),
        "paragraph_count": _body_paragraph_count(body),
        "inline_shape_count": len(document.findall(".//wp:inline", NS)),
        "table_count": len(document.findall(".//w:tbl", NS)),
    }


def audit_docx(source: Path, candidate: Path, baseline_path: Path = BASELINE_PATH) -> list[str]:
    """Return frozen-style-contract violations for a candidate DOCX.

    Text, table, and picture totals are reported by ``measure_docx`` but are not
    enforced here: targeted textbook edits are expected to change them.
    """
    baseline = load_baseline(baseline_path)
    actual_source_sha256 = sha256(source)
    if actual_source_sha256 != baseline["source_sha256"]:
        return [
            "source_sha256 differs: "
            f"baseline={baseline['source_sha256']!r}, supplied={actual_source_sha256!r}"
        ]

    reference = measure_docx(source)
    measured = measure_docx(candidate)
    errors: list[str] = []
    for field in (
        "section_count", "body_font", "body_size_pt", "heading_sizes_pt",
        "caption_format", "caption_count", "caption_records_sha256", "inline_widths_emu",
        "body_run_direct_format_sha256", "paragraph_count", "inline_shape_count", "table_count",
    ):
        if reference[field] != baseline[field]:
            errors.append(f"baseline.{field} differs from frozen source: baseline={baseline[field]!r}, source={reference[field]!r}")
    if reference["sections"] != baseline["sections"]:
        errors.append("baseline.sections differs from frozen source")

    for index, expected_section in enumerate(baseline["sections"]):
        if index >= len(measured["sections"]):
            break
        actual_section = measured["sections"][index]
        for field in ("page_cm", "margins_cm", "header_cm", "footer_cm"):
            if actual_section[field] != expected_section[field]:
                errors.append(
                    f"sections[{index}].{field} differs: "
                    f"baseline={expected_section[field]!r}, candidate={actual_section[field]!r}"
                )
    for field in (
        "section_count",
        "body_font",
        "body_size_pt",
        "heading_sizes_pt",
        "caption_count",
        "inline_widths_emu",
        "body_run_direct_format_sha256",
    ):
        if measured[field] != baseline[field]:
            errors.append(f"{field} differs: baseline={baseline[field]!r}, candidate={measured[field]!r}")
    source_captions = _figure_caption_records_from_docx(source)
    candidate_captions = _figure_caption_records_from_docx(candidate)
    for index, (expected, actual) in enumerate(zip(source_captions, candidate_captions)):
        if expected is None and actual is None:
            continue
        if expected is None or actual is None:
            errors.append(f"caption[{index}].adjacency differs: source={expected!r}, candidate={actual!r}")
            continue
        for field in ("numbering", "font", "size_pt", "bold", "alignment"):
            if expected[field] != actual[field]:
                errors.append(f"caption[{index}].{field} differs: source={expected[field]!r}, candidate={actual[field]!r}")
        if len(expected["text_runs"]) != len(actual["text_runs"]):
            errors.append(
                f"caption[{index}].text_runs count differs: "
                f"source={len(expected['text_runs'])}, candidate={len(actual['text_runs'])}"
            )
            continue
        for run_index, (expected_run, actual_run) in enumerate(zip(expected["text_runs"], actual["text_runs"])):
            for field in ("font", "size_pt", "bold"):
                if expected_run[field] != actual_run[field]:
                    errors.append(
                        f"caption[{index}].text_runs[{run_index}].{field} differs: "
                        f"source={expected_run[field]!r}, candidate={actual_run[field]!r}"
                    )
    if len(source_captions) != len(candidate_captions):
        errors.append(f"caption adjacency count differs: source={len(source_captions)}, candidate={len(candidate_captions)}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="immutable second-edition DOCX")
    parser.add_argument("--candidate", type=Path, required=True, help="DOCX to audit")
    arguments = parser.parse_args(argv)

    errors = audit_docx(arguments.source, arguments.candidate)
    source_hash = sha256(arguments.source)
    print(f"source SHA-256: {source_hash}")
    if any(error.startswith("source_sha256") for error in errors):
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        return 1

    source_measurement = measure_docx(arguments.source)
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
    if errors:
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print("PASS: candidate preserves the source style contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
