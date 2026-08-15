"""Textbook contracts for the chapter 4-8 narrative revision."""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
from PIL import Image, ImageChops


ROOT = Path(__file__).resolve().parents[2]
FRAGMENTS = ROOT / "third-edition-work" / "revision" / "fragments"
REVISION_ROOT = ROOT / "third-edition-work" / "revision"
BOOK_BUILDER = ROOT / "third-edition-work" / "tools" / "build_chapters_1_8_review_docx.py"
REVISION_TOOL = ROOT / "third-edition-work" / "tools" / "revise_second_edition.py"


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
                    r"^(?:\[root@(controller|compute) [^\]]+\]#|MariaDB \[[^\]]+\]>|\s+->|PS [^>]+>) ",
                    line,
                ), f"chapter {number}: command lacks a real prompt: {line}"


def test_chapter4_has_topology_tables_and_exact_environment_roles() -> None:
    text = chapter(4)
    for number in range(1, 4):
        figure = f"图4.{number}"
        assert text.count(figure) >= 2
        assert f"{{{{FIGURE:{figure}}}}}" in text
    assert "图4.4" not in text
    for number in range(1, 5):
        table = f"表4-{number}"
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


def test_chapter4_merges_topology_and_component_distribution() -> None:
    text = chapter(4)
    topology = (REVISION_ROOT / "figures" / "ch4" / "图4.2.svg").read_text(
        encoding="utf-8"
    )
    for term in (
        "双节点环境拓扑与组件分布",
        "MariaDB",
        "Keystone",
        "Glance",
        "Placement",
        "Nova控制服务",
        "nova-compute",
        "Neutron代理",
        "Cinder",
        "Swift",
        "/dev/sdb",
        "/dev/sdc",
    ):
        assert term in topology
    assert text.index("组件运行位置") < text.index("双网卡与网络平面")


def test_local_repository_is_packaged_uploaded_and_used_without_repo_switches() -> None:
    text = chapter(4)
    for term in (
        "教材配套环境",
        "openstack_repo.zip",
        "scp .\\openstack_repo.zip",
        "unzip -q /root/openstack_repo.zip -d /opt",
        "/opt/openstack_repo/repodata/repomd.xml",
        "/etc/yum.repos.d/openEuler-remote-backup",
    ):
        assert term in text
    all_text = "\n".join(chapter(number) for number in range(4, 9))
    assert "--disablerepo" not in all_text
    assert "--enablerepo" not in all_text


def test_chapter4_uses_only_the_packaged_local_repository() -> None:
    text = chapter(4)
    for forbidden in (
        "openstack-release-antelope",
        "openstack-antelope.repo",
        "repo.openeuler.org",
        "OpenStack_Antelope",
        "OpenStack_Antelope_update",
        "步骤八：安装Antelope发行包并修正软件仓路径",
    ):
        assert forbidden not in text
    assert "enabled=1" in text
    assert "baseurl=file:///opt/openstack_repo" in text
    assert "baseurl=ftp://controller/openstack_repo" in text


def test_chapter4_tables_are_numbered_in_reading_order() -> None:
    text = chapter(4)
    markers = re.findall(r"\{\{TABLE:(表4-\d+)\}\}", text)
    assert markers == ["表4-1", "表4-2", "表4-3", "表4-4"]


def test_empty_concept_subsections_are_filled_and_environment_wording_is_used() -> None:
    text5 = chapter(5)
    message = re.search(
        r"(?ms)^2．openstack消息账户\s*(.+?)(?=^二．Memcached缓存服务)", text5
    )
    boundary = re.search(
        r"(?ms)^2．客户端与服务端的边界\s*(.+?)(?=^四．时间基础与服务依赖)",
        text5,
    )
    assert message and len(message.group(1).strip()) >= 120
    assert boundary and len(boundary.group(1).strip()) >= 120
    assert all("实验中" not in chapter(number) for number in range(4, 9))
    assert "Antelope环境中" in chapter(6)


def test_code_block_properties_remove_first_line_and_hanging_indents() -> None:
    spec = importlib.util.spec_from_file_location("revise_second_edition", REVISION_TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    properties = (
        b'<w:pPr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        b'<w:ind w:left="420" w:firstLine="420" w:hangingChars="200"/>'
        b'</w:pPr>'
    )
    normalized = module._code_block_properties(properties)
    assert b'w:left="420"' in normalized
    assert b"firstLine" not in normalized
    assert b"hanging" not in normalized


@pytest.mark.parametrize("chapter_dir", ["ch03", "ch4", "ch5", "ch6", "ch7", "ch8"])
def test_rendered_figure_content_fills_the_png_canvas(chapter_dir: str) -> None:
    directory = REVISION_ROOT / "figures" / chapter_dir
    for path in directory.glob("*.png"):
        image = Image.open(path).convert("RGB")
        background = Image.new("RGB", image.size, "white")
        bbox = ImageChops.difference(image, background).getbbox()
        assert bbox is not None
        content_width = bbox[2] - bbox[0]
        assert content_width / image.width >= 0.70, path


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


def test_chapters_1_13_revision_map_is_complete_and_bounded() -> None:
    operations = json.loads(
        (REVISION_ROOT / "revision-map-ch01-08.json").read_text(encoding="utf-8")
    )
    assert len(operations) == 13
    assert [row["fragment"] for row in operations] == [
        f"fragments/ch{number:02d}.md" for number in range(1, 14)
    ]
    assert operations[0]["start_heading"] == "第一章 云计算基本概念"
    assert operations[-1]["end_heading"] == "第十四章 虚拟机镜像文件的制作"
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


def _all_diagram_svg_paths() -> list[Path]:
    manifests = [REVISION_ROOT / "figures" / "ch01-02-figure-manifest.json"]
    manifests.extend(
        REVISION_ROOT / "figures" / f"ch{number:02d}-figure-manifest.json"
        for number in range(3, 14)
    )
    paths: list[Path] = []
    for manifest in manifests:
        for record in json.loads(manifest.read_text(encoding="utf-8")):
            if record.get("kind", "diagram") == "diagram" and record.get("svg"):
                paths.append(REVISION_ROOT / record["svg"])
    return paths


def _css_font_size(payload: str, node: ET.Element) -> float:
    direct = node.attrib.get("font-size")
    if direct:
        return float(direct.removesuffix("px"))
    class_name = node.attrib.get("class")
    if class_name:
        match = re.search(
            rf"\.{re.escape(class_name)}\s*\{{[^}}]*font-size:(\d+(?:\.\d+)?)px",
            payload,
        )
        if match:
            return float(match.group(1))
    match = re.search(r"text\s*\{[^}]*font-size:(\d+(?:\.\d+)?)px", payload)
    if match:
        return float(match.group(1))
    raise AssertionError(f"text has no resolvable font size: {ET.tostring(node)}")


def _estimated_text_width(text: str, font_size: float) -> float:
    units = 0.0
    for char in text:
        if "\u4e00" <= char <= "\u9fff":
            units += 1.0
        elif char.isspace():
            units += 0.35
        elif char.isascii() and (char.isalnum() or char in "_-/"):
            units += 0.58
        else:
            units += 0.55
    return units * font_size


def test_all_diagram_arrowheads_are_compact() -> None:
    ns = "{http://www.w3.org/2000/svg}"
    for path in _all_diagram_svg_paths():
        root = ET.fromstring(path.read_text(encoding="utf-8"))
        for marker in root.iter(f"{ns}marker"):
            assert float(marker.attrib["markerWidth"]) <= 9, path
            assert float(marker.attrib["markerHeight"]) <= 7, path


def test_all_diagram_text_fits_inside_its_smallest_containing_box() -> None:
    ns = "{http://www.w3.org/2000/svg}"
    for path in _all_diagram_svg_paths():
        payload = path.read_text(encoding="utf-8")
        root = ET.fromstring(payload)
        view_width = float(root.attrib["viewBox"].split()[2])
        view_height = float(root.attrib["viewBox"].split()[3])
        rectangles = []
        for rect in root.iter(f"{ns}rect"):
            x = float(rect.attrib.get("x", 0))
            y = float(rect.attrib.get("y", 0))
            width = float(rect.attrib.get("width", 0))
            height = float(rect.attrib.get("height", 0))
            if width >= view_width and height >= view_height:
                continue
            rectangles.append((x, y, width, height))
        for node in root.iter(f"{ns}text"):
            if "x" not in node.attrib or "y" not in node.attrib:
                continue
            text = "".join(node.itertext()).strip()
            if not text:
                continue
            x = float(node.attrib["x"])
            y = float(node.attrib["y"])
            containing = [
                rect
                for rect in rectangles
                if rect[0] <= x <= rect[0] + rect[2]
                and rect[1] <= y <= rect[1] + rect[3]
            ]
            if not containing:
                continue
            box = min(containing, key=lambda rect: rect[2] * rect[3])
            available = box[2] - 24
            estimated = _estimated_text_width(text, _css_font_size(payload, node))
            assert estimated <= available, f"{path.name}: {text!r} exceeds {box}"


def test_china_market_figure_uses_one_value_font_size() -> None:
    path = REVISION_ROOT / "figures" / "ch01" / "图1.8.svg"
    root = ET.fromstring(path.read_text(encoding="utf-8"))
    ns = "{http://www.w3.org/2000/svg}"
    value_sizes = {
        float(node.attrib["font-size"])
        for node in root.iter(f"{ns}text")
        if "亿元" in "".join(node.itertext())
    }
    assert len(value_sizes) == 1


def test_metadata_figure_boxes_are_proportional_to_their_content() -> None:
    path = REVISION_ROOT / "figures" / "ch5" / "图5.1.svg"
    root = ET.fromstring(path.read_text(encoding="utf-8"))
    ns = "{http://www.w3.org/2000/svg}"
    boxes = [
        node
        for node in root.iter(f"{ns}rect")
        if node.attrib.get("x") in {"80", "860"}
    ]
    assert len(boxes) == 2
    assert all(float(box.attrib["height"]) <= 360 for box in boxes)


def test_chapter2_separates_public_cloud_architecture_from_domestic_products() -> None:
    text = chapter(2)
    headings = [line for line in text.splitlines() if line.startswith("## ")]
    assert "## 2.3 公有云服务体系" in headings
    assert "## 2.4 国内公有云产品" in headings
    assert text.index("## 2.3 公有云服务体系") < text.index("{{FIGURE:图2.11}}")
    assert text.index("{{FIGURE:图2.11}}") < text.index("## 2.4 国内公有云产品")
    assert "三．EasyStack、ZStack与其他国产平台" not in text


def test_all_diagrams_use_song_for_chinese_and_times_for_latin() -> None:
    for path in _all_diagram_svg_paths():
        payload = path.read_text(encoding="utf-8")
        assert "Times New Roman" in payload, path
        assert "SimSun" in payload and "宋体" in payload, path


def test_glance_flow_uses_short_labels_that_fit_each_module() -> None:
    path = REVISION_ROOT / "figures" / "ch7" / "图7.2.svg"
    payload = path.read_text(encoding="utf-8")
    for forbidden in ("建库、用户、服务、端点", "glance-manage db_sync", "openstack-glance-api"):
        assert forbidden not in payload
    for expected in ("建库、授权", "服务、端点", "编辑配置", "同步数据库", "启用glance-api"):
        assert expected in payload


def test_generated_word_runs_use_song_and_times_fonts() -> None:
    spec = importlib.util.spec_from_file_location("revise_second_edition_fonts", REVISION_TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    payload = module._text_runs("OpenStack云平台")
    assert b'Times New Roman' in payload
    assert "宋体".encode("utf-8") in payload


def test_word_style_normalizer_uses_second_edition_fonts_and_heading_sizes() -> None:
    spec = importlib.util.spec_from_file_location("book_font_normalizer", BOOK_BUILDER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    xml = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
    <w:styles xmlns:w="{module.W_NS}">
      <w:docDefaults><w:rPrDefault><w:rPr/></w:rPrDefault></w:docDefaults>
      <w:style w:type="paragraph" w:styleId="1"><w:rPr/></w:style>
      <w:style w:type="paragraph" w:styleId="2"><w:rPr/></w:style>
      <w:style w:type="paragraph" w:styleId="Normal"><w:rPr/></w:style>
    </w:styles>'''.encode("utf-8")
    normalized = module._normalize_styles_xml(xml)
    assert b'Times New Roman' in normalized
    assert "宋体".encode("utf-8") in normalized
    root = ET.fromstring(normalized)
    ns = {"w": module.W_NS}
    h1 = root.find(".//w:style[@w:styleId='1']/w:rPr/w:sz", ns)
    h2 = root.find(".//w:style[@w:styleId='2']/w:rPr/w:sz", ns)
    assert h1 is not None and h1.get(f"{{{module.W_NS}}}val") == "44"
    assert h2 is not None and h2.get(f"{{{module.W_NS}}}val") == "32"


def test_word_builder_forces_each_chapter_to_start_on_a_new_page() -> None:
    payload = BOOK_BUILDER.read_text(encoding="utf-8")
    assert "if is_chapter_heading:" in payload
    assert 'properties.find(f"{W}pageBreakBefore")' in payload
    assert 'page_break.set(f"{W}val", "1")' in payload


def test_word_builder_applies_song_and_times_through_word_before_save() -> None:
    payload = BOOK_BUILDER.read_text(encoding="utf-8")
    save_position = payload.index("document.SaveAs2(")
    for statement in (
        'document.Content.Font.NameFarEast = "宋体"',
        'document.Content.Font.NameAscii = "Times New Roman"',
        'document.Content.Font.NameOther = "Times New Roman"',
    ):
        assert 0 <= payload.index(statement) < save_position
    assert "_rewrite_styles_in_place(output_docx)" in payload
