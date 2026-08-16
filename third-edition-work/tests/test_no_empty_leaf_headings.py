"""Cross-chapter checks for leaf headings that have no textbook narration."""

from __future__ import annotations

import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
FRAGMENTS = ROOT / "third-edition-work" / "revision" / "fragments"
LEAF_HEADING = re.compile(r"^\d+．[^\n]+$")
ANY_HEADING = re.compile(
    r"^(?:#{1,2}\s+|[一二三四五六七八九十百]+[．、]|\d+[．、])"
)


def _outside_fences(lines: list[str]) -> list[tuple[int, str]]:
    result: list[tuple[int, str]] = []
    in_fence = False
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            result.append((index, stripped))
    return result


def _narrative_length(lines: list[str]) -> int:
    narrative: list[str] = []
    for _, line in _outside_fences(lines):
        if not line or line.startswith(("{{FIGURE:", "{{TABLE:", "|")):
            continue
        if re.fullmatch(r"[-: |]+", line):
            continue
        narrative.append(line)
    return len(re.sub(r"\s+", "", "".join(narrative)))


@pytest.mark.parametrize("chapter", range(1, 14))
def test_every_leaf_heading_has_explanatory_narration(chapter: int) -> None:
    path = FRAGMENTS / f"ch{chapter:02d}.md"
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    visible = _outside_fences(lines)
    failures: list[str] = []

    for position, (line_index, title) in enumerate(visible):
        if not LEAF_HEADING.fullmatch(title) or title.endswith(("。", "；", ";")):
            continue
        end_index = len(lines)
        for next_index, next_line in visible[position + 1 :]:
            if ANY_HEADING.match(next_line):
                end_index = next_index
                break
        if _narrative_length(lines[line_index + 1 : end_index]) < 20:
            failures.append(f"line {line_index + 1}: {title}")

    assert not failures, "leaf headings without narration: " + "; ".join(failures)
