from __future__ import annotations

import argparse
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


FIGURE = re.compile(r"图(\d+)\.(\d+)")
CAPTION = re.compile(r"\*\*(图\d+\.\d+)\s+(.+?)\*\*")
PROPOSED = re.compile(r"\[(?:绘图建议|绘图待制作|截图待采集)：?(图\d+\.\d+)\s+([^]]+)]")


def font(size: int) -> ImageFont.FreeTypeFont:
    for path in (Path(r"C:\Windows\Fonts\msyh.ttc"), Path(r"C:\Windows\Fonts\simhei.ttf")):
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def wrap(draw: ImageDraw.ImageDraw, text: str, width: int, text_font) -> list[str]:
    lines: list[str] = []
    current = ""
    for char in text:
        candidate = current + char
        if draw.textbbox((0, 0), candidate, font=text_font)[2] > width and current:
            lines.append(current)
            current = char
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def create(path: Path, number: str, caption: str) -> None:
    image = Image.new("RGB", (1920, 1080), "#F7F9FC")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 1920, 120), fill="#17365D")
    draw.text((70, 33), f"{number}  {caption}", font=font(38), fill="white")
    draw.rounded_rectangle((180, 230, 1740, 840), radius=36, outline="#7F8FA6", width=5, fill="white")
    label_font = font(62)
    label = "截图待采集"
    box = draw.textbbox((0, 0), label, font=label_font)
    draw.text(((1920 - (box[2] - box[0])) / 2, 430), label, font=label_font, fill="#A6A6A6")
    detail = "正式拍摄时保持1920×1080或更高分辨率；隐藏API Key、密码、Token、Cookie、邮箱和个人信息。"
    detail_font = font(28)
    y = 590
    for line in wrap(draw, detail, 1250, detail_font):
        box = draw.textbbox((0, 0), line, font=detail_font)
        draw.text(((1920 - (box[2] - box[0])) / 2, y), line, font=detail_font, fill="#666666")
        y += 48
    draw.text((70, 1018), "第三版初稿安全占位图——不得作为真实运行证据", font=font(22), fill="#C00000")
    image.save(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("figure_root", type=Path)
    parser.add_argument("chapters", nargs="+", type=Path)
    args = parser.parse_args()
    args.figure_root.mkdir(parents=True, exist_ok=True)
    count = 0
    for chapter in args.chapters:
        for line in chapter.read_text(encoding="utf-8-sig").splitlines():
            match = CAPTION.search(line.strip()) or PROPOSED.search(line.strip())
            if not match:
                continue
            target = args.figure_root / f"{match.group(1)}.png"
            if not target.exists():
                create(target, match.group(1), match.group(2))
                count += 1
    print(f"CREATED={count}")


if __name__ == "__main__":
    main()
