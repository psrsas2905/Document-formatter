"""Assemble template scaffolding: headers/footers, page numbers, captions, TOC.

TODO (Claude Code): implement after apply_styles works.
  - Header/footer text + page-number fields from the profile.
  - Auto-numbered Figure/Table captions.
  - Insert a TOC field and a List of Figures (fields; refreshed at export time).
Some of this needs lxml to write raw OOXML fields that python-docx can't.
"""

from __future__ import annotations

from pathlib import Path

from .template import TemplateProfile


def add_elements(docx_path: str | Path, profile: TemplateProfile) -> Path:
    """Add headers/footers/page numbers/TOC to an existing styled .docx."""
    raise NotImplementedError("add_elements(): headers, page numbers, TOC via lxml")
