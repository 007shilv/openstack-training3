"""Validate Chapter 1–2 textbook diagrams and real-image assets."""

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
    expected_numbers = [
        *(f"图1.{index}" for index in range(1, 10)),
        *(f"图2.{index}" for index in range(1, 16)),
    ]
    if not isinstance(records, list) or [record.get("number") for record in records] != expected_numbers:
        raise ValueError("manifest must contain the ordered 24 chapter figures")

    revision_root = manifest_path.parent.parent
    svg_hashes: set[str] = set()
    png_hashes: set[str] = set()
    raw_hashes: set[str] = set()
    report: list[str] = []

    for record in records:
        png_path = revision_root / record["png"]
        if not png_path.is_file():
            raise FileNotFoundError(f"missing PNG: {record['number']}")

        kind = record.get("kind")
        svg_digest = None
        raw_digest = None
        if kind == "diagram":
            svg_path = revision_root / record["svg"]
            if not svg_path.is_file():
                raise FileNotFoundError(f"missing SVG: {record['number']}")
            svg_payload = svg_path.read_text(encoding="utf-8")
            root = ET.fromstring(svg_payload)
            view_box = [float(value) for value in root.attrib["viewBox"].split()]
            if len(view_box) != 4 or view_box[2] < 960 or view_box[3] < 560:
                raise ValueError(f"invalid viewBox: {record['number']}")
            if "SimSun" not in svg_payload or "宋体" not in svg_payload:
                raise ValueError(f"missing Song font fallback: {record['number']}")
            visible_text = "".join(node.text or "" for node in root.findall(".//{*}text"))
            for phrase in ("仅供参考", "不作为结论", "图中不", "使用时核对"):
                if phrase in visible_text:
                    raise ValueError(f"editorial phrase in diagram: {record['number']}")

            rendered_width_pt = float(record["width_cm"]) * 72 / 2.54
            text_nodes = root.findall(".//{*}text")
            if not text_nodes:
                raise ValueError(f"figure has no text: {record['number']}")
            for node in text_nodes:
                if "font-size" not in node.attrib:
                    raise ValueError(f"text without explicit size: {record['number']}")
                rendered_pt = (
                    float(node.attrib["font-size"]) * rendered_width_pt / view_box[2]
                )
                if rendered_pt + 0.01 < float(record["minimum_font_pt"]):
                    raise ValueError(
                        f"text too small: {record['number']} {rendered_pt:.2f}pt"
                    )
            svg_digest = sha256(svg_path)
            if svg_digest in svg_hashes:
                raise ValueError(f"duplicate SVG payload: {record['number']}")
            svg_hashes.add(svg_digest)
        elif kind in {"photo", "screenshot"}:
            raw_path = revision_root / record["raw"]
            if not raw_path.is_file():
                raise FileNotFoundError(f"missing raw image: {record['number']}")
            raw_digest = sha256(raw_path)
            if raw_digest in raw_hashes:
                raise ValueError(f"duplicate raw image: {record['number']}")
            raw_hashes.add(raw_digest)
        else:
            raise ValueError(f"unknown figure kind: {record['number']} {kind!r}")

        width, height = png_dimensions(png_path)
        required = (2400, 1400) if kind == "diagram" else (1600, 900)
        if width < required[0] or height < required[1]:
            raise ValueError(f"raster too small: {record['number']} {width}x{height}")
        png_digest = sha256(png_path)
        if png_digest in png_hashes:
            raise ValueError(f"duplicate PNG payload: {record['number']}")
        png_hashes.add(png_digest)
        source = (
            f"svg={svg_digest[:12]}" if svg_digest else f"raw={raw_digest[:12]}"
        )
        report.append(f"{record['number']} {width}x{height} {source} png={png_digest[:12]}")

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
    print("PASS figures=24 svg=12 png=24 raw=12")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
