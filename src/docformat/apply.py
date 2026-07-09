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
    keep_cover = bool(profile.raw.get("cover_page", {}).get("keep"))
    cover_kept = _clear_body(out, keep_cover=keep_cover)
    if keep_cover and not cover_kept:
        doc.notes.append(
            "cover_page.keep is enabled but the template has no internal section "
            "break marking a cover page — nothing was kept."
        )
    # Resolve style OBJECTS by UI name and style id. Assigning the object (not
    # the name) sidesteps python-docx's builtin-name translation, which fails
    # on real-world templates whose styles carry nonstandard internal names.
    styles = _paragraph_styles(out)

    missing: dict[str, int] = {}
    for block in doc.blocks:
        style_name = _style_for_block(block, profile, set(styles))
        style = styles.get(style_name)
        if style is None:
            # Real-world templates often lack some mapped styles. Don't invent a
            # replacement: emit the paragraph unstyled (the template's document
            # defaults apply) and put the mismatch in the QA report.
            missing[style_name] = missing.get(style_name, 0) + 1
        text = block.text
        if block.label is BlockType.LIST_ITEM:
            text = LIST_MARKER_RE.sub("", text)
        para = out.add_paragraph(text)
        if style is not None:
            para.style = style

    for style_name, count in missing.items():
        doc.notes.append(
            f"Profile maps to style {style_name!r} but the template does not define "
            f"it — {count} paragraph(s) were left on the template's default "
            "formatting. Add the style to the template or fix the profile's style_map."
        )

    if doc.title:
        out.core_properties.title = doc.title
    out.save(out_path)
    return out_path


def _paragraph_styles(out) -> dict:
    """Paragraph styles keyed by UI name and by style id (first definition wins,
    so duplicate entries in malformed templates resolve deterministically)."""
    from docx.enum.style import WD_STYLE_TYPE

    styles: dict = {}
    for s in out.styles:
        if s.type == WD_STYLE_TYPE.PARAGRAPH:
            styles.setdefault(s.name, s)
            styles.setdefault(s.style_id, s)
    return styles


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


def _clear_body(out, keep_cover: bool = False) -> bool:
    """Remove the template's body content before pouring the draft in.

    With keep_cover, everything up to and including the template's first
    internal section break (i.e. the cover page section) is preserved.
    Returns True if a cover was kept.
    """
    from docx.oxml.ns import qn

    body = out.element.body
    cover_end = None
    if keep_cover:
        for el in body:
            pPr = el.find(qn("w:pPr"))
            if el.tag == qn("w:p") and pPr is not None and pPr.find(qn("w:sectPr")) is not None:
                cover_end = el  # paragraph carrying the cover section's break
                break

    in_cover = cover_end is not None
    for el in list(body):
        if el.tag == qn("w:sectPr"):
            continue  # the body-level section properties always stay
        if in_cover:
            if el is cover_end:
                in_cover = False
            continue  # keep cover content
        body.remove(el)
    return cover_end is not None


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
