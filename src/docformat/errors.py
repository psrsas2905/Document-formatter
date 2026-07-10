"""Shared mapping from expected failure classes to human-readable messages."""

from __future__ import annotations


def known_errors() -> tuple[type[Exception], ...]:
    """Failure classes whose messages are safe and useful to show users."""
    from docx.opc.exceptions import PackageNotFoundError

    return (ValueError, RuntimeError, FileNotFoundError, PackageNotFoundError)


def friendly(exc: Exception) -> str:
    from docx.opc.exceptions import PackageNotFoundError

    if isinstance(exc, PackageNotFoundError):
        return (
            "that file doesn't look like a valid Word document (it may be "
            "corrupt, renamed, or password-protected)."
        )
    return str(exc)
