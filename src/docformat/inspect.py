"""Introspect templates and validate profiles against them.

Two onboarding helpers for wiring up a new organization template:

  - `inspect_template` lists the named styles a .docx/.dotx defines (with the
    exact names a profile's style_map must use) and the `[Placeholder]` tokens
    found in its body/headers/footers/cover — the fields `--set`/`replace:` fill.
  - `validate_profile` checks that every style a profile maps to actually exists
    in its template, so a mismatch surfaces here instead of as a QA note buried
    in a formatted document.

Both are read-only. The CLI wraps them (`docformat inspect-template`,
`docformat validate-profile`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import docx
from docx.enum.style import WD_STYLE_TYPE
from docx.oxml.ns import qn

from .apply import _resolve_template
from .elements import PLACEHOLDER_RE
from .template import TemplateProfile

_TYPE_LABEL = {
    WD_STYLE_TYPE.PARAGRAPH: "paragraph",
    WD_STYLE_TYPE.CHARACTER: "character",
    WD_STYLE_TYPE.TABLE: "table",
    WD_STYLE_TYPE.LIST: "list",
}


@dataclass
class StyleInfo:
    name: str
    style_id: str
    kind: str  # paragraph | character | table | list
    builtin: bool
    used: bool  # referenced by at least one paragraph/table in the body


@dataclass
class TemplateReport:
    path: str
    styles: list[StyleInfo] = field(default_factory=list)
    placeholders: dict[str, int] = field(default_factory=dict)  # token -> occurrences

    def styles_of(self, kind: str) -> list[StyleInfo]:
        return [s for s in self.styles if s.kind == kind]


def inspect_template(template_path: str | Path) -> TemplateReport:
    """Read a template and report its styles + placeholder tokens."""
    template_path = Path(template_path)
    doc = docx.Document(str(template_path))

    used = _used_style_ids(doc)
    styles: list[StyleInfo] = []
    for s in doc.styles:
        kind = _TYPE_LABEL.get(s.type)
        if kind is None:
            continue
        styles.append(
            StyleInfo(
                name=s.name or s.style_id,
                style_id=s.style_id,
                kind=kind,
                builtin=bool(s.builtin),
                used=s.style_id in used or s.name in used,
            )
        )
    styles.sort(key=lambda s: (s.kind, s.name.lower()))

    return TemplateReport(
        path=str(template_path),
        styles=styles,
        placeholders=_placeholders(doc),
    )


def _used_style_ids(doc) -> set[str]:
    """Style ids referenced by paragraphs (w:pStyle) and tables (w:tblStyle)."""
    used: set[str] = set()
    body = doc.element.body
    for pstyle in body.iter(qn("w:pStyle")):
        val = pstyle.get(qn("w:val"))
        if val:
            used.add(val)
    for tstyle in body.iter(qn("w:tblStyle")):
        val = tstyle.get(qn("w:val"))
        if val:
            used.add(val)
    return used


def _placeholders(doc) -> dict[str, int]:
    """`[Token]` occurrences across body + every header/footer part."""
    from docx.text.paragraph import Paragraph

    roots = [doc.element.body]
    for section in doc.sections:
        for part in (section.header, section.footer,
                     section.first_page_header, section.first_page_footer):
            roots.append(part._element)

    counts: dict[str, int] = {}
    for root in roots:
        for p_el in root.iter(qn("w:p")):
            for token in PLACEHOLDER_RE.findall(Paragraph(p_el, doc).text):
                counts[token] = counts.get(token, 0) + 1
    return dict(sorted(counts.items()))


@dataclass
class ProfileIssue:
    severity: str  # "error" | "warning"
    message: str


def validate_profile(profile: TemplateProfile) -> list[ProfileIssue]:
    """Check a loaded profile against its template's actual styles.

    `load_profile` already enforces structural validity (required keys, YAML
    shape); this goes further and confirms every mapped style really exists in
    the template. Returns issues in report order (errors first, empty = clean).
    """
    issues: list[ProfileIssue] = []
    try:
        template_path = _resolve_template(profile)
    except FileNotFoundError as exc:
        return [ProfileIssue("error", str(exc))]

    report = inspect_template(template_path)
    # "Normal" is Word's mandatory default style: unstyled paragraphs fall back
    # to it even when a (malformed) template omits it from styles.xml, so a
    # mapping to Normal is always safe.
    para_names = {"Normal"} | {s.name for s in report.styles_of("paragraph")} | {
        s.style_id for s in report.styles_of("paragraph")
    }
    table_names = {s.name for s in report.styles_of("table")} | {
        s.style_id for s in report.styles_of("table")
    }

    for label, style_name in profile.style_map.items():
        if style_name not in para_names:
            issues.append(
                ProfileIssue(
                    "error",
                    f"style_map[{label}] -> {style_name!r} is not a paragraph style "
                    f"in {report.path} (paragraphs would fall back to the template "
                    "default).",
                )
            )

    table_style = profile.raw.get("table_style")
    if table_style and table_style not in table_names:
        issues.append(
            ProfileIssue(
                "warning",
                f"table_style {table_style!r} is not a table style in {report.path} "
                "— carried tables keep their source formatting.",
            )
        )

    page_size = profile.raw.get("page", {}).get("size")
    if page_size and page_size not in ("A4", "Letter"):
        issues.append(
            ProfileIssue(
                "warning",
                f"page.size {page_size!r} is not recognized (use A4 or Letter) — "
                "page dimensions will be left as the template's.",
            )
        )

    issues.sort(key=lambda i: 0 if i.severity == "error" else 1)
    return issues
