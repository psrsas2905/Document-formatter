# Changelog

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
