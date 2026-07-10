"""Human classification overrides — make manual fixes survive re-runs.

The classifier is ~80-90% right; a writer inevitably corrects the rest by hand.
Without a record, the next run of the same draft throws those corrections away.
This module closes that loop:

  - `--dry-run` writes a *plan*: an editable YAML listing the blocks the
    classifier was unsure about (plus a full document map, as comments, so any
    block can be pinned by index). No document is produced.
  - `--overrides FILE` re-applies those human decisions after classification and
    before styling. A pinned block is trusted (confidence 1.0) so it no longer
    nags in QA. Each pin is guarded by a text snippet: if the draft shifted and
    the snippet no longer matches, the pin is skipped and QA-noted rather than
    silently landing on the wrong paragraph.

The file is plain YAML a non-programmer can edit; labels are the BlockType
values (Heading1/Heading2/Heading3/Body/Caption/ListItem/Quote).
"""

from __future__ import annotations

from pathlib import Path

import yaml

from .classify import CONFIDENCE_THRESHOLD
from .models import BlockType, Document

# Labels a human may assign (structural TABLE / UNKNOWN are not hand-pinnable).
ASSIGNABLE = [
    BlockType.HEADING1,
    BlockType.HEADING2,
    BlockType.HEADING3,
    BlockType.BODY,
    BlockType.CAPTION,
    BlockType.LIST_ITEM,
    BlockType.QUOTE,
]
_ASSIGNABLE_VALUES = {b.value for b in ASSIGNABLE}

_PREVIEW_LEN = 60


def _preview(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= _PREVIEW_LEN else text[: _PREVIEW_LEN - 1] + "…"


def _snippet_matches(block_text: str, snippet: str) -> bool:
    """Whether `snippet` still identifies this block's text.

    Uses a prefix match against normalized text so a hand-copied or truncated
    snippet (the plan shows previews cut with '…') still matches, while genuinely
    different text — the draft was edited here — does not.
    """
    full = " ".join(block_text.split())
    want = " ".join(snippet.split()).rstrip("…").strip()
    if not want:
        return True  # no snippet given -> caller opted out of the drift guard
    return full.startswith(want) or want.startswith(full)


def write_plan(doc: Document, out_path: str | Path, source: str | None = None) -> Path:
    """Write an editable classification plan (a dry-run preview) for `doc`."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    source = source or doc.source_path or "unknown"

    review = [
        (i, b)
        for i, b in enumerate(doc.blocks)
        if b.label is BlockType.UNKNOWN or b.confidence < CONFIDENCE_THRESHOLD
    ]

    lines = [
        f"# Classification plan for {source}",
        "#",
        "# Edit the `label` of any row the classifier got wrong, then re-run:",
        "#   docformat format <input> -t <profile> --overrides <this file>",
        f"# Valid labels: {', '.join(sorted(_ASSIGNABLE_VALUES))}",
        "#",
        "# Pre-filled below are the blocks the classifier was unsure about. To pin",
        "# a block it was confident about, copy its index from the document map at",
        "# the bottom and add a row here.",
        "",
        f"source: {source}",
        "overrides:",
    ]
    if review:
        for i, b in review:
            lines.append(f"  - index: {i}")
            lines.append(f"    label: {b.label.value}")
            lines.append(f'    text: "{_yaml_str(_preview(b.text))}"')
    else:
        lines.append("  []  # nothing below the confidence threshold — all good")

    lines += ["", "# --- document map (reference only; edit rows above) ---"]
    for i, b in enumerate(doc.blocks):
        flag = "  <-- review" if (b.label is BlockType.UNKNOWN or b.confidence < CONFIDENCE_THRESHOLD) else ""
        lines.append(f"#  [{i}] {b.label.value} ({b.confidence:.2f}): {_preview(b.text)}{flag}")

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_path


def _yaml_str(text: str) -> str:
    """Escape a preview for a double-quoted YAML scalar."""
    return text.replace("\\", "\\\\").replace('"', '\\"')


def apply_overrides(doc: Document, path: str | Path) -> int:
    """Apply a classification-plan file to `doc` in place; return #pins applied.

    Mismatches (bad label, out-of-range index, drifted text) are appended to
    doc.notes for the QA report instead of failing the run.
    """
    path = Path(path)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"Overrides file {path} is not valid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"Overrides file {path} must be a YAML mapping with an 'overrides:' list.")

    rows = data.get("overrides") or []
    if not isinstance(rows, list):
        raise ValueError(f"Overrides file {path}: 'overrides' must be a list.")

    applied = 0
    for row in rows:
        if not isinstance(row, dict) or "index" not in row or "label" not in row:
            doc.notes.append(
                f"Override skipped — each entry needs 'index' and 'label' (got {row!r})."
            )
            continue
        index, label = row["index"], str(row["label"])
        if not isinstance(index, int) or not 0 <= index < len(doc.blocks):
            doc.notes.append(
                f"Override for index {index!r} skipped — out of range "
                f"(document has {len(doc.blocks)} blocks)."
            )
            continue
        if label not in _ASSIGNABLE_VALUES:
            doc.notes.append(
                f"Override for block {index} skipped — {label!r} is not a valid label "
                f"({', '.join(sorted(_ASSIGNABLE_VALUES))})."
            )
            continue

        block = doc.blocks[index]
        if block.label is BlockType.TABLE:
            doc.notes.append(
                f"Override for block {index} skipped — it is a table (structural, not "
                "hand-labelled)."
            )
            continue

        snippet = row.get("text")
        if snippet and not _snippet_matches(block.text, str(snippet)):
            doc.notes.append(
                f"Override for block {index} skipped — the draft changed here "
                f"(expected “{_preview(str(snippet))}”, found “{_preview(block.text)}”). "
                "Re-run --dry-run to refresh the plan."
            )
            continue

        block.label = BlockType(label)
        block.confidence = 1.0  # human-reviewed → trusted, drops out of QA
        applied += 1

    doc.notes.append(
        f"{applied} manual classification override(s) applied from {path.name}."
    )
    return applied
