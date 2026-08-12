"""Apply fail-closed, heading-bounded edits to the frozen second-edition DOCX.

The implementation deliberately edits existing Open XML parts.  It never
round-trips the book through python-docx and never rebuilds global styles.
"""

from __future__ import annotations

import argparse
from copy import copy
from dataclasses import dataclass, field
from html import escape
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
from typing import Any
from xml.etree import ElementTree as ET
import zipfile


WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
W = f"{{{WORD_NS}}}"
NS = {"w": WORD_NS}
ALLOWED_BLOCK_KINDS = frozenset(
    {"body", "command", "config", "heading1", "heading2", "caption", "figure"}
)
TEXT_BLOCK_KINDS = ALLOWED_BLOCK_KINDS - {"figure"}
OPERATION_FIELDS = {
    "replace": frozenset({"op", "start_heading", "end_heading", "fragment"}),
    "delete": frozenset({"op", "start_heading", "end_heading"}),
    "insert_before": frozenset({"op", "heading", "fragment"}),
}
TAG_PATTERN = re.compile(
    rb"<(?P<close>/)?(?P<name>[A-Za-z_][\w:.-]*)(?P<attrs>[^<>]*?)(?P<self>/)?>"
)
PPR_PATTERN = re.compile(rb"<w:pPr\b[^>]*(?:/>|>.*?</w:pPr>)", re.DOTALL)
ROOT_PATTERN = re.compile(rb"<w:document\b(?P<attrs>[^>]*)>")
BODY_PATTERN = re.compile(rb"<w:body\b[^>]*>")
CAPTION_PATTERN = re.compile(r"^图\s*\d+(?:[.\-]\d+)+")
COMMAND_PATTERN = re.compile(
    r"^(?:\[[^\]\r\n]+@[^\]]+\][#$]|MariaDB\s+\[[^\]]+\]>|[^\s]+@[^\s]+[$#])"
)
CONFIG_PATTERN = re.compile(r"^(?:\[[^\]\r\n]+\]|[A-Za-z0-9_.-]+\s*=)")
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
    ``caption`` carry editable text.  ``figure`` carries an image path and an
    optional width in centimetres.  Command text is intentionally stored as
    ordinary editable Word text; later content tasks enforce prompt syntax.
    """

    kind: str
    text: str = ""
    image: Path | None = None
    width_cm: float | None = None

    def __post_init__(self) -> None:
        if self.kind not in ALLOWED_BLOCK_KINDS:
            raise ValueError(f"unknown block kind: {self.kind!r}")
        if self.kind == "figure":
            if self.image is None or not isinstance(self.image, Path):
                raise ValueError("figure block requires an image Path")
            if self.text:
                raise ValueError("figure block cannot carry text")
            if self.width_cm is not None and self.width_cm <= 0:
                raise ValueError("figure width_cm must be positive")
        else:
            if self.image is not None:
                raise ValueError(f"{self.kind} block cannot carry an image")
            if self.width_cm is not None:
                raise ValueError(f"{self.kind} block cannot carry width_cm")
            if not isinstance(self.text, str) or not self.text.strip():
                raise ValueError(f"{self.kind} block requires non-empty text")


@dataclass
class DocxDocument:
    """A loaded DOCX package whose unchanged member payloads remain intact."""

    source: Path
    infos: list[zipfile.ZipInfo]
    payloads: dict[str, bytes]
    document_xml: bytes
    new_members: list[str] = field(default_factory=list)

    def set_payload(self, name: str, payload: bytes) -> None:
        self.payloads[name] = payload
        if name == "word/document.xml":
            self.document_xml = payload
        if name not in {info.filename for info in self.infos} and name not in self.new_members:
            self.new_members.append(name)


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
    if "word/document.xml" not in payloads:
        raise ValueError("DOCX is missing word/document.xml")
    document_xml = payloads["word/document.xml"]
    ET.fromstring(document_xml)
    return DocxDocument(path, infos, payloads, document_xml)


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


def _paragraph_has_drawing(document_xml: bytes, paragraph: bytes) -> bool:
    element = _parse_child(document_xml, paragraph)
    return element.find(".//w:drawing", NS) is not None


def _paragraph_properties(paragraph: bytes) -> bytes:
    match = PPR_PATTERN.search(paragraph)
    return b"<w:pPr/>" if match is None else bytes(match.group(0))


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
        wanted = "1" if kind == "heading1" else "2"
        candidates = [
            paragraph
            for paragraph, text, style in records
            if text and style is not None and style.casefold() in {wanted, f"heading{wanted}"}
        ]
    elif kind == "caption":
        candidates = [paragraph for paragraph, text, _ in records if CAPTION_PATTERN.match(text)]
    elif kind == "command":
        candidates = [paragraph for paragraph, text, _ in records if COMMAND_PATTERN.match(text)]
    elif kind == "config":
        candidates = [paragraph for paragraph, text, _ in records if CONFIG_PATTERN.match(text)]
    else:
        candidates = [
            paragraph
            for paragraph, text, style in records
            if text
            and style is None
            and not CAPTION_PATTERN.match(text)
            and not COMMAND_PATTERN.match(text)
            and not CONFIG_PATTERN.match(text)
            and not _paragraph_has_drawing(document.document_xml, paragraph)
        ]
    if candidates:
        return candidates[0]
    if kind in {"command", "config", "caption"}:
        return _template_paragraph(document, "body")
    raise ValueError(f"source DOCX has no usable {kind} paragraph template")


def _text_runs(text: str, *, caption: bool = False) -> bytes:
    lines = text.splitlines() or [text]
    chunks: list[str] = []
    for index, line in enumerate(lines):
        if index:
            chunks.append("<w:r><w:br/></w:r>")
        properties = "<w:rPr><w:b/><w:sz w:val=\"18\"/><w:szCs w:val=\"18\"/></w:rPr>" if caption else ""
        chunks.append(
            f'<w:r>{properties}<w:t xml:space="preserve">{escape(line)}</w:t></w:r>'
        )
    return "".join(chunks).encode("utf-8")


def _caption_properties(properties: bytes) -> bytes:
    if properties.endswith(b"/>"):
        properties = properties[:-2] + b"></w:pPr>"
    properties = re.sub(rb"<w:jc\b[^>]*/>", b"", properties)
    return properties.replace(b"</w:pPr>", b'<w:jc w:val="center"/></w:pPr>', 1)


def _next_relationship_id(relationships: bytes) -> str:
    existing = {match.decode("ascii") for match in re.findall(rb'\bId="([^"]+)"', relationships)}
    number = 1
    while f"rIdRevision{number}" in existing:
        number += 1
    return f"rIdRevision{number}"


def _ensure_content_type(document: DocxDocument, extension: str, content_type: str) -> None:
    name = "[Content_Types].xml"
    payload = document.payloads.get(name)
    if payload is None:
        raise ValueError("DOCX is missing [Content_Types].xml")
    if re.search(rb'Extension="' + re.escape(extension.encode()) + rb'"', payload, re.IGNORECASE):
        return
    default = f'<Default Extension="{escape(extension)}" ContentType="{escape(content_type)}"/>'.encode()
    if b"</Types>" in payload:
        payload = payload.replace(b"</Types>", default + b"</Types>", 1)
    elif re.search(rb"<Types\b[^>]*/>", payload):
        payload = re.sub(rb"<Types\b([^>]*)/>", rb"<Types\1>" + default + b"</Types>", payload, count=1)
    else:
        raise ValueError("[Content_Types].xml has no Types root")
    document.set_payload(name, payload)


def _add_figure(document: DocxDocument, block: Block) -> bytes:
    assert block.image is not None
    image = block.image
    if not image.is_file():
        raise FileNotFoundError(f"figure file does not exist: {image}")
    extension = image.suffix.lower().lstrip(".")
    if not extension:
        raise ValueError(f"figure has no file extension: {image}")
    media_number = 1
    while f"word/media/revision-image-{media_number:03d}.{extension}" in document.payloads:
        media_number += 1
    media_name = f"word/media/revision-image-{media_number:03d}.{extension}"
    document.set_payload(media_name, image.read_bytes())

    relationships_name = "word/_rels/document.xml.rels"
    relationships = document.payloads.get(relationships_name)
    if relationships is None:
        raise ValueError("DOCX is missing word/_rels/document.xml.rels")
    relationship_id = _next_relationship_id(relationships)
    relationship = (
        f'<Relationship Id="{relationship_id}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
        f'Target="media/{escape(Path(media_name).name)}"/>'
    ).encode()
    if b"</Relationships>" not in relationships:
        raise ValueError("document relationships have no Relationships root")
    document.set_payload(
        relationships_name,
        relationships.replace(b"</Relationships>", relationship + b"</Relationships>", 1),
    )
    content_type = mimetypes.types_map.get(f".{extension}", f"image/{extension}")
    _ensure_content_type(document, extension, content_type)

    all_ids = [int(value) for value in re.findall(rb'<wp:docPr\b[^>]*\bid="(\d+)"', document.document_xml)]
    drawing_id = max(all_ids, default=0) + 1
    extent = int(round((block.width_cm or 12.0) * 360000))
    properties = _paragraph_properties(_template_paragraph(document, "body"))
    return (
        b"<w:p>" + properties + b"<w:r><w:drawing>"
        + f'<wp:inline xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing">'
          f'<wp:extent cx="{extent}" cy="{extent}"/><wp:docPr id="{drawing_id}" name="Revision Figure {drawing_id}"/>'
          '<a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
          '<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
          '<pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">'
          '<pic:blipFill><a:blip xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
          f'r:embed="{relationship_id}"/></pic:blipFill><pic:spPr/></pic:pic>'
          '</a:graphicData></a:graphic></wp:inline>'.encode()
        + b"</w:drawing></w:r></w:p>"
    )


def _render_blocks(document: DocxDocument, blocks: list[Block]) -> list[bytes]:
    rendered: list[bytes] = []
    for block in blocks:
        if not isinstance(block, Block):
            raise TypeError("blocks must contain Block values")
        if block.kind == "figure":
            rendered.append(_add_figure(document, block))
            continue
        properties = _paragraph_properties(_template_paragraph(document, block.kind))
        if block.kind == "caption":
            properties = _caption_properties(properties)
        rendered.append(
            b"<w:p>" + properties + _text_runs(block.text, caption=block.kind == "caption") + b"</w:p>"
        )
    return rendered


def _write_children(document: DocxDocument, children: list[bytes]) -> None:
    prefix, _, suffix = _body_parts(document.document_xml)
    document.set_payload("word/document.xml", prefix + b"".join(children) + suffix)


def replace_between_headings(
    doc: DocxDocument, start: str, end: str, blocks: list[Block]
) -> None:
    """Replace top-level body elements strictly between two unique headings."""
    start_index = _unique_heading_index(doc, start)
    end_index = _unique_heading_index(doc, end)
    if start_index >= end_index:
        raise ValueError("heading order is invalid: start must occur before end")
    _, children, _ = _body_parts(doc.document_xml)
    replacement = _render_blocks(doc, blocks)
    _write_children(doc, children[: start_index + 1] + replacement + children[end_index:])


def delete_between_headings(doc: DocxDocument, start: str, end: str) -> None:
    """Delete top-level body elements strictly between two unique headings."""
    replace_between_headings(doc, start, end, [])


def insert_before_heading(doc: DocxDocument, heading: str, blocks: list[Block]) -> None:
    """Insert blocks immediately before one uniquely matching heading."""
    index = _unique_heading_index(doc, heading)
    _, children, _ = _body_parts(doc.document_xml)
    insertion = _render_blocks(doc, blocks)
    _write_children(doc, children[:index] + insertion + children[index:])


def save_candidate(doc: DocxDocument, output: Path) -> None:
    """Atomically save a candidate, preserving unchanged member payload bytes."""
    output = Path(output)
    if output.resolve() == doc.source.resolve():
        raise ValueError("refusing to overwrite the source DOCX")
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.", suffix=".tmp", dir=output.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with zipfile.ZipFile(temporary, "w") as archive:
            for info in doc.infos:
                archive.writestr(info, doc.payloads[info.filename])
            for name in doc.new_members:
                archive.writestr(name, doc.payloads[name], compress_type=zipfile.ZIP_DEFLATED)
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
            flush_paragraph()
            image_path = (path.parent / image.group("path").strip()).resolve()
            blocks.append(Block("figure", image=image_path))
            if image.group("caption").strip():
                blocks.append(Block("caption", image.group("caption").strip()))
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
        if op == "replace":
            blocks = parse_fragment(revision_map.parent / operation["fragment"])
            replace_between_headings(
                document, operation["start_heading"], operation["end_heading"], blocks
            )
        elif op == "delete":
            delete_between_headings(document, operation["start_heading"], operation["end_heading"])
        elif op == "insert_before":
            blocks = parse_fragment(revision_map.parent / operation["fragment"])
            insert_before_heading(document, operation["heading"], blocks)
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
