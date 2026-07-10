# Project Status & Handoff

> Last updated: 2026-07-10. Read `PROJECT_SPEC.md` first (the build contract),
> then this file (what actually exists and why), then `docs/BUILD_STATUS.md`
> (deployment readiness) and `docs/REVIEW_BACKLOG.md` (what's left).

## TL;DR for the next session

- **Branch:** `claude/docformat-offline-tool-3xb0yq` (all work here, pushed).
  No PR opened yet — the user hasn't asked for one.
- **Tests:** 51 passing (`python -m pytest -q`). Lint clean
  (`ruff check src tests scripts`).
- **CI:** green — `.github/workflows/ci.yml` runs lint+pytest on Ubuntu (with
  LibreOffice) then builds PyInstaller executables on Windows/macOS/Linux.
  Last run: all 4 jobs succeeded.
- **Status:** Spec v1 complete. Two expert-review tiers done: **Tier 1**
  (silent content loss) and **Tier 2** (deployment hardening). **Tier 3**
  (versatility) is the remaining roadmap — see `docs/REVIEW_BACKLOG.md`.
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
| `qa.py`         | `qa_report.md`: low-confidence blocks, heading jumps, alt text, `Document.notes`. |
| `log.py`        | Rotating file log in per-OS user dir. |
| `errors.py`     | Maps expected exceptions → friendly one-line messages (shared CLI/GUI). |
| `cli.py`        | `docformat format` / `gui` / `--version`; friendly error wrapping. |
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

## Where to start next session — Tier 3 (post-pilot versatility)

See `docs/REVIEW_BACKLOG.md` for the full list. Highest-value:
1. **Dry-run/preview + per-document overrides file** — re-runs currently
   destroy manual fixes; writers need a way to pin classifications.
2. **Batch processing** with a consolidated QA summary (migrate N docs).
3. **`docformat inspect-template` / `validate-profile`** — list a template's
   styles + placeholders; also feeds GUI field auto-suggestion.
4. **Character formatting** beyond bold/italic — sub/superscript (H₂O/x² is
   *meaning*), underline, strikethrough, highlight.
5. GUI: show active profile, export progress, honest "Ollama not running".
6. CJK/RTL heuristics (GB/T profile ships but classifier is English-only).

## Environment notes (fresh container)

- `apt-get install -y --no-install-recommends libreoffice-writer` (container
  ships only libreoffice-core; `apt-get update` first if 404s) and
  `poppler-utils` (pdftotext, tests/debug only).
- Playwright + `/opt/pw-browsers/chromium` (`args=["--no-sandbox"]`) for GUI
  screenshots; `pip install playwright`, don't run `playwright install`.
- Executable smoke test: `dist/docformat --version`; full run needs a profile
  + template on disk (bundled ones live under the PyInstaller `_MEIPASS`).
