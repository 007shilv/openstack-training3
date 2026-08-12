from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path


FIGURE = re.compile(r"图(\d+)\.(\d+)")
CAPTION = re.compile(r"\*\*(图\d+\.\d+)\s+(.+?)\*\*")
PROPOSED = re.compile(r"\[(?:绘图建议|绘图待制作|截图待采集)：?(图\d+\.\d+)\s+([^]]+)]")


def caption_candidates(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        match = CAPTION.search(line.strip()) or PROPOSED.search(line.strip())
        if match:
            values.setdefault(match.group(1), match.group(2).strip())
    return values


def key(number: str) -> tuple[int, int]:
    match = FIGURE.fullmatch(number)
    if not match:
        return (999, 999)
    return int(match.group(1)), int(match.group(2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("registry", type=Path)
    parser.add_argument("figure_root", type=Path)
    parser.add_argument("chapters", nargs="+", type=Path)
    args = parser.parse_args()

    existing: dict[str, dict[str, str]] = {}
    if args.registry.exists():
        with args.registry.open(encoding="utf-8-sig", newline="") as stream:
            existing = {row["figure_no"]: row for row in csv.DictReader(stream)}

    captions: dict[str, str] = {}
    for chapter in args.chapters:
        captions.update(caption_candidates(chapter))

    numbers = set(captions) | {path.stem for path in args.figure_root.glob("图*.png")}
    rows: list[dict[str, str]] = []
    for number in sorted(numbers, key=key):
        chapter, _ = key(number)
        old = existing.get(number, {})
        image_path = args.figure_root / f"{number}.png"
        status = old.get("status", "")
        if image_path.exists() and not status:
            status = "placeholder-needs-capture" if chapter in {12, 13} else "draft-redraw"
        rows.append(
            {
                "figure_no": number,
                "chapter": str(chapter),
                "caption": captions.get(number, old.get("caption", "待按正文复核")),
                "type": old.get("type", "real-screenshot" if chapter in {12, 13} else "redraw"),
                "source_url": old.get("source_url", ""),
                "access_date": old.get("access_date", "2026-08-12"),
                "local_path": f"第三版教材图片/{number}.png",
                "status": status or "pending-capture",
            }
        )

    args.registry.parent.mkdir(parents=True, exist_ok=True)
    with args.registry.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=("figure_no", "chapter", "caption", "type", "source_url", "access_date", "local_path", "status"),
        )
        writer.writeheader()
        writer.writerows(rows)
    print(f"REGISTERED={len(rows)}")


if __name__ == "__main__":
    main()
