# Workflow Schema

Teach-mode produces a JSON document that describes a user's intent step by
step. The selector field is deliberately layered so that replay can degrade
gracefully as the UI changes.

```json
{
  "version": "1.0",
  "name": "Open Excel and apply SUM formula",
  "target_app": "excel.exe",
  "created_at": 1713456789.123,
  "notes": "",
  "steps": [
    {
      "index": 0,
      "action": "window_focus",
      "intent": "Focus the Excel workbook",
      "selector": { "process": "excel.exe", "title_contains": "Book1" },
      "fallback_coord": null,
      "text": null,
      "keys": null,
      "timestamp_ms": 120,
      "metadata": {}
    },
    {
      "index": 1,
      "action": "click",
      "intent": "Click cell B2 to select it",
      "selector": { "a11y_name": "B2", "role": "DataItem" },
      "fallback_coord": [450, 310],
      "timestamp_ms": 850,
      "metadata": { "button": "left" }
    },
    {
      "index": 2,
      "action": "type",
      "intent": "Type a SUM formula",
      "text": "=SUM(A1:A10)",
      "timestamp_ms": 1400,
      "metadata": {}
    },
    {
      "index": 3,
      "action": "key",
      "intent": "Confirm the formula",
      "keys": ["enter"],
      "timestamp_ms": 1600,
      "metadata": {}
    }
  ]
}
```

## Selector resolution order

When the replayer re-plans a step against the live screen, selectors are tried
in the order below. The first match wins.

1. `a11y_name` + `role` — exact accessibility match
2. `automation_id`
3. `ocr_text` (for steps where OCR was captured)
4. `image_hash` of the target region (future extension)
5. `fallback_coord` — literal `[x, y]`, only used when nothing else matches

## Supported actions

| Action | Fields used | Notes |
| ------ | ----------- | ----- |
| `click` | `selector`, `fallback_coord`, `metadata.button` | Button defaults to left |
| `double_click` | same as click |
| `right_click` | same as click |
| `drag` | `selector`, `metadata.end_coord` |
| `type` | `text` |
| `key` | `keys` | List of keys for a hotkey chord |
| `scroll` | `fallback_coord`, `metadata.dx/dy` |
| `window_focus` | `selector.process`, `selector.title_contains` |
| `wait` | `metadata.duration_ms` |

## Replayer contract

The replayer feeds every step's `intent` + `selector` together with a fresh
screenshot to the LLM and expects exactly one `computer_use` action in
response. This means Lucid does not crash when buttons move, themes change, or
resolutions differ, as long as the intent remains visually recognizable.
