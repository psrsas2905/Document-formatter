# Changelog

## Unreleased — Tier 4 (real-world readiness)

- **GUI honesty & polish**: the local web app now shows the active template
  profile up front; disables PDF export with a note when LibreOffice isn't
  installed; annotates the AI option honestly when Ollama isn't running; shows
  an elapsed-time counter during formatting; and lists each flagged block's
  index (matching the `--overrides` plan) in the review table.
- **Honest AI fallback**: requesting AI assist when no local Ollama model is
  reachable now records a QA note (CLI and GUI) instead of silently presenting
  rule-based labels as AI-reviewed.

## Unreleased — Tier 3 (versatility)

Post-pilot versatility features, built on the v1 pipeline:

- **Manual fixes survive re-runs**: `format --dry-run` writes an editable
  classification plan; `format --overrides FILE` re-applies those human
  decisions (pinned blocks are trusted and drop out of QA). Pins are guarded by
  a text snippet, so a drifted draft skips the pin and QA-notes it instead of
  mis-labelling.
- **Batch processing**: `docformat batch FILES/DIRS` formats many drafts, each
  into its own subfolder, and writes a consolidated `batch_summary.md`
  (worst-review-first). One bad document is reported, not fatal.
  `--overrides-dir` re-applies per-document plans.
- **Template onboarding**: `docformat inspect-template` lists a template's named
  styles and `[placeholder]` tokens; `docformat validate-profile` checks every
  style a profile maps to actually exists in its template.
- **Semantic character formatting**: sub/superscript (x², H₂O), underline and
  strikethrough are preserved (previously only bold/italic).
- **Ordered lists**: a new `ListNumber` block type keeps manual "1." / "a)"
  lists numbered instead of rendering them as bullets.
- **`output.filename`** profile setting is now honored ({basename}/{version}/
  {date} tokens); was previously dead config.

## 0.1.0 — 2026-07-10 (unreleased)

Initial version. Highlights, in build order:

- **Deterministic pipeline**: ingest → heuristic classify → apply template
  named styles → headers/footers/page numbers/TOC/List of Figures/SEQ captions
  → tagged-PDF export via LibreOffice (with real field/TOC refresh) → QA report.
- **Brand templates**: pour content into any organization's .docx/.dotx —
  logos, cover pages (`cover_page.keep`), placeholder filling (`replace:`,
  `--set`, GUI document fields), per-org profiles; APA 7th and GB/T 7713.1
  presets included.
- **Content preservation**: OMML equations verbatim; images with size/alt;
  tables content-intact with relationship rewriting; footnotes and endnotes;
  hyperlinks; tracked changes auto-accepted (QA-noted); fields frozen to their
  cached text (QA-noted); content controls unwrapped; comments/text boxes/VML
  surfaced in the QA report — nothing is dropped silently.
- **Inputs**: .docx, .doc, .odt, .rtf, .txt (UTF-8/cp1252), .md (pandoc).
- **Local web GUI** on 127.0.0.1 with drag-and-drop, document fields, QA
  warnings inline; hardened (Host/Origin validation, upload cap, session
  eviction, timeouts).
- **Optional local AI** assist via Ollama (`--ai`) with hard heuristic fallback.
- **Ops**: platform-aware LibreOffice discovery (`DOCFORMAT_SOFFICE` override),
  isolated LO profiles and timeouts on every subprocess, rotating file logs,
  friendly error messages, `--version`, PyInstaller spec + CI build matrix.
