"""OPTIONAL offline AI classifier. Same signature as classify.classify().

Build this LAST, only after the deterministic path works end-to-end.

Design:
  - If a local LLM (Ollama) is reachable, use it to label ambiguous blocks.
  - If not reachable, fall back to the deterministic classifier.
  - MUST NOT require any network beyond localhost. The tool has to keep working
    when this returns nothing useful.
"""

from __future__ import annotations

from . import classify as _heuristic
from .models import Document


def classify_ai(doc: Document) -> Document:
    """AI-assisted labeling with a hard fallback to heuristics."""
    if not _ollama_available():
        return _heuristic.classify(doc)
    raise NotImplementedError("classify_ai(): call local Ollama, then fall back")


def _ollama_available() -> bool:
    """Return True if a local Ollama server responds. Offline-safe (localhost only)."""
    return False  # TODO: probe http://localhost:11434 with a short timeout
