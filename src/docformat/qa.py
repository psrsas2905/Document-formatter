"""Generate a human-review QA report.

TODO (Claude Code): list every block below the confidence threshold, any UNKNOWN
blocks, missing image alt text, and broken heading hierarchy (e.g. H1 -> H3 jump).
Output a readable qa_report.md.
"""

from __future__ import annotations

from pathlib import Path

from .models import Document


def write_report(doc: Document, out_path: str | Path) -> Path:
    """Write qa_report.md summarizing everything a human should double-check."""
    raise NotImplementedError("write_report(): low-confidence blocks, alt text, hierarchy")
