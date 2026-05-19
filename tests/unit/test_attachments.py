from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from lucid.agent.execute_mode import _slug_for_proof
from lucid.headless import HeadlessOptions, _load_attachments


def _dummy_png(tmp: Path, name: str = "ref.png") -> Path:
    path = tmp / name
    Image.new("RGB", (32, 24), (200, 100, 40)).save(path)
    return path


def test_load_attachments_opens_pil_image(tmp_path: Path) -> None:
    png = _dummy_png(tmp_path)
    loaded = _load_attachments([png], json_output=False)
    assert len(loaded) == 1
    path, img = loaded[0]
    assert path == png
    assert img.size == (32, 24)


def test_load_attachments_skips_missing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    real = _dummy_png(tmp_path, "ok.png")
    missing = tmp_path / "gone.png"
    loaded = _load_attachments([missing, real], json_output=False)
    assert len(loaded) == 1 and loaded[0][0] == real
    captured = capsys.readouterr()
    assert "attachment not found" in captured.out


def test_load_attachments_skips_non_image(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = tmp_path / "notes.txt"
    bad.write_text("not an image", encoding="utf-8")
    loaded = _load_attachments([bad], json_output=False)
    assert loaded == []
    captured = capsys.readouterr()
    assert "could not load attachment" in captured.out


def test_headless_options_defaults_empty_attachments() -> None:
    options = HeadlessOptions(prompt="hello")
    assert options.attachments == []


def test_proof_slug_sanitises_filesystem_unsafe_chars() -> None:
    slug = _slug_for_proof("Ahmet'e SEO için 12.000 TL fatura kes")
    assert "/" not in slug and "'" not in slug and "." not in slug
    assert len(slug) <= 40
    # Non-empty fallback when all characters are unsafe.
    assert _slug_for_proof("") == "task"
    assert _slug_for_proof("***///") == "task"
