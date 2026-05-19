"""Smoke test: every module can be imported without side effects."""

from __future__ import annotations

import importlib

MODULES = [
    "lucid",
    "lucid.app",
    "lucid.hotkey.listener",
    "lucid.capture",
    "lucid.capture.screenshot",
    "lucid.capture.windows",
    "lucid.capture.a11y",
    "lucid.config.settings",
    "lucid.config.secrets",
    "lucid.ui.overlay",
    "lucid.ui.prompt_bar",
    "lucid.ui.mode_picker",
    "lucid.ui.theme",
    "lucid.llm.provider",
    "lucid.llm.schemas",
    "lucid.llm.anthropic_client",
    "lucid.agent.state_machine",
    "lucid.agent.answer_mode",
    "lucid.agent.teach_mode",
    "lucid.agent.execute_mode",
    "lucid.recorder",
    "lucid.recorder.workflow",
    "lucid.recorder.input_recorder",
    "lucid.recorder.a11y_recorder",
    "lucid.recorder.video",
    "lucid.recorder.workflow_recorder",
    "lucid.replayer.semantic_replay",
    "lucid.executor.actions",
    "lucid.executor.safety",
    "lucid.executor.grounding",
    "lucid.backend.api_backend",
    "lucid.backend.cli_backend",
    "lucid.telemetry.anon",
]


def test_all_modules_import() -> None:
    for name in MODULES:
        importlib.import_module(name)
