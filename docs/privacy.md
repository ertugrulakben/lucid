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

When a teach-mode recording is summarised, the recorded workflow is sent too
(trimmed to 20 kB): clicks, key presses and the characters typed while
recording.

## Never transmitted

- API keys (stored in the OS keyring; never included in prompts or logs).
- Contents of password fields read from the screen: the accessibility tree
  carries names and roles, never field values, and password fields show
  masked characters. A password you write into your prompt is sent with the
  prompt, and the model sees the text it types.
- Any window whose title matches `screenshot.blacklist_titles`.

## Persisted locally

Lucid keeps its local files in one data folder: `data\` inside the Lucid
folder for a source checkout, `%APPDATA%\Lucid\` when that folder is
read-only, or the folder named by `LUCID_DATA_DIR`. `lucid status` prints it.

| File | Location | Contents |
| ---- | -------- | -------- |
| `settings.yaml` | data folder | Hotkey, provider, safety settings. No secrets. |
| `install_id` | data folder | Random UUID used for opt-in telemetry. |
| `logs\lucid.log` | data folder | Action names and parameters. Typed text is masked to its length; never prompt text, never screenshot bytes. |
| Screenshots | data folder, `screenshots\` | PNG files of every captured screen while `screenshot.persist` is on. Off by default since 0.6.2; a `settings.yaml` written by an earlier version still says `true`, and the tray app then shows a notice at start-up (also written to `lucid.log`). Deleted after `screenshot.retention_hours` (24). |
| Proofs | data folder, `proofs\` | The final screenshot of each Execute run while `screenshot.save_proof` is on (the default). Deleted after `screenshot.proof_retention_hours` (24). |
| Step Gallery | data folder, `journals\` | Before/after thumbnails of every Execute step and `index.jsonl` with the action parameters. Typed text, and MCP tool arguments named like a secret (password, token, API key, auth ...), are masked unless `journal.record_text` is on. The newest `journal.max_sessions` (30) are kept; `journal.retention_hours` (0, off) adds an age limit. |
| Scheduled runs | data folder, `schedule_logs\` | Output of each scheduled run (typed text masked). Deleted after `scheduler.log_retention_days` (14). |
| `memory.db` | data folder | Task goals with a one-line summary, proof screenshot paths, and facts when `memory.auto_fact_extract` is on. |
| Workflows | data folder, `workflows\` | Teach-mode JSON files, including the characters typed while recording. Stays local unless you export. |

Retention is enforced when Lucid starts and before every Execute run. A value
of 0 keeps that folder as it is. Only entries named the way Lucid names its
output are deleted (for example `1767225600000.png` in `screenshots\`), and
links (symlinks, junctions) are never followed or removed. Your own files in
a shared data folder stay, unless another program named a file the same way.

## Clipboard

Lucid types by pasting: it puts the text on the clipboard, sends Ctrl+V and
then puts your previous clipboard content back. On Windows the pasted text
is marked with the formats Windows documents for this purpose, so it stays
out of the clipboard history (Win+V) and is not synced to your other devices
by the cloud clipboard.

## Telemetry

Off by default. When enabled, Lucid sends event names and the install UUID
only. No prompt text, no screenshots, no window titles, no API keys. The
endpoint URL is user-configurable; if unset, telemetry is a no-op.

## Data deletion

Delete the data folder to wipe local data; uninstalling Lucid does not remove
`%APPDATA%\Lucid\` or a `LUCID_DATA_DIR` folder. Besides the files above it
holds `profile.yaml`. The OS keyring entry is stored under the service name
`lucid` and can be removed via your OS credential manager.

## Running fully offline

Set `backend.mode: cli` with no Claude CLI installed, or set the provider to
an unreachable endpoint - Lucid will refuse to submit prompts. The
hotkey, overlay, and recorder still work; Mode B workflows can be recorded
locally and replayed later once a provider is available.
