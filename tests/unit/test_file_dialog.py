from __future__ import annotations

from lucid.executor import file_dialog


def test_title_heuristic_matches_common_labels() -> None:
    for title in ("Aç", "Farklı Kaydet", "Open", "Save As", "Upload File"):
        assert any(hint in title.lower() for hint in file_dialog.FILE_DIALOG_TITLES), title


def test_navigate_empty_path_errors() -> None:
    result = file_dialog.navigate_file_dialog("")
    assert result.startswith("error")
