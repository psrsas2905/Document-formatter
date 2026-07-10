# Build Status & Deployment Readiness

> Snapshot: 2026-07-10 — **Tiers 1–4 merged to `main`** (PR #1 = Tiers 1–3,
> PR #2 = Tier 4), commit `0ad2a3c`. Pair with `docs/HANDOFF.md`.

## At a glance

| Area | Status |
|------|--------|
| Spec v1 acceptance criteria | ✅ all met |
| Test suite | ✅ 78 passing (`python -m pytest -q`) |
| Lint | ✅ clean (`ruff check src tests scripts`) |
| CI (GitHub Actions) | ✅ green on `main` — lint+test + 3-OS build matrix |
| Cross-platform executables | ✅ build + smoke-test on Win/macOS/Linux in CI |
| Content fidelity (Tier 1) | ✅ done — no silent loss |
| Deployment hardening (Tier 2) | ✅ done except code-signing |
| Versatility (Tier 3) | ✅ done — dry-run/overrides, batch, inspect/validate, char formatting, output.filename, ListNumber |
| Real-world readiness (Tier 4) | ✅ done — GUI polish, honest AI fallback, QA anchors, native ordered lists, page-breaks/section-flag, highlight + text-box carry |
| **Ship to a writing team** | ⚠️ **pilot-ready; general rollout gated on signing** |

## What "done" means concretely

### Verified working
- Full pipeline (CLI + GUI) on the messy, rich, and RedLotus fixtures,
  including tagged-PDF export with refreshed TOC.
- Rebuilt `dist/docformat` runs the full pipeline (incl. PDF) from a clean
  directory outside the repo.
- Latest CI on `main` (commit `0ad2a3c`, Tier 4 merge): `test` (ubuntu) ✅,
  `build` on ubuntu ✅ / windows ✅ / macos ✅ — each with a passing executable
  smoke check; artifacts uploaded.
- Content preservation proven by `tests/test_fidelity.py` (probe docs with
  tracked changes, fields, content controls, native lists (bullet + ordered),
  hyperlinks, comments, endnotes, table hyperlinks, manual page breaks, section
  breaks/landscape, and text boxes).
- GUI verified in a real browser (active profile, honest AI/PDF signals,
  block-index + heading-anchor review table).

### The one remaining blocker for unrestricted desktop rollout
**Code-signing / notarization.** `docformat.spec` sets
`codesign_identity=None` and UPX is off (both deliberate), but unsigned
binaries still trip macOS Gatekeeper and Windows SmartScreen/AV. This needs
certificates the owner must procure:
- macOS: Apple Developer ID + notarization.
- Windows: Authenticode code-signing certificate.
Until then, ship via `pip install` on a managed machine, or IT-whitelist the
binary for a small pilot.

## How to cut a build (per OS — PyInstaller does not cross-compile)

```bash
# Linux / macOS
bash scripts/build_exe.sh          # -> dist/docformat

# Windows
pyinstaller --noconfirm docformat.spec   # -> dist/docformat.exe
```
CI already produces all three as downloadable artifacts on every push
(`.github/workflows/ci.yml`, `build` job). To ship, download the artifacts,
sign/notarize, and distribute.

Runtime requirement on the target machine: **LibreOffice** (for PDF export
and .doc/.odt/.rtf input). It is discovered automatically in default install
locations; override with `DOCFORMAT_SOFFICE=/path/to/soffice`.

## Recommended rollout sequence

1. **Now:** pilot with 1–2 writers via `pip install` (or IT-whitelisted
   unsigned binary). Collect real drafts + templates.
2. **Procure signing certs** (lead time can exceed a week) → sign/notarize
   the CI artifacts → distribute to the full team.
3. **Iterate by pilot feedback** — Tiers 1–4 are done; the remaining backlog
   (CJK/RTL, injected comments, VML) is optional/situational. See
   `docs/REVIEW_BACKLOG.md`.

## Known limitations to communicate to users

- Footnotes carry as plain text (formatting inside notes dropped; QA-noted).
- Tracked changes are auto-accepted (QA-noted) — accept/reject in Word first
  if that matters.
- Character formatting: sub/superscript, underline, strikethrough and highlighter
  marks are preserved. Manual page breaks are carried; section breaks and
  landscape pages are QA-flagged (the template owns page setup).
- Text-box content is inlined into the flow in reading order (floating position
  not preserved; QA-noted).
- Classifier heuristics are English-oriented (CJK/RTL not yet done), though the
  template/geometry side of the GB/T preset works.
- Ordered lists: both typed "1."/"a)" and Word-native (ribbon) numbered lists
  map to the numbered style; bullets stay bullets.
- Every uncertain or dropped item is listed in `qa_report.md` — that report is
  the contract; tell writers to read it before signing off.
