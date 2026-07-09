"""Apply the template's named styles to a classified Document.

Opens the profile's template file so the output inherits the template's style
definitions and page setup, empties its body, then pours each block in with the
mapped named style. Blocks are re-written as fresh single-run paragraphs, so no
source direct formatting (hand-set sizes, bold, tabs) survives — the named style
is the only thing controlling appearance. Typed list markers are stripped
because the list style supplies its own bullet/number.
"""

from __future__ import annotations

from pathlib import Path

import docx

from .ingest import LIST_MARKER_RE
from .models import BlockType, Document
from .template import TemplateProfile


def apply_styles(doc: Document, profile: TemplateProfile, out_path: str | Path) -> Path:
    """Produce a styled .docx at out_path and return its path."""
    out_path = Path(out_path)
    template_path = _resolve_template(profile)

    out = docx.Document(str(template_path))
    _clear_body(out)
    available = {s.name for s in out.styles}

    for block in doc.blocks:
        style_name = _style_for_block(block, profile, available)
        if style_name not in available:
            raise ValueError(
                f"Style {style_name!r} (for {block.label.value}) not found in "
                f"template {template_path}. The template is the source of truth — "
                "fix the profile's style_map or the template."
            )
        text = block.text
        if block.label is BlockType.LIST_ITEM:
            text = LIST_MARKER_RE.sub("", text)
        out.add_paragraph(text, style=style_name)

    if doc.title:
        out.core_properties.title = doc.title
    out.save(out_path)
    return out_path


def _style_for_block(block, profile: TemplateProfile, available: set[str]) -> str:
    """Mapped style for the block's label; list items pick the level variant
    (e.g. 'List Bullet 2') when the template defines one."""
    label = block.label
    if label is BlockType.UNKNOWN:
        # Unclassifiable content is still emitted (as body) — qa.py reports it.
        label = BlockType.BODY
    style_name = profile.style_for(label.value)
    if style_name is None:
        raise ValueError(f"Profile {profile.name!r} has no style mapping for {label.value!r}")

    if label is BlockType.LIST_ITEM and block.hints.list_level > 0:
        leveled = f"{style_name} {block.hints.list_level + 1}"
        if leveled in available:
            return leveled
    return style_name


def _clear_body(out) -> None:
    """Remove any content the template document carries in its body."""
    for para in list(out.paragraphs):
        para._element.getparent().remove(para._element)
    for table in list(out.tables):
        table._element.getparent().remove(table._element)


def _resolve_template(profile: TemplateProfile) -> Path:
    """Template path as given (cwd-relative), else relative to the profile file."""
    path = Path(profile.template_file)
    if path.exists():
        return path
    profile_path = profile.raw.get("_profile_path")
    if profile_path:
        candidate = Path(profile_path).parent.parent / path
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        f"Template file {profile.template_file!r} not found (profile {profile.name!r})."
    )
