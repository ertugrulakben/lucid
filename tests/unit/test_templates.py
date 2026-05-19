from __future__ import annotations

import pytest

from lucid.templates import TemplateError, expand_template, list_templates, load_template


def test_list_templates_finds_ship_in_files() -> None:
    specs = list_templates()
    names = {s.name for s in specs}
    assert {
        "send_gmail",
        "excel_new_sheet",
        "attach_file",
        "screenshot_describe",
        "download_file",
        "chrome_new_tab_go",
        "clipboard_to_active",
    }.issubset(names)


def test_load_template_parses_required_vars() -> None:
    spec = load_template("send_gmail")
    assert "to" in spec.required_vars
    assert "{{to}}" in spec.prompt


def test_expand_substitutes_placeholders() -> None:
    prompt = expand_template(
        "chrome_new_tab_go",
        {"url": "https://example.com"},
    )
    assert "https://example.com" in prompt


def test_missing_required_var_raises() -> None:
    with pytest.raises(TemplateError):
        expand_template("send_gmail", {})


def test_unknown_template_raises() -> None:
    with pytest.raises(TemplateError):
        load_template("does-not-exist")


def test_defaults_are_applied_when_missing() -> None:
    prompt = expand_template("send_gmail", {"to": "x@y.com"})
    # ``subject`` has a default (empty string), so substitution leaves a clean slate.
    assert "{{subject}}" not in prompt
