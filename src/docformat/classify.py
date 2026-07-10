"""Deterministic, heuristic classifier. NO AI. This is the core engine.

Implements PROJECT_SPEC §5. Rules fire in trust order:
  1. an existing recognized template style wins outright;
  2. Figure/Table caption prefixes;
  3. typed list markers;
  4. font size larger than body -> heading, ranked largest=H1, next=H2, ...;
  5. short + bold + no trailing period at body size -> heading (level uncertain,
     so confidence lands below the QA threshold on purpose);
  6. indented italic -> quote;
  7. everything else -> body.

Every label carries a confidence in 0..1; anything below CONFIDENCE_THRESHOLD
is surfaced by qa.py for human review rather than silently trusted.
"""

from __future__ import annotations

import re

from .models import Block, BlockType, Document

CONFIDENCE_THRESHOLD = 0.6

# Font sizes within this tolerance of body size count as body-sized.
SIZE_TOLERANCE_PT = 0.5
# Default effective size when neither run nor style specifies one (Word's Normal).
DEFAULT_BODY_PT = 11.0
HEADING_MAX_WORDS = 12

CAPTION_RE = re.compile(r"^(figure|table)\s+\d+", re.IGNORECASE)
# "1 Title" / "1. Title" / "2.1 Title" / "1.0 TITLE" — section numbering at
# line start; group 2 records whether the number carries list-ish punctuation.
NUMBERED_RE = re.compile(r"^(\d{1,2}(?:\.\d{1,2}){0,3})([.)]?)\s+\S")
# Single-level "1." / "1)" item — used for run-of-items sequence detection.
SINGLE_NUM_ITEM_RE = re.compile(r"^\d{1,3}[.)]\s+")

# Built-in style names we recognize as already-valid labels (spec: trust them).
STYLE_TO_LABEL: dict[str, BlockType] = {
    "Title": BlockType.HEADING1,
    "Heading 1": BlockType.HEADING1,
    "Heading 2": BlockType.HEADING2,
    "Heading 3": BlockType.HEADING3,
    "Body Text": BlockType.BODY,
    "Caption": BlockType.CAPTION,
    "List Bullet": BlockType.LIST_ITEM,
    "List Number": BlockType.LIST_ITEM,
    "Quote": BlockType.QUOTE,
    "Intense Quote": BlockType.QUOTE,
}

_HEADING_LEVELS = [BlockType.HEADING1, BlockType.HEADING2, BlockType.HEADING3]


def classify(doc: Document) -> Document:
    """Label every block in-place and return the Document."""
    body_pt = _body_size(doc.blocks)
    size_rank = _heading_size_rank(doc.blocks, body_pt)

    is_num_item = [bool(SINGLE_NUM_ITEM_RE.match(b.text)) for b in doc.blocks]
    for i, block in enumerate(doc.blocks):
        neighbors_long = (
            i > 0
            and i + 1 < len(doc.blocks)
            and len(doc.blocks[i - 1].text) > 100
            and len(doc.blocks[i + 1].text) > 100
        )
        # "1." near other "N." lines is a run of list items, not a heading.
        in_sequence = any(
            is_num_item[j]
            for j in range(max(0, i - 2), min(len(doc.blocks), i + 3))
            if j != i
        )
        block.label, block.confidence = _classify_block(
            block, body_pt, size_rank, neighbors_long, in_sequence
        )

    if doc.title is None:
        doc.title = next(
            (b.text for b in doc.blocks if b.label is BlockType.HEADING1), None
        )
    return doc


def _classify_block(
    block: Block,
    body_pt: float,
    size_rank: dict[float, BlockType],
    neighbors_long: bool = False,
    in_sequence: bool = False,
) -> tuple[BlockType, float]:
    h = block.hints
    text = block.text

    # 0. Tables are structural, not stylistic — carried through as-is.
    if block.xml is not None:
        return BlockType.TABLE, 1.0

    # 1. Block already carries a valid template style name -> trust it.
    if h.existing_style in STYLE_TO_LABEL:
        return STYLE_TO_LABEL[h.existing_style], 1.0

    # 2. Starts with "Figure N" / "Table N" -> caption.
    if CAPTION_RE.match(text):
        return BlockType.CAPTION, 0.95

    # 3. Word-native list numbering (w:numPr) is definitive — the ribbon list
    #    button was used; the visible number/bullet lives in numbering.xml.
    if h.has_numbering:
        return BlockType.LIST_ITEM, 0.95

    size = h.font_size_pt if h.font_size_pt is not None else DEFAULT_BODY_PT
    is_short = len(text.split()) <= HEADING_MAX_WORDS and not text.rstrip().endswith(".")

    # 4. Number-led lines: decide heading vs list item BEFORE the generic list
    #    rule, or "1. Introduction" headings become bullets with the number
    #    deleted.
    m = NUMBERED_RE.match(text)
    if m:
        parts = m.group(1).split(".")
        if len(parts) > 1 and parts[-1] == "0":
            parts = parts[:-1]  # "1.0 PURPOSE" convention counts as level 1
        multi_level = len(parts) > 1
        punctuated = bool(m.group(2))

        if multi_level and is_short:
            level = min(len(parts), len(_HEADING_LEVELS))
            return _HEADING_LEVELS[level - 1], 0.9 if h.bold else 0.85
        if not multi_level and punctuated:
            # "1. xxx": sentence-like or part of a numbered run -> list item;
            # a lone short one is genuinely ambiguous -> low confidence (QA).
            if not is_short or in_sequence:
                return BlockType.LIST_ITEM, 0.9
            if h.bold:
                return BlockType.HEADING1, 0.85
            return BlockType.LIST_ITEM, 0.55
        if not multi_level and not punctuated and is_short and h.bold:
            return BlockType.HEADING1, 0.9
        # bare "5 people attended..." carries no heading signal: fall through.

    # 5. Typed bullet/letter/roman marker -> list item (level already in hints).
    if h.is_list_marker:
        return BlockType.LIST_ITEM, 0.9

    # 6. Larger than body -> heading; level from the document-wide size ranking.
    if size in size_rank:
        confidence = 0.9 if (h.bold or is_short) else 0.7
        return size_rank[size], confidence

    # 7. Short + bold + no trailing period at body size -> heading, but the level
    #    is a guess (one deeper than the deepest size-derived heading), so keep
    #    confidence under the threshold to route it to the QA report.
    if h.bold and is_short:
        deepest = max(
            (_HEADING_LEVELS.index(lbl) for lbl in size_rank.values()), default=-1
        )
        level = min(deepest + 1, len(_HEADING_LEVELS) - 1)
        return _HEADING_LEVELS[level], 0.55

    # 8. Indented italic -> quote.
    if h.italic and h.list_level > 0:
        return BlockType.QUOTE, 0.7

    # 9. Short plain line sandwiched between long paragraphs -> likely a
    #     heading whose formatting was lost; level unknowable, so it stays
    #     under the threshold and reaches the QA report.
    if (
        neighbors_long
        and len(text) < 40
        and is_short
        and not h.italic
        and not text.rstrip().endswith((":", ";", ","))
    ):
        return BlockType.HEADING2, 0.55

    # 10. Everything else -> body.
    return BlockType.BODY, 0.8


def _body_size(blocks: list[Block]) -> float:
    """Most common effective font size across blocks — assumed to be body text."""
    counts: dict[float, int] = {}
    for b in blocks:
        size = b.hints.font_size_pt if b.hints.font_size_pt is not None else DEFAULT_BODY_PT
        counts[size] = counts.get(size, 0) + 1
    return max(counts, key=lambda s: counts[s]) if counts else DEFAULT_BODY_PT


def _heading_size_rank(blocks: list[Block], body_pt: float) -> dict[float, BlockType]:
    """Map each distinct larger-than-body size to a heading level, largest = H1."""
    larger = sorted(
        {
            b.hints.font_size_pt
            for b in blocks
            if b.hints.font_size_pt is not None
            and b.hints.font_size_pt > body_pt + SIZE_TOLERANCE_PT
            and b.hints.existing_style is None  # styled blocks are handled by rule 1
        },
        reverse=True,
    )
    return {size: _HEADING_LEVELS[min(i, 2)] for i, size in enumerate(larger)}
