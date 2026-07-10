"""Load and expose a template profile (the 'source of truth' for formatting)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml


@dataclass
class TemplateProfile:
    """Parsed view of a template_profile.yaml file."""

    name: str
    template_file: str
    style_map: dict[str, str]
    raw: dict  # full parsed YAML for less-common fields (page, header, footer, toc...)

    def style_for(self, label: str) -> str | None:
        """Return the template style name for a given BlockType value."""
        return self.style_map.get(label)


def output_stem(profile: TemplateProfile, input_stem: str) -> str:
    """Output filename stem (no extension) from the profile's `output.filename`.

    Honors the {basename}, {version} and {date} tokens; falls back to
    '<input>_formatted' when the profile sets no filename. The result is
    sanitized to a safe filename.
    """
    output = profile.raw.get("output", {}) or {}
    spec = output.get("filename")
    if not spec:
        return f"{input_stem}_formatted"
    tokens = {
        "{basename}": input_stem,
        "{version}": str(output.get("version", "")),
        "{date}": date.today().isoformat(),
    }
    for token, value in tokens.items():
        spec = spec.replace(token, value)
    # Drop characters no filesystem accepts; collapse whitespace to underscores.
    spec = re.sub(r'[<>:"/\\|?*]', "", spec)
    spec = re.sub(r"\s+", "_", spec.strip()).strip("._")
    return spec or f"{input_stem}_formatted"


def apply_field_values(profile: TemplateProfile, values: dict[str, str]) -> None:
    """Merge per-document field values into the profile's replace map.

    Keys name template placeholders without brackets: 'Client Name' fills
    '[Client Name]'. Bracketed keys are used verbatim. Runtime values win
    over the profile's own replace entries.
    """
    if not values:
        return
    replace = profile.raw.setdefault("replace", {})
    for key, value in values.items():
        key = key.strip()
        placeholder = key if key.startswith("[") and key.endswith("]") else f"[{key}]"
        replace[placeholder] = value


# Every profile must map these labels (BlockType values the classifier emits).
REQUIRED_STYLE_KEYS = (
    "Heading1",
    "Heading2",
    "Heading3",
    "Body",
    "Caption",
    "ListItem",
    "Quote",
)


def load_profile(path: str | Path) -> TemplateProfile:
    """Read and validate a YAML profile from disk into a TemplateProfile.

    Raises FileNotFoundError if the profile is missing, ValueError with a
    human-readable message when it is malformed.
    """
    path = Path(path)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"Profile {path} is not valid YAML: {exc}") from exc

    if not isinstance(data, dict) or not data:
        raise ValueError(f"Profile {path} is empty or not a YAML mapping.")
    if not data.get("template_file"):
        raise ValueError(
            f"Profile {path} is missing 'template_file' — the path to the "
            "organization's .docx/.dotx template."
        )
    style_map = data.get("style_map", {})
    missing = [k for k in REQUIRED_STYLE_KEYS if not style_map.get(k)]
    if missing:
        raise ValueError(
            f"Profile {path} style_map is missing mappings for: "
            f"{', '.join(missing)}. Every label needs a template style name."
        )

    data["_profile_path"] = str(path.resolve())  # lets apply.py resolve template_file
    return TemplateProfile(
        name=data.get("name", "Unnamed"),
        template_file=data["template_file"],
        style_map=style_map,
        raw=data,
    )
