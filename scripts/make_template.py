"""Generate templates/org_standard.docx — a stand-in organization template.

The real workflow expects each organization to supply its own template file
whose named styles the profile's style_map references. Until one exists, this
script materializes python-docx's built-in default template (which defines all
styles the example profile maps to) so the pipeline is testable end-to-end.

Run from the repo root:  python scripts/make_template.py
"""

from __future__ import annotations

from pathlib import Path

import docx

REQUIRED_STYLES = [
    "Heading 1",
    "Heading 2",
    "Heading 3",
    "Body Text",
    "Caption",
    "List Bullet",
    "Quote",
]


def main() -> None:
    out = Path("templates/org_standard.docx")
    out.parent.mkdir(parents=True, exist_ok=True)

    doc = docx.Document()
    available = {s.name for s in doc.styles}
    missing = [s for s in REQUIRED_STYLES if s not in available]
    if missing:
        raise SystemExit(f"Default template is missing required styles: {missing}")

    doc.save(out)
    print(f"Wrote {out} (styles verified: {', '.join(REQUIRED_STYLES)})")


if __name__ == "__main__":
    main()
