"""Convert non-docx inputs to .docx before ingest — all offline.

  - .doc / .odt / .rtf : LibreOffice headless (already a dependency for PDF),
                          run with an isolated profile and a timeout so an open
                          desktop LibreOffice can't swallow the conversion
  - .txt               : built directly with python-docx (blank line = new
                          paragraph, single newlines joined); UTF-8 first,
                          then Windows-1252 for typical Word-adjacent text
  - .md                : pandoc if installed, otherwise a clear error
  - .docx              : passed through untouched
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from . import soffice as _soffice

SOFFICE_TYPES = {".doc", ".odt", ".rtf"}
PANDOC_TIMEOUT_S = 120


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
    if not _soffice.soffice_available():
        raise RuntimeError(
            f"Converting {source.suffix} input needs LibreOffice. "
            + _soffice.missing_message()
        )
    out = work_dir / (source.stem + ".docx")
    # A leftover from a previous run must not mask a failed conversion.
    out.unlink(missing_ok=True)
    _soffice.run_soffice(
        [
            "--headless",
            "--convert-to",
            "docx",
            "--outdir",
            str(work_dir),
            str(source.resolve()),
        ]
    )
    if not out.exists():
        raise RuntimeError(
            f"LibreOffice could not convert {source.name} — the file may be "
            "corrupt or password-protected."
        )
    return out


def _from_text(source: Path, work_dir: Path) -> Path:
    import docx

    out = work_dir / (source.stem + ".docx")
    raw = source.read_bytes()
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError:
        # Word-adjacent .txt files (curly quotes, en dashes) are usually cp1252.
        content = raw.decode("cp1252", errors="replace")
    doc = docx.Document()
    for para in content.split("\n\n"):
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
    out.unlink(missing_ok=True)
    try:
        result = subprocess.run(
            ["pandoc", str(source), "-o", str(out)],
            capture_output=True,
            text=True,
            timeout=PANDOC_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"pandoc did not finish within {PANDOC_TIMEOUT_S}s.") from exc
    if result.returncode != 0 or not out.exists():
        stderr = (result.stderr or "").strip()[-400:]
        raise RuntimeError(
            f"pandoc could not convert {source.name}."
            + (f" Details: {stderr}" if stderr else "")
        )
    return out
