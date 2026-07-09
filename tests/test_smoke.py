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
