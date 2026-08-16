"""Render real terminal text as a white-background textbook PNG."""

from __future__ import annotations

from pathlib import Path
import textwrap

from PIL import Image, ImageDraw, ImageFont


def _font(candidates: tuple[Path, ...], size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in candidates:
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default(size=size)


def _wrapped_lines(value: str, width: int = 100) -> list[str]:
    lines: list[str] = []
    for raw in value.splitlines() or [""]:
        lines.extend(textwrap.wrap(raw, width=width, replace_whitespace=False) or [""])
    return lines


def render_terminal_capture(
    *,
    title: str,
    command: str,
    output: str,
    destination: Path,
) -> None:
    """Render command and unchanged captured output to a high-resolution PNG."""

    if not title.strip() or not command.strip():
        raise ValueError("title and command must be non-empty")
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    title_font = _font(
        (Path(r"C:\Windows\Fonts\simsun.ttc"), Path(r"C:\Windows\Fonts\msyh.ttc")),
        34,
    )
    text_font = _font(
        (Path(r"C:\Windows\Fonts\consola.ttf"), Path(r"C:\Windows\Fonts\simsun.ttc")),
        28,
    )
    lines = [command, *_wrapped_lines(output)]
    line_height = 40
    width = 1600
    height = max(360, 105 + line_height * len(lines) + 55)
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((1, 1, width - 2, height - 2), outline=(185, 185, 185), width=3)
    draw.text((48, 28), title, fill=(20, 20, 20), font=title_font)
    draw.line((48, 78, width - 48, 78), fill=(210, 210, 210), width=2)
    y = 100
    for index, line in enumerate(lines):
        fill = (15, 65, 125) if index == 0 else (25, 25, 25)
        draw.text((48, y), line, fill=fill, font=text_font)
        y += line_height
    image.save(destination, format="PNG", optimize=True, dpi=(220, 220))

