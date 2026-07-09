"""Read a source .docx into the intermediate Document model.

Lossless enough for the classifier: each non-empty paragraph becomes a Block
whose FormatHints carry the raw signals (run-level font size/bold/italic, the
paragraph's existing style, and any typed list marker). Empty paragraphs —
double-Enter spacing in messy drafts — are dropped: vertical spacing comes from
the template's styles, never from blank paragraphs.
"""

from __future__ import annotations

import re
from pathlib import Path

import docx

from .models import Block, Document, FormatHints

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


def ingest(source_path: str | Path) -> Document:
    """Parse source .docx -> Document of unlabeled blocks.

    Contract:
      - input: path to a .docx
      - output: Document with blocks populated, labels still UNKNOWN
    """
    source_path = Path(source_path)
    src = docx.Document(str(source_path))

    blocks: list[Block] = []
    for para in src.paragraphs:
        raw = para.text
        leading_tabs = len(raw) - len(raw.lstrip("\t"))
        text = raw.strip()
        if not text:
            continue
        blocks.append(Block(text=text, hints=_hints_for(para, text, leading_tabs)))

    title = src.core_properties.title or None
    return Document(blocks=blocks, title=title, source_path=str(source_path))


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
