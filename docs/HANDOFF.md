# Project Status & Handoff

> Last updated: 2026-07-10. Read `PROJECT_SPEC.md` first (the build contract),
> then this file (what actually exists and why), then `docs/architecture.md`.

## Where things stand

**The tool is feature-complete against the spec's v1 acceptance criteria, plus
several rounds of extensions.** All work lives on branch
`claude/docformat-offline-tool-3xb0yq` (pushed). 43 tests pass
(`python -m pytest -q`). Lint is clean (`ruff check src tests scripts`).

Working end-to-end today:

```bash
pip install -e ".[dev]"

# CLI — full pipeline: convert -> ingest -> classify -> apply -> elements -> QA -> tagged PDF
docformat format samples/input_rich.docx -t config/template_profile.redlotus.yaml \
  --out out -s "Client Name=Acme Corporation" -s "Project No.=RL-2026-042"

# Local web GUI for writers (127.0.0.1 only, drag & drop, document fields)
docformat gui

# Standalone executable
bash scripts/build_exe.sh   # -> dist/docformat (rebuild after changes)
```

## What was built, in order (one commit per stage)

1. **Deterministic core** — `ingest` → `classify` (heuristics, PROJECT_SPEC §5)
   → `apply` (pour into template named styles) → `elements`
   (margins/header/footer/PAGE fields/TOC/LoF/SEQ captions) → `export`
   (LibreOffice + injected Basic macro: refreshes TOC/fields, writes *tagged*
   PDF) → `qa` (markdown report of everything uncertain).
2. **Brand templates** — profile's `template_file` or `--template-docx` points
   at the org's own .docx; only the template *body* is cleared, so
   header/footer logos survive. `cover_page.keep: true` preserves the cover
   section; `replace:` fills its placeholders; `--set "Name=Value"` (CLI) and
   GUI "Document fields" supply per-document values; leftovers are QA-flagged.
3. **Local AI (optional)** — `classify_ai.py` re-judges only low-confidence
   blocks via localhost Ollama; every failure mode falls back to heuristics.
4. **GUI** — stdlib http.server single-page app (`src/docformat/assets/gui.html`),
   no dependencies, no CDN. Shows QA warnings + low-confidence table inline.
5. **Content preservation** (ideas from Murchey/doc-form-master, GPL —
   reimplemented, no code copied): OMML equations verbatim, images re-embedded
   (size + alt), tables content-intact + `table_style`, footnotes via
   OPC-level `FootnoteWriter` (python-docx has no footnote API), inline
   bold/italic emphasis kept in body text, OLE/MathType QA-flagged.
6. **Input conversion** — `.doc/.odt/.rtf` via soffice, `.txt` direct,
   `.md` via pandoc if present (`convert.py`).
7. **Presets** — `config/template_profile.apa.yaml`, `...gbt7713.yaml`.

## Key design decisions (don't re-litigate without cause)

- **Template is the source of truth.** Never invent formatting; missing mapped
  styles degrade to template defaults + a QA "Template / profile warnings"
  entry (never a hard error — real templates are messy).
- **Style objects, not names.** `apply._paragraph_styles()` resolves styles by
  UI name *and* style id and assigns objects — python-docx name lookup breaks
  on real-world templates (nonstandard internal names, duplicate definitions,
  dangling style refs). RedLotus's template exercises all of this.
- **Human-in-the-loop.** Anything uncertain (confidence < 0.6, unfilled
  placeholders, uncarried objects) goes to `qa_report.md` / `Document.notes`,
  never a silent guess. Deliberate: some heuristics return 0.55 *on purpose*.
- **Offline is non-negotiable.** Only network touch is localhost Ollama behind
  `--ai`. PDF export needs LibreOffice Writer (`soffice` on PATH) — a plain
  `--convert-to pdf` does NOT refresh TOCs, hence the seeded-profile Basic
  macro in `export.py` (profile must be pre-initialized in a separate no-op
  launch or LO ignores the macro).
- **GUI serving:** one response per connection (`Connection: close`);
  `#results` visibility needs `style.display = "block"` (stylesheet default is
  `none` — `""` does not override it).

## Fixtures & templates

- `samples/input_messy.docx` — formatting-mess fixture (scripts/make_messy_sample.py)
- `samples/input_rich.docx` — content fixture: OMML equation, images, table,
  footnote, emphasis, numbered headings (scripts/make_rich_sample.py)
- `templates/org_standard.docx` — generated branded demo template (scripts/make_template.py)
- `templates/RedLotus_Master_Template.docx` — real client template (uploaded by
  user); profile `config/template_profile.redlotus.yaml`; regression tests in
  `tests/test_redlotus.py`
- `tests/golden/input_messy_styles.tsv` — golden style/text sequence

## Expert review (2026-07-10)

A four-perspective review ran (correctness, security, deployment, product).
**Tier 1 (silent content loss) is FIXED**: tracked changes auto-accepted with a
QA note, fields frozen to cached text, content controls unwrapped, native
w:numPr lists detected, hyperlinks carried (external) or QA-counted (internal),
endnotes carried as footnotes, comments listed in QA, table relationship ids
rewritten or stripped (never leaked), numbered-heading vs list discrimination
(sequence-aware), bare numbers no longer become H1s, letter markers now
case-sensitive. Regression suite: `tests/test_fidelity.py`.
Remaining Tier 2 (deployment) and Tier 3 (versatility) items:
`docs/REVIEW_BACKLOG.md` — Tier 2 must land before team rollout.

## Known gaps / natural next steps

- RedLotus template defines no Body/Caption/Quote styles → QA warning on every
  run. Fix belongs in the template (add "Body Text"/"Caption" styles in Word).
- Its Heading 3 lacks an outline level, so H3s don't appear in the TOC
  (template-side fix).
- Footnotes carry as plain text (formatting inside notes is dropped, QA-noted).
- Numbered lists map to `List Bullet` (manual `1.` markers become bullets);
  a ListNumber BlockType + `List Number` mapping was proposed and never
  requested — ask before building.
- `dist/docformat` is stale relative to the latest commits — rebuild with
  `bash scripts/build_exe.sh`. Executables are per-OS (no cross-compile);
  a CI matrix (GitHub Actions) for win/mac/linux builds was floated, not built.
- GUI could pre-scan an uploaded template for `[placeholders]` and auto-suggest
  field rows (floated, not built).
- No PR exists; work is branch-only. The user has not asked for one.

## Environment notes (for a fresh container)

- `apt-get install -y --no-install-recommends libreoffice-writer` (container
  ships only libreoffice-core; run `apt-get update` first if 404s) and
  `poppler-utils` (pdftotext, used by tests/debugging only).
- Playwright + `/opt/pw-browsers/chromium` (`args=["--no-sandbox"]`) was used
  for GUI screenshots; `pip install playwright` suffices, don't run
  `playwright install`.
