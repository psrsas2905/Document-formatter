# Project Status & Handoff

> Last updated: 2026-07-10. Read `PROJECT_SPEC.md` first (the build contract),
> then this file (what actually exists and why), then `docs/BUILD_STATUS.md`
> (deployment readiness) and `docs/REVIEW_BACKLOG.md` (what's left).

## TL;DR for the next session

- **Branch:** Tier 3 work continues on `claude/tier-3-continuation-cy9ari`
  (based on the completed `claude/docformat-offline-tool-3xb0yq`). No PR opened
  yet — the user hasn't asked for one.
- **Tests:** 71 passing (`python -m pytest -q`). Lint clean
  (`ruff check src tests scripts`).
- **CI:** green — `.github/workflows/ci.yml` runs lint+pytest on Ubuntu (with
  LibreOffice) then builds PyInstaller executables on Windows/macOS/Linux.
- **Status:** Spec v1 complete. **Tier 1** (silent content loss), **Tier 2**
  (deployment hardening) and most of **Tier 3** (versatility) are done — see
  `docs/REVIEW_BACKLOG.md` for the remaining Tier 3 items (GUI polish,
  sections/page-breaks, CJK/RTL, QA anchors).
- **Only true blocker left for a desktop rollout:** code-signing /
  notarization needs certificates only the owner can procure. Everything
  else technical is done.

Working end-to-end today:

```bash
pip install -e ".[dev]"

# CLI — full pipeline: convert -> ingest -> classify -> apply -> elements -> QA -> tagged PDF
docformat format samples/input_rich.docx -t config/template_profile.redlotus.yaml \
  --out out -s "Client Name=Acme Corporation" -s "Project No.=RL-2026-042"

docformat gui            # local web app, 127.0.0.1, drag & drop
docformat --version      # 0.1.0
bash scripts/build_exe.sh   # -> dist/docformat (rebuild after changes; runs docformat.spec)
```

## Module map (`src/docformat/`)

| Module          | Responsibility |
|-----------------|----------------|
| `models.py`     | `Block`, `Segment`, `FormatHints`, `Document`, `BlockType`. Pure data. |
| `ingest.py`     | .docx → `Document`. Walks body in order; per-paragraph `Segment`s (text+emphasis+hyperlink, OMML math XML, image blobs, foot/endnote refs, OLE); TABLE blocks carry `w:tbl` XML + image/link resources. Descends into `w:ins`/`w:sdt`/`w:fldSimple`. Counts dropped/converted content into `Document.notes`. |
| `classify.py`   | Heuristic labeller (PROJECT_SPEC §5 + Tier-1 number/list discrimination). Confidence 0–1; <0.6 → QA. |
| `classify_ai.py`| Optional: localhost Ollama re-judges low-confidence blocks; hard fallback to heuristics. |
| `template.py`   | Load + **validate** a profile YAML (`load_profile`); `apply_field_values` for `--set`. |
| `apply.py`      | Pour blocks into template named styles (style OBJECTS, not names). Carries math/images/emphasis/hyperlinks; rewrites/strips table relationship ids; cover-page keep; footnote writing. |
| `elements.py`   | Page setup, header/footer + PAGE fields, placeholder replace, SEQ captions, TOC/LoF fields. |
| `export.py`     | Tagged PDF via LibreOffice + seeded Basic macro (refreshes TOC/fields). |
| `footnotes.py`  | OPC-level footnotes part writer (python-docx has no footnote API). |
| `convert.py`    | .doc/.odt/.rtf → docx (soffice), .txt direct (utf-8/cp1252), .md (pandoc). |
| `soffice.py`    | **Cross-platform LibreOffice discovery**, isolated profiles, timeouts, stderr surfacing. |
| `qa.py`         | `qa_report.md`: low-confidence blocks, heading jumps, alt text, `Document.notes`. `review_counts`/`needs_review` shared with batch. |
| `overrides.py`  | Human classification plan: `write_plan` (`--dry-run`), `apply_overrides` (`--overrides`). Pins are text-snippet-guarded against draft drift. |
| `batch.py`      | `docformat batch`: expand files/dirs, format each into its own subfolder, write consolidated `batch_summary.md`; one bad doc is captured, not fatal. |
| `inspect.py`    | `inspect_template` (styles + `[placeholders]`) and `validate_profile` (mapped styles exist in the template). Read-only. |
| `log.py`        | Rotating file log in per-OS user dir. |
| `errors.py`     | Maps expected exceptions → friendly one-line messages (shared CLI/GUI). |
| `cli.py`        | `docformat format` (+ `--dry-run`/`--overrides`) / `batch` / `inspect-template` / `validate-profile` / `gui` / `--version`; friendly error wrapping. |
| `gui.py`        | Hardened stdlib HTTP server on 127.0.0.1 + `assets/gui.html`. |

## What was built, in order (one commit per stage, newest last)

1. Scaffold → deterministic core (ingest/classify/apply/elements/export/qa).
2. Brand templates (`--template-docx`, cover-page keep, `replace:`/`--set`).
3. Optional local AI (`--ai`), local web GUI, PyInstaller packaging.
4. Content preservation v1 (equations, images, tables, footnotes, emphasis).
5. Input conversion; APA + GB/T presets.
6. RedLotus real-template trial (style-object resolution, missing-style
   degradation, cover placeholders, per-document `--set` fields).
7. **Tier 1 review fixes** — eliminate silent content loss (see below).
8. **Tier 2** — deployment hardening across 4 commits (see below).
9. **Tier 3** — versatility (see below): character formatting, inspect/validate,
   dry-run/overrides, batch, output.filename, ListNumber.

## Tier 1 — silent content loss (DONE, `tests/test_fidelity.py`)

The pipeline previously violated its own "never a silent guess" contract.
Now every category is either carried or QA-reported:

- Tracked changes: insertions kept, deletions accepted, both QA-noted.
- Fields (`w:fldSimple`): frozen to cached text, QA-noted.
- Content controls (`w:sdt`): unwrapped (body-level and inline).
- Word-native lists (`w:numPr`): detected with real indent level.
- Hyperlinks: external URLs re-created as real relationships; internal counted.
- Endnotes: carried as footnotes; comments/text-boxes/VML: counted in QA.
- Table relationship ids: rewritten (images/links) or stripped (never leaked
  into the template package → no more corrupt-output risk).
- Classifier: numbered-heading vs list disambiguation (sequence-aware); bare
  "5 people…" no longer becomes H1; letter markers case-sensitive.

## Tier 2 — deployment & dependability (DONE except signing)

- `soffice.py`: DOCFORMAT_SOFFICE env → PATH → default Win/macOS/Linux install
  paths. Isolated profile + timeout on **every** soffice/pandoc call. Targets
  unlinked before conversion so a stale file can't mask a failure.
- `.txt` cp1252 fallback. Profile validation with friendly errors.
- `elements.py`: placeholder replace rebuilds only spanned runs (no hyperlink
  dup); captions keep inline images; front-matter anchors on the profile's H1
  and never lands above a kept cover.
- `log.py` rotating logs; CLI/GUI show one-line messages, log full tracebacks.
  `docformat --version`; GUI busy-port fallback.
- GUI hardening: Host + Origin validation (CSRF/DNS-rebind), 100 MB upload
  cap, session eviction (max 20) + shutdown cleanup, socket timeout.
- Packaging: `docformat.spec` COMMITTED (was gitignored) and single build
  source; UPX off (AV); `collect_all('docx')`. CI matrix win/mac/linux.
  `CHANGELOG.md`; version single-sourced from `docformat.__version__`.

## Tier 3 — versatility (DONE this session, `claude/tier-3-continuation-cy9ari`)

- **Character formatting** (`tests/test_rich.py`): sub/superscript carry on every
  block (meaning, e.g. x²/H₂O); underline/strike are inline emphasis (kept in
  Body/List/Quote, dropped when uniform, like bold/italic). Read in
  `ingest._run_segments`, emitted in `apply._emit_paragraph`.
- **inspect-template / validate-profile** (`inspect.py`, `tests/test_inspect.py`):
  onboarding helpers. `Normal` is always a valid mapped style (Word's default
  applies even when a template omits it — RedLotus does).
- **Dry-run + overrides** (`overrides.py`, `tests/test_overrides.py`): the plan
  pre-fills sub-threshold blocks and lists a full document map as comments; a
  pin sets confidence 1.0 (drops out of QA); prefix text-guard tolerates the
  plan's truncated previews but catches genuine drift.
- **batch** (`batch.py`, `tests/test_batch.py`): per-doc subfolders +
  `batch_summary.md`, worst-review-first; survives one bad document; optional
  `--overrides-dir`.
- **output.filename** honored (`template.output_stem`); **ListNumber** block type
  for ordered typed markers (bullets stay LIST_ITEM; ListNumber is an optional
  profile mapping, falls back to the ListItem style).

## Key design decisions (don't re-litigate without cause)

- **Template is the source of truth.** Never invent formatting; missing mapped
  styles degrade to template defaults + a QA note (never a hard error).
- **Style objects, not names** (`apply._paragraph_styles`) — python-docx name
  lookup breaks on real templates (nonstandard ids, dupes, dangling refs).
- **Human-in-the-loop.** Uncertain → `qa_report.md` / `Document.notes`. Some
  heuristics return 0.55 *on purpose* to force QA review.
- **Offline.** Only network touch is localhost Ollama behind `--ai`. PDF needs
  LibreOffice; a plain `--convert-to pdf` does NOT refresh TOCs, hence the
  seeded-profile Basic macro in `export.py`.
- **GUI serving:** one response per connection; `#results` needs
  `display="block"` (stylesheet default `none`).

## Fixtures & templates

- `samples/input_messy.docx` — formatting-mess fixture (`scripts/make_messy_sample.py`).
- `samples/input_rich.docx` — content fixture: equation, images, table,
  footnote, emphasis, numbered headings (`scripts/make_rich_sample.py`).
- `templates/org_standard.docx` — generated branded demo (`scripts/make_template.py`).
- `templates/RedLotus_Master_Template.docx` — real client template;
  profile `config/template_profile.redlotus.yaml`; tests `tests/test_redlotus.py`.
- `config/template_profile.{example,apa,gbt7713,redlotus}.yaml`.
- `tests/golden/input_messy_styles.tsv` — golden style/text sequence.

## Where to start next session — remaining Tier 3

The high-value Tier 3 items are done (above). What's left, see
`docs/REVIEW_BACKLOG.md`:
1. **GUI polish** — surface the active profile, PDF-export progress, block
   anchors in the review table, and an honest signal when `--ai` is checked but
   Ollama isn't running. `inspect.py`'s placeholder extraction is ready to feed
   GUI field auto-suggestion.
2. **Sections / page breaks / landscape** carried or QA-flagged; text-box
   content carry (currently QA-flagged only); VML image conversion.
3. **CJK/RTL heuristics** (GB/T profile ships but the classifier is English-only:
   char-based shortness, "。" as period, 图/表/第X章 patterns).
4. **QA report anchors** (nearest heading per row) or injected Word comments.
5. **Word-native (w:numPr) ordered lists** → ListNumber by reading numbering.xml
   (currently only typed "1."/"a)" markers route to ListNumber).

## Environment notes (fresh container)

- `apt-get install -y --no-install-recommends libreoffice-writer` (container
  ships only libreoffice-core; `apt-get update` first if 404s) and
  `poppler-utils` (pdftotext, tests/debug only).
- Playwright + `/opt/pw-browsers/chromium` (`args=["--no-sandbox"]`) for GUI
  screenshots; `pip install playwright`, don't run `playwright install`.
- Executable smoke test: `dist/docformat --version`; full run needs a profile
  + template on disk (bundled ones live under the PyInstaller `_MEIPASS`).
