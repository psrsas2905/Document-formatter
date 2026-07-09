# docformat

Turn a raw, inconsistently-formatted Word draft into a **publish-ready document**
that matches your organization's standard template — in minutes instead of hours.

> **Status:** v1 pipeline complete — deterministic core, TOC/captions/page
> numbers, tagged-PDF export, QA report, and the optional local-AI classifier.

## Why

Technical writers lose hours pushing a finished draft into the house template:
clearing someone's hand-applied bold, re-doing headings, rebuilding the table of
contents, fixing captions and page numbers. `docformat` automates the mechanical
90% and hands you a review report for the rest.

## How it works

The tool pours your content **into the template's named styles** instead of
reformatting in place. A deterministic rule-based engine does all the mechanical
work with **no cloud and no AI required**, so it runs fully offline on your desktop.
An optional local-AI layer improves heading/caption detection on messy documents,
but the tool never depends on it.

```
source.docx ─▶ ingest ─▶ classify ─▶ apply ─▶ elements ─▶ export ─▶ output.docx + .pdf
                                        ▲                                    │
                              template_profile.yaml                     qa report
```

## Requirements

- Python 3.10+
- [LibreOffice](https://www.libreoffice.org/) (for offline PDF export) — the `soffice` binary must be on your PATH
- *(optional)* [Ollama](https://ollama.com/) with a small instruct model, for the AI-assisted classifier

## Install (dev)

```bash
git clone https://github.com/<your-username>/docformat.git
cd docformat
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
```

## Usage

```bash
docformat format samples/input_messy.docx \
  --template config/template_profile.example.yaml \
  --out out/
```

Outputs a styled `.docx`, a tagged `.pdf`, and `qa_report.md`.

Use **your organization's brand template** (logo, colors, page setup — all
preserved) by pointing at it directly, no profile editing needed:

```bash
docformat format draft.docx -t config/template_profile.example.yaml \
  --template-docx path/to/your_brand_template.docx --out out/
```

Add `--ai` to let a locally installed [Ollama](https://ollama.com/) model
re-judge the blocks the heuristics were unsure about. If Ollama isn't running,
the flag is a no-op — the deterministic result stands. `--no-pdf` skips the
LibreOffice export.

### GUI (for non-technical writers)

```bash
docformat gui
```

Opens a local web app at `http://127.0.0.1:8765` (stdlib server, localhost
only — nothing ever leaves the machine): drag in the draft, optionally drag in
your organization's brand template, click **Format document**, download the
results, and see at a glance which blocks need a human look.

### Standalone executable

```bash
bash scripts/build_exe.sh   # -> dist/docformat (single file)
```

The executable bundles Python, python-docx, the example profile and the demo
template; only LibreOffice is still needed on the target machine for PDF
export. Build on each OS you ship to (PyInstaller doesn't cross-compile).

## Roadmap

- [x] Deterministic core: ingest → classify → apply → export
- [x] Auto TOC / List of Figures, headers & page numbers
- [x] QA report
- [x] Optional offline AI classifier (Ollama) behind `--ai`
- [x] Standalone executable (PyInstaller)
- [x] Local web GUI for non-technical writers

## Contributing

See [`PROJECT_SPEC.md`](PROJECT_SPEC.md) for the architecture and build order.

## License

MIT — see [`LICENSE`](LICENSE).
