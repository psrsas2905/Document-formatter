"""Offline PDF export + field refresh via LibreOffice headless.

The soffice conversion also forces TOC/field updates, which is why we route the
final PDF through LibreOffice rather than a pure-Python PDF writer.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def soffice_available() -> bool:
    """True if the LibreOffice 'soffice' binary is on PATH."""
    return shutil.which("soffice") is not None


def export_pdf(docx_path: str | Path, out_dir: str | Path) -> Path:
    """Convert a .docx to a tagged PDF, fully offline. Returns the PDF path."""
    docx_path = Path(docx_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if not soffice_available():
        raise RuntimeError(
            "LibreOffice ('soffice') not found on PATH. Install it for offline PDF export."
        )
    subprocess.run(
        ["soffice", "--headless", "--convert-to", "pdf", "--outdir", str(out_dir), str(docx_path)],
        check=True,
    )
    return out_dir / (docx_path.stem + ".pdf")
