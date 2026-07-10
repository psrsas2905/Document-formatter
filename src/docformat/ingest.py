"""Read a source .docx into the intermediate Document model.

Walks the body in order: paragraphs become Blocks carrying FormatHints (the
classifier's signals) plus Segments — the inline content in source order (text
with emphasis and hyperlink targets, OMML math carried as verbatim XML, images
as blobs, foot/endnote references with their body text, unsupported OLE
objects). Tables become TABLE blocks carrying their original XML plus
referenced image blobs and hyperlink targets. Empty paragraphs — double-Enter
spacing in messy drafts — are dropped: vertical spacing comes from the
template's styles, never from blank paragraphs.

Nothing is dropped silently. Content the pipeline cannot carry — comments,
text-box text, legacy VML images — and content it converts — tracked changes
(auto-accepted), field codes (frozen to their cached text), internal links
(flattened) — is counted here and lands in the QA report via Document.notes.
"""

from __future__ import annotations

import re
from pathlib import Path

import docx
from docx.oxml.ns import qn
from lxml import etree

from .models import Block, Document, FormatHints, Segment

# Typed list markers at the start of a line: bullet glyphs, "1." / "1)", and
# lowercase "a)" / roman "iv)" sub-markers. Deliberately case-sensitive for the
# letter forms: "A. Smith et al." is prose (or an appendix heading), not a list.
BULLET_GLYPHS = "•‣◦▪-–*"
LIST_MARKER_RE = re.compile(
    rf"^(?:[{re.escape(BULLET_GLYPHS)}]|\d{{1,3}}[.)]|[a-z][.)]|[ivxl]{{1,5}}[.)])\s+"
)
SUB_MARKER_RE = re.compile(r"^(?:[a-z][.)]|[ivxl]{1,5}[.)])\s")

# A typed tab in the default template advances one 36pt (0.5") stop; treat each
# such stop as one list/indent level.
INDENT_PT_PER_LEVEL = 36.0

_RT = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
RT_FOOTNOTES = f"{_RT}/footnotes"
RT_ENDNOTES = f"{_RT}/endnotes"
RT_COMMENTS = f"{_RT}/comments"
A_BLIP = "{http://schemas.openxmlformats.org/drawingml/2006/main}blip"
WP_EXTENT = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}extent"
WP_DOCPR = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}docPr"
M_OMATH = "{http://schemas.openxmlformats.org/officeDocument/2006/math}oMath"
M_OMATH_PARA = "{http://schemas.openxmlformats.org/officeDocument/2006/math}oMathPara"
R_EMBED = f"{{{_RT}}}embed"
R_ID = f"{{{_RT}}}id"
V_IMAGEDATA = "{urn:schemas-microsoft-com:vml}imagedata"
W_TXBX = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}txbxContent"


class _Stats:
    """Counters for converted/dropped content, rendered into QA notes."""

    def __init__(self) -> None:
        self.insertions = 0
        self.deletions = 0
        self.fields = 0
        self.internal_links = 0
        self.endnotes = 0
        self.textboxes = 0
        self.vml_images = 0
        self.comments: list[str] = []

    def notes(self) -> list[str]:
        out = []
        if self.insertions or self.deletions:
            out.append(
                f"Tracked changes were auto-accepted: {self.insertions} insertion(s) "
                f"kept, {self.deletions} deletion(s) removed. Review if the draft was "
                "mid-review."
            )
        if self.fields:
            out.append(
                f"{self.fields} field code(s) (cross-references, dates, ...) were "
                "frozen to their last-updated text — verify the values still hold."
            )
        if self.internal_links:
            out.append(
                f"{self.internal_links} within-document link(s) were flattened to "
                "plain text (bookmarks are not carried)."
            )
        if self.endnotes:
            out.append(f"{self.endnotes} endnote(s) were carried over as footnotes.")
        if self.textboxes:
            out.append(
                f"{self.textboxes} text box(es) containing text were dropped — "
                "copy their content across manually."
            )
        if self.vml_images:
            out.append(
                f"{self.vml_images} legacy (VML) image(s) could not be carried over."
            )
        out.extend(
            f"Comment dropped ({author}): “{excerpt}”" for author, excerpt in self.comments
        )
        return out


def ingest(source_path: str | Path) -> Document:
    """Parse source .docx -> Document of unlabeled blocks.

    Contract:
      - input: path to a .docx
      - output: Document with blocks populated, labels still UNKNOWN
    """
    source_path = Path(source_path)
    src = docx.Document(str(source_path))
    notes_ctx = {
        "footnotes": _note_texts(src, RT_FOOTNOTES, "w:footnote"),
        "endnotes": _note_texts(src, RT_ENDNOTES, "w:endnote"),
    }
    stats = _Stats()
    stats.comments = _comment_texts(src)

    numbering = _numbering_formats(src)
    blocks: list[Block] = []
    _walk_body(src.element.body, src, blocks, notes_ctx, stats, numbering)

    doc = Document(
        blocks=blocks,
        title=src.core_properties.title or None,
        source_path=str(source_path),
    )
    doc.notes.extend(stats.notes())
    return doc


def _walk_body(container, src, blocks: list[Block], notes_ctx, stats: _Stats, numbering) -> None:
    """Collect blocks from a body-level container, descending into content
    controls (w:sdt) so their wrapped paragraphs/tables are not lost."""
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    for el in container:
        if el.tag == qn("w:p"):
            para = Paragraph(el, src)
            segments = _segments_for(el, para, src, notes_ctx, stats)
            text = "".join(s.text for s in segments if s.kind in ("text", "object"))
            leading_tabs = len(text) - len(text.lstrip("\t"))
            text = text.strip()
            if not text and not any(s.kind != "text" for s in segments):
                continue
            blocks.append(
                Block(text=text, hints=_hints_for(para, text, leading_tabs, numbering),
                      segments=segments)
            )
        elif el.tag == qn("w:tbl"):
            blocks.append(_table_block(Table(el, src), src))
        elif el.tag == qn("w:sdt"):
            content = el.find(qn("w:sdtContent"))
            if content is not None:
                _walk_body(content, src, blocks, notes_ctx, stats, numbering)


# --- inline segments ---------------------------------------------------------


def _segments_for(p_el, para, src, notes_ctx, stats: _Stats) -> list[Segment]:
    """Inline content of a paragraph in source order.

    Descends into tracked insertions (kept), hyperlinks (target captured),
    simple fields (frozen to cached text) and inline content controls;
    tracked deletions are skipped (= accepted). Text boxes and VML images
    can't be carried and are counted for the QA report.
    """
    segments: list[Segment] = []
    _collect_inline(p_el, para, src, notes_ctx, stats, segments, link=None)
    return segments


def _collect_inline(el, para, src, notes_ctx, stats, segments, link) -> None:
    for child in el:
        tag = child.tag
        if tag == qn("w:r"):
            segments.extend(_run_segments(child, para, src, notes_ctx, stats, link))
        elif tag == qn("w:hyperlink"):
            target = _hyperlink_target(child, src)
            if target is None and (
                child.get(qn("w:anchor")) or child.get(R_ID)
            ):
                stats.internal_links += 1
            _collect_inline(child, para, src, notes_ctx, stats, segments, link=target)
        elif tag == qn("w:ins"):  # tracked insertion -> accept it
            stats.insertions += 1
            _collect_inline(child, para, src, notes_ctx, stats, segments, link=link)
        elif tag == qn("w:del"):  # tracked deletion -> accept (drop content)
            stats.deletions += 1
        elif tag == qn("w:fldSimple"):  # freeze the field to its cached text
            stats.fields += 1
            _collect_inline(child, para, src, notes_ctx, stats, segments, link=link)
        elif tag == qn("w:sdt"):  # inline content control -> unwrap
            content = child.find(qn("w:sdtContent"))
            if content is not None:
                _collect_inline(content, para, src, notes_ctx, stats, segments, link=link)
        elif tag == qn("w:smartTag"):
            _collect_inline(child, para, src, notes_ctx, stats, segments, link=link)
        elif tag in (M_OMATH, M_OMATH_PARA):
            segments.append(Segment(kind="math", xml=etree.tostring(child).decode()))


def _hyperlink_target(h_el, src) -> str | None:
    """External URL of a hyperlink element, or None for internal anchors."""
    rid = h_el.get(R_ID)
    if rid and rid in src.part.rels and src.part.rels[rid].is_external:
        return src.part.rels[rid].target_ref
    return None


def _run_segments(r_el, para, src, notes_ctx, stats: _Stats, link) -> list[Segment]:
    from docx.text.run import Run

    segments: list[Segment] = []

    fn_ref = r_el.find(qn("w:footnoteReference"))
    if fn_ref is not None:
        fn_id = fn_ref.get(qn("w:id"), "")
        segments.append(
            Segment(kind="footnote", text=notes_ctx["footnotes"].get(fn_id, ""))
        )
        return segments

    en_ref = r_el.find(qn("w:endnoteReference"))
    if en_ref is not None:
        en_id = en_ref.get(qn("w:id"), "")
        stats.endnotes += 1
        segments.append(
            Segment(kind="footnote", text=notes_ctx["endnotes"].get(en_id, ""))
        )
        return segments

    if r_el.find(qn("w:commentReference")) is not None:
        return segments  # comment bodies are QA-reported at document level

    if r_el.find(qn("w:object")) is not None:  # OLE (e.g. MathType) — can't carry
        run = Run(r_el, para)
        segments.append(Segment(kind="object", text=run.text))
        return segments

    # Text boxes and legacy VML images can't be carried — count for QA.
    for txbx in r_el.iter(W_TXBX):
        if "".join(t.text or "" for t in txbx.iter(qn("w:t"))).strip():
            stats.textboxes += 1
    if next(iter(r_el.iter(V_IMAGEDATA)), None) is not None:
        stats.vml_images += 1

    for blip in r_el.iter(A_BLIP):
        rid = blip.get(R_EMBED)
        if not rid or rid not in src.part.related_parts:
            continue
        part = src.part.related_parts[rid]
        extent = next(iter(r_el.iter(WP_EXTENT)), None)
        doc_pr = next(iter(r_el.iter(WP_DOCPR)), None)
        cx = extent.get("cx") if extent is not None else None
        cy = extent.get("cy") if extent is not None else None
        segments.append(
            Segment(
                kind="image",
                blob=part.blob,
                ext=Path(str(part.partname)).suffix.lstrip(".") or "png",
                width_emu=int(cx) if cx and cx.isdigit() else None,
                height_emu=int(cy) if cy and cy.isdigit() else None,
                alt=(doc_pr.get("descr") or "") if doc_pr is not None else "",
            )
        )

    run = Run(r_el, para)
    if run.text:
        style = para.style
        font = run.font
        segments.append(
            Segment(
                kind="text",
                text=run.text,
                bold=_effective(font.bold, style, "bold"),
                italic=_effective(font.italic, style, "italic"),
                # Semantic character formatting. superscript/subscript come from
                # w:vertAlign; underline may be an enum (WD_UNDERLINE.*) so we
                # coerce to a plain bool.
                superscript=_effective(font.superscript, style, "superscript"),
                subscript=_effective(font.subscript, style, "subscript"),
                underline=_effective(font.underline, style, "underline"),
                strike=_effective(font.strike, style, "strike"),
                link=link,
            )
        )
    return segments


def _note_texts(src, reltype: str, element: str) -> dict[str, str]:
    """Map note id -> plain text of its body, from a foot/endnotes part."""
    try:
        part = src.part.part_related_by(reltype)
    except KeyError:
        return {}
    root = etree.fromstring(part.blob)
    texts: dict[str, str] = {}
    for note in root.findall(qn(element)):
        if note.get(qn("w:type")) in ("separator", "continuationSeparator"):
            continue
        body = "".join(t.text or "" for t in note.iter(qn("w:t"))).strip()
        texts[note.get(qn("w:id"), "")] = body
    return texts


def _numbering_formats(src) -> dict[tuple[str, str], str]:
    """Map (numId, ilvl) -> numFmt ('decimal', 'bullet', 'lowerLetter', ...) by
    resolving numbering.xml: each w:num points at a w:abstractNum, whose w:lvl
    entries carry the w:numFmt. Empty when the document defines no numbering."""
    try:
        part = src.part.numbering_part
    except (KeyError, AttributeError, NotImplementedError, ValueError):
        return {}
    if part is None:
        return {}
    root = etree.fromstring(part.blob)

    abstract_fmt: dict[tuple[str, str], str] = {}
    for anum in root.findall(qn("w:abstractNum")):
        aid = anum.get(qn("w:abstractNumId"))
        for lvl in anum.findall(qn("w:lvl")):
            fmt_el = lvl.find(qn("w:numFmt"))
            if fmt_el is not None and fmt_el.get(qn("w:val")):
                abstract_fmt[(aid, lvl.get(qn("w:ilvl")))] = fmt_el.get(qn("w:val"))

    result: dict[tuple[str, str], str] = {}
    for num in root.findall(qn("w:num")):
        num_id = num.get(qn("w:numId"))
        aid_el = num.find(qn("w:abstractNumId"))
        if num_id is None or aid_el is None:
            continue
        aid = aid_el.get(qn("w:val"))
        for (a, ilvl), fmt in abstract_fmt.items():
            if a == aid:
                result[(num_id, ilvl)] = fmt
    return result


def _comment_texts(src) -> list[tuple[str, str]]:
    """(author, excerpt) for every comment in the source."""
    try:
        part = src.part.part_related_by(RT_COMMENTS)
    except KeyError:
        return []
    root = etree.fromstring(part.blob)
    out = []
    for c in root.findall(qn("w:comment")):
        body = "".join(t.text or "" for t in c.iter(qn("w:t"))).strip()
        excerpt = body if len(body) <= 80 else body[:79] + "…"
        out.append((c.get(qn("w:author"), "unknown"), excerpt))
    return out


# --- tables -------------------------------------------------------------------


def _table_block(table, src) -> Block:
    """A TABLE block: original XML plus the image blobs / link targets it
    references (relationship ids are only valid in the source package)."""
    el = table._element
    resources: dict[str, tuple[bytes, str]] = {}
    links: dict[str, str] = {}
    for blip in el.iter(A_BLIP):
        rid = blip.get(R_EMBED)
        if rid and rid in src.part.related_parts:
            part = src.part.related_parts[rid]
            resources[rid] = (part.blob, Path(str(part.partname)).suffix.lstrip("."))
    for h_el in el.iter(qn("w:hyperlink")):
        target = _hyperlink_target(h_el, src)
        rid = h_el.get(R_ID)
        if rid and target:
            links[rid] = target
    preview = " | ".join(
        cell.text.strip() for cell in table.rows[0].cells if cell.text.strip()
    ) if table.rows else ""
    return Block(
        text=preview[:120],
        xml=etree.tostring(el).decode(),
        resources=resources,
        links=links,
    )


# --- paragraph hints -----------------------------------------------------------


def _hints_for(para, text: str, leading_tabs: int, numbering: dict) -> FormatHints:
    """Distill a paragraph's raw formatting signals into FormatHints."""
    runs = [r for r in para.runs if r.text.strip()]

    sizes = [r.font.size.pt for r in runs if r.font.size is not None]
    font_size_pt = max(sizes) if sizes else _style_font_size(para.style)

    bold = bool(runs) and all(_effective(r.font.bold, para.style, "bold") for r in runs)
    italic = bool(runs) and all(_effective(r.font.italic, para.style, "italic") for r in runs)

    letters = [c for c in text if c.isalpha()]
    all_caps = bool(letters) and text.upper() == text

    # para.style is None when the paragraph references a style id the document
    # never defines (seen in real-world templates) — treat as unstyled.
    style_name = para.style.name if para.style is not None else None
    existing_style = style_name if style_name and style_name != "Normal" else None

    # Word-native list membership: w:numPr on the paragraph (set via the ribbon
    # list buttons). The visible number/bullet lives in numbering.xml, NOT the
    # text — without this hint such lists silently flatten to body prose.
    num_pr = para._p.find(f"{qn('w:pPr')}/{qn('w:numPr')}")
    has_numbering = num_pr is not None
    ilvl = num_pr.find(qn("w:ilvl")) if has_numbering else None
    num_id = num_pr.find(qn("w:numId")) if has_numbering else None

    is_list_marker = LIST_MARKER_RE.match(text) is not None

    indent = para.paragraph_format.left_indent
    indent_pt = (indent.pt if indent is not None else 0.0) + leading_tabs * INDENT_PT_PER_LEVEL
    list_level = int(indent_pt // INDENT_PT_PER_LEVEL) if indent_pt > 0 else 0
    ilvl_val = "0"
    if has_numbering and ilvl is not None:
        ilvl_val = ilvl.get(qn("w:val"), "0")
        list_level = int(ilvl_val)
    # "a)" / roman sub-markers imply nesting even without physical indent.
    elif is_list_marker and list_level == 0 and SUB_MARKER_RE.match(text):
        list_level = 1

    # Ordered vs bullet for native lists, resolved through numbering.xml. Bullet
    # (or unresolvable) stays False so the classifier keeps its safe default.
    list_ordered = False
    if has_numbering and num_id is not None:
        fmt = numbering.get((num_id.get(qn("w:val")), ilvl_val))
        list_ordered = fmt is not None and fmt not in ("bullet", "none")

    return FormatHints(
        font_size_pt=font_size_pt,
        bold=bold,
        italic=italic,
        all_caps=all_caps,
        existing_style=existing_style,
        is_list_marker=is_list_marker,
        has_numbering=has_numbering,
        list_ordered=list_ordered,
        list_level=list_level,
    )


def _effective(run_value, style, attr: str) -> bool:
    """Resolve a run's tri-state font attribute, falling back to the paragraph
    style. Coerced to a plain bool — font.underline may be a WD_UNDERLINE enum
    (e.g. SINGLE) rather than True/False."""
    if run_value is not None:
        return bool(run_value)
    font = getattr(style, "font", None)
    return bool(font is not None and getattr(font, attr))


def _style_font_size(style) -> float | None:
    """Font size defined by the paragraph's style, if any."""
    font = getattr(style, "font", None)
    if font is not None and font.size is not None:
        return font.size.pt
    return None
