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
