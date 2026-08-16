"""Apply fail-closed, heading-bounded edits to the frozen second-edition DOCX.

The implementation deliberately edits existing Open XML parts.  It never
round-trips the book through python-docx and never rebuilds global styles.
"""

from __future__ import annotations

import argparse
from copy import copy
from dataclasses import dataclass
from html import escape
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
from xml.etree import ElementTree as ET
import zipfile


WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{WORD_NS}}}"
NS = {"w": WORD_NS}
ALLOWED_BLOCK_KINDS = frozenset(
    {"body", "command", "config", "heading1", "heading2", "caption"}
)
OPERATION_FIELDS = {
    "replace": frozenset({"op", "start_heading", "end_heading", "fragment"}),
    "replace_with_part_opener": frozenset(
        {"op", "start_heading", "end_heading", "fragment", "part_title"}
    ),
    "delete": frozenset({"op", "start_heading", "end_heading"}),
    "insert_before": frozenset({"op", "heading", "fragment"}),
    "renumber_chapter": frozenset(
        {"op", "heading", "old_number", "new_number"}
    ),
}
TAG_PATTERN = re.compile(
    rb"<(?P<close>/)?(?P<name>[A-Za-z_][\w:.-]*)(?P<attrs>[^<>]*?)(?P<self>/)?>"
)
PPR_PATTERN = re.compile(rb"<w:pPr\b[^>]*(?:/>|>.*?</w:pPr>)", re.DOTALL)
TEXT_NODE_PATTERN = re.compile(rb"(?P<open><w:t\b[^>]*>).*?(?P<close></w:t>)", re.DOTALL)
ROOT_PATTERN = re.compile(rb"<w:document\b(?P<attrs>[^>]*)>")
BODY_PATTERN = re.compile(rb"<w:body\b[^>]*>")
CAPTION_PATTERN = re.compile(r"^图\s*\d+(?:[.\-]\d+)+")
PART_OPENER_PATTERN = re.compile(r"^第[〇零一二三四五六七八九十百]+部分(?:\s|$)")
COMMAND_PATTERN = re.compile(
    r"^(?:\[[^\]\r\n]+@[^\]]+\][#$]|MariaDB\s+\[[^\]]+\]>|[^\s]+@[^\s]+[$#])"
)
CONFIG_PATTERN = re.compile(
    r"^(?:\[[A-Za-z0-9_.:-]+\]\s*$|[A-Za-z][A-Za-z0-9_.-]*\s*=)"
)
IMAGE_MARKDOWN_PATTERN = re.compile(r"^!\[(?P<caption>[^]]*)\]\((?P<path>[^)]+)\)$")
FENCE_PATTERN = re.compile(r"^```(?P<kind>command|config)\s*$")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class Block:
    """One explicitly typed fragment block inserted into the existing DOCX.

    ``body``, ``command``, ``config``, ``heading1``, ``heading2``, and
    ``caption`` carry editable text.  Figure insertion is deliberately deferred
    to the later image-layout task.  Command text is intentionally stored as
    ordinary editable Word text; later content tasks enforce prompt syntax.
    """

    kind: str
    text: str = ""

    def __post_init__(self) -> None:
        if self.kind not in ALLOWED_BLOCK_KINDS:
            raise ValueError(f"unknown block kind: {self.kind!r}")
        if not isinstance(self.text, str) or not self.text.strip():
            raise ValueError(f"{self.kind} block requires non-empty text")


@dataclass
class DocxDocument:
    """A loaded DOCX package whose unchanged member payloads remain intact."""

    source: Path
    infos: list[zipfile.ZipInfo]
    payloads: dict[str, bytes]
    document_xml: bytes
    archive_comment: bytes
    styles: ET.Element | None

    def set_payload(self, name: str, payload: bytes) -> None:
        self.payloads[name] = payload
        if name == "word/document.xml":
            self.document_xml = payload
        elif name == "word/styles.xml":
            self.styles = ET.fromstring(payload)
        if name not in {info.filename for info in self.infos}:
            raise ValueError(f"cannot add a new package member in Task 2: {name}")


def copy_source(source: Path, output: Path) -> None:
    """Byte-copy ``source`` while refusing to overwrite an unknown output."""
    source = Path(source)
    output = Path(output)
    if source.resolve() == output.resolve():
        raise ValueError("source and output must be different paths")
    if output.exists():
        if _sha256(output) == _sha256(source):
            return
        raise FileExistsError(f"refusing to overwrite non-identical output: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, output)
    if _sha256(output) != _sha256(source):
        output.unlink(missing_ok=True)
        raise OSError("source copy failed its SHA-256 verification")


def load_docx(path: Path) -> DocxDocument:
    """Load a DOCX without extracting or rewriting any package member."""
    path = Path(path)
    with zipfile.ZipFile(path) as archive:
        infos = [copy(info) for info in archive.infolist()]
        payloads = {info.filename: archive.read(info.filename) for info in infos}
        archive_comment = archive.comment
    if "word/document.xml" not in payloads:
        raise ValueError("DOCX is missing word/document.xml")
    document_xml = payloads["word/document.xml"]
    ET.fromstring(document_xml)
    styles = ET.fromstring(payloads["word/styles.xml"]) if "word/styles.xml" in payloads else None
    return DocxDocument(path, infos, payloads, document_xml, archive_comment, styles)


def _document_root_attributes(xml: bytes) -> bytes:
    match = ROOT_PATTERN.search(xml)
    if match is None:
        raise ValueError("word/document.xml has no w:document root")
    return match.group("attrs")


def _body_parts(xml: bytes) -> tuple[bytes, list[bytes], bytes]:
    body = BODY_PATTERN.search(xml)
    if body is None:
        raise ValueError("word/document.xml has no w:body")
    closing = xml.rfind(b"</w:body>")
    if closing < body.end():
        raise ValueError("word/document.xml has an invalid w:body")
    inner = xml[body.end():closing]
    children: list[bytes] = []
    depth = 0
    start: int | None = None
    for tag in TAG_PATTERN.finditer(inner):
        is_close = tag.group("close") is not None
        is_self_closing = tag.group("self") is not None
        if not is_close and depth == 0:
            start = tag.start()
        if is_close:
            depth -= 1
            if depth < 0:
                raise ValueError("unbalanced XML in w:body")
            if depth == 0:
                assert start is not None
                children.append(inner[start:tag.end()])
                start = None
        elif is_self_closing:
            if depth == 0:
                assert start is not None
                children.append(inner[start:tag.end()])
                start = None
        else:
            depth += 1
    if depth != 0:
        raise ValueError("unbalanced XML in w:body")
    return xml[:body.end()], children, xml[closing:]


def _parse_child(document_xml: bytes, child: bytes) -> ET.Element:
    wrapper = b"<root" + _document_root_attributes(document_xml) + b">" + child + b"</root>"
    root = ET.fromstring(wrapper)
    if len(root) != 1:
        raise ValueError("expected one top-level DOCX body element")
    return root[0]


def _child_name(document_xml: bytes, child: bytes) -> str:
    return _parse_child(document_xml, child).tag


def _child_text(document_xml: bytes, child: bytes) -> str:
    element = _parse_child(document_xml, child)
    return "".join(node.text or "" for node in element.findall(".//w:t", NS))


def _normalize_heading(value: str) -> str:
    return " ".join(value.split())


def _unique_heading_index(document: DocxDocument, heading: str) -> int:
    normalized = _normalize_heading(heading)
    if not normalized:
        raise ValueError("heading must not be empty")
    _, children, _ = _body_parts(document.document_xml)
    matches = [
        index
        for index, child in enumerate(children)
        if _child_name(document.document_xml, child) == f"{W}p"
        and _is_heading_paragraph(document, child)
        and _normalize_heading(_child_text(document.document_xml, child)) == normalized
    ]
    if len(matches) != 1:
        raise ValueError(
            f"heading must match exactly one unique paragraph: {heading!r}; matches={len(matches)}"
        )
    return matches[0]


def _paragraph_style(document_xml: bytes, paragraph: bytes) -> str | None:
    element = _parse_child(document_xml, paragraph)
    style = element.find("w:pPr/w:pStyle", NS)
    return None if style is None else style.get(f"{W}val")


def _styles(document: DocxDocument) -> ET.Element | None:
    return document.styles


def _style_by_id(styles: ET.Element | None, style_id: str | None) -> ET.Element | None:
    if styles is None or style_id is None:
        return None
    return next(
        (style for style in styles.findall("w:style", NS) if style.get(f"{W}styleId") == style_id),
        None,
    )


def _paragraph_outline_level(document: DocxDocument, paragraph: bytes) -> int | None:
    element = _parse_child(document.document_xml, paragraph)
    direct = element.find("w:pPr/w:outlineLvl", NS)
    value = None if direct is None else direct.get(f"{W}val")
    if value is None:
        style = _style_by_id(_styles(document), _paragraph_style(document.document_xml, paragraph))
        inherited = None if style is None else style.find("w:pPr/w:outlineLvl", NS)
        value = None if inherited is None else inherited.get(f"{W}val")
    return int(value) if value is not None and value.isdigit() else None


def _is_heading_paragraph(document: DocxDocument, paragraph: bytes) -> bool:
    style_id = _paragraph_style(document.document_xml, paragraph)
    if style_id in {"1", "2", "Heading1", "Heading2", "heading1", "heading2"}:
        return True
    style = _style_by_id(_styles(document), style_id)
    name = None if style is None else style.find("w:name", NS)
    style_name = "" if name is None else (name.get(f"{W}val") or "").casefold().replace(" ", "")
    if style_name in {"heading1", "heading2"}:
        return True
    return _paragraph_outline_level(document, paragraph) in {0, 1}


def _paragraph_has_drawing(document_xml: bytes, paragraph: bytes) -> bool:
    element = _parse_child(document_xml, paragraph)
    return element.find(".//w:drawing", NS) is not None


def _is_empty_layout_break_paragraph(document_xml: bytes, paragraph: bytes) -> bool:
    element = _parse_child(document_xml, paragraph)
    if element.tag != f"{W}p" or _child_text(document_xml, paragraph).strip():
        return False
    if element.find("w:pPr/w:sectPr", NS) is not None:
        return True
    return any(
        line_break.get(f"{W}type") == "page"
        for line_break in element.findall(".//w:br", NS)
    )


def _has_section_break(document_xml: bytes, paragraph: bytes) -> bool:
    element = _parse_child(document_xml, paragraph)
    return element.tag == f"{W}p" and element.find("w:pPr/w:sectPr", NS) is not None


def _strip_text_from_section_break_paragraph(paragraph: bytes) -> bytes:
    """Keep a paragraph's exact pPr/sectPr while removing obsolete chapter text."""
    properties = PPR_PATTERN.search(paragraph)
    opening_end = paragraph.find(b">")
    if properties is None or opening_end < 0:
        raise ValueError("section-break paragraph has no preservable paragraph properties")
    return paragraph[: opening_end + 1] + properties.group(0) + b"</w:p>"


def _is_part_opener(document_xml: bytes, paragraph: bytes) -> bool:
    return (
        _child_name(document_xml, paragraph) == f"{W}p"
        and PART_OPENER_PATTERN.match(_child_text(document_xml, paragraph).strip()) is not None
    )


def _replace_text_preserving_paragraph_xml(paragraph: bytes, text: str) -> bytes:
    matches = list(TEXT_NODE_PATTERN.finditer(paragraph))
    if not matches:
        raise ValueError("part opener paragraph has no editable text")
    escaped = escape(text).encode("utf-8")
    rewritten: list[bytes] = []
    cursor = 0
    for index, match in enumerate(matches):
        rewritten.append(paragraph[cursor:match.start()])
        rewritten.append(match.group("open"))
        if index == 0:
            rewritten.append(escaped)
        rewritten.append(match.group("close"))
        cursor = match.end()
    rewritten.append(paragraph[cursor:])
    return b"".join(rewritten)


def _trailing_layout_transition(
    document: DocxDocument,
    children: list[bytes],
    start_index: int,
    end_index: int,
    part_title: str | None,
) -> list[bytes]:
    """Keep a source chapter's trailing section/page transition byte-for-byte."""
    tail_start = end_index
    part_index: int | None = None
    candidate = end_index - 1
    if (
        candidate > start_index
        and _is_part_opener(document.document_xml, children[candidate])
        and candidate - 1 > start_index
        and _is_empty_layout_break_paragraph(
            document.document_xml, children[candidate - 1]
        )
    ):
        part_index = candidate
        tail_start = candidate
    while tail_start - 1 > start_index:
        candidate_paragraph = children[tail_start - 1]
        if not (
            _is_empty_layout_break_paragraph(document.document_xml, candidate_paragraph)
            or _has_section_break(document.document_xml, candidate_paragraph)
        ):
            break
        tail_start -= 1
    transition = list(children[tail_start:end_index])
    transition = [
        _strip_text_from_section_break_paragraph(paragraph)
        if _has_section_break(document.document_xml, paragraph)
        and _child_text(document.document_xml, paragraph).strip()
        else paragraph
        for paragraph in transition
    ]
    if part_title is not None:
        if part_index is None:
            raise ValueError("replace_with_part_opener requires a trailing source part opener")
        transition[part_index - tail_start] = _replace_text_preserving_paragraph_xml(
            children[part_index], part_title
        )
    return transition


def _paragraph_properties(paragraph: bytes) -> bytes:
    match = PPR_PATTERN.search(paragraph)
    return b"<w:pPr/>" if match is None else bytes(match.group(0))


def _code_block_properties(properties: bytes) -> bytes:
    """Keep a code block's left indent while aligning every visual line."""

    def normalize_indent(match: re.Match[bytes]) -> bytes:
        indent = match.group(0)
        return re.sub(
            rb'\s+w:(?:firstLine|firstLineChars|hanging|hangingChars)="[^"]*"',
            b"",
            indent,
        )

    return re.sub(rb"<w:ind\b[^>]*/>", normalize_indent, properties)


def _attribute(element: ET.Element | None, name: str) -> str | None:
    return None if element is None else element.get(f"{W}{name}")


def _normal_style(styles: ET.Element | None) -> ET.Element | None:
    if styles is None:
        return None
    return next(
        (
            style
            for style in styles.findall("w:style", NS)
            if style.get(f"{W}type") == "paragraph" and style.get(f"{W}default") == "1"
        ),
        None,
    )


def _body_template_candidate(document: DocxDocument, paragraph: bytes) -> bool:
    element = _parse_child(document.document_xml, paragraph)
    properties = element.find("w:pPr", NS)
    if properties is None:
        return False
    styles = _styles(document)
    normal = _normal_style(styles)
    normal_id = None if normal is None else normal.get(f"{W}styleId")
    style_id = _paragraph_style(document.document_xml, paragraph)
    if style_id not in {None, normal_id}:
        return False
    indentation = properties.find("w:ind", NS)
    if _attribute(indentation, "firstLineChars") != "200":
        return False
    alignment = properties.find("w:jc", NS)
    if alignment is None and normal is not None:
        alignment = normal.find("w:pPr/w:jc", NS)
    if _attribute(alignment, "val") != "both":
        return False
    paragraph_run = properties.find("w:rPr", NS)
    fonts = None if paragraph_run is None else paragraph_run.find("w:rFonts", NS)
    if fonts is None and normal is not None:
        fonts = normal.find("w:rPr/w:rFonts", NS)
    if fonts is None and styles is not None:
        fonts = styles.find("w:docDefaults/w:rPrDefault/w:rPr/w:rFonts", NS)
    if _attribute(fonts, "eastAsia") != "宋体":
        return False
    size = None if paragraph_run is None else paragraph_run.find("w:sz", NS)
    if size is None and styles is not None:
        size = styles.find("w:docDefaults/w:rPrDefault/w:rPr/w:sz", NS)
    return _attribute(size, "val") == "21"


def _template_paragraph(document: DocxDocument, kind: str) -> bytes:
    _, children, _ = _body_parts(document.document_xml)
    paragraphs = [
        child
        for child in children
        if _child_name(document.document_xml, child) == f"{W}p"
    ]
    records = [
        (
            paragraph,
            _child_text(document.document_xml, paragraph).strip(),
            _paragraph_style(document.document_xml, paragraph),
        )
        for paragraph in paragraphs
    ]
    if kind in {"heading1", "heading2"}:
        wanted_outline = 0 if kind == "heading1" else 1
        candidates = [
            paragraph
            for paragraph, text, style in records
            if text and _paragraph_outline_level(document, paragraph) == wanted_outline
        ]
    elif kind == "caption":
        candidates = [paragraph for paragraph, text, _ in records if CAPTION_PATTERN.match(text)]
    elif kind == "command":
        candidates = [paragraph for paragraph, text, _ in records if COMMAND_PATTERN.match(text)]
    elif kind == "config":
        candidates = [
            paragraph
            for paragraph, text, _ in records
            if CONFIG_PATTERN.match(text) and not COMMAND_PATTERN.match(text)
        ]
    else:
        candidates = [
            paragraph
            for paragraph, text, style in records
            if text
            and not CAPTION_PATTERN.match(text)
            and not COMMAND_PATTERN.match(text)
            and not CONFIG_PATTERN.match(text)
            and not _paragraph_has_drawing(document.document_xml, paragraph)
            and _body_template_candidate(document, paragraph)
        ]
    if candidates:
        return candidates[0]
    raise ValueError(f"source DOCX has no usable {kind} paragraph template")


def _text_runs(text: str, *, caption: bool = False) -> bytes:
    lines = text.splitlines() or [text]
    chunks: list[str] = []
    for index, line in enumerate(lines):
        if index:
            chunks.append("<w:r><w:br/></w:r>")
        font_properties = (
            '<w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" '
            'w:eastAsia="宋体" w:cs="Times New Roman"/>'
        )
        emphasis = '<w:b/><w:sz w:val="18"/><w:szCs w:val="18"/>' if caption else ""
        properties = f"<w:rPr>{font_properties}{emphasis}</w:rPr>"
        chunks.append(
            f'<w:r>{properties}<w:t xml:space="preserve">{escape(line)}</w:t></w:r>'
        )
    return "".join(chunks).encode("utf-8")


def _caption_properties(properties: bytes) -> bytes:
    if properties.endswith(b"/>"):
        properties = properties[:-2] + b"></w:pPr>"
    properties = re.sub(rb"<w:jc\b[^>]*/>", b"", properties)
    return properties.replace(b"</w:pPr>", b'<w:jc w:val="center"/></w:pPr>', 1)


def _render_blocks(document: DocxDocument, blocks: list[Block]) -> list[bytes]:
    rendered: list[bytes] = []
    templates: dict[str, bytes] = {}
    for block in blocks:
        if not isinstance(block, Block):
            raise TypeError("blocks must contain Block values")
        if block.kind not in templates:
            templates[block.kind] = _template_paragraph(document, block.kind)
        properties = _paragraph_properties(templates[block.kind])
        if block.kind == "caption":
            properties = _caption_properties(properties)
        elif block.kind in {"command", "config"}:
            properties = _code_block_properties(properties)
        rendered.append(
            b"<w:p>" + properties + _text_runs(block.text, caption=block.kind == "caption") + b"</w:p>"
        )
    return rendered


def _write_children(document: DocxDocument, children: list[bytes]) -> None:
    prefix, _, suffix = _body_parts(document.document_xml)
    document.set_payload("word/document.xml", prefix + b"".join(children) + suffix)


def replace_between_headings(
    doc: DocxDocument,
    start: str,
    end: str,
    blocks: list[Block],
    *,
    part_title: str | None = None,
) -> None:
    """Replace chapter content while retaining its trailing layout transition."""
    start_index = _unique_heading_index(doc, start)
    end_index = _unique_heading_index(doc, end)
    if start_index >= end_index:
        raise ValueError("heading order is invalid: start must occur before end")
    _, children, _ = _body_parts(doc.document_xml)
    replacement = _render_blocks(doc, blocks)
    transition = _trailing_layout_transition(
        doc, children, start_index, end_index, part_title
    )
    retains_start_heading = not blocks or blocks[0].kind != "heading1"
    prefix_end = start_index + 1 if retains_start_heading else start_index
    _write_children(
        doc,
        children[:prefix_end] + replacement + transition + children[end_index:],
    )


def delete_between_headings(doc: DocxDocument, start: str, end: str) -> None:
    """Delete top-level body elements strictly between two unique headings."""
    replace_between_headings(doc, start, end, [])


def insert_before_heading(doc: DocxDocument, heading: str, blocks: list[Block]) -> None:
    """Insert blocks immediately before one uniquely matching heading."""
    index = _unique_heading_index(doc, heading)
    _, children, _ = _body_parts(doc.document_xml)
    insertion = _render_blocks(doc, blocks)
    _write_children(doc, children[:index] + insertion + children[index:])


def _replace_text_node_values(
    paragraph: bytes, replacements: tuple[tuple[str, str], ...]
) -> bytes:
    """Replace literal values only inside existing ``w:t`` nodes."""

    rewritten: list[bytes] = []
    cursor = 0
    for match in TEXT_NODE_PATTERN.finditer(paragraph):
        rewritten.append(paragraph[cursor:match.start()])
        value = match.group(0)
        for old, new in replacements:
            value = value.replace(old.encode("utf-8"), new.encode("utf-8"))
        rewritten.append(value)
        cursor = match.end()
    rewritten.append(paragraph[cursor:])
    return b"".join(rewritten)


def renumber_chapter(
    doc: DocxDocument,
    heading: str,
    old_number: int,
    new_number: int,
) -> None:
    """Mechanically renumber one uniquely bounded chapter without rewriting prose."""

    if not isinstance(old_number, int) or not isinstance(new_number, int):
        raise TypeError("chapter numbers must be integers")
    if old_number <= 0 or new_number <= 0 or old_number == new_number:
        raise ValueError("chapter numbers must be different positive integers")
    expected_prefix = f"第{old_number}章"
    chinese_numbers = {
        1: "一", 2: "二", 3: "三", 4: "四", 5: "五",
        6: "六", 7: "七", 8: "八", 9: "九", 10: "十",
        11: "十一", 12: "十二", 13: "十三", 14: "十四",
        15: "十五", 16: "十六", 17: "十七", 18: "十八",
        19: "十九", 20: "二十",
    }
    old_chinese = chinese_numbers.get(old_number)
    new_chinese = chinese_numbers.get(new_number)
    if old_chinese is None or new_chinese is None:
        raise ValueError("chapter renumbering supports chapter numbers 1 through 20")
    expected_chinese_prefix = f"第{old_chinese}章"
    if not _normalize_heading(heading).startswith(expected_chinese_prefix):
        raise ValueError(
            f"heading does not match old chapter number {old_number}: {heading!r}"
        )

    start_index = _unique_heading_index(doc, heading)
    _, children, _ = _body_parts(doc.document_xml)
    end_index = len(children)
    for index in range(start_index + 1, len(children)):
        child = children[index]
        if _child_name(doc.document_xml, child) == f"{W}sectPr":
            end_index = index
            break
        if (
            _child_name(doc.document_xml, child) == f"{W}p"
            and _paragraph_outline_level(doc, child) == 0
        ):
            end_index = index
            break

    rewritten = list(children)
    for index in range(start_index, end_index):
        child = children[index]
        if _child_name(doc.document_xml, child) != f"{W}p":
            continue
        text = _normalize_heading(_child_text(doc.document_xml, child))
        replacements: list[tuple[str, str]] = [
            (f"图{old_number}.", f"图{new_number}."),
            (f"表{old_number}-", f"表{new_number}-"),
            (f"第{old_number}.", f"第{new_number}."),
        ]
        if index == start_index:
            replacements.append((expected_chinese_prefix, f"第{new_chinese}章"))
        elif _paragraph_outline_level(doc, child) == 1 and text.startswith(
            f"{old_number}."
        ):
            replacements.append((f"{old_number}.", f"{new_number}."))
        rewritten[index] = _replace_text_node_values(child, tuple(replacements))

    if expected_prefix in _normalize_heading(_child_text(doc.document_xml, rewritten[start_index])):
        raise ValueError("chapter heading uses unsupported Arabic chapter form")
    _write_children(doc, rewritten)


def save_candidate(doc: DocxDocument, output: Path) -> None:
    """Atomically save a candidate, preserving unchanged member payload bytes."""
    output = Path(output)
    if output.resolve() == doc.source.resolve():
        raise ValueError("refusing to overwrite the source DOCX")
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing output: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.", suffix=".tmp", dir=output.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with zipfile.ZipFile(temporary, "w") as archive:
            archive.comment = doc.archive_comment
            for info in doc.infos:
                archive.writestr(info, doc.payloads[info.filename])
        with zipfile.ZipFile(temporary) as archive:
            ET.fromstring(archive.read("word/document.xml"))
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)


def load_revision_map(path: Path) -> list[dict[str, str]]:
    """Load the strict list-shaped revision-map schema."""
    path = Path(path)
    with path.open(encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, list):
        raise ValueError("revision map must be a JSON array")
    operations: list[dict[str, str]] = []
    for index, operation in enumerate(value):
        if not isinstance(operation, dict):
            raise ValueError(f"operation {index} must be an object")
        op = operation.get("op")
        if op not in OPERATION_FIELDS:
            raise ValueError(f"operation {index} has unknown op: {op!r}")
        expected = OPERATION_FIELDS[op]
        actual = frozenset(operation)
        missing = sorted(expected - actual)
        unknown = sorted(actual - expected)
        if missing:
            raise ValueError(f"operation {index} has missing fields: {missing}")
        if unknown:
            raise ValueError(f"operation {index} has unknown fields: {unknown}")
        for key in expected - {"op"}:
            field_value = operation[key]
            if not isinstance(field_value, str) or not field_value.strip():
                raise ValueError(f"operation {index} field {key!r} must be a non-empty string")
        operations.append({key: operation[key] for key in expected})
    return operations


def parse_fragment(path: Path) -> list[Block]:
    """Parse the deliberately small Markdown fragment dialect into Blocks."""
    path = Path(path)
    lines = path.read_text(encoding="utf-8").splitlines()
    blocks: list[Block] = []
    paragraph: list[str] = []
    fence_kind: str | None = None
    fenced: list[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            blocks.append(Block("body", " ".join(line.strip() for line in paragraph)))
            paragraph.clear()

    for line_number, line in enumerate(lines, start=1):
        if fence_kind is not None:
            if line.strip() == "```":
                blocks.append(Block(fence_kind, "\n".join(fenced)))
                fence_kind = None
                fenced.clear()
            else:
                fenced.append(line)
            continue
        fence = FENCE_PATTERN.match(line.strip())
        if fence:
            flush_paragraph()
            fence_kind = fence.group("kind")
            continue
        if line.strip().startswith("```"):
            raise ValueError(f"unsupported fence at {path}:{line_number}; use command or config")
        image = IMAGE_MARKDOWN_PATTERN.match(line.strip())
        if image:
            raise ValueError(
                f"figure blocks are deferred to the later image-layout task: {path}:{line_number}"
            )
        elif line.startswith("## "):
            flush_paragraph()
            blocks.append(Block("heading2", line[3:].strip()))
        elif line.startswith("# "):
            flush_paragraph()
            blocks.append(Block("heading1", line[2:].strip()))
        elif not line.strip():
            flush_paragraph()
        else:
            paragraph.append(line)
    if fence_kind is not None:
        raise ValueError(f"unclosed {fence_kind} fence in {path}")
    flush_paragraph()
    return blocks


def _resolve_fragment_path(revision_map: Path, fragment: str) -> Path:
    """Resolve a regular, non-symlink fragment strictly beneath the map directory."""
    relative = Path(fragment)
    if relative.is_absolute() or relative.drive or ".." in relative.parts:
        raise ValueError(f"fragment path must stay beneath the revision-map directory: {fragment!r}")
    base = revision_map.parent.resolve(strict=True)
    lexical = revision_map.parent / relative
    current = revision_map.parent
    for part in relative.parts:
        current = current / part
        if current.is_symlink() or (hasattr(current, "is_junction") and current.is_junction()):
            raise ValueError(f"fragment path must not contain a symlink: {fragment!r}")
    try:
        resolved = lexical.resolve(strict=True)
    except OSError as error:
        raise ValueError(f"fragment must be an existing regular file: {fragment!r}") from error
    try:
        resolved.relative_to(base)
    except ValueError as error:
        raise ValueError(f"fragment path escapes the revision-map directory: {fragment!r}") from error
    if not resolved.is_file():
        raise ValueError(f"fragment must be a regular file: {fragment!r}")
    return resolved


def apply_revision_map(source: Path, revision_map: Path, output: Path) -> None:
    """Apply a strict revision map, byte-copying the source when it is empty."""
    source = Path(source)
    revision_map = Path(revision_map)
    output = Path(output)
    operations = load_revision_map(revision_map)
    if not operations:
        copy_source(source, output)
        return
    document = load_docx(source)
    for operation in operations:
        op = operation["op"]
        if op in {"replace", "replace_with_part_opener"}:
            blocks = parse_fragment(_resolve_fragment_path(revision_map, operation["fragment"]))
            replace_between_headings(
                document,
                operation["start_heading"],
                operation["end_heading"],
                blocks,
                part_title=operation.get("part_title"),
            )
        elif op == "delete":
            delete_between_headings(document, operation["start_heading"], operation["end_heading"])
        elif op == "insert_before":
            blocks = parse_fragment(_resolve_fragment_path(revision_map, operation["fragment"]))
            insert_before_heading(document, operation["heading"], blocks)
        elif op == "renumber_chapter":
            if not operation["old_number"].isdigit() or not operation["new_number"].isdigit():
                raise ValueError("renumber_chapter numbers must contain decimal digits")
            renumber_chapter(
                document,
                operation["heading"],
                int(operation["old_number"]),
                int(operation["new_number"]),
            )
        else:  # load_revision_map makes this unreachable.
            raise AssertionError(f"unhandled operation: {op}")
    save_candidate(document, output)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="immutable second-edition DOCX")
    parser.add_argument("--map", dest="revision_map", type=Path, required=True, help="revision map JSON")
    parser.add_argument("--output", type=Path, required=True, help="candidate third-edition DOCX")
    arguments = parser.parse_args(argv)
    try:
        apply_revision_map(arguments.source, arguments.revision_map, arguments.output)
    except (OSError, ValueError, json.JSONDecodeError, zipfile.BadZipFile) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"PASS: wrote {arguments.output}")
    print(f"SHA-256: {_sha256(arguments.output)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
