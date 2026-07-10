"""Apply the template's named styles to a classified Document.

Opens the profile's template file so the output inherits the template's style
definitions and page setup, empties its body (optionally keeping the cover
page), then pours each block in with the mapped named style.

Content preservation rules (per block, in source order):
  - text: re-emitted as fresh runs — paragraph-level direct formatting dies with
    the source. Inline bold/italic *emphasis* inside Body/List/Quote blocks is
    kept, unless the whole paragraph was uniformly bold/italic (that was
    decorative pseudo-heading formatting, which the named style replaces).
  - OMML math: carried verbatim — never re-rendered.
  - images: re-embedded from their blobs with original size and alt text.
  - footnotes: re-attached via the footnotes part (plain text).
  - tables: the original w:tbl is imported content-intact, image relationships
    rewritten, and the profile's table_style applied when the template has it.
  - OLE objects (e.g. MathType): cannot be carried — QA-flagged.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import docx
from docx.oxml import parse_xml
from docx.oxml.ns import qn
from docx.shared import Emu

from .footnotes import FootnoteWriter
from .ingest import A_BLIP, LIST_MARKER_RE, R_EMBED
from .models import BlockType, Document, Segment
from .template import TemplateProfile

_EMPHASIS_LABELS = {BlockType.BODY, BlockType.LIST_ITEM, BlockType.QUOTE}


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
    footnotes = FootnoteWriter(out)
    missing: dict[str, int] = {}
    objects = 0

    for block in doc.blocks:
        if block.label is BlockType.TABLE:
            _emit_table(out, block, profile, doc)
            continue
        style_name = _style_for_block(block, profile, set(styles))
        style = styles.get(style_name)
        if style is None:
            # Real-world templates often lack some mapped styles. Don't invent a
            # replacement: emit the paragraph unstyled (the template's document
            # defaults apply) and put the mismatch in the QA report.
            missing[style_name] = missing.get(style_name, 0) + 1
        objects += _emit_paragraph(out, block, style, footnotes)

    carried = footnotes.flush()
    if carried:
        doc.notes.append(
            f"{carried} footnote(s) carried over as plain text — verify their "
            "formatting and placement."
        )
    if objects:
        doc.notes.append(
            f"{objects} embedded object(s) (e.g. MathType/OLE) could not be carried "
            "over — only their fallback text was kept. Re-insert them manually."
        )
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


# --- paragraph emission -------------------------------------------------------


def _emit_paragraph(out, block, style, footnotes: FootnoteWriter) -> int:
    """Write one block as a paragraph; returns count of uncarriable objects."""
    para = out.add_paragraph()
    if style is not None:
        para.style = style

    segments = block.segments or [Segment(kind="text", text=block.text)]
    texts = [s for s in segments if s.kind == "text" and s.text.strip()]
    uniform_bold = bool(texts) and all(s.bold for s in texts)
    uniform_italic = bool(texts) and all(s.italic for s in texts)
    # Underline/strike are inline emphasis like bold/italic — a paragraph that is
    # uniformly underlined was decorative styling the named style now owns.
    uniform_underline = bool(texts) and all(s.underline for s in texts)
    uniform_strike = bool(texts) and all(s.strike for s in texts)
    keep_emphasis = block.label in _EMPHASIS_LABELS
    objects = 0
    lead_pending = True  # strip indentation/list markers from the leading text

    for seg in segments:
        if seg.kind == "text":
            text = seg.text
            if lead_pending:
                text = text.lstrip("\t ")
                if block.label is BlockType.LIST_ITEM:
                    text = LIST_MARKER_RE.sub("", text)
                if text:
                    lead_pending = False
            if not text:
                continue
            if seg.link:
                _append_hyperlink(out, para, text, seg.link)
                continue
            run = para.add_run(text)
            # Super/subscript carry meaning (x², H₂O) — preserve on every block,
            # never treated as decorative. vertAlign holds one value, so a run is
            # at most one of the two.
            if seg.superscript:
                run.font.superscript = True
            elif seg.subscript:
                run.font.subscript = True
            if keep_emphasis:
                if seg.bold and not uniform_bold:
                    run.font.bold = True
                if seg.italic and not uniform_italic:
                    run.font.italic = True
                if seg.underline and not uniform_underline:
                    run.font.underline = True
                if seg.strike and not uniform_strike:
                    run.font.strike = True
        elif seg.kind == "math":
            para._p.append(parse_xml(seg.xml))
            lead_pending = False
        elif seg.kind == "image" and seg.blob:
            run = para.add_run()
            size = {}
            if seg.width_emu:
                size["width"] = Emu(seg.width_emu)
            if seg.height_emu:
                size["height"] = Emu(seg.height_emu)
            picture = run.add_picture(BytesIO(seg.blob), **size)
            if seg.alt:
                picture._inline.docPr.set("descr", seg.alt)
            lead_pending = False
        elif seg.kind == "footnote":
            _append_footnote_ref(para, footnotes.add(seg.text))
        elif seg.kind == "object":
            if seg.text:
                para.add_run(seg.text)
            objects += 1
    return objects


RT_HYPERLINK = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink"
)


def _append_hyperlink(out, para, text: str, url: str) -> None:
    """Re-create an external hyperlink (new relationship in the output package)."""
    from docx.oxml import OxmlElement

    rid = out.part.relate_to(url, RT_HYPERLINK, is_external=True)
    h = OxmlElement("w:hyperlink")
    h.set(qn("r:id"), rid)
    run = OxmlElement("w:r")
    rpr = OxmlElement("w:rPr")
    rstyle = OxmlElement("w:rStyle")
    rstyle.set(qn("w:val"), "Hyperlink")  # honored when the template defines it
    rpr.append(rstyle)
    run.append(rpr)
    t = OxmlElement("w:t")
    t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    t.text = text
    run.append(t)
    h.append(run)
    para._p.append(h)


def _append_footnote_ref(para, fn_id: int) -> None:
    from docx.oxml import OxmlElement

    run = OxmlElement("w:r")
    rpr = OxmlElement("w:rPr")
    va = OxmlElement("w:vertAlign")
    va.set(qn("w:val"), "superscript")
    rpr.append(va)
    run.append(rpr)
    ref = OxmlElement("w:footnoteReference")
    ref.set(qn("w:id"), str(fn_id))
    run.append(ref)
    para._p.append(run)


# --- tables ---------------------------------------------------------------------


def _emit_table(out, block, profile: TemplateProfile, doc: Document) -> None:
    """Import the source table content-intact; restyle via the template.

    Relationship ids inside the carried XML are only meaningful in the SOURCE
    package — every one must be rewritten (images, hyperlinks) or stripped
    (anything else), or they rebind to arbitrary parts of the template and can
    corrupt the output.
    """
    tbl = parse_xml(block.xml)

    for blip in tbl.iter(A_BLIP):
        rid = blip.get(R_EMBED)
        if rid and rid in block.resources:
            blob, _ext = block.resources[rid]
            new_rid, _ = out.part.get_or_add_image(BytesIO(blob))
            blip.set(R_EMBED, new_rid)

    for h_el in list(tbl.iter(qn("w:hyperlink"))):
        rid = h_el.get(qn("r:id"))
        if rid and rid in block.links:
            new_rid = out.part.relate_to(block.links[rid], RT_HYPERLINK, is_external=True)
            h_el.set(qn("r:id"), new_rid)
        else:  # internal/unresolvable link: keep the text, drop the link
            parent = h_el.getparent()
            idx = list(parent).index(h_el)
            for child in reversed(list(h_el)):
                parent.insert(idx, child)
            parent.remove(h_el)

    _strip_foreign_rels(tbl, out, doc)

    style_name = profile.raw.get("table_style")
    if style_name:
        style = _table_style(out, style_name)
        if style is not None:
            _set_table_style(tbl, style.style_id)
        else:
            _note_once(
                doc,
                f"Profile sets table_style {style_name!r} but the template does not "
                "define that table style — tables keep their source formatting.",
            )

    body = out.element.body
    sect = body.find(qn("w:sectPr"))
    if sect is not None:
        sect.addprevious(tbl)
    else:
        body.append(tbl)


_R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def _strip_foreign_rels(tbl, out, doc: Document) -> None:
    """Remove any element still referencing a relationship id that does not
    exist in the OUTPUT package (charts, OLE, note refs inside cells...) —
    rewritten images/hyperlinks now hold valid output rids, so anything left
    is a dangling source-package reference that could rebind arbitrarily.
    Each removal is QA-noted."""
    valid = set(out.part.rels)
    dropped = 0
    for el in list(tbl.iter()):
        foreign = any(
            attr.startswith(f"{{{_R_NS}}}") and value not in valid
            for attr, value in el.attrib.items()
        )
        if not foreign:
            continue
        victim = el
        for ancestor in el.iterancestors():
            if ancestor.tag in (qn("w:drawing"), qn("w:object"), qn("w:pict")):
                victim = ancestor
                break
        parent = victim.getparent()
        if parent is not None:
            parent.remove(victim)
            dropped += 1
    if dropped:
        doc.notes.append(
            f"{dropped} embedded element(s) inside a carried table (chart, OLE "
            "object, or cross-reference) could not be transferred and were "
            "removed — re-insert them manually."
        )


def _table_style(out, name: str):
    from docx.enum.style import WD_STYLE_TYPE

    for s in out.styles:
        if s.type == WD_STYLE_TYPE.TABLE and name in (s.name, s.style_id):
            return s
    return None


def _set_table_style(tbl, style_id: str) -> None:
    """Point the table at the template's style; drop direct border formatting."""
    tbl_pr = tbl.find(qn("w:tblPr"))
    if tbl_pr is None:
        tbl_pr = parse_xml(
            '<w:tblPr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"/>'
        )
        tbl.insert(0, tbl_pr)
    for tag in ("w:tblStyle", "w:tblBorders"):
        el = tbl_pr.find(qn(tag))
        if el is not None:
            tbl_pr.remove(el)
    style_el = parse_xml(
        f'<w:tblStyle xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        f'w:val="{style_id}"/>'
    )
    tbl_pr.insert(0, style_el)


def _note_once(doc: Document, note: str) -> None:
    if note not in doc.notes:
        doc.notes.append(note)


# --- template plumbing ----------------------------------------------------------


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
