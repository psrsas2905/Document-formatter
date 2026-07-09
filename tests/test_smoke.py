"""Smoke tests — expand into real regression tests against samples/ as stages land."""

from docformat.template import load_profile


def test_profile_loads():
    profile = load_profile("config/template_profile.example.yaml")
    assert profile.style_map["Heading1"] == "Heading 1"
    assert profile.raw["page"]["size"] in {"A4", "Letter"}


def test_ingest_sample():
    from docformat.ingest import ingest

    doc = ingest("samples/input_messy.docx")
    assert len(doc.blocks) == 21  # empty spacing paragraphs dropped
    texts = [b.text for b in doc.blocks]

    title = doc.blocks[texts.index("ACME WIDGET INSTALLATION GUIDE")]
    assert title.hints.font_size_pt == 18.0 and title.hints.bold and title.hints.all_caps

    bullets = [b for b in doc.blocks if b.text.startswith(("•", "-", "*"))]
    assert len(bullets) == 3 and all(b.hints.is_list_marker for b in bullets)

    sub = doc.blocks[texts.index("a) Torque each bolt to the value shown below.")]
    assert sub.hints.is_list_marker and sub.hints.list_level == 1

    styled = doc.blocks[texts.index("Maintenance Schedule")]
    assert styled.hints.existing_style == "Heading 2"


def test_classify_sample():
    from docformat.classify import CONFIDENCE_THRESHOLD, classify
    from docformat.ingest import ingest
    from docformat.models import BlockType

    doc = classify(ingest("samples/input_messy.docx"))
    by_text = {b.text: b for b in doc.blocks}

    assert doc.title == "ACME WIDGET INSTALLATION GUIDE"
    assert by_text["ACME WIDGET INSTALLATION GUIDE"].label is BlockType.HEADING1
    assert by_text["Overview"].label is BlockType.HEADING2
    assert by_text["Figure 1: Wiring diagram for single-phase supply"].label is BlockType.CAPTION
    assert by_text["Table 2 - Torque settings by bolt size"].label is BlockType.CAPTION
    assert by_text["• Wear insulated gloves rated to 1000 V"].label is BlockType.LIST_ITEM
    assert by_text["3. Connect the signal cable to port A."].label is BlockType.LIST_ITEM

    trusted = by_text["Maintenance Schedule"]
    assert trusted.label is BlockType.HEADING2 and trusted.confidence == 1.0

    ambiguous = by_text["Safety Precautions"]
    assert ambiguous.label in {BlockType.HEADING2, BlockType.HEADING3}
    assert ambiguous.confidence < CONFIDENCE_THRESHOLD  # must reach the QA report

    assert all(b.label is not BlockType.UNKNOWN for b in doc.blocks)


def test_apply_styles(tmp_path):
    import docx

    from docformat.apply import apply_styles
    from docformat.classify import classify
    from docformat.ingest import ingest
    from docformat.template import load_profile

    profile = load_profile("config/template_profile.example.yaml")
    doc = classify(ingest("samples/input_messy.docx"))
    out = apply_styles(doc, profile, tmp_path / "styled.docx")

    result = docx.Document(str(out))
    styles = [p.style.name for p in result.paragraphs]
    assert styles[0] == "Heading 1"
    assert "List Bullet" in styles and "Caption" in styles and "Quote" in styles
    assert "List Bullet 2" in styles  # nested a)/b) items pick the level variant

    for para in result.paragraphs:
        assert "\t" not in para.text
        for run in para.runs:  # no direct formatting survives
            assert run.font.size is None and run.font.bold is None and run.font.italic is None
    markers = ("•", "-", "*", "1.", "a)")
    assert not any(p.text.startswith(markers) for p in result.paragraphs)


def _run_pipeline(tmp_path):
    from docformat.apply import apply_styles
    from docformat.classify import classify
    from docformat.elements import add_elements
    from docformat.ingest import ingest
    from docformat.template import load_profile

    profile = load_profile("config/template_profile.example.yaml")
    doc = classify(ingest("samples/input_messy.docx"))
    styled = apply_styles(doc, profile, tmp_path / "input_messy_formatted.docx")
    add_elements(styled, profile)
    return doc, styled


def test_golden_regression(tmp_path):
    import docx

    _, styled = _run_pipeline(tmp_path)
    result = docx.Document(str(styled))
    got = [f"{p.style.name}\t{p.text}" for p in result.paragraphs]
    expected = open("tests/golden/input_messy_styles.tsv", encoding="utf-8").read().splitlines()
    assert got == expected


def test_brand_template_preserved(tmp_path):
    import docx

    _, styled = _run_pipeline(tmp_path)
    result = docx.Document(str(styled))
    header = result.sections[0].header
    blips = header._element.findall(
        ".//{http://schemas.openxmlformats.org/drawingml/2006/main}blip"
    )
    assert len(blips) == 1  # the org logo survived into the output header
    assert any("ACME CORP" in p.text for p in header.paragraphs)


def test_qa_report(tmp_path):
    from docformat.qa import write_report

    doc, _ = _run_pipeline(tmp_path)
    report = write_report(doc, tmp_path / "qa_report.md")
    text = report.read_text(encoding="utf-8")
    assert "Safety Precautions" in text  # the one deliberately ambiguous block
    assert "No level jumps detected" in text


def test_export_pdf(tmp_path):
    import subprocess

    import pytest

    from docformat.export import export_pdf, soffice_available

    if not soffice_available():
        pytest.skip("LibreOffice not installed")
    _, styled = _run_pipeline(tmp_path)
    pdf = export_pdf(styled, tmp_path)
    assert pdf.exists() and pdf.stat().st_size > 10_000
    data = pdf.read_bytes()
    assert b"/Marked true" in data  # tagged PDF
    text = subprocess.run(
        ["pdftotext", str(pdf), "-"], capture_output=True, text=True
    ).stdout
    assert "Table of Contents" in text
    assert "Overview" in text.split("Table of Contents")[1][:600]  # TOC populated
