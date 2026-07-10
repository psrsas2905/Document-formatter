# PyInstaller build definition — the single source of truth for packaging.
# Build with:  pyinstaller --noconfirm docformat.spec   (per OS; no cross-compile)
#
# UPX is deliberately OFF: packed onefile binaries are a prime antivirus
# false-positive pattern. Binaries should additionally be code-signed
# (Authenticode) / notarized (macOS) before distribution to end users.

from PyInstaller.utils.hooks import collect_all

# collect_all (not collect_data_files): python-docx's default templates under
# docx/templates/ are not declared package data and get missed otherwise.
docx_datas, docx_binaries, docx_hidden = collect_all("docx")

datas = docx_datas + [
    ("src/docformat/assets", "docformat/assets"),
    ("config", "config"),
    ("templates/org_standard.docx", "templates"),
]

a = Analysis(
    ["src/docformat/__main__.py"],
    pathex=["src"],
    binaries=docx_binaries,
    datas=datas,
    hiddenimports=docx_hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="docformat",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    codesign_identity=None,
    entitlements_file=None,
)
