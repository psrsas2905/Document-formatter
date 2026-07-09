"""Offline PDF export + field/TOC refresh via LibreOffice headless.

A bare `soffice --convert-to pdf` does NOT refresh TOC/List-of-Figures fields —
they'd export as their placeholder text. So we seed a throwaway LibreOffice
user profile with a small Basic macro that loads the document hidden, updates
every document index and text field (twice — page numbers shift once the TOC
grows), then stores a *tagged* PDF. Everything runs locally; no network.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

_MACRO_XBA = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE script:module PUBLIC "-//OpenOffice.org//DTD OfficeDocument 1.0//EN" "module.dtd">
<script:module xmlns:script="http://openoffice.org/2000/script" script:name="Module1" script:language="StarBasic">
Sub RefreshExport(inUrl As String, outUrl As String)
    Dim oDoc, oIndexes, i, pass
    Dim loadArgs(0) As New com.sun.star.beans.PropertyValue
    loadArgs(0).Name = "Hidden" : loadArgs(0).Value = True
    oDoc = StarDesktop.loadComponentFromURL(inUrl, "_blank", 0, loadArgs())

    For pass = 1 To 2
        oDoc.refresh()
        oIndexes = oDoc.getDocumentIndexes()
        For i = 0 To oIndexes.getCount() - 1
            oIndexes.getByIndex(i).update()
        Next i
    Next pass

    Dim fd(0) As New com.sun.star.beans.PropertyValue
    fd(0).Name = "UseTaggedPDF" : fd(0).Value = True
    Dim exportArgs(1) As New com.sun.star.beans.PropertyValue
    exportArgs(0).Name = "FilterName" : exportArgs(0).Value = "writer_pdf_Export"
    exportArgs(1).Name = "FilterData" : exportArgs(1).Value = fd()
    oDoc.storeToURL(outUrl, exportArgs())
    oDoc.close(False)
End Sub
</script:module>
"""

_SCRIPT_XLB = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE library:library PUBLIC "-//OpenOffice.org//DTD OfficeDocument 1.0//EN" "library.dtd">
<library:library xmlns:library="http://openoffice.org/2000/library" library:name="Standard" library:readonly="false" library:passwordprotected="false">
 <library:element library:name="Module1"/>
</library:library>
"""

_SCRIPT_XLC = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE library:libraries PUBLIC "-//OpenOffice.org//DTD OfficeDocument 1.0//EN" "libraries.dtd">
<library:libraries xmlns:library="http://openoffice.org/2000/library" xmlns:xlink="http://www.w3.org/1999/xlink">
 <library:library library:name="Standard" xlink:href="$(USER)/basic/Standard/script.xlb/" xlink:type="simple" library:link="false"/>
</library:libraries>
"""


def soffice_available() -> bool:
    """True if the LibreOffice 'soffice' binary is on PATH."""
    return shutil.which("soffice") is not None


def export_pdf(docx_path: str | Path, out_dir: str | Path) -> Path:
    """Refresh fields/TOC and convert a .docx to a tagged PDF, fully offline."""
    docx_path = Path(docx_path).resolve()
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    if not soffice_available():
        raise RuntimeError(
            "LibreOffice ('soffice') not found on PATH. Install it for offline PDF export."
        )

    pdf_path = out_dir / (docx_path.stem + ".pdf")
    with tempfile.TemporaryDirectory(prefix="docformat_lo_") as tmp:
        profile = _seed_profile(Path(tmp))
        macro = (
            "macro:///Standard.Module1.RefreshExport("
            f'"{docx_path.as_uri()}","{pdf_path.as_uri()}")'
        )
        subprocess.run(
            [
                "soffice",
                f"-env:UserInstallation={profile.as_uri()}",
                "--headless",
                "--norestore",
                macro,
            ],
            check=True,
            capture_output=True,
        )

    if not pdf_path.exists():
        raise RuntimeError(f"LibreOffice did not produce {pdf_path}")
    return pdf_path


def _seed_profile(tmp: Path) -> Path:
    """Create a throwaway LO user profile carrying the refresh/export macro.

    LibreOffice ignores a macro: URL on the same launch that first initializes
    a user profile, so initialize it in a separate no-op run, then inject the
    macro files for the real run.
    """
    profile = tmp / "profile"
    subprocess.run(
        [
            "soffice",
            f"-env:UserInstallation={profile.as_uri()}",
            "--headless",
            "--terminate_after_init",
        ],
        check=True,
        capture_output=True,
    )
    basic = profile / "user" / "basic"
    (basic / "Standard").mkdir(parents=True, exist_ok=True)
    (basic / "script.xlc").write_text(_SCRIPT_XLC, encoding="utf-8")
    (basic / "Standard" / "script.xlb").write_text(_SCRIPT_XLB, encoding="utf-8")
    (basic / "Standard" / "Module1.xba").write_text(_MACRO_XBA, encoding="utf-8")
    return profile
