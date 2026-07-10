# Build Status & Deployment Readiness

> Snapshot: 2026-07-10, Tier 3 on `claude/tier-3-continuation-cy9ari`
> (based on the completed `claude/docformat-offline-tool-3xb0yq`).
> Pair with `docs/HANDOFF.md`.

## At a glance

| Area | Status |
|------|--------|
| Spec v1 acceptance criteria | ✅ all met |
| Test suite | ✅ 71 passing (`python -m pytest -q`) |
| Lint | ✅ clean (`ruff check src tests scripts`) |
| CI (GitHub Actions) | ✅ green — lint+test + 3-OS build matrix |
| Cross-platform executables | ✅ build on Win/macOS/Linux in CI |
| Content fidelity (Tier 1) | ✅ done — no silent loss |
| Deployment hardening (Tier 2) | ✅ done except code-signing |
| Versatility (Tier 3) | ✅ high-value items done (dry-run/overrides, batch, inspect/validate, char formatting, ordered lists); GUI polish + CJK/RTL remain |
| **Ship to a writing team** | ⚠️ **pilot-ready; general rollout gated on signing** |

## What "done" means concretely

### Verified working
- Full pipeline (CLI + GUI) on the messy, rich, and RedLotus fixtures,
  including tagged-PDF export with refreshed TOC.
- Rebuilt `dist/docformat` runs the full pipeline (incl. PDF) from a clean
  directory outside the repo.
- CI run #1 (commit `c9212cd`): `test` (ubuntu) ✅, `build` on
  ubuntu ✅ / windows ✅ / macos ✅ — executables uploaded as artifacts.
- Content preservation proven by `tests/test_fidelity.py` (probe docs with
  tracked changes, fields, content controls, native lists, hyperlinks,
  comments, endnotes, table hyperlinks).

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
3. **Tier 3** by pilot feedback (dry-run/preview, batch, template inspection —
   see `docs/REVIEW_BACKLOG.md`).

## Known limitations to communicate to users

- Footnotes carry as plain text (formatting inside notes dropped; QA-noted).
- Tracked changes are auto-accepted (QA-noted) — accept/reject in Word first
  if that matters.
- Character formatting: sub/superscript, underline and strikethrough are now
  preserved; highlight is still dropped (the template governs colour).
- Classifier heuristics are English-oriented (CJK/RTL is still Tier 3), though
  the template/geometry side of the GB/T preset works.
- Ordered lists: typed "1."/"a)" lists map to the numbered style; Word-native
  (ribbon) numbered lists still map to the bullet style (Tier 3).
- Every uncertain or dropped item is listed in `qa_report.md` — that report is
  the contract; tell writers to read it before signing off.
