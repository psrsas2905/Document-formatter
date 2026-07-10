"""Format many drafts in one run, with a consolidated QA summary.

Migrating a folder of legacy documents one CLI call at a time is tedious and
hides the overall picture. `docformat batch` formats every supported draft under
the given paths into its own subfolder and writes a single `batch_summary.md`
ranking the documents by how much human review they still need — so a reviewer
knows where to look first. One document failing (corrupt file, missing style)
never aborts the rest; its error lands in the summary.

Optionally, `overrides_dir` supplies a per-document classification plan
(`<stem>_overrides.yaml`, produced by `format --dry-run`) so batch re-runs honor
earlier manual fixes.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import apply as _apply
from . import classify as _classify
from . import classify_ai as _classify_ai
from . import convert as _convert
from . import elements as _elements
from . import export as _export
from . import ingest as _ingest
from . import overrides as _overrides
from . import qa as _qa
from .template import TemplateProfile

# Input types ingest understands directly or via convert.ensure_docx.
SUPPORTED_SUFFIXES = {".docx", ".doc", ".odt", ".rtf", ".txt", ".md", ".markdown"}


@dataclass
class DocResult:
    source: str
    ok: bool
    blocks: int = 0
    needs_review: int = 0
    notes: int = 0
    output: str | None = None
    pdf: str | None = None
    error: str | None = None


def collect_inputs(paths: list[Path]) -> list[Path]:
    """Expand files and directories into a sorted, de-duplicated list of
    supported source documents (temp conversion artifacts are skipped)."""
    found: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        candidates = (
            sorted(p for p in path.rglob("*") if p.is_file())
            if path.is_dir()
            else [path]
        )
        for c in candidates:
            if c.suffix.lower() not in SUPPORTED_SUFFIXES:
                continue
            if "_converted" in c.parts:  # our own intermediate output
                continue
            resolved = c.resolve()
            if resolved not in seen:
                seen.add(resolved)
                found.append(c)
    return found


def format_document(
    input: Path,
    profile: TemplateProfile,
    out_dir: Path,
    *,
    ai: bool = False,
    pdf: bool = True,
    overrides: Path | None = None,
) -> DocResult:
    """Run the full pipeline for one document; never raises — errors are
    captured in the returned DocResult so a batch keeps going."""
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        source = _convert.ensure_docx(input, out_dir / "_converted")
        doc = _ingest.ingest(source)
        doc = _classify_ai.classify_ai(doc) if ai else _classify.classify(doc)
        if overrides is not None and overrides.exists():
            _overrides.apply_overrides(doc, overrides)

        styled = _apply.apply_styles(doc, profile, out_dir / (input.stem + "_formatted.docx"))
        _elements.add_elements(styled, profile, doc)
        _qa.write_report(doc, out_dir / "qa_report.md")

        pdf_path = None
        if pdf:
            pdf_path = _export.export_pdf(styled, out_dir)

        total, review = _qa.review_counts(doc)
        return DocResult(
            source=str(input),
            ok=True,
            blocks=total,
            needs_review=review,
            notes=len(doc.notes),
            output=str(styled),
            pdf=str(pdf_path) if pdf_path else None,
        )
    except Exception as exc:  # noqa: BLE001 — batch must survive one bad doc
        return DocResult(source=str(input), ok=False, error=f"{type(exc).__name__}: {exc}")


def run_batch(
    inputs: list[Path],
    profile: TemplateProfile,
    out_root: Path,
    *,
    ai: bool = False,
    pdf: bool = True,
    overrides_dir: Path | None = None,
    on_result=None,
) -> list[DocResult]:
    """Format every input into out_root/<stem>/; write batch_summary.md.

    `on_result(DocResult)` is called after each document for progress output.
    """
    out_root.mkdir(parents=True, exist_ok=True)
    results: list[DocResult] = []
    used_dirs: dict[str, int] = {}
    for input in inputs:
        # Distinct subfolders even when two inputs share a stem (a.docx / a.txt).
        stem = input.stem
        n = used_dirs.get(stem, 0)
        used_dirs[stem] = n + 1
        sub = out_root / (stem if n == 0 else f"{stem}_{n}")

        overrides = None
        if overrides_dir is not None:
            candidate = overrides_dir / f"{input.stem}_overrides.yaml"
            if candidate.exists():
                overrides = candidate

        result = format_document(input, profile, sub, ai=ai, pdf=pdf, overrides=overrides)
        results.append(result)
        if on_result is not None:
            on_result(result)

    write_summary(results, out_root / "batch_summary.md", profile)
    return results


def write_summary(results: list[DocResult], out_path: str | Path, profile: TemplateProfile) -> Path:
    """Consolidated QA summary across the batch, worst-first."""
    out_path = Path(out_path)
    ok = [r for r in results if r.ok]
    failed = [r for r in results if not r.ok]
    total_review = sum(r.needs_review for r in ok)

    lines = [
        "# Batch QA Summary",
        "",
        f"Profile: **{profile.name}**",
        f"Documents: {len(results)} — {len(ok)} formatted, {len(failed)} failed.",
        f"Total blocks needing review across the batch: {total_review}.",
        "",
        "## Documents (most review first)",
        "",
        "| Document | Blocks | Needs review | Notes | PDF |",
        "|----------|-------:|-------------:|------:|:---:|",
    ]
    for r in sorted(ok, key=lambda r: r.needs_review, reverse=True):
        lines.append(
            f"| {_name(r.source)} | {r.blocks} | {r.needs_review} | {r.notes} | "
            f"{'yes' if r.pdf else 'no'} |"
        )
    lines.append("")

    if failed:
        lines += ["## Failed documents", ""]
        for r in failed:
            lines.append(f"- **{_name(r.source)}**: {r.error}")
        lines.append("")

    lines += [
        "## Next steps",
        "",
        "Open each document's own `qa_report.md` (in its subfolder) for the block-",
        "by-block detail. Start with the documents at the top of the table.",
    ]
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_path


def _name(source: str) -> str:
    return Path(source).name.replace("|", "\\|")
