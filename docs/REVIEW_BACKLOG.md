# Expert-review backlog

A four-perspective review (pipeline correctness, security, deployment, product)
was run on 2026-07-10. **Tier 1 — silent content loss — is fixed** (see
`tests/test_fidelity.py` for the regression suite). This file tracks what
remains, in priority order.

## Tier 2 — deployment & dependability (before team rollout)

- [x] LibreOffice discovery: search default install paths on Windows
      (`C:\Program Files\LibreOffice\program\soffice.exe`) and macOS
      (`/Applications/LibreOffice.app/Contents/MacOS/soffice`) + a
      `DOCFORMAT_SOFFICE` env override (`export.py`, `convert.py`).
- [x] `convert._via_soffice`: isolate with `-env:UserInstallation` like
      `export.py` does (fails when desktop LibreOffice is open).
- [x] Stale-output masking: unlink the target PDF/docx before invoking
      soffice in `export.py` and `convert.py`.
- [x] Subprocess timeouts + surface stderr in error messages.
- [x] Logging: rotating file log in a per-user app-data dir; log tracebacks
      and soffice stderr; keep friendly client messages.
- [x] Friendly CLI/GUI errors for corrupt docx, missing LibreOffice, busy port
      (retry on port 0 or point at the running instance).
- [x] GUI hardening: validate Host header + Origin on POST (CSRF/DNS-rebinding),
      cap upload size (~100 MB), evict/delete session dirs (LRU + shutdown
      cleanup), socket timeouts.
- [x] Packaging (except signing): commit `docformat.spec` (currently gitignored/untracked!),
      un-drift it from `build_exe.sh` (spec bundles only the example profile),
      disable UPX, Windows path-separator handling, CI matrix
      (win/mac/linux build + pytest) — DONE. Code signing / notarization
      still requires certificates (procurement lead time).
- [x] `docformat --version`, CHANGELOG.md, real author in pyproject.
- [x] Windows `.txt` encoding: try utf-8 then cp1252 in `convert._from_text`.
- [x] `_replace_placeholders` cross-run fallback duplicates hyperlink text and
      collapses run formatting (`elements.py`) — rebuild only spanned runs.
- [x] `_front_matter_anchor` hardcodes "Heading 1" — use the profile's mapped
      H1 style name; when anchorless with a kept cover, insert after the cover.
- [x] `_auto_number_captions` drops non-text runs when rebuilding captions.
- [x] Profile validation at load (missing keys, unknown keys, style_map
      completeness) with friendly errors.

## Tier 3 — versatility (post-pilot, by user feedback)

- [x] Dry-run/preview mode + per-document classification overrides file
      (re-runs no longer destroy manual fixes) — `format --dry-run` /
      `--overrides FILE`, `src/docformat/overrides.py`.
- [x] Batch processing with a consolidated QA summary — `docformat batch`,
      `src/docformat/batch.py`.
- [x] `docformat inspect-template` (list styles + placeholders) and
      `docformat validate-profile` — `src/docformat/inspect.py`.
- [x] Character formatting beyond bold/italic: sub/superscript (H₂O/x² are
      *meaning*), underline, strikethrough. (Highlight still deferred — it is a
      colour the template governs, not clearly semantic.)
- [x] Honor `output.filename` profile setting — `template.output_stem`.
- [x] ListNumber block type so manual "1." lists map to `List Number`.
- [x] GUI: show active profile, progress during PDF export, block anchors in
      the review table, honest signal when --ai is checked but Ollama absent
      (`/meta` endpoint, `gui.html`). (inspect-template's placeholder extraction
      is still available to feed GUI field auto-suggestion — not wired yet.)
- [x] QA report anchors (nearest heading per row) — `qa.heading_anchors`, shown
      in the report's "Under heading" column and the GUI review table.
- [x] Word-native (w:numPr) lists: detect ordered vs bullet from numbering.xml
      so ribbon-numbered lists also become ListNumber — `ingest._numbering_formats`
      + `FormatHints.list_ordered`.
- [ ] Sections/page breaks/landscape carried or QA-flagged; text-box content
      carry (currently QA-flagged only); VML image conversion.
- [ ] CJK/RTL: char-based shortness, "。" as period, 图/表/第X章 patterns.
- [ ] Injected Word comments on flagged blocks (anchors done; comments still open).
- [ ] Highlight (font.highlight_color) carry, if pilots want author annotations.
