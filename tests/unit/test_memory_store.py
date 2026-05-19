from __future__ import annotations

from pathlib import Path

import pytest

from lucid.memory.store import MemoryStore


@pytest.fixture
def store(tmp_path: Path) -> MemoryStore:
    return MemoryStore(tmp_path / "memory.db", max_facts=50, max_files=50, max_task_patterns=50)


def test_add_and_recent_facts(store: MemoryStore) -> None:
    store.add_fact("gmail", "Ctrl+Shift+A opens the attach dialog.", source="task#1")
    store.add_fact("excel", "F2 edits cell without clearing.", source="task#2")
    recent = store.recent_facts(limit=5)
    assert len(recent) == 2
    assert any("attach" in f.content for f in recent)


def test_search_facts_prefers_matching_topic(store: MemoryStore) -> None:
    store.add_fact("chrome", "Ctrl+L focuses the omnibox.")
    store.add_fact("excel", "F2 edits a cell.")
    results = store.search_facts("chrome omnibox")
    assert results and "chrome" in results[0].topic.lower()


def test_file_index_is_sorted_by_recency(store: MemoryStore) -> None:
    store.touch_file("C:/a.txt")
    store.touch_file("C:/b.txt")
    store.touch_file("C:/a.txt")  # bump a.txt to most-recent
    recent = store.recent_files(limit=5)
    assert recent[0].path.lower().endswith("a.txt")


def test_find_files_by_fragment(store: MemoryStore) -> None:
    store.touch_file(r"C:\Users\test\Desktop\rapor_2026.xlsx", kind="xlsx", tags="muhasebe")
    store.touch_file(r"C:\Users\test\Documents\notes.txt")
    hits = store.find_files("rapor muhasebe")
    assert hits and "rapor" in hits[0].path.lower()


def test_task_pattern_search_filters_by_app(store: MemoryStore) -> None:
    store.add_task_pattern(
        "send an email", "composed with Tab nav", target_app="chrome.exe", step_count=5
    )
    store.add_task_pattern("fill excel column", "A1 to A10", target_app="excel.exe", step_count=11)
    chrome_hits = store.search_task_patterns("email", target_app="chrome.exe")
    assert chrome_hits and chrome_hits[0].target_app == "chrome.exe"


def test_captcha_rate_limit_counter(store: MemoryStore) -> None:
    store.log_captcha_attempt("recaptcha_checkbox", True)
    store.log_captcha_attempt("turnstile", False)
    assert store.captcha_attempts_last_hour() >= 2


def test_trim_respects_max_facts(tmp_path: Path) -> None:
    s = MemoryStore(tmp_path / "m.db", max_facts=5, max_files=50, max_task_patterns=50)
    for i in range(10):
        s.add_fact(f"topic_{i}", f"content {i}")
    assert s.stats()["facts"] == 5
