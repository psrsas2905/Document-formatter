"""Generate a human-review QA report.

Human-in-the-loop by design: the pipeline targets 80-90% automation, and this
report is where the remaining uncertainty lands instead of being silently
guessed. It lists low-confidence / unknown blocks, heading-hierarchy jumps
(e.g. H1 -> H3), and images missing alt text.
"""

from __future__ import annotations

from pathlib import Path

from .classify import CONFIDENCE_THRESHOLD
from .models import BlockType, Document

_HEADING_RANK = {BlockType.HEADING1: 1, BlockType.HEADING2: 2, BlockType.HEADING3: 3}


def needs_review(block) -> bool:
    """True if a block should be surfaced for human review."""
    return block.label is BlockType.UNKNOWN or block.confidence < CONFIDENCE_THRESHOLD


def review_counts(doc: Document) -> tuple[int, int]:
    """(total blocks, blocks needing review) — shared by the report and batch."""
    return len(doc.blocks), sum(needs_review(b) for b in doc.blocks)


_HEADING_LABELS = {BlockType.HEADING1, BlockType.HEADING2, BlockType.HEADING3}


def heading_anchors(doc: Document) -> list[str | None]:
    """For each block, the text of the nearest heading *above* it (None before
    the first heading). Lets a reviewer locate a flagged block by section
    instead of scrolling — shared by the report and the GUI."""
    anchors: list[str | None] = []
    current: str | None = None
    for block in doc.blocks:
        anchors.append(current)  # heading in effect before this block (not itself)
        if block.label in _HEADING_LABELS:
            current = block.text
    return anchors


def write_report(doc: Document, out_path: str | Path) -> Path:
    """Write qa_report.md summarizing everything a human should double-check."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    anchors = heading_anchors(doc)
    uncertain = [
        (i, b, anchors[i - 1]) for i, b in enumerate(doc.blocks, 1) if needs_review(b)
    ]
    jumps = _hierarchy_jumps(doc)
    alt_issues = _missing_alt_text(doc)
    total = len(doc.blocks)
    auto = total - len(uncertain)

    lines = [
        "# QA Report",
        "",
        f"Source: `{doc.source_path or 'unknown'}`",
        f"Blocks processed: {total} — {auto} classified confidently, "
        f"{len(uncertain)} need review (threshold {CONFIDENCE_THRESHOLD}).",
        "",
    ]
    if doc.notes:
        lines += ["## Template / profile warnings", ""]
        lines += [f"- {note}" for note in doc.notes]
        lines += [""]
    lines += [
        "## Blocks needing human review",
        "",
    ]
    if uncertain:
        lines += [
            "| # | Under heading | Assigned label | Confidence | Text |",
            "|---|---------------|----------------|------------|------|",
        ]
        for i, b, anchor in uncertain:
            where = _snip(anchor, 40) if anchor else "_(document start)_"
            lines.append(
                f"| {i} | {where} | {b.label.value} | {b.confidence:.2f} | {_snip(b.text)} |"
            )
        lines += [
            "",
            "Check each block's assigned style in the output document and fix in "
            "Word if wrong.",
        ]
    else:
        lines.append("None — every block classified above the confidence threshold.")

    lines += ["", "## Heading hierarchy", ""]
    if jumps:
        for prev, cur, text in jumps:
            lines.append(
                f"- Level jump {prev} → {cur} at heading “{_snip(text, 60)}” "
                "(a level may be missing or misclassified)."
            )
    else:
        lines.append("No level jumps detected.")

    lines += ["", "## Images / alt text", ""]
    if alt_issues:
        lines += [f"- {msg}" for msg in alt_issues]
    else:
        lines.append("No image issues detected in the source body.")

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_path


def _hierarchy_jumps(doc: Document) -> list[tuple[int, int, str]]:
    """Headings that skip a level relative to the previous heading."""
    jumps = []
    prev = 0
    for b in doc.blocks:
        rank = _HEADING_RANK.get(b.label)
        if rank is None:
            continue
        if prev and rank > prev + 1:
            jumps.append((prev, rank, b.text))
        prev = rank
    return jumps


def _missing_alt_text(doc: Document) -> list[str]:
    """Inspect the source docx for inline images lacking alt text."""
    if not doc.source_path or not Path(doc.source_path).exists():
        return []
    import docx
    from docx.oxml.ns import qn

    src = docx.Document(doc.source_path)
    issues = []
    for i, shape in enumerate(src.inline_shapes, 1):
        doc_pr = shape._inline.find(qn("wp:docPr"))
        descr = doc_pr.get("descr") if doc_pr is not None else None
        if not descr:
            issues.append(f"Image {i} in the source has no alt text (add one for accessibility).")
    return issues


def _snip(text: str, limit: int = 70) -> str:
    text = text.replace("\n", " ").replace("|", "\\|")
    return text if len(text) <= limit else text[: limit - 1] + "…"
