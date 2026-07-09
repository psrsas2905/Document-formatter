"""Convert non-docx inputs to .docx before ingest — all offline.

  - .doc / .odt / .rtf : LibreOffice headless (already a dependency for PDF)
  - .txt               : built directly with python-docx (blank line = new
                          paragraph, single newlines joined)
  - .md                : pandoc if installed, otherwise a clear error
  - .docx              : passed through untouched
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

SOFFICE_TYPES = {".doc", ".odt", ".rtf"}


def ensure_docx(source: str | Path, work_dir: str | Path) -> Path:
    """Return a .docx path for `source`, converting into work_dir if needed."""
    source = Path(source)
    work_dir = Path(work_dir)
    suffix = source.suffix.lower()

    if suffix == ".docx":
        return source
    work_dir.mkdir(parents=True, exist_ok=True)

    if suffix in SOFFICE_TYPES:
        return _via_soffice(source, work_dir)
    if suffix == ".txt":
        return _from_text(source, work_dir)
    if suffix in (".md", ".markdown"):
        return _via_pandoc(source, work_dir)
    raise ValueError(
        f"Unsupported input type {suffix!r}. Supported: .docx, .doc, .odt, .rtf, .txt, .md"
    )


def _via_soffice(source: Path, work_dir: Path) -> Path:
    if shutil.which("soffice") is None:
        raise RuntimeError(
            f"Converting {source.suffix} input needs LibreOffice ('soffice' on PATH)."
        )
    subprocess.run(
        [
            "soffice",
            "--headless",
            "--convert-to",
            "docx",
            "--outdir",
            str(work_dir),
            str(source.resolve()),
        ],
        check=True,
        capture_output=True,
    )
    out = work_dir / (source.stem + ".docx")
    if not out.exists():
        raise RuntimeError(f"LibreOffice failed to convert {source} to .docx")
    return out


def _from_text(source: Path, work_dir: Path) -> Path:
    import docx

    out = work_dir / (source.stem + ".docx")
    doc = docx.Document()
    for para in source.read_text(encoding="utf-8", errors="replace").split("\n\n"):
        text = " ".join(line.strip() for line in para.splitlines()).strip()
        if text:
            doc.add_paragraph(text)
    doc.save(out)
    return out


def _via_pandoc(source: Path, work_dir: Path) -> Path:
    if shutil.which("pandoc") is None:
        raise RuntimeError(
            "Converting Markdown needs pandoc (https://pandoc.org) on PATH — "
            "or save the draft as .docx/.txt instead."
        )
    out = work_dir / (source.stem + ".docx")
    subprocess.run(
        ["pandoc", str(source), "-o", str(out)],
        check=True,
        capture_output=True,
    )
    return out
