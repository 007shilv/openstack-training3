import json
import importlib.util
import re
import struct
import tempfile
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[2]
CHAPTER = ROOT / "third-edition-work" / "revision" / "fragments" / "ch03.md"
SOURCES = (
    ROOT
    / "third-edition-work"
    / "revision"
    / "research"
    / "ch03-sources-20260815.json"
)
RESEARCH = (
    ROOT
    / "third-edition-work"
    / "revision"
    / "research"
    / "ch03-official-research-20260815.md"
)
FIGURE_MANIFEST = (
    ROOT
    / "third-edition-work"
    / "revision"
    / "figures"
    / "ch03-figure-manifest.json"
)
OPENXML_BUILDER = ROOT / "third-edition-work" / "tools" / "build_chapter3_openxml.py"


def chapter_text() -> str:
    return CHAPTER.read_text(encoding="utf-8")


def compact_text() -> str:
    return "".join(chapter_text().split())


def _paragraph_text_for_test(paragraph: ET.Element, namespace: str) -> str:
    return "".join(node.text or "" for node in paragraph.iter(f"{{{namespace}}}t"))


def test_chapter3_official_source_register_is_complete():
    data = json.loads(SOURCES.read_text(encoding="utf-8"))
    assert data["cutoff_date"] == "2026-07-31"
    assert len(data["sources"]) >= 12
    urls = {row["url"] for row in data["sources"]}
    assert "https://releases.openstack.org/" in urls
    assert "https://releases.openstack.org/gazpacho/index.html" in urls
    assert "https://releases.openstack.org/hibiscus/schedule.html" in urls
    assert "https://releases.openstack.org/antelope/index.html" in urls
    research = RESEARCH.read_text(encoding="utf-8")
    for term in ("Gazpacho", "Hibiscus", "Antelope", "SLURP", "逻辑架构"):
        assert term in research


def test_chapter3_has_approved_two_section_structure():
    text = chapter_text()
    assert text.count("## 3.1 OpenStack技术简介") == 1
    assert text.count("## 3.2 OpenStack生态体系") == 1
    assert "体验原生OpenStack云平台" not in text
    headings = re.findall(r"^## .+$", text, flags=re.MULTILINE)
    assert headings == ["## 3.1 OpenStack技术简介", "## 3.2 OpenStack生态体系"]


def test_chapter3_uses_textbook_levels_and_avoids_editorial_language():
    text = chapter_text()
    for heading in ("一．", "二．", "1．", "2．"):
        assert heading in text
    banned = (
        "教学活动",
        "不宜把",
        "编写规则",
        "产品名称还原",
        "学生应当",
        "本章写作",
        "研究口径",
        "使用提示",
        "只有同时说明这些维度",
        "把三条边界分开",
        "理解这一区分后",
        "新建生产云仍需",
    )
    for term in banned:
        assert term not in text
    assert not re.search(r"(?m)^注[：:]", text)
    assert "已经与openEuler 24.03 LTS SP3信创化环境完成稳定适配与集成" in text


def test_manuscript_sources_use_experiment_environment_not_teaching_cloud():
    forbidden_term = "教学" + "云"
    paths = [
        ROOT / "third-edition-work" / "revision" / "fragments" / f"ch{number:02d}.md"
        for number in range(1, 4)
    ]
    paths.extend((ROOT / "third-edition-work" / "revision" / "figures").glob("*.json"))
    paths.extend((ROOT / "third-edition-work" / "revision" / "figures").glob("*.csv"))
    paths.extend((ROOT / "third-edition-work" / "revision" / "research").glob("ch03-*"))
    for path in paths:
        assert forbidden_term not in path.read_text(encoding="utf-8"), path
    text = chapter_text()
    assert "2．OpenStack实验环境与生产环境的差异" in text
    assert "在学习OpenStack相关知识的过程中" in text


def test_chapter3_has_continuous_figure_and_table_references():
    text = chapter_text()
    for number in range(1, 10):
        label = f"图3.{number}"
        assert text.count(label) >= 2
        assert f"{{{{FIGURE:{label}}}}}" in text
    for number in range(1, 6):
        label = f"表3-{number}"
        assert text.count(label) >= 2
        assert f"{{{{TABLE:{label}}}}}" in text


def test_chapter3_figure_and_table_markers_follow_reading_order():
    text = chapter_text()
    figure_markers = re.findall(r"\{\{FIGURE:(图3\.\d+)\}\}", text)
    table_markers = re.findall(r"\{\{TABLE:(表3-\d+)\}\}", text)
    assert figure_markers == [f"图3.{number}" for number in range(1, 10)]
    assert table_markers == [f"表3-{number}" for number in range(1, 6)]


def test_chapter3_keeps_version_boundaries_precise():
    text = chapter_text()
    assert "2026.1 Gazpacho" in text
    assert "2026年4月1日" in text
    assert "2026.2 Hibiscus" in text
    assert re.search(r"Hibiscus.{0,80}(开发|计划)", text, flags=re.DOTALL)
    assert "2026年9月30日" in text
    assert "2023.1 Antelope" in text
    assert "Unmaintained" in text
    assert "SLURP" in text
    assert "LTS" in text
    assert re.search(r"SLURP.{0,160}(不是|不等于).{0,20}LTS", text, flags=re.DOTALL)


def test_chapter3_has_required_architecture_and_ecosystem_topics():
    text = chapter_text()
    required = (
        "Keystone",
        "Glance",
        "Placement",
        "Nova",
        "Neutron",
        "Cinder",
        "Swift",
        "Horizon",
        "Heat",
        "Ironic",
        "Manila",
        "Octavia",
        "Barbican",
        "Magnum",
        "Cyborg",
        "Ceilometer",
        "Aodh",
        "RabbitMQ",
        "数据库",
        "REST API",
        "SDK",
        "openEuler",
        "OpenInfra Foundation",
        "Governing Board",
        "Technical Committee",
        "Project Team",
        "四项开放原则",
        "Open Source",
        "Open Design",
        "Open Development",
        "Open Community",
        "Gerrit",
        "Zuul",
        "Developer Certificate of Origin",
    )
    for term in required:
        assert term in text


def test_chapter3_has_textbook_scale_and_no_deployment_material():
    text = chapter_text()
    assert 14000 <= len(compact_text()) <= 20000
    banned = (
        "```python",
        "paramiko",
        "pytest",
        "审计证据",
        "Windows Server 2012",
        "远程桌面",
        "关闭系统防火墙",
    )
    for term in banned:
        assert term not in text


def test_chapter3_paragraphs_are_readable_and_not_fragmented():
    paragraphs = [
        line.strip()
        for line in chapter_text().splitlines()
        if line.strip()
        and not line.startswith("#")
        and not line.startswith("{{")
        and not line.startswith("|")
    ]
    prose = [line for line in paragraphs if not re.match(r"^[一二三四五六七八九十0-9]+[．.]", line)]
    assert prose
    assert max(len(line) for line in prose) <= 240
    assert sum(len(line) >= 45 for line in prose) >= 70


def test_chapter3_figure_manifest_has_nine_readable_assets():
    records = json.loads(FIGURE_MANIFEST.read_text(encoding="utf-8"))
    assert [row["number"] for row in records] == [f"图3.{number}" for number in range(1, 10)]
    revision_root = FIGURE_MANIFEST.parent.parent
    for row in records:
        assert row["kind"] == "diagram"
        assert float(row["width_cm"]) >= 13.5
        assert float(row["minimum_font_pt"]) >= 9.0
        svg_path = revision_root / row["svg"]
        png_path = revision_root / row["png"]
        assert svg_path.is_file()
        assert png_path.is_file()
        root = ET.fromstring(svg_path.read_text(encoding="utf-8"))
        view_box = [float(value) for value in root.attrib["viewBox"].split()]
        assert view_box[2] >= 1200 and view_box[3] >= 700
        text_nodes = root.findall(".//{*}text")
        assert text_nodes
        default_size = re.search(r"text\{[^}]*font-size:(\d+(?:\.\d+)?)px", svg_path.read_text(encoding="utf-8"))
        rendered_width_pt = float(row["width_cm"]) * 72 / 2.54
        for node in text_nodes:
            size = node.attrib.get("font-size") or (default_size.group(1) if default_size else None)
            assert size is not None
            assert float(size) * rendered_width_pt / view_box[2] >= 9.0
        svg_payload = svg_path.read_text(encoding="utf-8")
        assert "SimSun" in svg_payload and "宋体" in svg_payload
        for banned in ("注：", "仅供参考", "不作为结论", "教学活动"):
            assert banned not in svg_payload
        payload = png_path.read_bytes()
        assert payload[:8] == b"\x89PNG\r\n\x1a\n" and payload[12:16] == b"IHDR"
        width, height = struct.unpack(">II", payload[16:24])
        assert width >= 2400 and height >= 1400


def test_chapter3_openxml_builder_inserts_figures_tables_and_captions():
    spec = importlib.util.spec_from_file_location("build_chapter3_openxml", OPENXML_BUILDER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    rel = "http://schemas.openxmlformats.org/package/2006/relationships"
    document_relationship = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    paragraphs = ["第三章 原生OpenStack云平台"]
    paragraphs.extend(f"{{{{FIGURE:图3.{number}}}}}" for number in range(1, 10))
    paragraphs.extend(f"{{{{TABLE:表3-{number}}}}}" for number in range(1, 6))
    paragraphs.append("第四章 openEuler与信创OpenStack实验环境准备")
    body = "".join(f'<w:p><w:r><w:t>{text}</w:t></w:r></w:p>' for text in paragraphs)
    mc = "http://schemas.openxmlformats.org/markup-compatibility/2006"
    w14 = "http://schemas.microsoft.com/office/word/2010/wordml"
    wp14 = "http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing"
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{w}" xmlns:mc="{mc}" xmlns:w14="{w14}" '
        f'xmlns:wp14="{wp14}" mc:Ignorable="w14 wp14">'
        f'<w:body>{body}<w:sectPr/></w:body></w:document>'
    ).encode("utf-8")
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '</Types>'
    ).encode("utf-8")
    package_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<Relationships xmlns="{rel}"><Relationship Id="rId1" Type="{document_relationship}/officeDocument" Target="word/document.xml"/></Relationships>'
    ).encode("utf-8")
    document_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<Relationships xmlns="{rel}"/>'
    ).encode("utf-8")
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "source.docx"
        output = Path(directory) / "output.docx"
        with ZipFile(source, "w", compression=ZIP_DEFLATED) as package:
            package.writestr("[Content_Types].xml", content_types)
            package.writestr("_rels/.rels", package_rels)
            package.writestr("word/document.xml", document_xml)
            package.writestr("word/_rels/document.xml.rels", document_rels)
            package.writestr("custom/unchanged.bin", b"unchanged")
        module.build_review_docx(source, output, FIGURE_MANIFEST, ROOT / "third-edition-work" / "revision" / "tables" / "ch03-table-manifest.json")
        with ZipFile(output) as package:
            document_payload = package.read("word/document.xml")
            root = ET.fromstring(document_payload)
            rel_root = ET.fromstring(package.read("word/_rels/document.xml.rels"))
            texts = [node.text or "" for node in root.iter(f"{{{w}}}t")]
            assert not any("{{FIGURE:" in text or "{{TABLE:" in text for text in texts)
            assert len(list(root.iter(f"{{{w}}}tbl"))) == 5
            assert len(list(root.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}drawing"))) == 9
            image_rels = [row for row in rel_root if row.attrib.get("Type", "").endswith("/image")]
            assert len(image_rels) == 9
            assert package.read("custom/unchanged.bin") == b"unchanged"
            root_tag = re.search(rb"<w:document\b.*?>", document_payload, flags=re.DOTALL)
            assert root_tag is not None
            assert b'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"' in root_tag.group(0)
            assert b'xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml"' in root_tag.group(0)
            assert b'xmlns:wp14="http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing"' in root_tag.group(0)
            for table in root.iter(f"{{{w}}}tbl"):
                table_properties = table.find(f"{{{w}}}tblPr")
                assert table_properties is not None
                property_names = [child.tag.rsplit("}", 1)[-1] for child in table_properties]
                assert property_names.index("tblBorders") < property_names.index("tblLayout")
            for shading in root.iter(f"{{{w}}}shd"):
                assert shading.attrib.get(f"{{{w}}}val") == "clear"
            generated_paragraphs = [
                paragraph
                for paragraph in root.iter(f"{{{w}}}p")
                if paragraph.find(f".//{{{w}}}drawing") is not None
                or _paragraph_text_for_test(paragraph, w).startswith(("图3.", "表3-"))
            ]
            assert len(generated_paragraphs) == 23
            for paragraph in generated_paragraphs:
                paragraph_properties = paragraph.find(f"{{{w}}}pPr")
                assert paragraph_properties is not None
                property_names = [child.tag.rsplit("}", 1)[-1] for child in paragraph_properties]
                assert property_names.index("spacing") < property_names.index("jc")
            for number in range(1, 10):
                assert f"图3.{number}" in texts
                assert f"word/media/ch03-figure-{number}.png" in package.namelist()
            for number in range(1, 6):
                assert f"表3-{number}" in texts
