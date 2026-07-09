"""Apply the template's named styles to a classified Document.

TODO (Claude Code): open the profile's template_file with python-docx, then for
each block: clear direct formatting and apply the mapped named style. Write a new
.docx. This is the first visible win — verify output opens cleanly in Word.
"""

from __future__ import annotations

from pathlib import Path

from .models import Document
from .template import TemplateProfile


def apply_styles(doc: Document, profile: TemplateProfile, out_path: str | Path) -> Path:
    """Produce a styled .docx at out_path and return its path."""
    raise NotImplementedError("apply_styles(): map BlockType -> named style, write docx")
