"""Generate samples/input_rich.docx — fixture for content-preservation features.

Contains what real technical drafts contain and messy formatting alone doesn't
cover: an OMML equation, an inline image and a standalone figure image, a data
table (with caption), footnotes, inline bold/italic emphasis inside body text,
and numbered headings (1 / 1.1 style).

Run from the repo root:  python scripts/make_rich_sample.py
"""

from __future__ import annotations

from pathlib import Path

import docx
from docx.oxml import parse_xml
from docx.shared import Pt

M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"

# x = (-b ± sqrt(b^2 - 4ac)) / 2a, as OMML
QUADRATIC_OMML = f"""
<m:oMath xmlns:m="{M_NS}" xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <m:r><m:t>x=</m:t></m:r>
  <m:f>
    <m:num>
      <m:r><m:t>&#8722;b&#177;</m:t></m:r>
      <m:rad>
        <m:radPr><m:degHide m:val="1"/></m:radPr>
        <m:deg/>
        <m:e>
          <m:sSup><m:e><m:r><m:t>b</m:t></m:r></m:e><m:sup><m:r><m:t>2</m:t></m:r></m:sup></m:sSup>
          <m:r><m:t>&#8722;4ac</m:t></m:r>
        </m:e>
      </m:rad>
    </m:num>
    <m:den><m:r><m:t>2a</m:t></m:r></m:den>
  </m:f>
</m:oMath>
"""


def main() -> None:
    out = Path("samples/input_rich.docx")
    logo = Path("templates/assets/acme_logo.png")
    if not logo.exists():
        raise SystemExit("Run scripts/make_template.py first (needs the logo png).")
    doc = docx.Document()

    t = doc.add_paragraph()
    r = t.add_run("Signal Processing Design Note")
    r.font.size, r.font.bold = Pt(18), True

    doc.add_paragraph("1 Introduction").runs[0].font.bold = True

    p = doc.add_paragraph("This note describes the ")
    p.add_run("critically damped").bold = True
    p.add_run(" filter response. The method is ")
    p.add_run("only valid").italic = True
    p.add_run(" below the Nyquist frequency.")
    p.add_run("1")  # will become a footnote reference via raw XML below

    doc.add_paragraph("1.1 Governing Equation").runs[0].font.bold = True
    eq = doc.add_paragraph("The roots follow from ")
    eq._p.append(parse_xml(QUADRATIC_OMML))
    eq.add_run(" for the characteristic polynomial.")

    doc.add_paragraph("1.2 Reference Data").runs[0].font.bold = True
    table = doc.add_table(rows=3, cols=3)
    for j, head in enumerate(("Parameter", "Symbol", "Value")):
        table.rows[0].cells[j].text = head
    for i, row in enumerate((("Damping ratio", "zeta", "0.707"),
                             ("Natural frequency", "omega_n", "12.5 rad/s")), start=1):
        for j, val in enumerate(row):
            table.rows[i].cells[j].text = val
    doc.add_paragraph("Table 1: Filter design parameters", style=None).runs[0].font.size = Pt(9)

    doc.add_paragraph("2 Hardware Layout").runs[0].font.bold = True
    pic = doc.add_paragraph()
    pic.add_run().add_picture(str(logo), width=Pt(72), height=Pt(72))
    doc.add_paragraph("Figure 1: Board orientation marker").runs[0].font.size = Pt(9)

    inline = doc.add_paragraph("Align the marker ")
    inline.add_run().add_picture(str(logo), width=Pt(11), height=Pt(11))
    inline.add_run(" with the silkscreen arrow before fastening.")

    # Semantic character formatting: sub/superscript carry meaning, plus an
    # underlined term and a struck-through correction.
    chem = doc.add_paragraph("The coolant is ")
    chem.add_run("H")
    chem.add_run("2").font.subscript = True
    chem.add_run("O; dissipation scales with ")
    chem.add_run("v")
    chem.add_run("2").font.superscript = True
    chem.add_run(". The ")
    chem.add_run("thermal budget").font.underline = True
    chem.add_run(" is fixed; the ")
    chem.add_run("old 5 W limit").font.strike = True
    chem.add_run(" no longer applies. ")
    from docx.enum.text import WD_COLOR_INDEX
    chem.add_run("Confirm the tolerance").font.highlight_color = WD_COLOR_INDEX.YELLOW

    doc.save(out)
    _add_footnote(out)
    print(f"Wrote {out}")


def _add_footnote(path: Path) -> None:
    """Attach a real footnote (part + reference) — python-docx has no API."""
    import re
    import shutil
    import zipfile

    W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    footnotes_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:footnotes xmlns:w="{W}">
  <w:footnote w:type="separator" w:id="-1"><w:p><w:r><w:separator/></w:r></w:p></w:footnote>
  <w:footnote w:type="continuationSeparator" w:id="0"><w:p><w:r><w:continuationSeparator/></w:r></w:p></w:footnote>
  <w:footnote w:id="1"><w:p><w:r><w:rPr><w:vertAlign w:val="superscript"/></w:rPr><w:footnoteRef/></w:r><w:r><w:t xml:space="preserve"> Sampling above 2x the highest component frequency.</w:t></w:r></w:p></w:footnote>
</w:footnotes>"""

    tmp = path.with_suffix(".tmp.docx")
    with zipfile.ZipFile(path) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.namelist():
            data = zin.read(item)
            if item == "word/document.xml":
                text = data.decode("utf-8")
                # Replace the literal "1" run after 'Nyquist frequency.' with a footnote ref.
                text = text.replace(
                    "<w:r><w:t>1</w:t></w:r>",
                    '<w:r><w:rPr><w:vertAlign w:val="superscript"/></w:rPr>'
                    '<w:footnoteReference w:id="1"/></w:r>',
                    1,
                )
                data = text.encode("utf-8")
            elif item == "[Content_Types].xml":
                text = data.decode("utf-8").replace(
                    "</Types>",
                    '<Override PartName="/word/footnotes.xml" ContentType="application/vnd.'
                    'openxmlformats-officedocument.wordprocessingml.footnotes+xml"/></Types>',
                )
                data = text.encode("utf-8")
            elif item == "word/_rels/document.xml.rels":
                text = data.decode("utf-8").replace(
                    "</Relationships>",
                    '<Relationship Id="rIdFn1" Type="http://schemas.openxmlformats.org/'
                    'officeDocument/2006/relationships/footnotes" Target="footnotes.xml"/>'
                    "</Relationships>",
                )
                data = text.encode("utf-8")
            zout.writestr(item, data)
        zout.writestr("word/footnotes.xml", footnotes_xml)
    shutil.move(tmp, path)
    assert re.search(rb"footnoteReference", zipfile.ZipFile(path).read("word/document.xml"))


if __name__ == "__main__":
    main()
