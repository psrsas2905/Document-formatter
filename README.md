# docformat

Turn a raw, inconsistently-formatted Word draft into a **publish-ready document**
that matches your organization's standard template — in minutes instead of hours.

> **Status:** early / work-in-progress. Building the deterministic core first.

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

## Roadmap

- [ ] Deterministic core: ingest → classify → apply → export
- [ ] Auto TOC / List of Figures, headers & page numbers
- [ ] QA report
- [ ] Optional offline AI classifier (Ollama) behind `--ai`
- [ ] Standalone executable (PyInstaller)
- [ ] Simple GUI for non-technical writers

## Contributing

See [`PROJECT_SPEC.md`](PROJECT_SPEC.md) for the architecture and build order.

## License

MIT — see [`LICENSE`](LICENSE).
