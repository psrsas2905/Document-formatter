#!/usr/bin/env bash
# Build a standalone docformat executable with PyInstaller.
# Run from the repo root: bash scripts/build_exe.sh
# Result: dist/docformat (single file; needs LibreOffice on the target machine
# for PDF export, everything else is self-contained).
set -euo pipefail

pyinstaller \
  --name docformat \
  --onefile \
  --console \
  --noconfirm \
  --clean \
  --collect-all docx \
  --paths src \
  --add-data "src/docformat/assets:docformat/assets" \
  --add-data "config:config" \
  --add-data "templates/org_standard.docx:templates" \
  src/docformat/__main__.py

echo
echo "Built: dist/docformat"
dist/docformat --help >/dev/null && echo "Smoke check OK"
