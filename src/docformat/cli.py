"""Command-line interface for docformat.

`docformat format INPUT --template PROFILE --out DIR`
`docformat gui`

Known failure classes surface as one-line human messages; full tracebacks go
to the rotating log file (see log.py for its per-OS location).
"""

from __future__ import annotations

import logging
from pathlib import Path

import typer

from . import __version__
from . import apply as _apply
from . import classify as _classify
from . import classify_ai as _classify_ai
from . import convert as _convert
from . import elements as _elements
from . import export as _export
from . import ingest as _ingest
from . import qa as _qa
from .errors import friendly as _friendly
from .errors import known_errors
from .log import setup_logging
from .template import apply_field_values, load_profile

log = logging.getLogger("docformat.cli")


def _parse_set_options(pairs: list[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for pair in pairs:
        key, sep, value = pair.partition("=")
        if not sep or not key.strip():
            raise typer.BadParameter(f'--set expects "Name=Value", got {pair!r}')
        values[key.strip()] = value.strip()
    return values


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"docformat {__version__}")
        raise typer.Exit()


app = typer.Typer(help="Turn raw Word drafts into publish-ready, template-conformant documents.")


@app.callback()
def _main(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the docformat version and exit.",
    ),
) -> None:
    """Keep 'format' as an explicit subcommand (docformat format INPUT ...)."""


@app.command()
def format(
    input: Path = typer.Argument(..., exists=True, help="Source document to format."),
    template: Path = typer.Option(..., "--template", "-t", help="Path to template_profile.yaml."),
    template_docx: Path | None = typer.Option(
        None,
        "--template-docx",
        exists=True,
        help="Your organization's brand template (.docx/.dotx, logo and all); "
        "overrides the profile's template_file.",
    ),
    out: Path = typer.Option(Path("out"), "--out", "-o", help="Output directory."),
    set_field: list[str] = typer.Option(
        [],
        "--set",
        "-s",
        help='Fill a template placeholder for this document, e.g. '
        '--set "Client Name=Acme Corp" (repeatable; matches [Client Name] in the template).',
    ),
    ai: bool = typer.Option(False, "--ai", help="Use optional local-AI classifier (offline)."),
    pdf: bool = typer.Option(True, "--pdf/--no-pdf", help="Also export a PDF."),
) -> None:
    """Run the full formatting pipeline on INPUT."""
    log_file = setup_logging()
    log.info("docformat %s: format %s (template %s)", __version__, input, template)
    try:
        _run_format(input, template, template_docx, out, set_field, ai, pdf)
    except known_errors() as exc:
        log.exception("format failed")
        typer.secho(f"Error: {_friendly(exc)}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    except Exception as exc:  # anything else: keep the user message short
        log.exception("format crashed")
        typer.secho(
            f"Unexpected error: {exc}\nDetails were written to {log_file}",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1) from exc


def _run_format(input, template, template_docx, out, set_field, ai, pdf) -> None:
    out.mkdir(parents=True, exist_ok=True)
    profile = load_profile(template)
    if template_docx is not None:
        profile.template_file = str(template_docx)
    apply_field_values(profile, _parse_set_options(set_field))
    typer.echo(f"Template profile: {profile.name} (template: {profile.template_file})")

    source = _convert.ensure_docx(input, out / "_converted")
    if source != input:
        typer.echo(f"Converted {input.suffix} input -> {source.name}")

    doc = _ingest.ingest(source)
    doc = _classify_ai.classify_ai(doc) if ai else _classify.classify(doc)

    styled = _apply.apply_styles(doc, profile, out / (input.stem + "_formatted.docx"))
    _elements.add_elements(styled, profile, doc)
    _qa.write_report(doc, out / "qa_report.md")

    if pdf:
        pdf_path = _export.export_pdf(styled, out)
        typer.echo(f"PDF: {pdf_path}")

    typer.echo(f"Done. Output in: {out}")


@app.command()
def gui(
    template: Path | None = typer.Option(
        None,
        "--template",
        "-t",
        help="template_profile.yaml to use (default: config/template_profile.example.yaml).",
    ),
    port: int = typer.Option(8765, "--port", help="Port on 127.0.0.1 to serve the GUI."),
    browser: bool = typer.Option(True, "--browser/--no-browser", help="Open the browser."),
) -> None:
    """Launch the local web GUI (everything stays on this machine)."""
    from . import gui as _gui

    setup_logging()
    profile_path = template or _gui.default_profile_path()
    if profile_path is None or not Path(profile_path).exists():
        raise typer.BadParameter(
            "No template profile found — pass one with --template path/to/profile.yaml"
        )
    try:
        load_profile(profile_path)  # fail fast with a friendly message
    except ValueError as exc:
        typer.secho(f"Error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    _gui.serve(Path(profile_path), port=port, open_browser=browser)


if __name__ == "__main__":
    app()
