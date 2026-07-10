"""Intermediate data structures shared across the pipeline.

These are deliberately simple, framework-agnostic containers. `ingest` produces
them, `classify` labels them, `apply` consumes them. Keep them pure data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class BlockType(str, Enum):
    """The label assigned to each block. Maps to a template style via the profile."""

    HEADING1 = "Heading1"
    HEADING2 = "Heading2"
    HEADING3 = "Heading3"
    BODY = "Body"
    CAPTION = "Caption"
    LIST_ITEM = "ListItem"  # unordered (bullet) list item
    LIST_NUMBER = "ListNumber"  # ordered (1./a)/i)) list item
    QUOTE = "Quote"
    TABLE = "Table"  # carried through content-intact, restyled by the template
    UNKNOWN = "Unknown"  # could not classify confidently -> goes to QA report


@dataclass
class Segment:
    """One inline piece of a paragraph, in source order.

    kind:
      - "text":     `text` plus inline bold/italic emphasis and semantic
                    character formatting (super/subscript, underline, strike)
      - "math":     `xml` holds the original OMML (carried verbatim)
      - "image":    `blob`/`ext` hold the picture; size in EMU; `alt` its alt text
      - "footnote": `text` holds the footnote body text (re-attached on output)
      - "object":   embedded OLE object (e.g. MathType) — cannot be carried;
                    flagged in the QA report, `text` holds any fallback text
    """

    kind: str
    text: str = ""
    bold: bool = False
    italic: bool = False
    # Semantic character formatting. superscript/subscript carry *meaning*
    # (x², H₂O) and are preserved on every block; underline/strike are inline
    # emphasis, kept like bold/italic (Body/List/Quote, when not decorative).
    superscript: bool = False
    subscript: bool = False
    underline: bool = False
    strike: bool = False
    xml: str | None = None
    blob: bytes | None = None
    ext: str = "png"
    width_emu: int | None = None
    height_emu: int | None = None
    alt: str = ""
    # For text segments inside an external hyperlink: the target URL,
    # re-related in the output so links keep working.
    link: str | None = None


@dataclass
class FormatHints:
    """Raw formatting signals read from the source, used by the classifier."""

    font_size_pt: float | None = None
    bold: bool = False
    italic: bool = False
    all_caps: bool = False
    existing_style: str | None = None
    is_list_marker: bool = False
    # True when the paragraph carries Word-native list numbering (w:numPr).
    has_numbering: bool = False
    # True when that native numbering is an ordered format (decimal/letter/roman)
    # rather than a bullet — resolved from numbering.xml. Only meaningful when
    # has_numbering is True.
    list_ordered: bool = False
    list_level: int = 0


@dataclass
class Block:
    """One logical block of the source document (a paragraph or a table)."""

    text: str
    hints: FormatHints = field(default_factory=FormatHints)
    label: BlockType = BlockType.UNKNOWN
    confidence: float = 0.0  # 0..1; low values are flagged for human review
    # Inline content in source order; empty means plain text-only paragraph.
    segments: list[Segment] = field(default_factory=list)
    # For TABLE blocks: the original w:tbl XML, plus image blobs and external
    # hyperlink targets keyed by the relationship ids referenced in that XML.
    xml: str | None = None
    resources: dict[str, tuple[bytes, str]] = field(default_factory=dict)
    links: dict[str, str] = field(default_factory=dict)


@dataclass
class Document:
    """The whole document as an ordered list of blocks, plus metadata."""

    blocks: list[Block] = field(default_factory=list)
    title: str | None = None
    source_path: str | None = None
    # Pipeline-level warnings for the QA report (e.g. profile maps a label to a
    # style the template doesn't define). Human-readable sentences.
    notes: list[str] = field(default_factory=list)
