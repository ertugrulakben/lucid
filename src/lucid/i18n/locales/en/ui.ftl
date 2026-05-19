### Lucid UI strings (overlay, dialogs, status)

# Overlay shell
overlay-title = Lucid
overlay-placeholder = Type a request, paste an image, or press Tab to switch mode
overlay-mode-answer = Answer
overlay-mode-teach = Teach
overlay-mode-execute = Execute
overlay-hint-submit = Enter to send
overlay-hint-dismiss = Esc to close
overlay-hint-mode-cycle = Tab to switch mode

# Tray
tray-tooltip = Lucid is running. Press the global hotkey to open.
tray-menu-show = Show overlay
tray-menu-settings = Settings
tray-menu-pause = Pause hotkey
tray-menu-resume = Resume hotkey
tray-menu-quit = Quit Lucid

# Settings dialog
settings-title = Lucid Settings
settings-tab-general = General
settings-tab-backend = Model & Backend
settings-tab-overlay = Overlay
settings-tab-memory = Memory
settings-tab-safety = Safety
settings-tab-advanced = Advanced
settings-save = Save
settings-cancel = Cancel
settings-reset = Reset to defaults
settings-locale = Interface language
settings-hotkey = Global hotkey
settings-restart-required = Some changes take effect after restart.

# Modal confirmations
confirm-destructive-title = Confirm action
confirm-destructive-body = Lucid is about to perform an action that may be hard to undo. Continue?
confirm-button-yes = Continue
confirm-button-no = Stop

# Generic
button-ok = OK
button-cancel = Cancel
button-close = Close
button-retry = Retry
loading = Loading...

# Toolbar
toolbar-attach-image = 📎 Attach image
toolbar-attach-tooltip = Attach a reference image (PNG/JPG/WebP). Ctrl+V pastes from clipboard.
toolbar-workflows = 💾 Workflows
toolbar-workflows-tooltip = Named workflows you recorded in Teach mode — click to run.
toolbar-schedule = 🕘 Scheduled tasks
toolbar-schedule-tooltip = Cron / every-N / one-shot scheduled tasks — run now or open the file.
toolbar-actions = 📜 Actions
toolbar-actions-tooltip = Toggle the last-10-actions panel (Execute mode debug).
toolbar-stop = ⏹ Stop  (Ctrl+Shift+K)

# Window controls
window-minimize = ▁
window-minimize-tooltip = Minimize to tray (Ctrl+M). Hotkey reopens it.
window-dock = 🧷
window-dock-tooltip = Dock to a corner of the active screen (Ctrl+D).
window-close = ✕
window-close-tooltip = Close the overlay (Esc).

# Status / placeholders
status-shortcuts = Ctrl+N: new conversation   Esc: close   Ctrl+M: minimize   Ctrl+D: dock
status-working = Claude is working…  type a new prompt + Enter to redirect
status-error = Error
status-done = Done. Type the next step + Enter, or Esc to close.
status-new = New conversation. Ask away.
status-click-through-on = Click-through ON  (Ctrl+Alt+T to toggle)
status-click-through-off = Click-through OFF  (Ctrl+Alt+T to toggle)
status-working-mode = Working… ({ $mode })

placeholder-answer = Ask Lucid…  (Ctrl+1/2/3 switch modes, Tab cycles)
placeholder-teach = Describe what you will teach…  (overlay hides on Enter, hotkey stops recording)
placeholder-execute = Tell Lucid what to DO…  (it will take over mouse and keyboard)

# Workflow / schedule menus
menu-no-workflows = No saved workflows yet
menu-how-to-record = How to record? Ctrl+Alt+J → Ctrl+2 (Teach)
menu-no-tasks = No scheduled tasks yet
menu-add-task = Add one: lucid schedule add --cron "0 9 * * *" --prompt "…"
menu-open-schedule-file = Open scheduled_tasks.json

# Mode picker
mode-answer = Answer
mode-teach = Teach
mode-execute = Execute

# Tray menu
tray-tooltip-base = Lucid — { $hotkey }
tray-tooltip-recording = Lucid — RECORDING (press { $hotkey } to stop)
tray-tooltip-executing = Lucid — EXECUTING (press Ctrl+Shift+K to stop)
tray-open = Open
tray-new-conversation = New conversation
tray-saved-workflows = Saved workflows
tray-scheduled-tasks = Scheduled tasks
tray-no-workflows = (None — record with Teach mode)
tray-no-schedules = (None — lucid schedule add …)
tray-settings = Settings…
tray-open-settings-file = Open settings.yaml
tray-quit = Quit
tray-settings-saved-title = Lucid — Settings saved
tray-settings-saved-body = Backend changed. Quit and relaunch the tray to activate.
