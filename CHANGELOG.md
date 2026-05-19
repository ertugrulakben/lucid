# Changelog

All notable changes to Lucid are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.5.0] — 2026-05-19

First public open-source release.

### Highlights

- **3 modes**: Answer (vision Q&A), Teach (record & replay), Execute (autonomous computer use).
- **4 backends**: Anthropic API, Claude Code CLI, LM Studio (offline), and third-party plugin support via the `lucid.llm.providers` entry-point group.
- **Multi-monitor aware**: `focus_monitor` action + per-monitor screenshot routing.
- **Profile injection**: per-user `data/profile.yaml` (name, email, signatures, frequent folders, pinned apps, knowledge sources) feeds the agent's prompts.
- **Named workflows**: `lucid run <slug>` with aliases, natural-language phrase matching, and variable substitution (`--var customer=Acme`).
- **Scheduled tasks**: cron / every-N / one-shot / relative-delay (`lucid schedule add --in 30m`).
- **Settings dialog**: in-app provider picker (Anthropic / CLI / LM Studio), overlay opacity + dock corner + click-through.
- **Safety layer**: destructive action confirmation modal, Ctrl+Shift+K kill switch, per-action timeout, retry escalation with loop detector.
- **Reference image attachments**: `lucid exec --image foo.png` injects visual context.
- **i18n**: English + Turkish UI/CLI/prompts via Project Fluent.
- **Resilient long-task mode**: `--resilient` raises step/timeout budgets and tells the agent to persist until every sub-goal is complete.
- **Auto-updater**: `lucid update --check` polls GitHub Releases.
- **OmniParser-v2 grounding** (optional extra): numbered-element overlay for click precision.
- **175+ tests**, GitHub Actions CI (lint, test, build), pre-commit hooks (ruff, black, codespell).

### Architecture

- Action registry (`lucid.actions`) with entry-point + user-plugin discovery (`LUCID_USER_PLUGINS=1`).
- LLM provider registry mirroring the same plugin pattern.
- Anthropic streaming hardening: classifies SDK errors into retriable vs fatal, retries with exponential backoff + full jitter.
- Hybrid capture mode (`settings.capture.mode = vision | a11y_only | hybrid`).
- Multi-agent router: planner/verifier split across two models, low-confidence verifier replies escalate.
- Hardcoded-string CI guard (`scripts/check_no_hardcoded_text.py`).

### Notes

- Python 3.10+ required (3.12 tested).
- Windows 10/11 primary platform (UI Automation backbone is Windows-only); Linux/macOS partial via direct mouse/keyboard.
- MIT licensed.

## [Unreleased — pre-public history]

### Added (v1.0 roadmap, 2026-05-03)
- **i18n with Project Fluent**: full English + Turkish locale bundles for UI,
  CLI help, mode prompts, and error messages. Resolution order is
  ``LUCID_LOCALE`` env -> ``settings.locale`` -> OS locale -> English.
  System prompts moved out of code into ``locales/<lang>/prompts.ftl`` so
  reviewers can edit model guidance without touching Python.
- **Settings expansion**: ``Settings.locale``, ``SchedulerSettings.poll_interval_seconds``,
  ``ExecutorSettings.resilient_min_timeout``, ``ExecutorSettings.resilient_min_max_steps``,
  ``CaptchaSettings.max_per_hour`` (Field validators), plus four new config
  sections: ``GroundingSettings``, ``CaptureSettings``, ``UpdaterSettings``,
  ``SchedulerSettings``. ``backend.lm_studio_model`` now defaults to ""
  (auto-pick first loaded model on the local server).
- **Typer-based CLI**: ``lucid.__main__`` delegates to a Typer app with
  subcommands ``run, exec, replay, workflows, forget, templates, status,
  schedule, profile, doctor, actions list, update check``. Help text is
  pulled from the active locale.
- **``lucid doctor`` self-diagnostic**: 5 checks (API key, hotkey, DPI
  awareness, data-dir writability, model reachability) with both human
  and ``--json`` output.
- **Action registry** (``lucid.actions``): decorator-based, with
  entry-point and user-plugin discovery (``LUCID_USER_PLUGINS=1`` opts
  in). Five built-in actions migrated to the registry pattern:
  ``focus_window, click_element, type_text, file_dialog_paste, wait``.
  ``lucid actions list`` prints registered actions + schemas.
- **LLM provider registry** (``lucid.llm.registry``): four built-in
  backends (Anthropic, Claude Code CLI, LM Studio, Kimi) registered via
  the same pattern; third-party providers can extend the
  ``lucid.llm.providers`` entry-point group.
- **Anthropic streaming hardening**: classifies SDK errors into
  retriable (rate limit, network, server, timeout) vs fatal (auth,
  bad request, not found, permission). Retriable errors retry with
  exponential backoff + full jitter, capped at 3 attempts.
- **LM Studio probe**: confirms the local server is reachable and
  auto-selects a model when ``lm_studio_model`` is blank; warns when
  the requested model is not in the listing.
- **Set-of-Mark grounding** (``lucid.grounding``): UIA tree walk for
  numbered-element overlay; OmniParser-v2 fallback gated behind the
  ``lucid[omniparser]`` extra. ``settings.grounding.mode`` selects
  ``off | uia | uia+omniparser``.
- **Hybrid capture** (``settings.capture.mode``): ``vision``,
  ``a11y_only``, or ``hybrid`` (skips screenshots when the a11y tree
  is substantial). ``capture.cheap_mode`` forces text-only for the
  current turn.
- **Multi-agent router** (``lucid.llm.router``): planner/verifier
  split across two models (Sonnet/Opus + Haiku). Low-confidence
  verifier replies escalate to the planner.
- **Auto-updater** (``lucid.updater``): ``lucid update --check`` polls
  the GitHub Releases API and reports newer Windows installers. Never
  modifies the running install -- the user downloads and runs the
  installer manually.
- **Examples**: ``examples/01_answer_screenshot.py``,
  ``examples/02_custom_action_plugin.py``,
  ``examples/03_lm_studio_offline.py``.
- **Hardcoded-string CI guard**: ``scripts/check_no_hardcoded_text.py``
  fails when watched modules (UI, agent, ``__main__``) contain
  user-facing strings outside ``_("...")``, comments, or docstrings.
- **New tests**: i18n bootstrap (12), action registry (10), LLM
  provider registry (6), grounding (9), capture modes (8), router (5),
  updater (11) -- all green.

### Added (initial)
- Initial project skeleton.
- Global hotkey listener (Ctrl+Shift+J).
- Frameless translucent Spotlight overlay (PySide6).
- Screenshot capture with multi-monitor support (mss).
- Active window and process detection (pygetwindow + pywin32).
- Optional UI Automation accessibility tree snapshot.
- Anthropic Claude provider with streaming and computer_use tool.
- Mode A (Answer): vision prompt returns a direct textual answer.
- Mode B (Teach): input and accessibility recorder, workflow JSON schema, semantic replayer.
- Mode C (Execute): Claude computer_use loop with safety guard and kill switch.
- Backend strategy: direct Anthropic API or Claude Code CLI subprocess.
- Keyring-backed secret storage for API keys.
- Opt-in anonymous telemetry.
- Windows installer (PyInstaller + NSIS).
- GitHub Actions CI (lint, test, build).

## [0.1.0] — TBD

First public release.
