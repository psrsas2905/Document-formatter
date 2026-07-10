"""Human classification overrides + dry-run plan (make manual fixes survive
re-runs). See src/docformat/overrides.py."""

import yaml

from docformat.classify import classify
from docformat.ingest import ingest
from docformat.models import Block, BlockType, Document, FormatHints
from docformat.overrides import apply_overrides, write_plan


def _doc():
    return Document(
        source_path="draft.docx",
        blocks=[
            Block(text="Introduction", label=BlockType.HEADING2, confidence=0.55,
                  hints=FormatHints()),
            Block(text="Some body paragraph that is long enough to be prose here.",
                  label=BlockType.BODY, confidence=0.8, hints=FormatHints()),
            Block(text="Ambiguous line", label=BlockType.BODY, confidence=0.55,
                  hints=FormatHints()),
        ],
    )


def test_write_plan_lists_uncertain_blocks(tmp_path):
    plan = write_plan(_doc(), tmp_path / "plan.yaml", "draft.docx")
    data = yaml.safe_load(plan.read_text())
    indexes = {r["index"] for r in data["overrides"]}
    assert indexes == {0, 2}  # the two sub-threshold blocks, not the 0.8 body
    # The full document map (comments) references every block.
    text = plan.read_text()
    assert "# --- document map" in text and "[1] Body" in text


def test_apply_override_pins_label_and_trusts_it(tmp_path):
    doc = _doc()
    plan = tmp_path / "p.yaml"
    plan.write_text(yaml.safe_dump({
        "overrides": [{"index": 0, "label": "Heading1", "text": "Introduction"}]
    }))
    applied = apply_overrides(doc, plan)
    assert applied == 1
    assert doc.blocks[0].label is BlockType.HEADING1
    assert doc.blocks[0].confidence == 1.0  # human-reviewed -> out of QA


def test_apply_override_guards(tmp_path):
    doc = _doc()
    plan = tmp_path / "p.yaml"
    plan.write_text(yaml.safe_dump({"overrides": [
        {"index": 99, "label": "Body"},               # out of range
        {"index": 1, "label": "Bogus"},               # invalid label
        {"index": 2, "label": "Heading2", "text": "Totally different text"},  # drift
    ]}))
    applied = apply_overrides(doc, plan)
    assert applied == 0
    assert doc.blocks[2].label is BlockType.BODY  # drift guard left it alone
    assert sum("skipped" in n for n in doc.notes) == 3


def test_snippet_prefix_tolerates_truncation(tmp_path):
    doc = _doc()
    plan = tmp_path / "p.yaml"
    # snippet is a truncated prefix of the real (longer) block text
    plan.write_text(yaml.safe_dump({"overrides": [
        {"index": 1, "label": "Quote", "text": "Some body paragraph that is long"}
    ]}))
    assert apply_overrides(doc, plan) == 1
    assert doc.blocks[1].label is BlockType.QUOTE


def test_table_block_not_overridable(tmp_path):
    doc = Document(blocks=[Block(text="tbl", label=BlockType.TABLE, confidence=1.0,
                                 xml="<w:tbl/>")])
    plan = tmp_path / "p.yaml"
    plan.write_text(yaml.safe_dump({"overrides": [{"index": 0, "label": "Body"}]}))
    assert apply_overrides(doc, plan) == 0
    assert doc.blocks[0].label is BlockType.TABLE


def test_dry_run_roundtrip_on_real_sample(tmp_path):
    """Plan generated from the messy sample re-applies cleanly to a fresh run."""
    doc = classify(ingest("samples/input_messy.docx"))
    plan = write_plan(doc, tmp_path / "plan.yaml", "samples/input_messy.docx")

    fresh = classify(ingest("samples/input_messy.docx"))
    applied = apply_overrides(fresh, plan)
    # Every pre-filled row matches a block (no drift) and gets trusted.
    assert applied == len(yaml.safe_load(plan.read_text())["overrides"])
    for b in fresh.blocks:
        if b.label is not BlockType.TABLE:
            assert b.confidence >= 0.6 or b.label is BlockType.UNKNOWN
