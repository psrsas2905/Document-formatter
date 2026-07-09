"""Deterministic, heuristic classifier. NO AI. This is the core engine.

TODO (Claude Code): implement the heuristics from PROJECT_SPEC section 5.
Assign a BlockType and a confidence (0..1) to every block. Anything below
CONFIDENCE_THRESHOLD should remain low-confidence so QA can flag it.
"""

from __future__ import annotations

from .models import Document

CONFIDENCE_THRESHOLD = 0.6


def classify(doc: Document) -> Document:
    """Label every block in-place and return the Document.

    Heuristics (see spec): relative font size -> heading level; short+bold+no
    trailing period -> heading; 'Figure N'/'Table N' -> caption; list markers ->
    list items; valid existing style -> trust it; else -> body.
    """
    raise NotImplementedError("classify(): implement heuristics from PROJECT_SPEC §5")
