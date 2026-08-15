"""Textbook contracts for the chapter 4-8 narrative revision."""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest


ROOT = Path(__file__).resolve().parents[2]
FRAGMENTS = ROOT / "third-edition-work" / "revision" / "fragments"
REVISION_ROOT = ROOT / "third-edition-work" / "revision"
BOOK_BUILDER = ROOT / "third-edition-work" / "tools" / "build_chapters_1_8_review_docx.py"


def chapter(number: int) -> str:
    return (FRAGMENTS / f"ch{number:02d}.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("number", range(4, 9))
def test_chapter_uses_two_inner_textbook_levels(number: int) -> None:
    text = chapter(number)
    assert re.search(r"(?m)^一．\S", text)
    assert re.search(r"(?m)^二．\S", text)
    assert re.search(r"(?m)^1．\S", text)
    assert re.search(r"(?m)^2．\S", text)
    assert not re.search(r"(?m)^### ", text)


@pytest.mark.parametrize("number", range(4, 9))
def test_chapter_avoids_editorial_and_classroom_language(number: int) -> None:
    text = chapter(number)
    forbidden = (
        "教学云",
        "教学活动",
        "不宜把",
        "产品名称还原",
        "学生应当",
        "课堂环境",
        "课堂口令",
        "教学环境",
        "复习思考",
        "思考题",
        "审计报告",
        "部署门禁",
    )
    for term in forbidden:
        assert term not in text


@pytest.mark.parametrize("number", range(4, 9))
def test_practicum_goals_are_numbered_and_manual(number: int) -> None:
    text = chapter(number)
    goal_match = re.search(
        r"(?ms)^三．实训目标\s*(.+?)(?=^四．实训步骤及其详解)", text
    )
    assert goal_match, f"chapter {number} must retain the second-edition practicum frame"
    goals = re.findall(r"(?m)^(\d+)．\S.+$", goal_match.group(1))
    assert goals[:4] == ["1", "2", "3", "4"]
    assert "vi /" in text
    assert "```python" not in text
    assert "paramiko" not in text.lower()
    assert "pytest" not in text.lower()


@pytest.mark.parametrize("number", range(4, 9))
def test_all_linux_command_lines_keep_a_system_prompt(number: int) -> None:
    text = chapter(number)
    blocks = re.findall(r"```command\s*\n(.*?)```", text, flags=re.DOTALL)
    assert blocks
    for block in blocks:
        for line in block.splitlines():
            if line.strip():
                assert re.match(
                    r"^(?:\[root@(controller|compute) [^\]]+\]#|MariaDB \[[^\]]+\]>|\s+->) ",
                    line,
                ), f"chapter {number}: command lacks a real prompt: {line}"


def test_chapter4_has_topology_tables_and_exact_environment_roles() -> None:
    text = chapter(4)
    for number in range(1, 5):
        figure = f"图4.{number}"
        table = f"表4-{number}"
        assert text.count(figure) >= 2
        assert f"{{{{FIGURE:{figure}}}}}" in text
        assert text.count(table) >= 2
        assert f"{{{{TABLE:{table}}}}}" in text
    for term in (
        "192.168.234.151",
        "192.168.234.150",
        "ens33",
        "ens34",
        "/dev/sdb",
        "/dev/sdc",
        "50 GiB",
        "openEuler 24.03 LTS SP3",
        "2023.1 Antelope",
    ):
        assert term in text


@pytest.mark.parametrize("number", range(5, 9))
def test_service_chapters_have_explanatory_figures_and_tables(number: int) -> None:
    text = chapter(number)
    for index in range(1, 3):
        figure = f"图{number}.{index}"
        table = f"表{number}-{index}"
        assert text.count(figure) >= 2
        assert f"{{{{FIGURE:{figure}}}}}" in text
        assert text.count(table) >= 2
        assert f"{{{{TABLE:{table}}}}}" in text


@pytest.mark.parametrize("number", range(4, 9))
def test_experiment_password_is_consistent(number: int) -> None:
    text = chapter(number)
    assert "qwer1234" in text
    for forbidden in ("guosai@205", "ADMIN_PASS", "SERVICE_PASS", "RABBIT_PASS"):
        assert forbidden not in text


def test_chapters_1_8_revision_map_is_complete_and_bounded() -> None:
    operations = json.loads(
        (REVISION_ROOT / "revision-map-ch01-08.json").read_text(encoding="utf-8")
    )
    assert len(operations) == 8
    assert [row["fragment"] for row in operations] == [
        f"fragments/ch{number:02d}.md" for number in range(1, 9)
    ]
    assert operations[0]["start_heading"] == "第一章 云计算基本概念"
    assert operations[-1]["end_heading"] == "第九章 Nova的安装及其配置"
    assert all(row["op"] == "replace" for row in operations)


def test_chapters_1_8_word_builder_normalizes_table_schemas() -> None:
    spec = importlib.util.spec_from_file_location("build_chapters_1_8_review_docx", BOOK_BUILDER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    normalized = module.normalize_table_record(
        {
            "number": "表4-1",
            "title": "示例",
            "headers": ["节点", "地址"],
            "rows": [["controller", "192.168.234.151"]],
        }
    )
    assert normalized["columns"] == ["节点", "地址"]
    assert normalized["font_pt"] == 9.0
    assert round(sum(normalized["column_widths_cm"]), 1) == 14.5


@pytest.mark.parametrize("number", range(4, 9))
def test_chapter_diagram_text_is_at_least_nine_points_when_printed(number: int) -> None:
    manifest = json.loads(
        (REVISION_ROOT / "figures" / f"ch{number:02d}-figure-manifest.json").read_text(
            encoding="utf-8"
        )
    )
    for record in manifest:
        svg_path = REVISION_ROOT / record["svg"]
        payload = svg_path.read_text(encoding="utf-8")
        root = ET.fromstring(payload)
        view_box_width = float(root.attrib["viewBox"].split()[2])
        sizes = [float(value) for value in re.findall(r"font-size:(\d+(?:\.\d+)?)px", payload)]
        assert sizes
        rendered_width_pt = float(record["width_cm"]) * 72 / 2.54
        assert min(sizes) * rendered_width_pt / view_box_width >= 9.0
