"""Assemble template scaffolding: headers/footers, page numbers, captions, TOC.

Operates on the already-styled .docx produced by apply_styles:
  - page size/margins from the profile
  - header/footer text with {page}/{pages}/{doc_title}/{version}/{classification}
    tokens — {page}/{pages} become real PAGE/NUMPAGES fields (lxml OOXML)
  - the template's own header/footer content (brand logo etc.) is PRESERVED;
    profile text is appended alongside it
  - TOC and List of Figures inserted as dirty field codes; LibreOffice (export
    stage) or Word refreshes them into real entries

Field codes need raw OOXML that python-docx has no API for, hence lxml here.
"""

from __future__ import annotations

import re
from pathlib import Path

import docx
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Mm

PAGE_SIZES_MM = {"A4": (210, 297), "Letter": (215.9, 279.4)}
FIELD_TOKENS = {"{page}": "PAGE", "{pages}": "NUMPAGES"}


def add_elements(docx_path: str | Path, profile) -> Path:
    """Add headers/footers/page numbers/TOC to an existing styled .docx."""
    docx_path = Path(docx_path)
    doc = docx.Document(str(docx_path))
    raw = profile.raw

    tokens = {
        "{doc_title}": doc.core_properties.title or "",
        "{version}": str(raw.get("output", {}).get("version", "")),
        "{classification}": str(raw.get("footer", {}).get("classification", "")),
    }

    _apply_page_setup(doc, raw.get("page", {}))
    _write_header_footer(doc, raw, tokens)
    _auto_number_captions(doc, profile)
    _insert_front_matter(doc, raw)

    doc.save(docx_path)
    return docx_path


# --- page setup -------------------------------------------------------------


def _apply_page_setup(doc, page: dict) -> None:
    size = PAGE_SIZES_MM.get(page.get("size", ""), None)
    margins = page.get("margins_mm", {})
    for section in doc.sections:
        if size:
            section.page_width, section.page_height = Mm(size[0]), Mm(size[1])
        for side in ("top", "bottom", "left", "right"):
            if side in margins:
                setattr(section, f"{side}_margin", Mm(margins[side]))


# --- header / footer --------------------------------------------------------


def _write_header_footer(doc, raw: dict, tokens: dict) -> None:
    header_spec = raw.get("header", {})
    footer_spec = raw.get("footer", {})

    for section in doc.sections:
        if header_spec.get("text"):
            _append_marginal_text(
                section.header, header_spec["text"], tokens, style_hint="Header",
                align=WD_ALIGN_PARAGRAPH.RIGHT,
            )
        if footer_spec.get("text"):
            _append_marginal_text(
                section.footer, footer_spec["text"], tokens, style_hint="Footer",
                align=WD_ALIGN_PARAGRAPH.CENTER,
            )
        if not header_spec.get("show_on_first_page", True):
            section.different_first_page_header_footer = True
            # First-page header/footer stay empty (created blank on demand).
            _ = section.first_page_header, section.first_page_footer

    doc.settings.element  # ensure settings part exists before saving


def _append_marginal_text(container, text: str, tokens: dict, style_hint: str, align) -> None:
    """Append one paragraph of profile text to a header/footer, preserving
    whatever the template already put there (e.g. the brand logo)."""
    container.is_linked_to_previous = False
    para = container.add_paragraph()
    try:
        para.style = style_hint
    except KeyError:
        pass
    para.alignment = align

    for token in tokens:
        text = text.replace(token, tokens[token])
    # Split on {page}/{pages} so those become live fields, not literals.
    for piece in re.split(r"(\{pages?\})", text):
        if piece in FIELD_TOKENS:
            _add_field_run(para, FIELD_TOKENS[piece])
        elif piece:
            para.add_run(piece)


def _add_field_run(para, instr: str, placeholder: str = "1") -> None:
    """Append a simple field (PAGE / NUMPAGES / SEQ ...) as raw OOXML."""
    fld = OxmlElement("w:fldSimple")
    fld.set(qn("w:instr"), f" {instr} ")
    run = OxmlElement("w:r")
    t = OxmlElement("w:t")
    t.text = placeholder  # shown until fields refresh
    run.append(t)
    fld.append(run)
    para._p.append(fld)


# --- captions ----------------------------------------------------------------

CAPTION_NUM_RE = re.compile(r"^(Figure|Table)\s+\d+(\s*[:.\-–]?\s*)(.*)$", re.IGNORECASE)


def _auto_number_captions(doc, profile) -> None:
    """Replace static 'Figure 1'/'Table 2' numbers in caption paragraphs with
    SEQ fields, so numbering self-heals and the List of Figures can find them."""
    caption_style = profile.style_map.get("Caption", "Caption")
    counters: dict[str, int] = {}
    for para in doc.paragraphs:
        if para.style.name != caption_style:
            continue
        m = CAPTION_NUM_RE.match(para.text)
        if not m:
            continue
        kind = m.group(1).capitalize()
        counters[kind] = counters.get(kind, 0) + 1
        sep, rest = m.group(2) or " ", m.group(3)

        for run in list(para.runs):
            run._element.getparent().remove(run._element)
        para.add_run(f"{kind} ")
        _add_field_run(para, rf"SEQ {kind} \* ARABIC", placeholder=str(counters[kind]))
        para.add_run(f"{sep}{rest}" if rest else "")


# --- TOC / List of Figures --------------------------------------------------


def _insert_front_matter(doc, raw: dict) -> None:
    """Insert TOC and List of Figures after the document title (or at start)."""
    anchor = _front_matter_anchor(doc)

    toc = raw.get("toc", {})
    lof = raw.get("list_of_figures", {})

    if toc.get("enabled"):
        max_level = int(toc.get("max_level", 3))
        anchor = _insert_field_block(
            doc, anchor, toc.get("title", "Table of Contents"),
            rf'TOC \o "1-{max_level}" \h \z \u',
        )
    if lof.get("enabled"):
        anchor = _insert_field_block(
            doc, anchor, lof.get("title", "List of Figures"),
            r'TOC \h \z \c "Figure"',
        )


def _front_matter_anchor(doc):
    """Element after which front matter goes: the leading H1 title, else None."""
    paras = doc.paragraphs
    if paras and paras[0].style.name == "Heading 1":
        return paras[0]._p
    return None


def _insert_field_block(doc, anchor, title: str, instr: str):
    """Insert '<title paragraph><dirty field paragraph>' after anchor.

    Returns the field paragraph element (the next block's anchor).
    """
    body = doc.element.body

    title_p = _make_paragraph(doc, title, _pick_style(doc, "TOC Heading", "Heading 1"))
    field_p = OxmlElement("w:p")
    fld = OxmlElement("w:fldSimple")
    fld.set(qn("w:instr"), f" {instr} ")
    fld.set(qn("w:dirty"), "true")
    run = OxmlElement("w:r")
    t = OxmlElement("w:t")
    t.text = "(updated on export)"
    run.append(t)
    fld.append(run)
    field_p.append(fld)

    if anchor is not None:
        anchor.addnext(title_p)
    else:
        body.insert(0, title_p)
    title_p.addnext(field_p)
    return field_p


def _make_paragraph(doc, text: str, style_name: str):
    para = doc.add_paragraph(text, style=style_name)
    para._p.getparent().remove(para._p)
    return para._p


def _pick_style(doc, preferred: str, fallback: str) -> str:
    names = {s.name for s in doc.styles}
    return preferred if preferred in names else fallback
