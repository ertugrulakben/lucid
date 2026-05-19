"""Settings dialog — user-friendly picker for backend/provider + overlay.

Opens from the tray menu ("Settings…"). Writes back to the same YAML file
that ``get_settings()`` reads, so changes survive restart. Running
backends are not swapped hot — user restarts the tray for provider
changes; overlay opacity + dock corner update live via the controller.
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml  # PyYAML is already a transitive dep via pydantic-yaml
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from lucid.config.settings import Settings

log = logging.getLogger("lucid.ui.settings_dialog")


PROVIDER_CHOICES = [
    ("api", "Anthropic API (default, needs API key)"),
    ("cli", "Claude Code CLI (uses your Claude subscription)"),
    ("lm_studio", "LM Studio / local (offline, OpenAI-compatible)"),
]

DOCK_CORNERS = [
    ("top-right", "Top-right (default)"),
    ("top-left", "Top-left"),
    ("bottom-right", "Bottom-right"),
    ("bottom-left", "Bottom-left"),
]


class SettingsDialog(QDialog):
    """Plain Qt dialog — no web frontend, native-feeling, 1 file."""

    # Emitted when the user hits Save and the settings were persisted.
    # The controller reloads relevant subsystems (overlay paint, etc.).
    settings_saved = Signal(object)  # emits the new Settings instance

    def __init__(self, settings: Settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Lucid — Settings")
        self.setModal(True)
        self.setMinimumWidth(520)
        self._settings = settings

        root = QVBoxLayout(self)

        # ── Backend / provider ─────────────────────────────────────────
        provider_box = QGroupBox("LLM Backend", self)
        pform = QFormLayout(provider_box)

        self.provider_combo = QComboBox(provider_box)
        for key, label in PROVIDER_CHOICES:
            self.provider_combo.addItem(label, key)
        self._select_combo(self.provider_combo, settings.backend.mode or "api")
        self.provider_combo.currentIndexChanged.connect(self._refresh_visibility)
        pform.addRow("Provider:", self.provider_combo)

        # Anthropic-specific
        self.api_model = QLineEdit(settings.model, provider_box)
        pform.addRow("Answer model:", self.api_model)
        self.execute_model = QLineEdit(settings.execute_model, provider_box)
        pform.addRow("Execute model:", self.execute_model)

        # LM Studio-specific
        self.lm_url = QLineEdit(settings.backend.lm_studio_url, provider_box)
        self.lm_url.setPlaceholderText("http://localhost:1234/v1")
        pform.addRow("LM Studio URL:", self.lm_url)
        self.lm_model = QLineEdit(settings.backend.lm_studio_model, provider_box)
        self.lm_model.setPlaceholderText("google/gemma-4-26b-a4b")
        pform.addRow("LM Studio model:", self.lm_model)

        # CLI-specific
        self.cli_path = QLineEdit(settings.backend.cli_path or "", provider_box)
        self.cli_path.setPlaceholderText("(leave empty to use 'claude' on PATH)")
        pform.addRow("Claude CLI path:", self.cli_path)

        root.addWidget(provider_box)

        # ── Overlay appearance ─────────────────────────────────────────
        overlay_box = QGroupBox("Overlay", self)
        oform = QFormLayout(overlay_box)

        opacity_row = QWidget(overlay_box)
        opacity_h = QHBoxLayout(opacity_row)
        opacity_h.setContentsMargins(0, 0, 0, 0)
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal, overlay_box)
        self.opacity_slider.setRange(40, 100)  # 0.40 .. 1.00
        self.opacity_slider.setValue(int(round(settings.overlay.opacity * 100)))
        self.opacity_value = QLabel(f"{self.opacity_slider.value()}%", overlay_box)
        self.opacity_slider.valueChanged.connect(lambda v: self.opacity_value.setText(f"{v}%"))
        opacity_h.addWidget(self.opacity_slider, 1)
        opacity_h.addWidget(self.opacity_value)
        oform.addRow("Opacity (Execute dock):", opacity_row)

        self.dock_combo = QComboBox(overlay_box)
        for key, label in DOCK_CORNERS:
            self.dock_combo.addItem(label, key)
        self._select_combo(self.dock_combo, settings.overlay.dock_corner or "top-right")
        oform.addRow("Dock corner:", self.dock_combo)

        self.click_through_combo = QComboBox(overlay_box)
        self.click_through_combo.addItem("Off — overlay always captures clicks", False)
        self.click_through_combo.addItem("On — Ctrl+Alt+T toggles click-through while docked", True)
        self.click_through_combo.setCurrentIndex(1 if settings.overlay.click_through_on_dock else 0)
        oform.addRow("Click-through:", self.click_through_combo)

        root.addWidget(overlay_box)

        # ── Info / path ────────────────────────────────────────────────
        path_label = QLabel(
            f"<span style='color:#888'>File: {settings.config_path}</span>",
            self,
        )
        path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addWidget(path_label)

        # ── Buttons ────────────────────────────────────────────────────
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self._refresh_visibility()

    # ---------- helpers ----------
    @staticmethod
    def _select_combo(combo: QComboBox, key: str) -> None:
        for i in range(combo.count()):
            if combo.itemData(i) == key:
                combo.setCurrentIndex(i)
                return
        combo.setCurrentIndex(0)

    def _refresh_visibility(self) -> None:
        """Hide irrelevant rows based on the selected provider."""
        mode = self.provider_combo.currentData()
        is_api = mode == "api"
        is_lm = mode == "lm_studio"
        is_cli = mode == "cli"
        self.api_model.setEnabled(is_api)
        self.execute_model.setEnabled(is_api)
        self.lm_url.setEnabled(is_lm)
        self.lm_model.setEnabled(is_lm)
        self.cli_path.setEnabled(is_cli)

    def _on_save(self) -> None:
        new_mode = self.provider_combo.currentData() or "api"
        opacity = self.opacity_slider.value() / 100.0
        dock = self.dock_combo.currentData() or "top-right"
        click_through = bool(self.click_through_combo.currentData())

        updates: dict = {
            "model": self.api_model.text().strip() or self._settings.model,
            "execute_model": self.execute_model.text().strip() or self._settings.execute_model,
            "backend": {
                "mode": new_mode,
                "cli_path": self.cli_path.text().strip() or None,
                "lm_studio_url": self.lm_url.text().strip() or self._settings.backend.lm_studio_url,
                "lm_studio_model": self.lm_model.text().strip()
                or self._settings.backend.lm_studio_model,
                "lm_studio_api_key": self._settings.backend.lm_studio_api_key,
            },
            "overlay": {
                "opacity": opacity,
                "dock_corner": dock,
                "click_through_on_dock": click_through,
            },
        }
        try:
            _write_yaml_patch(self._settings.config_path, updates)
        except Exception as exc:
            log.exception("settings save failed: %s", exc)
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.critical(self, "Lucid — Save failed", str(exc))
            return
        # Reload settings so downstream code sees the new values
        from lucid.config.settings import get_settings

        get_settings.cache_clear()  # type: ignore[attr-defined]
        new_settings = get_settings()
        self.settings_saved.emit(new_settings)
        self.accept()


def _write_yaml_patch(path: Path, patch: dict) -> None:
    """Merge ``patch`` into the YAML at ``path`` without blowing away
    keys we don't touch (safety, memory, captcha, etc.)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: dict = {}
    if path.exists():
        try:
            with path.open("r", encoding="utf-8") as fh:
                existing = yaml.safe_load(fh) or {}
        except Exception:
            existing = {}
    merged = _deep_merge(existing, patch)
    with path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(merged, fh, allow_unicode=True, sort_keys=False)


def _deep_merge(base: dict, patch: dict) -> dict:
    out = dict(base)
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out
