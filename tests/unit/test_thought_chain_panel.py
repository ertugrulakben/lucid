"""Unit tests for the ThoughtChain panel (UI behaviour, no rendering check)."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from lucid.ui.thought_chain import ThoughtChainPanel


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


def test_panel_starts_empty(qt_app) -> None:
    panel = ThoughtChainPanel()
    assert len(panel._entries) == 0  # noqa: SLF001 -- intentional internal check
    assert "idle" in panel.title.text().lower() or "boş" in panel.title.text().lower()


def test_append_thought_records_entry(qt_app) -> None:
    panel = ThoughtChainPanel()
    panel.append_thought("Open Notepad with Win+R")
    panel.append_thought("🛠 plan: type 'notepad'")
    assert len(panel._entries) == 2
    html = panel.viewer.toHtml()
    assert "Open Notepad" in html
    assert "plan" in html


def test_history_is_bounded(qt_app) -> None:
    panel = ThoughtChainPanel(history=25)
    for i in range(60):
        panel.append_thought(f"thought {i}")
    assert len(panel._entries) == 25
    # The oldest thoughts must have dropped off.
    html = panel.viewer.toHtml()
    assert "thought 59" in html
    assert "thought 0" not in html


def test_clear_resets(qt_app) -> None:
    panel = ThoughtChainPanel()
    panel.append_thought("first")
    panel.clear()
    assert len(panel._entries) == 0  # noqa: SLF001
    assert panel.viewer.toPlainText() == ""


def test_html_is_escaped(qt_app) -> None:
    panel = ThoughtChainPanel()
    panel.append_thought("<script>alert(1)</script>")
    html = panel.viewer.toHtml()
    # Raw <script> must not appear; the angle brackets must be entity-encoded.
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
