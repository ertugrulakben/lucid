# Lucid v0.1.0 → v1.0 World-Class Roadmap

> Status: **In Progress** (started 2026-05-03)

## Goal

Take Lucid from v0.1.0 (alpha, ~9.1K LOC, 73 Python files) to v1.0 production OSS release at the level of OpenAdapt, Browser-Use, Skyvern.

## Phases

### Phase 0 — Pre-flight (1.5 days)

OSS governance, demo assets, CI hardening.

- `.github/CODE_OF_CONDUCT.md` (Contributor Covenant 2.1)
- `.github/SECURITY.md` (90-day disclosure window)
- `.github/PULL_REQUEST_TEMPLATE.md`
- `.github/FUNDING.yml`
- `.github/dependabot.yml` (weekly pip + github-actions)
- `.pre-commit-config.yaml` (ruff, ruff-format, codespell, check-yaml, end-of-file-fixer)
- `pyproject.toml` URL fix + `Alpha → Beta`
- `docs/hero.png` + `docs/demo.gif`
- CI: remove `continue-on-error` from mypy, add cache, add Linux runner

### Phase 1 — Foundation refactor (4 days)

#### 1a. i18n — Project Fluent

```
src/lucid/i18n/
├── __init__.py        # _("key", **kwargs), set_locale(), available_locales()
├── loader.py          # FluentLocalization wrapper, lru_cache
└── locales/
    ├── en/            # ui.ftl, modes.ftl, cli.ftl, prompts.ftl, errors.ftl
    └── tr/            # mirror
```

Bootstrap: `i18n.init()` runs BEFORE Qt or argparse import.
Resolution: `LUCID_LOCALE` env → `settings.locale` → `QLocale.system().name()` → `"en"`.

CI guard: `scripts/check_no_hardcoded_text.py` — fail PR on non-ASCII chars outside `_("...")`, comments, docstrings.

Library: `fluent.runtime==0.4.0`.

#### 1b. Magic numbers → Settings

- `Settings.locale: str = "en"`
- `SchedulerSettings.poll_interval_seconds = 20`
- `ExecutorSettings.resilient_min_timeout = 600`
- `CaptchaSettings.max_per_hour = 10`
- `BackendSettings.lm_studio_model` default `""`

#### 1c. CLI — Typer 0.12

`__main__.py` 570 LOC argparse → ~250 LOC Typer subcommand tree.

Subcommands: `run, exec, teach, schedule, memory, config, doctor, version`.

`lucid doctor` checks: API key, hotkey conflict, DPI, permissions, model availability.

#### 1d. Targeted exception handling

3 tranches: `executor/actions.py` → `OSError, pyautogui.FailSafeException, uiautomation.LookupError`. `agent/execute_mode.py` → `anthropic.APIError, anthropic.RateLimitError`. Rest get `# noqa: BLE001`.

### Phase 2 — Architecture upgrades (6 days)

#### 2a. Plugin system

```
src/lucid/actions/
├── registry.py        # @register_action decorator
└── builtin/           # 20+ existing actions migrated, one per file
```

3rd-party plugins via `[project.entry-points."lucid.actions"]`.

Same pattern for LLM backends (`lucid.llm.providers` entry-point).

4 backend production hardening: streaming retry, subprocess timeout, connection probe, Kimi WIP→production.

#### 2b. Set-of-Mark grounding — UIA + OmniParser bundled

```
src/lucid/grounding/
├── som.py             # detect_elements()
├── overlay_render.py  # PIL numbered boxes
└── omniparser.py      # gated on `lucid[omniparser]` extra
```

Cascade: UIA (free, ~50ms) → OmniParser v2 fallback if <3 elements.

`grounding.mode = "uia" | "uia+omniparser" | "off"`.

#### 2c. Hybrid capture

`capture.mode = "vision" | "a11y_only" | "hybrid"`. Reduces text-editor session cost ~70%.

#### 2d. Multi-agent orchestration

Planner: Sonnet/Opus. Verification + disambiguation: Haiku 4.5.

Bench fixture: 5 sabit task. Goal: -40% cost, success rate ±2%.

### Phase 3 — Quality & coverage (3.5 days)

70% line / 60% branch coverage. Currently ~30/73 modules tested.

Fixture stack: `mock_screen`, `fake_uia_tree`, `fake_provider`, `mock_executor`.

New tests: actions, overlay (pytest-qt), execute_mode, teach_mode, capture, grounding, plugin loading, backend smoke.

Mypy strict: `executor/, agent/, llm/`.

CI matrix: Windows + Linux (`QT_QPA_PLATFORM=offscreen`).

### Phase 4 — Distribution & polish (3 days)

- Auto-updater (50 LOC, GitHub Releases API)
- Signed manifest (Ed25519, repo public key)
- Docs site (`mkdocs-material`)
- `examples/` folder (6 scripts)
- Marketing assets (60s screen recording, social preview)

### Phase 5 — Benchmark & launch (1.5 days)

- WindowsAgentArena 12-task subset
- ScreenSpot SoM grounding accuracy
- Launch posts (HN, r/LocalLLaMA, X)
- CHANGELOG v1.0.0 consolidated entry

## Acceptance Criteria for v1.0

- `pytest --cov=lucid --cov-fail-under=70` green on Windows + Linux
- `lucid doctor` green on Win10 + Win11
- `mkdocs gh-deploy` site live
- 4 backend smoke tests green
- WindowsAgentArena baseline published
- README has demo.gif + 60s embed
- `git tag v1.0.0` produces signed artifact bundle
