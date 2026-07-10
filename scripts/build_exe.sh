#!/usr/bin/env bash
# Build a standalone docformat executable with PyInstaller.
# The build definition lives in docformat.spec (works on all OSes):
#   Linux/macOS:  bash scripts/build_exe.sh
#   Windows:      pyinstaller --noconfirm docformat.spec
# Result: dist/docformat (needs LibreOffice on the target machine for PDF
# export; everything else is self-contained). Sign/notarize before shipping.
set -euo pipefail

pyinstaller --noconfirm --clean docformat.spec

echo
echo "Built: dist/docformat"
dist/docformat --version && echo "Smoke check OK"
