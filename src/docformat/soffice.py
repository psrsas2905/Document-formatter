"""Locate and run LibreOffice reliably across platforms.

Default installs on Windows and macOS do NOT put `soffice` on PATH, so lookup
order is: the DOCFORMAT_SOFFICE environment variable, PATH, then the
platform's well-known install locations. Every invocation gets a timeout and
an isolated throwaway user profile (a headless run sharing the user's default
profile silently defers to an open desktop LibreOffice and produces nothing).
"""

from __future__ import annotations

import glob
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

log = logging.getLogger("docformat.soffice")

DEFAULT_TIMEOUT_S = 300

_WINDOWS_CANDIDATES = [
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
]
_MACOS_CANDIDATES = [
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    str(Path.home() / "Applications/LibreOffice.app/Contents/MacOS/soffice"),
]
_LINUX_GLOBS = [
    "/usr/bin/soffice",
    "/usr/local/bin/soffice",
    "/opt/libreoffice*/program/soffice",
    "/snap/bin/libreoffice",
]


def find_soffice() -> str | None:
    """Full path to the LibreOffice binary, or None if not installed."""
    override = os.environ.get("DOCFORMAT_SOFFICE")
    if override:
        if Path(override).is_file():
            return override
        log.warning("DOCFORMAT_SOFFICE=%r does not exist; ignoring", override)

    on_path = shutil.which("soffice")
    if on_path:
        return on_path

    if sys.platform.startswith("win"):
        candidates = _WINDOWS_CANDIDATES
    elif sys.platform == "darwin":
        candidates = _MACOS_CANDIDATES
    else:
        candidates = [p for pattern in _LINUX_GLOBS for p in glob.glob(pattern)]
    for candidate in candidates:
        if Path(candidate).is_file():
            return candidate
    return None


def soffice_available() -> bool:
    return find_soffice() is not None


def missing_message() -> str:
    return (
        "LibreOffice was not found. Install it from https://www.libreoffice.org "
        "(or set DOCFORMAT_SOFFICE to the full path of the soffice binary)."
    )


def run_soffice(
    args: list[str],
    timeout: int = DEFAULT_TIMEOUT_S,
    profile_dir: str | Path | None = None,
) -> None:
    """Run LibreOffice headless with an isolated profile and a hard timeout.

    `profile_dir`: reuse a caller-managed profile (export.py seeds a macro into
    one); default is a fresh throwaway profile per call.
    """
    exe = find_soffice()
    if exe is None:
        raise RuntimeError(missing_message())

    def _invoke(profile: Path) -> None:
        cmd = [exe, f"-env:UserInstallation={profile.resolve().as_uri()}", *args]
        log.info("running: %s", " ".join(cmd))
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"LibreOffice did not finish within {timeout}s "
                f"(command: {' '.join(args[:3])}...). Close any LibreOffice "
                "dialogs and try again."
            ) from exc
        if result.returncode != 0:
            stderr = (result.stderr or "").strip()[-800:]
            log.error("soffice failed rc=%s stderr=%s", result.returncode, stderr)
            raise RuntimeError(
                f"LibreOffice failed (exit {result.returncode})."
                + (f" Details: {stderr}" if stderr else "")
            )
        if result.stderr:
            log.debug("soffice stderr: %s", result.stderr.strip()[-800:])

    if profile_dir is not None:
        _invoke(Path(profile_dir))
    else:
        with tempfile.TemporaryDirectory(prefix="docformat_lo_") as tmp:
            _invoke(Path(tmp) / "profile")
