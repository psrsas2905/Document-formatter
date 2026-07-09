"""Load and expose a template profile (the 'source of truth' for formatting)."""

from __future__ import annotations

from dataclasses import dataclass
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


def load_profile(path: str | Path) -> TemplateProfile:
    """Read a YAML profile from disk into a TemplateProfile.

    Raises FileNotFoundError if the profile is missing.
    """
    path = Path(path)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["_profile_path"] = str(path.resolve())  # lets apply.py resolve template_file
    return TemplateProfile(
        name=data.get("name", "Unnamed"),
        template_file=data["template_file"],
        style_map=data.get("style_map", {}),
        raw=data,
    )
