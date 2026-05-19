# Privacy

Lucid runs locally on your machine. This document is the complete list of
places it may transmit or persist your data.

## Transmitted to the LLM provider

When you submit a prompt:
- The prompt text you typed.
- The current screenshot (downscaled to `screenshot.max_width`, PNG, base64).
- A short summary of the active window and up to 10 other open window titles.
- Optional: the accessibility tree for the focused window (names and roles, no
  text content of password fields).

Replay of a teach-mode workflow sends the same payload for every step.

## Never transmitted

- API keys (stored in the OS keyring; never included in prompts or logs).
- Contents of password fields (detected via UI Automation
  `IsPassword=True` and suppressed before the screenshot is taken).
- Any window whose title matches `screenshot.blacklist_titles`.

## Persisted locally

| File | Location | Contents |
| ---- | -------- | -------- |
| `settings.yaml` | `%APPDATA%\Lucid\` | Hotkey, provider, safety settings. No secrets. |
| `install_id` | `%APPDATA%\Lucid\` | Random UUID used for opt-in telemetry. |
| `logs\lucid.log` | `%APPDATA%\Lucid\` | Action names and sizes. Never prompt text, never screenshot bytes. |
| Screenshots | `%TEMP%\lucid\screenshots\` | PNG files used during an active prompt. Auto-deleted after `screenshot.retention_hours` (default 24). |
| Workflows | `%APPDATA%\Lucid\workflows\` | Teach-mode JSON files. Stays local unless you export. |

## Telemetry

Off by default. When enabled, Lucid sends event names and the install UUID
only. No prompt text, no screenshots, no window titles, no API keys. The
endpoint URL is user-configurable; if unset, telemetry is a no-op.

## Data deletion

Uninstalling Lucid does not remove `%APPDATA%\Lucid\`. Delete the folder
manually to wipe local data. The OS keyring entry is stored under the service
name `lucid` and can be removed via your OS credential manager.

## Running fully offline

Set `backend.mode: cli` with no Claude CLI installed, or set the provider to
an unreachable endpoint — Lucid will refuse to submit prompts. The
hotkey, overlay, and recorder still work; Mode B workflows can be recorded
locally and replayed later once a provider is available.
