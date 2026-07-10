# Expert-review backlog

A four-perspective review (pipeline correctness, security, deployment, product)
was run on 2026-07-10. **Tier 1 — silent content loss — is fixed** (see
`tests/test_fidelity.py` for the regression suite). This file tracks what
remains, in priority order.

## Tier 2 — deployment & dependability (before team rollout)

- [ ] LibreOffice discovery: search default install paths on Windows
      (`C:\Program Files\LibreOffice\program\soffice.exe`) and macOS
      (`/Applications/LibreOffice.app/Contents/MacOS/soffice`) + a
      `DOCFORMAT_SOFFICE` env override (`export.py`, `convert.py`).
- [ ] `convert._via_soffice`: isolate with `-env:UserInstallation` like
      `export.py` does (fails when desktop LibreOffice is open).
- [ ] Stale-output masking: unlink the target PDF/docx before invoking
      soffice in `export.py` and `convert.py`.
- [ ] Subprocess timeouts + surface stderr in error messages.
- [ ] Logging: rotating file log in a per-user app-data dir; log tracebacks
      and soffice stderr; keep friendly client messages.
- [ ] Friendly CLI/GUI errors for corrupt docx, missing LibreOffice, busy port
      (retry on port 0 or point at the running instance).
- [ ] GUI hardening: validate Host header + Origin on POST (CSRF/DNS-rebinding),
      cap upload size (~100 MB), evict/delete session dirs (LRU + shutdown
      cleanup), socket timeouts.
- [ ] Packaging: commit `docformat.spec` (currently gitignored/untracked!),
      un-drift it from `build_exe.sh` (spec bundles only the example profile),
      disable UPX, Windows path-separator handling, CI matrix
      (win/mac/linux build + pytest), code signing / notarization.
- [ ] `docformat --version`, CHANGELOG.md, real author in pyproject.
- [ ] Windows `.txt` encoding: try utf-8 then cp1252 in `convert._from_text`.
- [ ] `_replace_placeholders` cross-run fallback duplicates hyperlink text and
      collapses run formatting (`elements.py`) — rebuild only spanned runs.
- [ ] `_front_matter_anchor` hardcodes "Heading 1" — use the profile's mapped
      H1 style name; when anchorless with a kept cover, insert after the cover.
- [ ] `_auto_number_captions` drops non-text runs when rebuilding captions.
- [ ] Profile validation at load (missing keys, unknown keys, style_map
      completeness) with friendly errors.

## Tier 3 — versatility (post-pilot, by user feedback)

- [ ] Dry-run/preview mode + per-document classification overrides file
      (re-runs currently destroy manual fixes).
- [ ] Batch processing with a consolidated QA summary.
- [ ] `docformat inspect-template` (list styles + placeholders — also feeds
      GUI field auto-suggestion) and `docformat validate-profile`.
- [ ] GUI: show active profile, progress during PDF export, block anchors in
      the review table, honest signal when --ai is checked but Ollama absent.
- [ ] Character formatting beyond bold/italic: sub/superscript (H₂O/x² are
      *meaning*, not styling), underline, strikethrough, highlight.
- [ ] Sections/page breaks/landscape carried or QA-flagged; text-box content
      carry (currently QA-flagged only); VML image conversion.
- [ ] CJK/RTL: char-based shortness, "。" as period, 图/表/第X章 patterns.
- [ ] QA report anchors (nearest heading per row) or injected Word comments.
- [ ] Honor `output.filename` profile setting (currently dead config).
- [ ] ListNumber block type so manual "1." lists can map to `List Number`.
