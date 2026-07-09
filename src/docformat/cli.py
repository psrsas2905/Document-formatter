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
from .template import load_profile

app = typer.Typer(help="Turn raw Word drafts into publish-ready, template-conformant documents.")


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
    ai: bool = typer.Option(False, "--ai", help="Use optional local-AI classifier (offline)."),
    pdf: bool = typer.Option(True, "--pdf/--no-pdf", help="Also export a PDF."),
) -> None:
    """Run the full formatting pipeline on INPUT."""
    out.mkdir(parents=True, exist_ok=True)
    profile = load_profile(template)
    if template_docx is not None:
        profile.template_file = str(template_docx)
    typer.echo(f"Template profile: {profile.name} (template: {profile.template_file})")

    doc = _ingest.ingest(input)
    doc = _classify_ai.classify_ai(doc) if ai else _classify.classify(doc)

    styled = _apply.apply_styles(doc, profile, out / (input.stem + "_formatted.docx"))
    _elements.add_elements(styled, profile)
    _qa.write_report(doc, out / "qa_report.md")

    if pdf:
        pdf_path = _export.export_pdf(styled, out)
        typer.echo(f"PDF: {pdf_path}")

    typer.echo(f"Done. Output in: {out}")


if __name__ == "__main__":
    app()
