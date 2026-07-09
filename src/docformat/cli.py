"""Command-line interface for docformat.

`docformat format INPUT --template PROFILE --out DIR`

The pipeline is wired end-to-end here. Individual stages currently raise
NotImplementedError; implement them per PROJECT_SPEC in build order.
"""

from __future__ import annotations

from pathlib import Path

import typer

from . import apply as _apply
from . import classify as _classify
from . import classify_ai as _classify_ai
from . import elements as _elements
from . import export as _export
from . import ingest as _ingest
from . import qa as _qa
from .template import apply_field_values, load_profile


def _parse_set_options(pairs: list[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for pair in pairs:
        key, sep, value = pair.partition("=")
        if not sep or not key.strip():
            raise typer.BadParameter(f'--set expects "Name=Value", got {pair!r}')
        values[key.strip()] = value.strip()
    return values

app = typer.Typer(help="Turn raw Word drafts into publish-ready, template-conformant documents.")


@app.callback()
def _main() -> None:
    """Keep 'format' as an explicit subcommand (docformat format INPUT ...)."""


@app.command()
def format(
    input: Path = typer.Argument(..., exists=True, help="Source .docx to format."),
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
    out.mkdir(parents=True, exist_ok=True)
    profile = load_profile(template)
    if template_docx is not None:
        profile.template_file = str(template_docx)
    apply_field_values(profile, _parse_set_options(set_field))
    typer.echo(f"Template profile: {profile.name} (template: {profile.template_file})")

    doc = _ingest.ingest(input)
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

    profile_path = template or _gui.default_profile_path()
    if profile_path is None or not Path(profile_path).exists():
        raise typer.BadParameter(
            "No template profile found — pass one with --template path/to/profile.yaml"
        )
    _gui.serve(Path(profile_path), port=port, open_browser=browser)


if __name__ == "__main__":
    app()
