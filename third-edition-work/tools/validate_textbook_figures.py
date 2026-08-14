"""Validate Chapter 1–2 textbook SVG/PNG figure pairs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import sys
from xml.etree import ElementTree as ET


def png_dimensions(path: Path) -> tuple[int, int]:
    payload = path.read_bytes()
    if payload[:8] != b"\x89PNG\r\n\x1a\n" or payload[12:16] != b"IHDR":
        raise ValueError(f"not a PNG: {path}")
    return struct.unpack(">II", payload[16:24])


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(manifest_path: Path) -> list[str]:
    manifest_path = manifest_path.resolve()
    records = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(records, list) or len(records) != 12:
        raise ValueError("manifest must contain exactly 12 records")

    revision_root = manifest_path.parent.parent
    svg_hashes: set[str] = set()
    png_hashes: set[str] = set()
    report: list[str] = []

    for record in records:
        svg_path = revision_root / record["svg"]
        png_path = revision_root / record["png"]
        if not svg_path.is_file() or not png_path.is_file():
            raise FileNotFoundError(f"missing figure pair: {record['number']}")

        svg_payload = svg_path.read_text(encoding="utf-8")
        root = ET.fromstring(svg_payload)
        view_box = [float(value) for value in root.attrib["viewBox"].split()]
        if len(view_box) != 4 or view_box[2] < 960 or view_box[3] < 560:
            raise ValueError(f"invalid viewBox: {record['number']}")
        if "SimSun" not in svg_payload or "宋体" not in svg_payload:
            raise ValueError(f"missing Song font fallback: {record['number']}")

        rendered_width_pt = float(record["width_cm"]) * 72 / 2.54
        text_nodes = root.findall(".//{*}text")
        if not text_nodes:
            raise ValueError(f"figure has no text: {record['number']}")
        for node in text_nodes:
            if "font-size" not in node.attrib:
                raise ValueError(f"text without explicit size: {record['number']}")
            rendered_pt = float(node.attrib["font-size"]) * rendered_width_pt / view_box[2]
            if rendered_pt + 0.01 < float(record["minimum_font_pt"]):
                raise ValueError(
                    f"text too small: {record['number']} {rendered_pt:.2f}pt"
                )

        width, height = png_dimensions(png_path)
        if width < 2400 or height < 1400:
            raise ValueError(f"raster too small: {record['number']} {width}x{height}")
        svg_digest = sha256(svg_path)
        png_digest = sha256(png_path)
        if svg_digest in svg_hashes or png_digest in png_hashes:
            raise ValueError(f"duplicate figure payload: {record['number']}")
        svg_hashes.add(svg_digest)
        png_hashes.add(png_digest)
        report.append(
            f"{record['number']} {width}x{height} "
            f"svg={svg_digest[:12]} png={png_digest[:12]}"
        )

    return report


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: validate_textbook_figures.py MANIFEST.json", file=sys.stderr)
        return 2
    try:
        report = validate(Path(sys.argv[1]))
    except Exception as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 1
    for line in report:
        print(line)
    print("PASS figures=12 svg=12 png=12")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
