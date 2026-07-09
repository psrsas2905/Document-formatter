# PROJECT_SPEC — docformat

> This file is the single source of truth for the build. It is written to be
> read by Claude Code at the start of a session. Read it fully before writing code.

## 1. Goal

Turn a raw, inconsistently-formatted `.docx` draft into a **publish-ready document**
that conforms to an organization's standard template — collapsing hours of manual
formatting into minutes. The output is a formatted `.docx` and a tagged `.pdf`,
plus a QA report listing anything a human still needs to review.

## 2. Hard constraints (do not violate)

1. **Must run fully offline on a desktop.** The shipped tool cannot depend on any
   cloud API at runtime for its core function.
2. **Hybrid engine with graceful degradation.** A deterministic rule-based core does
   100% of the mechanical work with zero AI. An *optional* AI layer improves
   classification accuracy but is never required. Order of preference at runtime:
   local LLM (Ollama) if present → pure heuristics. (An online Claude path may be
   added later as an opt-in, but the tool must never break without it.)
3. **The template is the source of truth.** Content is poured *into* the template's
   named styles. We never invent formatting; we map source content onto the
   template's existing style definitions.
4. **Human-in-the-loop by design.** Target 80–90% automation. Everything uncertain
   goes into the QA report rather than being silently guessed.

## 3. Tech stack

- Python 3.10+
- `python-docx` — read/write docx, apply named styles
- `lxml` — reach OOXML that python-docx can't (TOC field, numbering)
- LibreOffice headless (`soffice --headless`) — offline PDF export + field/TOC refresh
- `typer` — CLI
- `pyyaml` — template profiles
- (optional) Ollama + a small instruct model — offline AI classifier
- (later) PyInstaller — bundle a standalone executable

## 4. Architecture — pipeline of modules

Each stage has a narrow contract. Data flows as the intermediate model in `models.py`.

```
source.docx ─▶ ingest ─▶ classify ─▶ apply ─▶ elements ─▶ export ─▶ output.docx + .pdf
                                        ▲                                    │
                              template_profile.yaml                      qa report
```

| Module          | Responsibility                                                                 |
|-----------------|--------------------------------------------------------------------------------|
| `models.py`     | Intermediate data structures (`Block`, `BlockType`, `Document`). Pure data.    |
| `ingest.py`     | Read source .docx → list of `Block`s carrying text + formatting hints.         |
| `classify.py`   | Label each block (Heading1/2/3, Body, Caption, ListItem, Quote) via heuristics.|
| `classify_ai.py`| Optional. Same signature as classify; uses local LLM; falls back to heuristics.|
| `template.py`   | Load `template_profile.yaml`; expose style names, margins, header/footer spec. |
| `apply.py`      | Clear direct formatting; apply template's named styles per block label.        |
| `elements.py`   | Headers/footers, page numbers, auto-numbered captions, TOC/List of Figures.    |
| `export.py`     | Refresh fields + export tagged PDF via LibreOffice headless.                    |
| `qa.py`         | Produce QA report: unmapped blocks, low-confidence labels, missing alt text.   |
| `cli.py`        | `docformat format INPUT --template PROFILE --out DIR` wires the pipeline.       |

## 5. Classification heuristics (the deterministic core)

- Relative font size larger than body → heading; largest = H1, next = H2, etc.
- Short line (< ~12 words), bold, no trailing period → likely heading.
- Starts with `Figure N` / `Table N` → Caption.
- Line begins with a bullet glyph or `1.`/`a)` list marker → ListItem (capture level).
- Block already carries a valid template style name → trust it.
- Everything else → Body.
- Attach a `confidence` (0–1) to every label. Below a threshold → flag for QA.

## 6. Build order — THIN SLICE FIRST

Build and verify each step end-to-end on ONE real sample before adding the next.
Do **not** build the AI layer until the deterministic path works completely.

1. `models.py` + `template.py` + load `template_profile.example.yaml`.
2. `ingest.py` → prove we can read `samples/input_messy.docx` into blocks.
3. `classify.py` heuristics only.
4. `apply.py` → produce a styled `.docx`. **This is the first visible win.**
5. `export.py` → PDF via LibreOffice.
6. `elements.py` → headers/footers, page numbers, then TOC.
7. `qa.py` → the review report.
8. Regression: keep `samples/` outputs as golden files in `tests/`.
9. THEN `classify_ai.py` (Ollama, optional, behind a `--ai` flag).
10. THEN packaging (PyInstaller) and a simple GUI if wanted.

## 7. Acceptance criteria (definition of done for v1)

- `pip install -e .` works; `docformat --help` runs.
- `docformat format samples/input_messy.docx --template config/template_profile.example.yaml --out out/`
  produces `out/*.docx` with template named styles applied (no direct formatting).
- Generated TOC reflects the heading hierarchy.
- A tagged PDF is produced offline.
- A `qa_report.md` lists every block the tool was unsure about.
- Runs with **no network connection**.

## 8. Notes for Claude Code

- Start by reading this file and `docs/architecture.md`.
- Fill in the stubs under `src/docformat/`; they already define the intended contracts.
- Add a real messy sample to `samples/input_messy.docx` early (or generate one) so
  every stage is testable against actual output.
- Commit after each working slice with a clear message.
