from __future__ import annotations

from pathlib import Path

import yaml

from lucid.config.profile import Profile, ensure_profile_file, pick_profile_snippet


def test_profile_from_dict_populates_fields() -> None:
    p = Profile._from_dict(
        {
            "name": "Test User",
            "email": "test@example.com",
            "website": "https://example.com",
            "default_browser": "Chrome",
            "signatures": {"email": "Best regards,\nTest User"},
            "frequent_folders": ["C:/Users/X/Desktop"],
            "pinned_apps": ["chrome", "excel"],
            "notes": ["admin url is admin.example.com"],
            "languages": ["tr", "en"],
        }
    )
    assert p.name == "Test User"
    assert p.email.endswith("@example.com")
    assert p.default_browser == "chrome"
    assert "Best regards" in p.signatures["email"]
    assert p.is_complete() is True


def test_profile_redacts_secret_notes_in_prompt_block() -> None:
    p = Profile._from_dict(
        {
            "name": "X",
            "email": "x@y.com",
            "notes": [
                "My Gmail password is hunter2",
                "Meeting with Alex tomorrow",
            ],
        }
    )
    block = p.to_prompt_block()
    assert "hunter2" not in block
    assert "Meeting with Alex" in block


def test_pick_snippet_for_email_hint_focuses_on_sig() -> None:
    p = Profile._from_dict(
        {
            "name": "X",
            "email": "x@y.com",
            "signatures": {"email": "Cheers,\nX"},
            "frequent_folders": ["C:/Desktop"],
        }
    )
    snippet = pick_profile_snippet(p, context_hint="Gmail'de mail at")
    assert "x@y.com" in snippet
    assert "Signature" in snippet


def test_ensure_profile_file_copies_example(tmp_path: Path) -> None:
    class _Settings:
        pass

    s = _Settings()
    s.profile_path = tmp_path / "data" / "profile.yaml"  # type: ignore[attr-defined]
    s.profile_example_path = tmp_path / "profile.example.yaml"  # type: ignore[attr-defined]
    s.profile_example_path.write_text(  # type: ignore[attr-defined]
        yaml.safe_dump({"name": "You", "email": "you@example.com"}),
        encoding="utf-8",
    )
    path = ensure_profile_file(s)
    assert path.exists()
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data["email"] == "you@example.com"
