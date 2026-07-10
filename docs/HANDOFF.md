# Project Status & Handoff

> Last updated: 2026-07-10. Read `PROJECT_SPEC.md` first (the build contract),
> then this file (what actually exists and why), then `docs/BUILD_STATUS.md`
> (deployment readiness) and `docs/REVIEW_BACKLOG.md` (what's left).

## TL;DR for the next session

- **Branch / main:** Tiers 1–4 are all merged into `main` (PR #1 = Tiers 1–3,
  PR #2 = Tier 4). Start new work from `main`. The working branch
  `claude/tier-3-continuation-cy9ari` is reused per session — restart it from
  `main` before adding commits.
- **Tests:** 78 passing (`python -m pytest -q`). Lint clean
  (`ruff check src tests scripts`).
- **CI:** green on `main` — `.github/workflows/ci.yml` runs lint+pytest on
  Ubuntu (with LibreOffice), then builds + smoke-tests PyInstaller executables
  on Windows/macOS/Linux. Last run on `main` (commit `0ad2a3c`): all 4 jobs ✅.
- **Status:** Spec v1 complete. **Tier 1** (silent content loss), **Tier 2**
  (deployment hardening), **Tier 3** (versatility) and **Tier 4** (real-world
  readiness) are all done. See `docs/REVIEW_BACKLOG.md` for what remains
  (all optional/situational): CJK/RTL heuristics, injected Word comments
  (deliberately declined — would pollute the publish-ready output; QA anchors
  cover locate-ability), and VML legacy-image conversion.
- **Only true blocker left for a desktop rollout:** code-signing /
  notarization needs certificates only the owner can procure. Everything
  else technical is done.

Working end-to-end today:

```bash
pip install -e ".[dev]"

# CLI — full pipeline: convert -> ingest -> classify -> apply -> elements -> QA -> tagged PDF
docformat format samples/input_rich.docx -t config/template_profile.redlotus.yaml \
  --out out -s "Client Name=Acme Corporation" -s "Project No.=RL-2026-042"

docformat format draft.docx -t <profile> --out out --dry-run     # preview plan (Tier 3)
docformat format draft.docx -t <profile> --out out --overrides out/draft_overrides.yaml
docformat batch drafts/ -t <profile> --out out                   # many docs + summary
docformat inspect-template <template.docx>                        # styles + placeholders
docformat validate-profile <profile.yaml>                        # styles exist in template
docformat gui            # local web app, 127.0.0.1, drag & drop; GET /meta
docformat --version      # 0.1.0
bash scripts/build_exe.sh   # -> dist/docformat (rebuild after changes; runs docformat.spec)
```

## Module map (`src/docformat/`)

| Module          | Responsibility |
|-----------------|----------------|
| `models.py`     | `Block`, `Segment`, `FormatHints`, `Document`, `BlockType`. Pure data. |
| `ingest.py`     | .docx → `Document`. Walks body in order; per-paragraph `Segment`s (text + emphasis + super/subscript/underline/strike/highlight + hyperlink, OMML math XML, image blobs, foot/endnote refs, OLE); TABLE blocks carry `w:tbl` XML + image/link resources. Descends into `w:ins`/`w:sdt`/`w:fldSimple`; **inlines text-box content**; carries **manual page breaks** and flags section breaks/landscape; resolves `numbering.xml` for ordered-vs-bullet (`_numbering_formats`). Counts dropped/converted content into `Document.notes`. |
| `classify.py`   | Heuristic labeller (PROJECT_SPEC §5 + Tier-1 number/list discrimination). Ordered markers + native ordered lists → `ListNumber`, bullets → `ListItem`. Confidence 0–1; <0.6 → QA. |
| `classify_ai.py`| Optional: localhost Ollama re-judges low-confidence blocks; hard fallback to heuristics (QA-notes when requested but Ollama absent). |
| `template.py`   | Load + **validate** a profile YAML (`load_profile`); `apply_field_values` for `--set`; `output_stem` for `output.filename`. |
| `apply.py`      | Pour blocks into template named styles (style OBJECTS, not names). Carries math/images/emphasis (bold/italic/under/strike/super-sub/highlight)/hyperlinks/page-breaks; `ListNumber` falls back to `ListItem` style; rewrites/strips table relationship ids; cover-page keep; footnote writing. |
| `elements.py`   | Page setup, header/footer + PAGE fields, placeholder replace, SEQ captions, TOC/LoF fields. |
| `export.py`     | Tagged PDF via LibreOffice + seeded Basic macro (refreshes TOC/fields). |
| `footnotes.py`  | OPC-level footnotes part writer (python-docx has no footnote API). |
| `convert.py`    | .doc/.odt/.rtf → docx (soffice), .txt direct (utf-8/cp1252), .md (pandoc). |
| `soffice.py`    | **Cross-platform LibreOffice discovery**, isolated profiles, timeouts, stderr surfacing. |
| `qa.py`         | `qa_report.md`: low-confidence blocks (with an "Under heading" anchor from `heading_anchors`), heading jumps, alt text, `Document.notes`. `review_counts`/`needs_review`/`heading_anchors` shared with batch + GUI. |
| `overrides.py`  | Human classification plan: `write_plan` (`--dry-run`), `apply_overrides` (`--overrides`). Pins are text-snippet-guarded against draft drift. |
| `batch.py`      | `docformat batch`: expand files/dirs, format each into its own subfolder, write consolidated `batch_summary.md`; one bad doc is captured, not fatal. |
| `inspect.py`    | `inspect_template` (styles + `[placeholders]`) and `validate_profile` (mapped styles exist in the template). Read-only. |
| `log.py`        | Rotating file log in per-OS user dir. |
| `errors.py`     | Maps expected exceptions → friendly one-line messages (shared CLI/GUI). |
| `cli.py`        | `docformat format` (+ `--dry-run`/`--overrides`) / `batch` / `inspect-template` / `validate-profile` / `gui` / `--version`; friendly error wrapping. |
| `gui.py`        | Hardened stdlib HTTP server on 127.0.0.1 + `assets/gui.html`. `GET /meta` reports active profile + PDF/AI availability; review rows carry block index + heading anchor. |

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
   dry-run/overrides, batch, output.filename, ListNumber. **Merged to `main` as
   PR #1.**
10. **Tier 4** — real-world readiness (see below): GUI polish, honest AI
    fallback, QA anchors, native ordered lists, page-breaks + section flagging,
    highlight carry, text-box content carry. **Merged to `main` as PR #2.**

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

## Tier 4 — real-world readiness (DONE, merged to `main` as PR #2)

- **GUI polish** (`gui.py` `GET /meta` + `assets/gui.html`, `tests/test_gui.py`):
  shows the active profile; disables PDF with a note when LibreOffice is absent;
  annotates the AI option honestly when Ollama is down; elapsed-time counter;
  review rows carry a `#` index and an "Under heading" anchor.
- **Honest AI fallback** (`classify_ai`): requesting `--ai`/AI with no reachable
  Ollama model records a QA note instead of passing heuristic labels off as AI.
- **QA anchors** (`qa.heading_anchors`): nearest heading above each flagged block,
  in the report ("Under heading" column) and the GUI.
- **Native ordered lists**: `ingest._numbering_formats` resolves `numbering.xml`
  → `FormatHints.list_ordered`; ribbon-numbered (decimal/letter/roman) lists →
  `ListNumber`, bullets/unresolvable stay `ListItem`.
- **Page breaks + sections** (`tests/test_fidelity.py`): manual page breaks
  (Ctrl+Enter / `pageBreakBefore`) carried via `Block.page_break_before`;
  section breaks + landscape are QA-flagged (`ingest._section_notes`) — the
  template owns page setup.
- **Highlight carry** (`Segment.highlight`): highlighter marks preserved as
  author annotations (always kept, never treated as decorative).
- **Text-box content carry** (`ingest._outer_textboxes`): text-box paragraphs/
  tables inlined into the flow in reading order (was silently dropped), QA-noted.
- **Audit fixes** (PR #2 self-review): `w:highlight` inserted in correct `rPr`
  schema order (typed setter, not raw append); page-break scan ignores breaks
  nested inside text boxes.

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
  footnote, emphasis, numbered headings, and character formatting
  (sub/superscript, underline, strike, highlight) (`scripts/make_rich_sample.py`).
- `templates/org_standard.docx` — generated branded demo (`scripts/make_template.py`).
- `templates/RedLotus_Master_Template.docx` — real client template;
  profile `config/template_profile.redlotus.yaml`; tests `tests/test_redlotus.py`.
- `config/template_profile.{example,apa,gbt7713,redlotus}.yaml`.
- `tests/golden/input_messy_styles.tsv` — golden style/text sequence.

## Where to start next session

Tiers 1–4 are all merged to `main`. Start from `main`
(`git fetch origin main && git checkout -B <branch> origin/main`). Everything
in `docs/REVIEW_BACKLOG.md` that remains is **optional / situational** — pick by
real need, not sequence:

1. **Code-signing / notarization** — the only real rollout blocker, and it's on
   the owner: Apple Developer ID + notarization (macOS), an Authenticode cert
   (Windows). Until then, ship via `pip install` or an IT-whitelisted binary.
2. **CJK/RTL heuristics** — only worth doing if real Chinese/Arabic/Hebrew
   drafts exist. The GB/T page geometry ships but the classifier is English-only
   (char-based shortness, "。" as period, 图/表/第X章 patterns). No CJK fixture
   yet — build one first; the classifier is carefully tuned, so guard the golden.
3. **Injected Word comments** on flagged blocks — *deliberately declined* in
   Tier 4: comments in the "publish-ready" output risk being published by
   accident, and the QA anchors already give locate-ability. Only revisit if a
   pilot explicitly asks, and make it opt-in.
4. **VML (legacy) image conversion** — still QA-flagged only; niche in modern
   docs.

For a fresh container, see "Environment notes" below (install
`libreoffice-writer` + `poppler-utils`; two `test_smoke` tests skip without
LibreOffice).

## Environment notes (fresh container)

- `apt-get install -y --no-install-recommends libreoffice-writer` (container
  ships only libreoffice-core; `apt-get update` first if 404s) and
  `poppler-utils` (pdftotext, tests/debug only).
- Playwright + `/opt/pw-browsers/chromium` (`args=["--no-sandbox"]`) for GUI
  screenshots; `pip install playwright`, don't run `playwright install`.
- Executable smoke test: `dist/docformat --version`; full run needs a profile
  + template on disk (bundled ones live under the PyInstaller `_MEIPASS`).
