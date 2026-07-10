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
    overrides: Path | None = typer.Option(
        None,
        "--overrides",
        exists=True,
        help="Apply hand-pinned classifications from a plan file (see --dry-run).",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview classification only: write an editable overrides plan + "
        "qa_report, produce no document.",
    ),
) -> None:
    """Run the full formatting pipeline on INPUT."""
    log_file = setup_logging()
    log.info("docformat %s: format %s (template %s)", __version__, input, template)
    try:
        _run_format(input, template, template_docx, out, set_field, ai, pdf, overrides, dry_run)
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


def _run_format(input, template, template_docx, out, set_field, ai, pdf, overrides, dry_run) -> None:
    from . import overrides as _overrides

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

    if overrides is not None:
        applied = _overrides.apply_overrides(doc, overrides)
        typer.echo(f"Applied {applied} classification override(s) from {overrides.name}")

    if dry_run:
        plan = _overrides.write_plan(doc, out / (input.stem + "_overrides.yaml"), str(input))
        _qa.write_report(doc, out / "qa_report.md")
        typer.echo(f"Dry run — no document produced.\nPlan: {plan}\nQA: {out / 'qa_report.md'}")
        return

    styled = _apply.apply_styles(doc, profile, out / (input.stem + "_formatted.docx"))
    _elements.add_elements(styled, profile, doc)
    _qa.write_report(doc, out / "qa_report.md")

    if pdf:
        pdf_path = _export.export_pdf(styled, out)
        typer.echo(f"PDF: {pdf_path}")

    typer.echo(f"Done. Output in: {out}")


@app.command()
def batch(
    inputs: list[Path] = typer.Argument(
        ..., exists=True, help="Files and/or directories of drafts to format."
    ),
    template: Path = typer.Option(..., "--template", "-t", help="Path to template_profile.yaml."),
    template_docx: Path | None = typer.Option(
        None, "--template-docx", exists=True,
        help="Brand template overriding the profile's template_file.",
    ),
    out: Path = typer.Option(Path("out"), "--out", "-o", help="Output directory."),
    ai: bool = typer.Option(False, "--ai", help="Use optional local-AI classifier (offline)."),
    pdf: bool = typer.Option(True, "--pdf/--no-pdf", help="Also export each PDF."),
    overrides_dir: Path | None = typer.Option(
        None, "--overrides-dir", exists=True, file_okay=False,
        help="Folder of <stem>_overrides.yaml plans to re-apply per document.",
    ),
) -> None:
    """Format many drafts at once with a consolidated QA summary."""
    from . import batch as _batch

    log_file = setup_logging()
    try:
        profile = load_profile(template)
        if template_docx is not None:
            profile.template_file = str(template_docx)
        sources = _batch.collect_inputs(inputs)
        if not sources:
            typer.secho("No supported documents found in the given paths.", fg=typer.colors.YELLOW)
            raise typer.Exit(code=1)
        typer.echo(f"Formatting {len(sources)} document(s) with profile {profile.name!r}...")

        def _progress(r: _batch.DocResult) -> None:
            if r.ok:
                typer.secho(
                    f"  ✓ {Path(r.source).name} — {r.needs_review} block(s) need review",
                    fg=typer.colors.GREEN,
                )
            else:
                typer.secho(f"  ✗ {Path(r.source).name} — {r.error}", fg=typer.colors.RED)

        results = _batch.run_batch(
            sources, profile, out, ai=ai, pdf=pdf,
            overrides_dir=overrides_dir, on_result=_progress,
        )
    except known_errors() as exc:
        log.exception("batch failed")
        typer.secho(f"Error: {_friendly(exc)}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    except typer.Exit:
        raise
    except Exception as exc:
        log.exception("batch crashed")
        typer.secho(
            f"Unexpected error: {exc}\nDetails were written to {log_file}",
            fg=typer.colors.RED, err=True,
        )
        raise typer.Exit(code=1) from exc

    failed = [r for r in results if not r.ok]
    typer.echo(f"Done. Summary: {out / 'batch_summary.md'}")
    if failed:
        raise typer.Exit(code=1)


@app.command("inspect-template")
def inspect_template(
    template_docx: Path = typer.Argument(
        ..., exists=True, help="The .docx/.dotx template to introspect."
    ),
) -> None:
    """List a template's named styles and [placeholder] tokens.

    Use the style names shown here in a profile's style_map, and the
    placeholders as --set / replace: keys.
    """
    from . import inspect as _inspect

    setup_logging()
    try:
        report = _inspect.inspect_template(template_docx)
    except known_errors() as exc:
        typer.secho(f"Error: {_friendly(exc)}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"Template: {report.path}\n")
    for kind in ("paragraph", "table", "character", "list"):
        group = report.styles_of(kind)
        if not group:
            continue
        typer.secho(f"{kind.capitalize()} styles ({len(group)}):", bold=True)
        for s in group:
            tags = []
            if s.used:
                tags.append("used")
            if not s.builtin:
                tags.append("custom")
            suffix = f"  [{', '.join(tags)}]" if tags else ""
            typer.echo(f"  {s.name}{suffix}")
        typer.echo("")

    typer.secho("Placeholders:", bold=True)
    if report.placeholders:
        for token, count in report.placeholders.items():
            typer.echo(f"  {token} ×{count}")
    else:
        typer.echo("  (none found)")


@app.command("validate-profile")
def validate_profile(
    template: Path = typer.Argument(
        ..., exists=True, help="Path to template_profile.yaml."
    ),
    template_docx: Path | None = typer.Option(
        None,
        "--template-docx",
        exists=True,
        help="Validate against this template instead of the profile's template_file.",
    ),
) -> None:
    """Check that every style a profile maps to exists in its template."""
    from . import inspect as _inspect

    setup_logging()
    try:
        profile = load_profile(template)
    except (ValueError, FileNotFoundError) as exc:
        typer.secho(f"Error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    if template_docx is not None:
        profile.template_file = str(template_docx)

    issues = _inspect.validate_profile(profile)
    errors = [i for i in issues if i.severity == "error"]
    for issue in issues:
        color = typer.colors.RED if issue.severity == "error" else typer.colors.YELLOW
        typer.secho(f"{issue.severity.upper()}: {issue.message}", fg=color)
    if not issues:
        typer.secho(
            f"OK — profile {profile.name!r} is consistent with its template.",
            fg=typer.colors.GREEN,
        )
    if errors:
        raise typer.Exit(code=1)


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
