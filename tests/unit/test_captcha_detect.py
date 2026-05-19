from __future__ import annotations

from lucid.safety.captcha import detect_captcha


def test_detects_recaptcha_checkbox_by_name() -> None:
    tree = {
        "name": "window",
        "role": "Window",
        "children": [
            {"name": "I'm not a robot", "role": "CheckBox"},
        ],
    }
    hit = detect_captcha(tree)
    assert hit is not None
    assert hit.kind == "recaptcha_checkbox"


def test_detects_turnstile_branding() -> None:
    tree = {
        "name": "Doc",
        "role": "Pane",
        "children": [
            {"name": "Cloudflare Turnstile challenge", "role": "Frame"},
        ],
    }
    hit = detect_captcha(tree)
    assert hit is not None and hit.kind == "turnstile"


def test_returns_none_when_tree_is_clean() -> None:
    tree = {
        "name": "login form",
        "role": "Form",
        "children": [
            {"name": "Username", "role": "Edit"},
            {"name": "Password", "role": "Edit"},
            {"name": "Sign in", "role": "Button"},
        ],
    }
    assert detect_captcha(tree) is None


def test_handles_none_tree() -> None:
    assert detect_captcha(None) is None
