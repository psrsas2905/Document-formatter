"""Batch formatting with a consolidated QA summary (docformat batch).

PDF export is disabled here to keep the suite offline/fast — it's covered by
test_smoke."""

import shutil

import yaml

from docformat.batch import collect_inputs, format_document, run_batch
from docformat.template import load_profile


def _profile():
    return load_profile("config/template_profile.example.yaml")


def test_collect_inputs_expands_and_filters(tmp_path):
    (tmp_path / "a.docx").write_bytes(b"x")
    (tmp_path / "note.txt").write_text("hi")
    (tmp_path / "ignore.pdf").write_bytes(b"x")
    sub = tmp_path / "_converted"
    sub.mkdir()
    (sub / "temp.docx").write_bytes(b"x")  # our own artifact -> skipped

    found = {p.name for p in collect_inputs([tmp_path])}
    assert found == {"a.docx", "note.txt"}


def test_format_document_captures_error(tmp_path):
    bad = tmp_path / "broken.docx"
    bad.write_text("not a docx")
    result = format_document(bad, _profile(), tmp_path / "out", pdf=False)
    assert not result.ok and result.error and result.blocks == 0


def test_run_batch_summary_and_subfolders(tmp_path):
    inp = tmp_path / "in"
    inp.mkdir()
    shutil.copy("samples/input_messy.docx", inp / "input_messy.docx")
    shutil.copy("samples/input_rich.docx", inp / "input_rich.docx")
    (inp / "broken.docx").write_text("nope")

    out = tmp_path / "out"
    results = run_batch(collect_inputs([inp]), _profile(), out, pdf=False)

    ok = [r for r in results if r.ok]
    failed = [r for r in results if not r.ok]
    assert len(ok) == 2 and len(failed) == 1

    summary = (out / "batch_summary.md").read_text()
    assert "2 formatted, 1 failed" in summary
    assert "input_messy.docx" in summary and "broken.docx" in summary

    # Each formatted doc gets its own subfolder with a report + document.
    assert (out / "input_messy" / "qa_report.md").exists()
    assert list((out / "input_messy").glob("*.docx"))  # named per output.filename


def test_batch_applies_overrides_dir(tmp_path):
    inp = tmp_path / "in"
    inp.mkdir()
    shutil.copy("samples/input_messy.docx", inp / "input_messy.docx")

    ov = tmp_path / "plans"
    ov.mkdir()
    (ov / "input_messy_overrides.yaml").write_text(
        yaml.safe_dump({"overrides": [
            {"index": 3, "label": "Heading2", "text": "Safety Precautions"}
        ]})
    )

    out = tmp_path / "out"
    run_batch(collect_inputs([inp]), _profile(), out, pdf=False, overrides_dir=ov)

    import docx
    formatted = next((out / "input_messy").glob("*.docx"))
    d = docx.Document(str(formatted))
    styled = {p.text: p.style.name for p in d.paragraphs if p.text.startswith("Safety")}
    assert styled.get("Safety Precautions") == "Heading 2"


def test_run_batch_disambiguates_same_stem(tmp_path):
    inp = tmp_path / "in"
    inp.mkdir()
    shutil.copy("samples/input_messy.docx", inp / "doc.docx")
    # a .txt with the same stem -> must not clobber the first's output folder
    (inp / "doc.txt").write_text("Just one plain paragraph of body text here.")

    out = tmp_path / "out"
    run_batch(collect_inputs([inp]), _profile(), out, pdf=False)
    subdirs = {p.name for p in out.iterdir() if p.is_dir()}
    assert {"doc", "doc_1"} <= subdirs
