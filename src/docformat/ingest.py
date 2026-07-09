"""Read a source .docx into the intermediate Document model.

Walks the body in order: paragraphs become Blocks carrying FormatHints (the
classifier's signals) plus Segments — the inline content in source order (text
with emphasis, OMML math carried as verbatim XML, images as blobs, footnote
references with their body text, unsupported OLE objects). Tables become TABLE
blocks carrying their original XML plus referenced image blobs. Empty
paragraphs — double-Enter spacing in messy drafts — are dropped: vertical
spacing comes from the template's styles, never from blank paragraphs.
"""

from __future__ import annotations

import re
from pathlib import Path

import docx
from docx.oxml.ns import qn
from lxml import etree

from .models import Block, Document, FormatHints, Segment

# Typed list markers at the start of a line: bullet glyphs, "1." / "1)", "a)" / "a.",
# and roman "iv)" variants. The marker is stripped from the text when styles apply.
BULLET_GLYPHS = "•‣◦▪-–*"
LIST_MARKER_RE = re.compile(
    rf"^(?:[{re.escape(BULLET_GLYPHS)}]|\d{{1,3}}[.)]|[a-z][.)]|[ivxl]{{1,5}}[.)])\s+",
    re.IGNORECASE,
)
SUB_MARKER_RE = re.compile(r"^(?:[a-z][.)]|[ivxl]{1,5}[.)])\s")

# A typed tab in the default template advances one 36pt (0.5") stop; treat each
# such stop as one list/indent level.
INDENT_PT_PER_LEVEL = 36.0

RT_FOOTNOTES = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/footnotes"
)
A_BLIP = "{http://schemas.openxmlformats.org/drawingml/2006/main}blip"
WP_EXTENT = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}extent"
WP_DOCPR = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}docPr"
M_OMATH = "{http://schemas.openxmlformats.org/officeDocument/2006/math}oMath"
M_OMATH_PARA = "{http://schemas.openxmlformats.org/officeDocument/2006/math}oMathPara"
R_EMBED = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed"


def ingest(source_path: str | Path) -> Document:
    """Parse source .docx -> Document of unlabeled blocks.

    Contract:
      - input: path to a .docx
      - output: Document with blocks populated, labels still UNKNOWN
    """
    source_path = Path(source_path)
    src = docx.Document(str(source_path))
    footnotes = _footnote_texts(src)

    blocks: list[Block] = []
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    for el in src.element.body:
        if el.tag == qn("w:p"):
            para = Paragraph(el, src)
            raw = para.text
            leading_tabs = len(raw) - len(raw.lstrip("\t"))
            text = raw.strip()
            segments = _segments_for(para, src, footnotes)
            if not text and not any(s.kind != "text" for s in segments):
                continue
            blocks.append(
                Block(
                    text=text,
                    hints=_hints_for(para, text, leading_tabs),
                    segments=segments,
                )
            )
        elif el.tag == qn("w:tbl"):
            table = Table(el, src)
            blocks.append(_table_block(table, src))

    title = src.core_properties.title or None
    return Document(blocks=blocks, title=title, source_path=str(source_path))


# --- inline segments ---------------------------------------------------------


def _segments_for(para, src, footnotes: dict[str, str]) -> list[Segment]:
    """Inline content of a paragraph in source order."""
    segments: list[Segment] = []
    for child in para._p:
        if child.tag == qn("w:r"):
            segments.extend(_run_segments(child, para, src, footnotes))
        elif child.tag == qn("w:hyperlink"):
            for run in child.findall(qn("w:r")):
                segments.extend(_run_segments(run, para, src, footnotes))
        elif child.tag in (M_OMATH, M_OMATH_PARA):
            segments.append(Segment(kind="math", xml=etree.tostring(child).decode()))
    return segments


def _run_segments(r_el, para, src, footnotes: dict[str, str]) -> list[Segment]:
    from docx.text.run import Run

    segments: list[Segment] = []

    fn_ref = r_el.find(qn("w:footnoteReference"))
    if fn_ref is not None:
        fn_id = fn_ref.get(qn("w:id"), "")
        segments.append(Segment(kind="footnote", text=footnotes.get(fn_id, "")))
        return segments

    if r_el.find(qn("w:object")) is not None:  # OLE (e.g. MathType) — can't carry
        run = Run(r_el, para)
        segments.append(Segment(kind="object", text=run.text))
        return segments

    for blip in r_el.iter(A_BLIP):
        rid = blip.get(R_EMBED)
        if not rid or rid not in src.part.related_parts:
            continue
        part = src.part.related_parts[rid]
        extent = next(iter(r_el.iter(WP_EXTENT)), None)
        doc_pr = next(iter(r_el.iter(WP_DOCPR)), None)
        segments.append(
            Segment(
                kind="image",
                blob=part.blob,
                ext=Path(str(part.partname)).suffix.lstrip(".") or "png",
                width_emu=int(extent.get("cx")) if extent is not None else None,
                height_emu=int(extent.get("cy")) if extent is not None else None,
                alt=(doc_pr.get("descr") or "") if doc_pr is not None else "",
            )
        )

    run = Run(r_el, para)
    if run.text:
        style = para.style
        segments.append(
            Segment(
                kind="text",
                text=run.text,
                bold=_effective(run.font.bold, style, "bold"),
                italic=_effective(run.font.italic, style, "italic"),
            )
        )
    return segments


def _footnote_texts(src) -> dict[str, str]:
    """Map footnote id -> plain text of its body, from the footnotes part."""
    try:
        part = src.part.part_related_by(RT_FOOTNOTES)
    except KeyError:
        return {}
    root = etree.fromstring(part.blob)
    texts: dict[str, str] = {}
    for fn in root.findall(qn("w:footnote")):
        if fn.get(qn("w:type")) in ("separator", "continuationSeparator"):
            continue
        body = "".join(t.text or "" for t in fn.iter(qn("w:t"))).strip()
        texts[fn.get(qn("w:id"), "")] = body
    return texts


# --- tables -------------------------------------------------------------------


def _table_block(table, src) -> Block:
    """A TABLE block: original XML plus the image blobs it references."""
    el = table._element
    resources: dict[str, tuple[bytes, str]] = {}
    for blip in el.iter(A_BLIP):
        rid = blip.get(R_EMBED)
        if rid and rid in src.part.related_parts:
            part = src.part.related_parts[rid]
            resources[rid] = (part.blob, Path(str(part.partname)).suffix.lstrip("."))
    preview = " | ".join(
        cell.text.strip() for cell in table.rows[0].cells if cell.text.strip()
    ) if table.rows else ""
    return Block(
        text=preview[:120],
        xml=etree.tostring(el).decode(),
        resources=resources,
    )


# --- paragraph hints -----------------------------------------------------------


def _hints_for(para, text: str, leading_tabs: int) -> FormatHints:
    """Distill a paragraph's raw formatting signals into FormatHints."""
    runs = [r for r in para.runs if r.text.strip()]

    sizes = [r.font.size.pt for r in runs if r.font.size is not None]
    font_size_pt = max(sizes) if sizes else _style_font_size(para.style)

    bold = bool(runs) and all(_effective(r.font.bold, para.style, "bold") for r in runs)
    italic = bool(runs) and all(_effective(r.font.italic, para.style, "italic") for r in runs)

    letters = [c for c in text if c.isalpha()]
    all_caps = bool(letters) and text.upper() == text

    # para.style is None when the paragraph references a style id the document
    # never defines (seen in real-world templates) — treat as unstyled.
    style_name = para.style.name if para.style is not None else None
    existing_style = style_name if style_name and style_name != "Normal" else None

    is_list_marker = LIST_MARKER_RE.match(text) is not None

    indent = para.paragraph_format.left_indent
    indent_pt = (indent.pt if indent is not None else 0.0) + leading_tabs * INDENT_PT_PER_LEVEL
    list_level = int(indent_pt // INDENT_PT_PER_LEVEL) if indent_pt > 0 else 0
    # "a)" / roman sub-markers imply nesting even without physical indent.
    if is_list_marker and list_level == 0 and SUB_MARKER_RE.match(text):
        list_level = 1

    return FormatHints(
        font_size_pt=font_size_pt,
        bold=bold,
        italic=italic,
        all_caps=all_caps,
        existing_style=existing_style,
        is_list_marker=is_list_marker,
        list_level=list_level,
    )


def _effective(run_value, style, attr: str) -> bool:
    """Resolve a run's tri-state font attribute, falling back to the paragraph style."""
    if run_value is not None:
        return run_value
    font = getattr(style, "font", None)
    return bool(font is not None and getattr(font, attr))


def _style_font_size(style) -> float | None:
    """Font size defined by the paragraph's style, if any."""
    font = getattr(style, "font", None)
    if font is not None and font.size is not None:
        return font.size.pt
    return None
