"""Focused contracts for the theory enrichment of Chapters 7-13."""

from __future__ import annotations

import json
import re
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest


ROOT = Path(__file__).resolve().parents[2]
REVISION = ROOT / "third-edition-work" / "revision"
FRAGMENTS = REVISION / "fragments"


NEW_SECTIONS = {
    7: "7.3 镜像生命周期与任务处理",
    8: "8.3 调度候选与并发控制",
    9: "9.3 调度重试与实例状态",
    10: "10.3 端口绑定与网络状态同步",
    11: "11.3 卷调度、连接与状态变化",
    12: "12.3 副本一致性与后台维护",
    13: "13.3 请求处理与权限控制",
}

MIN_THEORY_CHARS = {7: 8500, 8: 9000, 9: 5900, 10: 5900, 11: 4700, 12: 4600, 13: 4300}


def chapter(number: int) -> str:
    return (FRAGMENTS / f"ch{number:02d}.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("number", range(7, 14))
def test_each_chapter_has_a_substantial_new_theory_section(number: int) -> None:
    text = chapter(number)
    heading = f"## {NEW_SECTIONS[number]}"
    practicum = f"## {number}.4 实训项目"
    assert heading in text
    assert practicum in text
    theory = text[: text.index(practicum)]
    compact = re.sub(r"\s+", "", theory)
    assert len(compact) >= MIN_THEORY_CHARS[number]
    assert re.search(rf"(?m)^图{number}\.3表示", theory)
    assert f"{{{{FIGURE:图{number}.3}}}}" in theory
    assert re.search(rf"(?m)^表{number}-3", theory)
    assert f"{{{{TABLE:表{number}-3}}}}" in theory


@pytest.mark.parametrize("number", range(7, 14))
def test_new_logic_diagram_has_decision_branch_and_loop(number: int) -> None:
    path = REVISION / "figures" / f"ch{number}" / f"图{number}.3.svg"
    root = ET.parse(path).getroot()
    serialized = ET.tostring(root, encoding="unicode")
    assert 'class="decision"' in serialized
    assert 'class="feedback-loop"' in serialized
    assert "是" in serialized and "否" in serialized
    assert "SimSun" in serialized and "Times New Roman" in serialized
    assert 'font-size="36"' in serialized or 'font-size:36px' in serialized


@pytest.mark.parametrize("number", range(7, 14))
def test_manifests_are_extended_in_chapter_order(number: int) -> None:
    figures = json.loads(
        (REVISION / "figures" / f"ch{number:02d}-figure-manifest.json").read_text(
            encoding="utf-8"
        )
    )
    tables = json.loads(
        (REVISION / "tables" / f"ch{number:02d}-table-manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert [row["number"] for row in figures] == [
        f"图{number}.1",
        f"图{number}.2",
        f"图{number}.3",
    ]
    assert [row["number"] for row in tables] == [
        f"表{number}-1",
        f"表{number}-2",
        f"表{number}-3",
    ]


def test_course_ideology_is_integrated_without_classroom_tasks() -> None:
    assert "开放协作与自主创新" in chapter(8)
    assert "工程责任与安全边界" in chapter(10)
    assert "最小权限与职业伦理" in chapter(13)
    all_text = "\n".join(chapter(n) for n in range(7, 14))
    for forbidden in ("教学活动", "小组讨论", "课堂任务", "复习思考", "教学云"):
        assert forbidden not in all_text


def test_research_register_uses_traceable_sources() -> None:
    register = json.loads(
        (REVISION / "research" / "ch07-13-sources-20260815.json").read_text(
            encoding="utf-8"
        )
    )
    components = {row["component"] for row in register["sources"]}
    assert components == {"Glance", "Placement", "Nova", "Neutron", "Cinder", "Swift", "Horizon"}
    for row in register["sources"]:
        assert row["url"].startswith("https://")
        assert row["title"]
        assert row["supports"]


@pytest.mark.parametrize("number", range(7, 14))
def test_new_figure_is_cited_before_and_explained_after(number: int) -> None:
    text = chapter(number)
    marker = f"{{{{FIGURE:图{number}.3}}}}"
    before, after = text.split(marker, maxsplit=1)
    assert f"图{number}.3表示" in before[-500:]
    assert f"图{number}.3" in after[:700]
