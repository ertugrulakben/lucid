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

Lucid keeps its local files in one data folder: `data\` inside the Lucid
folder for a source checkout, `%APPDATA%\Lucid\` when that folder is
read-only, or the folder named by `LUCID_DATA_DIR`. `lucid status` prints it.

| File | Location | Contents |
| ---- | -------- | -------- |
| `settings.yaml` | data folder | Hotkey, provider, safety settings. No secrets. |
| `install_id` | data folder | Random UUID used for opt-in telemetry. |
| `logs\lucid.log` | data folder | Action names and sizes. Never prompt text, never screenshot bytes. |
| Screenshots | data folder, `screenshots\` | PNG files of captured screens while `screenshot.persist` is on (the default). `screenshot.retention_hours` is not enforced yet, so they stay until you delete them. |
| Workflows | data folder, `workflows\` | Teach-mode JSON files. Stays local unless you export. |

## Telemetry

Off by default. When enabled, Lucid sends event names and the install UUID
only. No prompt text, no screenshots, no window titles, no API keys. The
endpoint URL is user-configurable; if unset, telemetry is a no-op.

## Data deletion

Delete the data folder to wipe local data; uninstalling Lucid does not remove
`%APPDATA%\Lucid\` or a `LUCID_DATA_DIR` folder. Besides the files above it
holds `memory.db`, `profile.yaml` and the Step Gallery `journals\`
(before/after screenshots of Execute runs). The OS keyring entry is stored
under the service name `lucid` and can be removed via your OS credential
manager.

## Running fully offline

Set `backend.mode: cli` with no Claude CLI installed, or set the provider to
an unreachable endpoint - Lucid will refuse to submit prompts. The
hotkey, overlay, and recorder still work; Mode B workflows can be recorded
locally and replayed later once a provider is available.
