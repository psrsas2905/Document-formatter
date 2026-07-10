"""inspect_template + validate_profile: template introspection and profile
consistency checks (docformat inspect-template / validate-profile)."""

from docformat.inspect import inspect_template, validate_profile
from docformat.template import TemplateProfile, load_profile


def test_inspect_lists_styles_and_placeholders():
    report = inspect_template("templates/org_standard.docx")
    para = {s.name for s in report.styles_of("paragraph")}
    assert {"Heading 1", "Heading 2", "Body Text", "Caption"} <= para
    tables = {s.name for s in report.styles_of("table")}
    assert "Table Grid" in tables


def test_inspect_finds_template_placeholders():
    report = inspect_template("templates/RedLotus_Master_Template.docx")
    assert "[Client Name]" in report.placeholders
    assert report.placeholders["[Client Name]"] >= 1
    # Style names are reported exactly as the profile must reference them.
    assert any(s.name == "Heading 1" for s in report.styles_of("paragraph"))


def test_validate_clean_profile():
    profile = load_profile("config/template_profile.example.yaml")
    assert validate_profile(profile) == []


def test_validate_flags_missing_paragraph_style():
    profile = TemplateProfile(
        name="Broken",
        template_file="templates/org_standard.docx",
        style_map={
            "Heading1": "Heading 1",
            "Heading2": "Heading 2",
            "Heading3": "Heading 3",
            "Body": "No Such Style",
            "Caption": "Caption",
            "ListItem": "List Bullet",
            "Quote": "Quote",
        },
        raw={"template_file": "templates/org_standard.docx", "table_style": "Bogus"},
    )
    issues = validate_profile(profile)
    errors = [i for i in issues if i.severity == "error"]
    warnings = [i for i in issues if i.severity == "warning"]
    assert any("No Such Style" in i.message for i in errors)
    assert any("Bogus" in i.message for i in warnings)


def test_validate_treats_normal_as_valid():
    """RedLotus maps Body/Quote -> Normal; that template omits Normal from
    styles.xml but paragraphs still default to it — must not error."""
    profile = load_profile("config/template_profile.redlotus.yaml")
    assert [i for i in validate_profile(profile) if i.severity == "error"] == []


def test_validate_missing_template_errors():
    profile = TemplateProfile(
        name="NoTemplate",
        template_file="templates/does_not_exist.docx",
        style_map={},
        raw={"template_file": "templates/does_not_exist.docx"},
    )
    issues = validate_profile(profile)
    assert issues and issues[0].severity == "error"
