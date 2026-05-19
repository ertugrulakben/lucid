"""Portable settings loaded from YAML inside the Lucid project.

Everything Lucid writes — settings, profile, memory, logs, screenshots,
workflows — stays under ``<lucid_root>/data`` so the whole tool is a single
movable folder with no APPDATA footprint. Set ``LUCID_DATA_DIR`` env var
to override (useful for CI or shared installs).
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field


class ScreenshotSettings(BaseModel):
    max_width: int = 1024
    persist: bool = True
    retention_hours: int = 24
    blacklist_titles: list[str] = Field(
        default_factory=lambda: [
            "Bitwarden",
            "1Password",
            "KeePass",
            "Incognito",
            "Private Browsing",
        ]
    )


class SafetySettings(BaseModel):
    destructive_confirm: bool = True
    kill_switch_hotkey: str = "ctrl+shift+k"
    failsafe: bool = True
    pause_seconds: float = 0.1


class TelemetrySettings(BaseModel):
    enabled: bool = False
    endpoint: str | None = None


class RecorderSettings(BaseModel):
    capture_video: bool = False
    video_fps: int = 4
    max_duration_seconds: int = 300


class ExecutorSettings(BaseModel):
    max_steps: int = Field(default=50, ge=1, le=2000)
    step_timeout_seconds: float = Field(default=30.0, gt=0.0)
    retry_max_attempts: int = Field(default=3, ge=0)
    resilient_min_timeout: int = Field(default=600, ge=60)
    resilient_min_max_steps: int = Field(default=200, ge=1)


class BackendSettings(BaseModel):
    """Which LLM drives Answer/Teach/Execute.

    mode="api"       → direct Anthropic SDK. Needs ANTHROPIC_API_KEY in keyring.
    mode="cli"       → Claude Code CLI subprocess (uses existing subscription).
    mode="lm_studio" → local LM Studio / Ollama / any OpenAI-compatible endpoint.
                       Zero API cost, fully offline. Configure url + model.

    Third-party providers can register themselves through the
    ``lucid.llm.providers`` entry-point group.
    """

    mode: str = "api"
    cli_path: str | None = None
    # LM Studio / OpenAI-compatible local server
    lm_studio_url: str = "http://localhost:1234/v1"
    lm_studio_model: str = ""  # empty -> use the first model the local server reports
    lm_studio_api_key: str = "lm-studio"  # placeholder (LM Studio ignores it)

    # Extra free-form fields are tolerated so plugin backends can attach their
    # own config without modifying core. Schema-strict providers should still
    # validate inputs themselves.
    model_config = {"extra": "allow"}


class OverlaySettings(BaseModel):
    """How the Spotlight overlay looks and behaves."""

    opacity: float = 0.78  # 0.0 fully transparent → 1.0 fully opaque
    dock_corner: str = "top-right"  # "top-right" | "top-left" | "bottom-right" | "bottom-left"
    click_through_on_dock: bool = (
        False  # Dock'tayken altındaki pencereye tıklamaya izin ver (Ctrl+Alt+T toggle)
    )


class MemorySettings(BaseModel):
    enabled: bool = True
    auto_fact_extract: bool = False
    max_facts: int = 2000
    max_files: int = 500
    max_task_patterns: int = 500


class CaptchaSettings(BaseModel):
    enabled: bool = True
    max_per_hour: int = Field(default=10, ge=0, le=1000)
    try_checkbox: bool = True
    try_image_challenge: bool = True
    try_audio_challenge: bool = True


class SchedulerSettings(BaseModel):
    """Background scheduler daemon timings."""

    poll_interval_seconds: int = Field(default=20, ge=1, le=3600)
    log_retention_days: int = Field(default=14, ge=0)


class GroundingSettings(BaseModel):
    """Set-of-Mark element detection configuration.

    mode="uia"            -> use only the Windows accessibility tree (free, fast)
    mode="uia+omniparser" -> fall back to the OmniParser model when UIA is sparse
    mode="off"            -> no element overlay; the model gets the raw screenshot
    """

    mode: str = "uia"
    label_color: str = "#00C853"
    label_size: int = Field(default=14, ge=8, le=64)
    min_uia_elements: int = Field(default=3, ge=0)
    omniparser_model_id: str = "microsoft/OmniParser-v2.0"


class CaptureSettings(BaseModel):
    """How visible the model is to the screen.

    mode="vision"   -> always send a screenshot
    mode="a11y_only"-> never send a screenshot, only the accessibility text tree
    mode="hybrid"   -> a11y first; screenshot only when a11y is sparse or a vision
                       call is explicitly requested
    """

    mode: str = "hybrid"
    cheap_mode: bool = False
    a11y_max_chars: int = Field(default=12000, ge=500)


class UpdaterSettings(BaseModel):
    enabled: bool = True
    channel: str = "stable"
    check_interval_hours: int = Field(default=24, ge=1)


class OCRSettings(BaseModel):
    enabled: bool = False  # requires optional `lucid[ocr]` extras
    engine: str = "easyocr"
    languages: list[str] = Field(default_factory=lambda: ["tr", "en"])


class Settings(BaseModel):
    hotkey: str = "ctrl+alt+j"
    locale: str = ""  # empty -> i18n.init() resolves from env / OS / English
    provider: str = "anthropic"
    model: str = "claude-opus-4-7"
    execute_model: str = "claude-sonnet-4-6"
    execute_subagent_model: str = "claude-haiku-4-5"
    capture_a11y: bool = True
    auto_undo_on_stop: bool = False

    screenshot: ScreenshotSettings = ScreenshotSettings()
    safety: SafetySettings = SafetySettings()
    telemetry: TelemetrySettings = TelemetrySettings()
    recorder: RecorderSettings = RecorderSettings()
    executor: ExecutorSettings = ExecutorSettings()
    backend: BackendSettings = BackendSettings()
    overlay: OverlaySettings = OverlaySettings()
    memory: MemorySettings = MemorySettings()
    captcha: CaptchaSettings = CaptchaSettings()
    ocr: OCRSettings = OCRSettings()
    scheduler: SchedulerSettings = SchedulerSettings()
    grounding: GroundingSettings = GroundingSettings()
    capture: CaptureSettings = CaptureSettings()
    updater: UpdaterSettings = UpdaterSettings()

    config_path: Path = Field(default_factory=lambda: _default_config_path())
    data_dir: Path = Field(default_factory=lambda: _default_data_dir())

    @property
    def log_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def screenshot_dir(self) -> Path:
        return self.data_dir / "screenshots"

    @property
    def workflows_dir(self) -> Path:
        return self.data_dir / "workflows"

    @property
    def memory_db_path(self) -> Path:
        return self.data_dir / "memory.db"

    @property
    def profile_path(self) -> Path:
        return self.data_dir / "profile.yaml"

    @property
    def profile_example_path(self) -> Path:
        return _lucid_root() / "profile.example.yaml"

    @property
    def templates_dir(self) -> Path:
        return _lucid_root() / "src" / "lucid" / "templates"

    model_config = ConfigDict(arbitrary_types_allowed=True)


def _lucid_root() -> Path:
    """Absolute path of the Lucid project root (where pyproject.toml lives).

    Walks up from this file: settings.py → config → lucid → src → <root>.
    """
    return Path(__file__).resolve().parents[3]


def _default_data_dir() -> Path:
    # Explicit override always wins.
    env_dir = os.environ.get("LUCID_DATA_DIR")
    if env_dir:
        return Path(env_dir)

    # Portable mode: prefer <lucid_root>/data if the install tree is writable.
    root_data = _lucid_root() / "data"
    try:
        root_data.mkdir(parents=True, exist_ok=True)
        probe = root_data / ".write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return root_data
    except OSError:
        pass

    # Fallback for read-only installs (pip / pipx global install).
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "Lucid"
    return Path.home() / ".lucid"


def _default_config_path() -> Path:
    return _default_data_dir() / "settings.yaml"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    path = _default_config_path()
    if path.exists():
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            data = {}
        data.pop("config_path", None)
        data.pop("data_dir", None)
        return Settings(**data)
    path.parent.mkdir(parents=True, exist_ok=True)
    settings = Settings()
    write_settings(settings)
    return settings


def write_settings(settings: Settings) -> None:
    path = settings.config_path
    path.parent.mkdir(parents=True, exist_ok=True)
    dump = settings.model_dump(mode="json", exclude={"config_path", "data_dir"})
    path.write_text(yaml.safe_dump(dump, sort_keys=False, allow_unicode=True), encoding="utf-8")
