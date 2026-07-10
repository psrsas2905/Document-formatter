"""Carry footnotes into the output document at the OPC package level.

python-docx (1.2) has no footnote API, so this works directly with the
footnotes part: create it (with the mandatory separator entries) or extend the
template's existing one, append one footnote per collected text, and return the
ids to reference from the body. All content is plain text — source footnote
formatting is not preserved (the QA report says so when footnotes are carried).
"""

from __future__ import annotations

from docx.opc.packuri import PackURI
from docx.opc.part import Part
from lxml import etree

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
RT_FOOTNOTES = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/footnotes"
)
CT_FOOTNOTES = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.footnotes+xml"
)

_EMPTY_FOOTNOTES = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:footnotes xmlns:w="{W}">
  <w:footnote w:type="separator" w:id="-1"><w:p><w:r><w:separator/></w:r></w:p></w:footnote>
  <w:footnote w:type="continuationSeparator" w:id="0"><w:p><w:r><w:continuationSeparator/></w:r></w:p></w:footnote>
</w:footnotes>"""


class FootnoteWriter:
    """Accumulates footnote texts for one output document."""

    def __init__(self, out) -> None:
        self._doc = out
        self._root = None
        self._part = None
        self._next_id = 1
        self._added = 0

    def add(self, text: str) -> int:
        """Register a footnote body; returns the id to reference in the run."""
        if self._root is None:
            self._load_or_create()
        fn_id = self._next_id
        self._next_id += 1
        self._added += 1
        fn = etree.SubElement(self._root, f"{{{W}}}footnote")
        fn.set(f"{{{W}}}id", str(fn_id))
        p = etree.SubElement(fn, f"{{{W}}}p")
        ref_r = etree.SubElement(p, f"{{{W}}}r")
        rpr = etree.SubElement(ref_r, f"{{{W}}}rPr")
        va = etree.SubElement(rpr, f"{{{W}}}vertAlign")
        va.set(f"{{{W}}}val", "superscript")
        etree.SubElement(ref_r, f"{{{W}}}footnoteRef")
        txt_r = etree.SubElement(p, f"{{{W}}}r")
        t = etree.SubElement(txt_r, f"{{{W}}}t")
        t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        t.text = f" {text}"
        return fn_id

    def flush(self) -> int:
        """Write the accumulated footnotes back into the part; returns count added."""
        if self._root is None:
            return 0
        self._part._blob = etree.tostring(
            self._root, xml_declaration=True, encoding="UTF-8", standalone=True
        )
        return self._added

    def _load_or_create(self) -> None:
        doc_part = self._doc.part
        try:
            self._part = doc_part.part_related_by(RT_FOOTNOTES)
            self._root = etree.fromstring(self._part.blob)
        except KeyError:
            self._part = Part(
                PackURI("/word/footnotes.xml"),
                CT_FOOTNOTES,
                _EMPTY_FOOTNOTES.encode(),
                doc_part.package,
            )
            doc_part.relate_to(self._part, RT_FOOTNOTES)
            self._root = etree.fromstring(self._part.blob)
        ids = [
            int(fn.get(f"{{{W}}}id", "0"))
            for fn in self._root.findall(f"{{{W}}}footnote")
        ]
        self._next_id = max(ids, default=0) + 1
