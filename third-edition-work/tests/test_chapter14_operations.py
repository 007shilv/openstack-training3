"""Contracts for the new Chapter 14 OpenStack operations chapter."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import zipfile

import pytest


WORK_ROOT = Path(__file__).resolve().parents[1]
REVISION_TOOL = WORK_ROOT / "tools" / "revise_second_edition.py"
CAPTURE_TOOL = WORK_ROOT / "tools" / "capture_ch14_operations.py"
RENDER_TOOL = WORK_ROOT / "tools" / "render_terminal_capture.py"
HORIZON_TOOL = WORK_ROOT / "tools" / "capture_ch14_horizon.py"
CH14_FRAGMENT = WORK_ROOT / "revision" / "fragments" / "ch14.md"
CH14_FIGURES = WORK_ROOT / "revision" / "figures" / "ch14-figure-manifest.json"
CH14_TABLES = WORK_ROOT / "revision" / "tables" / "ch14-table-manifest.json"


def load_revision_tool():
    spec = importlib.util.spec_from_file_location("chapter14_revision_tool", REVISION_TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_tool(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def paragraph(text: str, style: str | None = None) -> str:
    style_xml = f'<w:pStyle w:val="{style}"/>' if style else ""
    return (
        f"<w:p><w:pPr>{style_xml}</w:pPr>"
        f"<w:r><w:t>{text}</w:t></w:r></w:p>"
    )


def write_fixture(path: Path, *, duplicate: bool = False) -> None:
    chapter14 = (
        paragraph("第十四章 虚拟机镜像文件的制作", "1")
        + paragraph("14.1 镜像制作基础", "2")
        + paragraph("镜像制作流程如图14.1所示，参数见表14-1。")
        + paragraph("图14.1 镜像制作流程")
        + paragraph("表14-1 镜像格式")
    )
    if duplicate:
        chapter14 += paragraph("第十四章 虚拟机镜像文件的制作", "1")
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>"
        + paragraph("第十三章 Horizon的安装及云平台初始化", "1")
        + paragraph("图13.1 Horizon访问过程")
        + chapter14
        + '<w:sectPr><w:pgSz w:w="10432" w:h="14740"/></w:sectPr>'
        + "</w:body></w:document>"
    ).encode("utf-8")
    styles = (
        '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:style w:type="paragraph" w:styleId="1"><w:name w:val="heading 1"/>'
        '<w:pPr><w:outlineLvl w:val="0"/></w:pPr></w:style>'
        '<w:style w:type="paragraph" w:styleId="2"><w:name w:val="heading 2"/>'
        '<w:pPr><w:outlineLvl w:val="1"/></w:pPr></w:style></w:styles>'
    ).encode("utf-8")
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", b"<Types/>")
        archive.writestr("word/document.xml", document)
        archive.writestr("word/styles.xml", styles)
        archive.writestr("word/footer1.xml", b"<footer>unchanged</footer>")


def visible_text(module, document) -> list[str]:
    _, children, _ = module._body_parts(document.document_xml)
    return [module._child_text(document.document_xml, child) for child in children]


def test_renumber_chapter_changes_only_bounded_chapter(tmp_path: Path) -> None:
    module = load_revision_tool()
    source = tmp_path / "source.docx"
    write_fixture(source)
    document = module.load_docx(source)
    unchanged = {
        name: payload
        for name, payload in document.payloads.items()
        if name != "word/document.xml"
    }

    module.renumber_chapter(
        document,
        "第十四章 虚拟机镜像文件的制作",
        14,
        15,
    )

    text = visible_text(module, document)
    assert "第十三章 Horizon的安装及云平台初始化" in text
    assert "图13.1 Horizon访问过程" in text
    assert "第十五章 虚拟机镜像文件的制作" in text
    assert "15.1 镜像制作基础" in text
    assert "镜像制作流程如图15.1所示，参数见表15-1。" in text
    assert "图15.1 镜像制作流程" in text
    assert "表15-1 镜像格式" in text
    assert not any("第十四章 虚拟机镜像文件的制作" in value for value in text)
    assert unchanged == {
        name: payload
        for name, payload in document.payloads.items()
        if name != "word/document.xml"
    }


@pytest.mark.parametrize("duplicate", [False, True])
def test_renumber_chapter_fails_closed_for_missing_or_duplicate_heading(
    tmp_path: Path, duplicate: bool
) -> None:
    module = load_revision_tool()
    source = tmp_path / "source.docx"
    write_fixture(source, duplicate=duplicate)
    document = module.load_docx(source)
    heading = (
        "第十四章 不存在的标题"
        if not duplicate
        else "第十四章 虚拟机镜像文件的制作"
    )

    with pytest.raises(ValueError, match="exactly one"):
        module.renumber_chapter(document, heading, 14, 15)


def test_revision_map_accepts_only_complete_renumber_operation(tmp_path: Path) -> None:
    module = load_revision_tool()
    valid = tmp_path / "valid.json"
    valid.write_text(
        '[{"op":"renumber_chapter","heading":"第十四章 虚拟机镜像文件的制作",'
        '"old_number":"14","new_number":"15"}]',
        encoding="utf-8",
    )
    assert module.load_revision_map(valid)[0]["op"] == "renumber_chapter"

    invalid = tmp_path / "invalid.json"
    invalid.write_text(
        '[{"op":"renumber_chapter","heading":"第十四章 虚拟机镜像文件的制作",'
        '"old_number":"14"}]',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="missing fields"):
        module.load_revision_map(invalid)


@pytest.mark.parametrize(
    "unsafe",
    [
        "OS_PASSWORD=qwer1234",
        "X-Auth-Token: secret-token",
        "Cookie: sessionid=secret",
        "-----BEGIN PRIVATE KEY-----",
        "mysql+pymysql://user:password@controller/db",
    ],
)
def test_sanitize_output_rejects_secret_bearing_text(unsafe: str) -> None:
    module = load_tool(CAPTURE_TOOL, "chapter14_capture_tool")
    with pytest.raises(ValueError, match="sensitive"):
        module.sanitize_output(unsafe)


def test_sanitize_output_preserves_normal_openstack_table() -> None:
    module = load_tool(CAPTURE_TOOL, "chapter14_capture_tool")
    text = "+----+---------+\n| ID | Name    |\n+----+---------+\n| 01 | bookops |"
    assert module.sanitize_output(text) == text


def test_capture_source_uses_reviewed_host_keys_and_reject_policy() -> None:
    source = CAPTURE_TOOL.read_text(encoding="utf-8")
    assert "load_host_keys" in source
    assert "RejectPolicy" in source
    assert "AutoAddPolicy" not in source
    assert "ssh-keyscan" not in source
    assert "getpass" in source


def test_terminal_renderer_outputs_white_png_with_dark_text(tmp_path: Path) -> None:
    module = load_tool(RENDER_TOOL, "chapter14_terminal_renderer")
    output = tmp_path / "terminal.png"
    module.render_terminal_capture(
        title="查看项目",
        command="[root@controller ~]# openstack project list",
        output="+----+---------+\n| ID | Name    |\n+----+---------+\n| 01 | bookops |",
        destination=output,
    )
    from PIL import Image

    with Image.open(output) as image:
        assert image.format == "PNG"
        assert image.width >= 1000
        assert image.height >= 300
        assert image.getpixel((0, 0))[:3] == (255, 255, 255)
        pixels = (
            image.get_flattened_data()
            if hasattr(image, "get_flattened_data")
            else image.getdata()
        )
        dark_pixels = sum(
            1
            for red, green, blue, *_ in pixels
            if red < 80 and green < 80 and blue < 80
        )
        assert dark_pixels > 100


def test_horizon_capture_is_headless_isolated_and_secret_silent() -> None:
    source = HORIZON_TOOL.read_text(encoding="utf-8")
    assert "headless=True" in source
    assert "browser.new_context" in source
    assert "context.close()" in source
    assert "browser.close()" in source
    assert "getpass" in source
    assert "launch_persistent_context" not in source
    assert "print(password" not in source
    assert "storage_state" not in source


def test_horizon_capture_has_expected_dashboard_targets() -> None:
    source = HORIZON_TOOL.read_text(encoding="utf-8")
    for required in (
        "dashboard-login.png",
        "dashboard-project.png",
        "dashboard-images.png",
        "dashboard-instances.png",
        "dashboard-networks.png",
        "dashboard-volumes.png",
    ):
        assert required in source


def test_chapter14_manuscript_structure_and_scope() -> None:
    text = CH14_FRAGMENT.read_text(encoding="utf-8")
    assert text.count("# 第十四章 OpenStack云平台各组件运维") == 1
    expected = [
        "14.1 Keystone身份与权限运维",
        "14.2 Glance镜像运维",
        "14.3 Placement资源信息运维",
        "14.4 Nova实例、规格与配额运维",
        "14.5 Neutron网络运维",
        "14.6 Cinder卷与快照运维",
        "14.7 Swift容器与对象运维",
        "14.8 Horizon图形化运维",
    ]
    assert [line[3:] for line in text.splitlines() if line.startswith("## ")] == expected
    for forbidden in (
        "教学活动",
        "复习思考",
        "作者建议",
        "不宜把",
        "教学云",
        "Python",
        "脚本",
    ):
        assert forbidden not in text
    assert "第十五章" not in text


def test_chapter14_commands_are_manual_and_prompted() -> None:
    text = CH14_FRAGMENT.read_text(encoding="utf-8")
    blocks = text.split("```command\n")[1:]
    assert len(blocks) >= 24
    for block in blocks:
        payload = block.split("```", 1)[0].strip().splitlines()
        assert payload
        for line in payload:
            if line.startswith(("export ", "OS_", "[", "name=", "auth_")):
                continue
            assert line.startswith(("[root@controller ~]#", "[root@compute ~]#", "MariaDB")), line
    assert "qwer1234" in text


def test_chapter14_figures_and_tables_are_complete_and_referenced() -> None:
    import json

    text = CH14_FRAGMENT.read_text(encoding="utf-8")
    figures = json.loads(CH14_FIGURES.read_text(encoding="utf-8"))
    tables = json.loads(CH14_TABLES.read_text(encoding="utf-8"))
    assert [row["number"] for row in figures] == [f"图14.{n}" for n in range(1, 25)]
    assert [row["number"] for row in tables] == [f"表14-{n}" for n in range(1, 9)]
    for row in figures:
        marker = "{{FIGURE:" + row["number"] + "}}"
        assert text.count(marker) == 1
        before, after = text.split(marker, 1)
        assert row["number"] in before[-500:]
        assert len(after.strip()) >= 80
        image_path = WORK_ROOT / "revision" / row["png"]
        assert image_path.is_file()
    for row in tables:
        marker = "{{TABLE:" + row["number"] + "}}"
        assert text.count(marker) == 1
        before, after = text.split(marker, 1)
        assert row["number"] in before[-500:]
        assert len(after.strip()) >= 80
