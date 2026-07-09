"""Read a source .docx into the intermediate Document model.

TODO (Claude Code): implement using python-docx.
For each paragraph, capture text and FormatHints (font size, bold, existing style,
list marker). Return a Document. Keep it lossless enough for the classifier to work.
"""

from __future__ import annotations

from pathlib import Path

from .models import Document


def ingest(source_path: str | Path) -> Document:
    """Parse source .docx -> Document of unlabeled blocks.

    Contract:
      - input: path to a .docx
      - output: Document with blocks populated, labels still UNKNOWN
    """
    raise NotImplementedError("ingest(): read paragraphs + FormatHints via python-docx")
