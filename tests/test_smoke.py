"""Smoke tests — expand into real regression tests against samples/ as stages land."""

from docformat.template import load_profile


def test_profile_loads():
    profile = load_profile("config/template_profile.example.yaml")
    assert profile.style_map["Heading1"] == "Heading 1"
    assert profile.raw["page"]["size"] in {"A4", "Letter"}
