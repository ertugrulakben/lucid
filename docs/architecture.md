# Architecture

Lucid is a small desktop application written in Python. It binds a global
hotkey, captures a screenshot plus window context, and routes the result to one
of three modes. The LLM layer is abstracted so the same agent core can run on
top of different providers; Anthropic Claude is the default.

## Process model

A single Qt event loop owns the UI. Background work (hotkey polling, input
recording, LLM streaming, computer_use execution) runs on daemon threads. All
cross-thread communication goes through Qt `Signal` objects with
`QueuedConnection`, which guarantees handlers run on the main thread.

```
         ┌────────────────┐
         │  HotkeyListener│ (keyboard lib, daemon thread)
         └───────┬────────┘
                 │ triggered (Qt signal, queued)
                 ▼
         ┌────────────────┐       ┌────────────────┐
         │ AppController  │ ──────▶ ContextSnapshot│ (mss, pygetwindow,
         └───────┬────────┘       │   .capture()   │  pywin32, uiautomation)
                 │ present()      └────────────────┘
                 ▼
         ┌────────────────┐
         │ OverlayWindow  │ (PySide6 frameless translucent)
         │  • PromptBar   │
         │  • ResultPane  │
         │  • ModePicker  │
         └───────┬────────┘
                 │ submitted(prompt, mode)
                 ▼
         ┌────────────────┐       ┌────────────────┐
         │  ModeRouter    │ ─────▶│  LLMProvider   │ (anthropic SDK,
         │                │       │                │  streaming)
         │ ┌────────────┐ │       └────────────────┘
         │ │AnswerMode  │ │
         │ │TeachMode   │ │───▶ WorkflowRecorder (pynput + uiautomation + mss)
         │ │ExecuteMode │ │───▶ Actions (pyautogui / pydirectinput)
         │ └────────────┘ │        │
         └────────────────┘        ▼
                              SafetyGuard (kill switch, destructive detection)
```

## Module dependency graph (top to bottom)

```
app → agent → llm, capture, executor, recorder, replayer
agent → ui (via signals only)
executor → capture (for blacklist/a11y)
recorder → capture
replayer → llm, executor, capture
backend → llm
llm → config
```

Every module depends on `config`. No module imports from `app` (the app
controller is the only coordinator).

## Signal and thread map

| Signal | Emitter | Connection type | Consumer |
| ------ | ------- | --------------- | -------- |
| `HotkeyListener.triggered` | keyboard daemon thread | `Qt.QueuedConnection` | `AppController._on_hotkey` |
| `OverlayWindow.submitted` | main thread | `DirectConnection` | `AppController._on_submitted` |
| `ModeRouter.stream_chunk` | worker thread | auto (queued by Qt) | `OverlayWindow.append_result` |
| `ModeRouter.stream_done` | worker thread | auto | `OverlayWindow.mark_done` |
| `ModeRouter.error` | worker thread | auto | `OverlayWindow.show_error` |

## LLM loop (Mode C)

```
snapshot = capture(screen)
messages = [system, user(goal + image)]
while steps < max:
    for event in provider.stream(messages, tools=[computer]):
        if text_delta:   yield text
        if tool_use:     buffer action
        if done:         break
    if no tool_use:      exit (goal reached)
    for action in buffer:
        if safety.requires_confirm: ask user
        result = executor.run(action)
        new_snapshot = capture(screen)
        append tool_result(result, image=new_snapshot)
    messages.append(assistant_blocks, tool_results)
```

The kill-switch hotkey (`Ctrl+Alt+K` by default) is registered only while a
Mode C loop is running; it sets the same `threading.Event` the loop polls, so
cancellation propagates within one tick.
