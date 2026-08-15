"""Textbook contracts for the manual Nova-through-Horizon deployment chapters."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
REVISION = ROOT / "third-edition-work" / "revision"
FRAGMENTS = REVISION / "fragments"


def chapter(number: int) -> str:
    return (FRAGMENTS / f"ch{number:02d}.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("number", range(9, 14))
def test_deployment_chapters_keep_textbook_hierarchy(number: int) -> None:
    text = chapter(number)
    assert len(re.findall(r"(?m)^# ", text)) == 1
    assert len(re.findall(r"(?m)^## ", text)) >= 3
    assert not re.search(r"(?m)^### ", text)
    assert re.search(r"(?m)^一．\S", text)
    assert re.search(r"(?m)^二．\S", text)
    assert re.search(r"(?m)^1．\S", text)
    assert re.search(r"(?m)^2．\S", text)


@pytest.mark.parametrize("number", range(9, 14))
def test_practicum_goals_have_four_numbered_items(number: int) -> None:
    text = chapter(number)
    match = re.search(
        r"(?ms)^[一二三四五六七八九十]+．实训目标\s*(.+?)(?=^[一二三四五六七八九十]+．)",
        text,
    )
    assert match
    assert re.findall(r"(?m)^(\d+)．", match.group(1))[:4] == ["1", "2", "3", "4"]


@pytest.mark.parametrize("number", range(9, 14))
def test_deployment_is_manual_and_uses_only_the_local_repository(number: int) -> None:
    text = chapter(number)
    lowered = text.lower()
    for forbidden in (
        "```python",
        "python ",
        "python3",
        "paramiko",
        "pytest",
        "--enablerepo",
        "--disablerepo",
        "repo.openeuler.org",
        "openstack-release-antelope",
        "教学云",
        "教学活动",
        "复习思考",
        "部署门禁",
        "验收报告",
    ):
        assert forbidden not in lowered
    assert "vi /" in text
    assert "dnf -y install" in text
    assert "systemctl start" in text or number == 13


@pytest.mark.parametrize("number", range(9, 14))
def test_linux_commands_have_prompts(number: int) -> None:
    text = chapter(number)
    command_words = re.compile(
        r"^(?:dnf|vi|mysql|source|openstack|systemctl|su|nova-manage|neutron-db-manage|"
        r"pvcreate|vgcreate|wipefs|blkid|lsblk|findmnt|pvs|read|test|mkfs|mkdir|mount|"
        r"chown|chmod|scp|swift-ring-builder|cd)\b"
    )
    in_fence = False
    executable_fence = False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("```"):
            if not in_fence:
                in_fence = True
                executable_fence = line in {"```text", "```command"}
            else:
                in_fence = False
                executable_fence = False
            continue
        if in_fence and executable_fence and command_words.match(line):
            raise AssertionError(f"chapter {number} command lacks prompt: {line}")


@pytest.mark.parametrize("number", range(9, 14))
def test_figures_and_tables_are_cited_and_numbered(number: int) -> None:
    text = chapter(number)
    for index in (1, 2):
        figure = f"图{number}.{index}"
        table = f"表{number}-{index}"
        assert text.count(figure) >= 2
        assert f"{{{{FIGURE:{figure}}}}}" in text
        assert text.count(table) >= 2
        assert f"{{{{TABLE:{table}}}}}" in text
    figures = json.loads(
        (REVISION / "figures" / f"ch{number:02d}-figure-manifest.json").read_text(encoding="utf-8")
    )
    tables = json.loads(
        (REVISION / "tables" / f"ch{number:02d}-table-manifest.json").read_text(encoding="utf-8")
    )
    assert [row["number"] for row in figures] == [f"图{number}.1", f"图{number}.2"]
    assert [row["number"] for row in tables] == [f"表{number}-1", f"表{number}-2"]


def test_fixed_lab_parameters_are_consistent() -> None:
    text = "\n".join(chapter(number) for number in range(9, 14))
    assert "192.168.234.151" in text
    assert "192.168.234.150" in text
    assert "/dev/sdb" in chapter(11)
    assert "/dev/sdc" in chapter(12)
    assert "qwer1234" in text
    for forbidden in ("guosai@205", "ADMIN_PASS", "SERVICE_PASS", "RABBIT_PASS"):
        assert forbidden not in text


def test_service_order_and_manual_database_steps_are_present() -> None:
    nova = chapter(9)
    assert nova.index("nova-manage api_db sync") < nova.index("nova-manage cell_v2 map_cell0")
    assert nova.index("nova-manage cell_v2 create_cell") < nova.index("nova-manage db sync")
    neutron = chapter(10)
    assert "neutron-db-manage --config-file /etc/neutron/neutron.conf" in neutron
    cinder = chapter(11)
    assert "cinder-manage db sync" in cinder
    assert cinder.index("systemctl start targetclid") < cinder.index("systemctl start openstack-cinder-volume")
    swift = chapter(12)
    assert swift.index("swift-ring-builder account.builder create") < swift.index("swift-ring-builder account.builder rebalance")
    horizon = chapter(13)
    assert horizon.index("openstack project create") < horizon.index("openstack server create")
