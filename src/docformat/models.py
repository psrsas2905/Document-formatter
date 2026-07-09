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
    LIST_ITEM = "ListItem"
    QUOTE = "Quote"
    UNKNOWN = "Unknown"  # could not classify confidently -> goes to QA report


@dataclass
class FormatHints:
    """Raw formatting signals read from the source, used by the classifier."""

    font_size_pt: float | None = None
    bold: bool = False
    italic: bool = False
    all_caps: bool = False
    existing_style: str | None = None
    is_list_marker: bool = False
    list_level: int = 0


@dataclass
class Block:
    """One logical paragraph of the source document."""

    text: str
    hints: FormatHints = field(default_factory=FormatHints)
    label: BlockType = BlockType.UNKNOWN
    confidence: float = 0.0  # 0..1; low values are flagged for human review


@dataclass
class Document:
    """The whole document as an ordered list of blocks, plus metadata."""

    blocks: list[Block] = field(default_factory=list)
    title: str | None = None
    source_path: str | None = None
