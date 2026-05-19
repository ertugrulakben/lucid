"""Execute Anthropic computer_use actions against the live desktop."""

from __future__ import annotations

import logging
import sys
import time
from typing import Any

from lucid.config.settings import Settings
from lucid.llm.schemas import ActionBlock

log = logging.getLogger("lucid.executor.actions")

import pyautogui  # noqa: E402

try:
    if sys.platform == "win32":
        import pydirectinput
    else:
        pydirectinput = None  # type: ignore[assignment]
except ImportError:
    pydirectinput = None  # type: ignore[assignment]


ANTHROPIC_KEY_MAP = {
    "return": "enter",
    "page_up": "pageup",
    "page_down": "pagedown",
    "prior": "pageup",
    "next": "pagedown",
}


class Actions:
    def __init__(self, settings: Settings, memory_store: Any = None) -> None:
        self.settings = settings
        self.memory_store = memory_store
        pyautogui.FAILSAFE = bool(settings.safety.failsafe)
        pyautogui.PAUSE = float(settings.safety.pause_seconds)

    def run(self, action: ActionBlock) -> str:
        name = action.action
        params = action.params
        log.info("executing action=%s params=%s", name, _summarize_params(params))
        try:
            if name in ("mouse_move", "cursor_position"):
                return self._move(params)
            if name == "left_click":
                return self._click("left", params)
            if name == "right_click":
                return self._click("right", params)
            if name == "middle_click":
                return self._click("middle", params)
            if name == "double_click":
                return self._click("left", params, clicks=2)
            if name == "triple_click":
                return self._click("left", params, clicks=3)
            if name == "left_click_drag":
                return self._drag(params)
            if name == "type":
                return self._type(params)
            if name == "key":
                return self._key(params)
            if name == "hold_key":
                return self._hold_key(params)
            if name == "scroll":
                return self._scroll(params)
            if name == "wait":
                return self._wait(params)
            if name == "screenshot":
                return "ok"
            if name == "focus_window":
                return self._focus_window(params)
            if name == "click_element":
                return self._click_element(params)
            if name == "scroll_into_view":
                return self._scroll_into_view(params)
            if name == "file_dialog_paste":
                return self._file_dialog_paste(params)
            if name == "solve_captcha":
                return self._solve_captcha(params)
            if name == "screenshot_to_clipboard":
                return self._screenshot_to_clipboard(params)
            if name == "run_shell":
                return self._run_shell(params)
            if name == "focus_monitor":
                return self._focus_monitor(params)
            return f"unsupported action: {name}"
        except Exception as exc:
            log.exception("action %s failed", name)
            return f"error: {exc}"

    def _move(self, params: dict[str, Any]) -> str:
        coord = params.get("coordinate")
        if not coord:
            return "error: no coordinate"
        pyautogui.moveTo(int(coord[0]), int(coord[1]), duration=0.1)
        return f"moved to {coord[0]},{coord[1]}"

    def _click(self, button: str, params: dict[str, Any], clicks: int = 1) -> str:
        coord = params.get("coordinate")
        if coord:
            pyautogui.moveTo(int(coord[0]), int(coord[1]), duration=0.05)
        pyautogui.click(button=button, clicks=clicks)
        return f"{button} click{'s' if clicks > 1 else ''} x{clicks}"

    def _drag(self, params: dict[str, Any]) -> str:
        """Mouse-down → waypoint-interpolated move → mouse-up.

        ``pyautogui.dragTo`` works for flat screens but Excel's fill handle,
        Photoshop selections, or Windows Explorer drag-to-attach need the
        mouse to visibly traverse the path so the source application updates
        hover state between waypoints. We interpolate 10 intermediate points
        at ~30ms apart, then release.
        """
        start = params.get("start_coordinate")
        end = params.get("coordinate") or params.get("end_coordinate")
        if not start or not end:
            return "error: drag requires start_coordinate and coordinate"
        sx, sy = int(start[0]), int(start[1])
        ex, ey = int(end[0]), int(end[1])
        pyautogui.moveTo(sx, sy, duration=0.08)
        pyautogui.mouseDown(button="left")
        try:
            steps = 10
            for i in range(1, steps + 1):
                t = i / steps
                x = int(sx + (ex - sx) * t)
                y = int(sy + (ey - sy) * t)
                pyautogui.moveTo(x, y, duration=0)
                time.sleep(0.03)
        finally:
            pyautogui.moveTo(ex, ey, duration=0)
            pyautogui.mouseUp(button="left")
        return f"dragged {sx},{sy} -> {ex},{ey} ({10} waypoints)"

    def _type(self, params: dict[str, Any]) -> str:
        """Insert text via clipboard paste.

        Typing through scan codes is brittle across keyboard layouts: on a
        Turkish layout pyautogui/pydirectinput deliver the wrong characters
        for punctuation (``/`` → ``.``, ``:`` → ``ç``, etc.) because the scan
        codes are resolved against the active layout. Clipboard paste
        sidesteps the layout entirely: we put the text on the clipboard and
        issue Ctrl+V, which the OS inserts verbatim regardless of language.

        Falls back to a slow per-character type only if the clipboard path
        fails (e.g. inside password fields that block paste).
        """
        text = params.get("text", "")
        if not text:
            return "error: no text"
        try:
            import pyperclip  # type: ignore[import-not-found]
        except ImportError:
            pyperclip = None  # type: ignore[assignment]

        if pyperclip is not None:
            saved: str | None = None
            try:
                saved = pyperclip.paste()
            except Exception:
                saved = None
            try:
                pyperclip.copy(text)
                time.sleep(0.05)
                pyautogui.hotkey("ctrl", "v")
                time.sleep(0.05)
                return f"pasted {len(text)} chars"
            except Exception as exc:
                log.warning("clipboard paste failed, falling back to typewrite: %s", exc)
            finally:
                if saved is not None:
                    try:
                        pyperclip.copy(saved)
                    except Exception:
                        pass

        pyautogui.typewrite(text, interval=0.01)
        return f"typed {len(text)} chars (fallback)"

    def _key(self, params: dict[str, Any]) -> str:
        keys = params.get("keys") or [params.get("text", "")]
        translated = [ANTHROPIC_KEY_MAP.get(k.lower(), k.lower()) for k in keys if k]
        if not translated:
            return "error: no keys"
        if len(translated) == 1:
            pyautogui.press(translated[0])
            return f"key {translated[0]}"
        # Task switcher combos (alt+tab, win+tab) need the modifier held
        # across a short delay. pyautogui.hotkey fires too fast for the
        # Windows switcher to react.
        needs_hold = any(k in translated for k in ("alt", "win", "winleft", "winright"))
        if needs_hold and "tab" in translated:
            modifiers = [k for k in translated if k != "tab"]
            for m in modifiers:
                pyautogui.keyDown(m)
            try:
                pyautogui.press("tab")
                time.sleep(0.25)
            finally:
                for m in reversed(modifiers):
                    pyautogui.keyUp(m)
            return f"key {'+'.join(translated)} (held)"
        pyautogui.hotkey(*translated)
        return f"key {'+'.join(translated)}"

    def _hold_key(self, params: dict[str, Any]) -> str:
        keys = params.get("keys") or []
        duration_ms = int(params.get("duration_ms", 200))
        for key in keys:
            pyautogui.keyDown(ANTHROPIC_KEY_MAP.get(key.lower(), key.lower()))
        time.sleep(duration_ms / 1000)
        for key in reversed(keys):
            pyautogui.keyUp(ANTHROPIC_KEY_MAP.get(key.lower(), key.lower()))
        return f"held {keys} for {duration_ms}ms"

    def _scroll(self, params: dict[str, Any]) -> str:
        direction = (params.get("scroll_direction") or "down").lower()
        amount = int(params.get("scroll_amount", 3))
        coord = params.get("coordinate")
        if coord:
            pyautogui.moveTo(int(coord[0]), int(coord[1]), duration=0.05)
        delta = amount if direction == "up" else -amount
        pyautogui.scroll(delta)
        return f"scrolled {direction} x{amount}"

    def _wait(self, params: dict[str, Any]) -> str:
        duration_ms = int(params.get("duration_ms", 500))
        time.sleep(duration_ms / 1000)
        return f"waited {duration_ms}ms"

    def _focus_window(self, params: dict[str, Any]) -> str:
        """Bring a window with a matching title substring to the foreground.

        Far more reliable than Alt+Tab: walks visible top-level windows and
        calls ``ShowWindow + SetForegroundWindow`` via Win32 directly.
        """
        needle = (params.get("window_title") or params.get("text") or "").strip().lower()
        if not needle:
            return "error: no window_title"
        try:
            import win32con  # type: ignore[import-not-found]
            import win32gui  # type: ignore[import-not-found]
        except ImportError:
            return "error: win32 unavailable"

        match = {"hwnd": 0, "title": ""}

        def _enum(hwnd: int, _extra: Any) -> bool:
            if not win32gui.IsWindowVisible(hwnd):
                return True
            title = win32gui.GetWindowText(hwnd) or ""
            if needle in title.lower():
                if not match["hwnd"] or len(title) < len(match["title"] or ""):
                    match["hwnd"] = hwnd
                    match["title"] = title
            return True

        win32gui.EnumWindows(_enum, None)
        if not match["hwnd"]:
            return f"no window matching {needle!r}"
        try:
            win32gui.ShowWindow(match["hwnd"], win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(match["hwnd"])
        except Exception as exc:
            return f"focus failed: {exc}"
        time.sleep(0.2)
        return f"focused: {match['title']}"

    def _click_element(self, params: dict[str, Any]) -> str:
        """Click a UI element by its accessibility name (pixel-free).

        This is the most reliable way to hit a button: we walk the live
        accessibility tree from the foreground window, find the first
        element whose name matches the requested substring (case-insensitive),
        optionally filter by role, and click the centre of its bounding
        rectangle. No guessing, no screenshot math.
        """
        name = (params.get("element_name") or params.get("name") or "").strip().lower()
        role_filter = (params.get("element_role") or params.get("role") or "").strip().lower()
        clicks = int(params.get("clicks", 1))
        button = str(params.get("button", "left")).lower()

        if not name:
            return "error: no element_name"

        try:
            if sys.platform != "win32":
                return "error: click_element requires Windows"
            import uiautomation as auto  # type: ignore[import-not-found]
        except ImportError:
            return "error: uiautomation not available"

        try:
            root = auto.GetFocusedControl() or auto.GetRootControl()
        except Exception as exc:
            return f"error: a11y root failed: {exc}"

        match: dict[str, Any] = {"node": None, "name": ""}

        def walk(node: Any, depth: int = 0) -> None:
            if match["node"] is not None or depth > 6:
                return
            try:
                node_name = (getattr(node, "Name", "") or "").strip()
                node_role = (getattr(node, "ControlTypeName", "") or "").strip().lower()
                if node_name and name in node_name.lower():
                    if not role_filter or role_filter in node_role:
                        rect = getattr(node, "BoundingRectangle", None)
                        if rect and rect.right > rect.left and rect.bottom > rect.top:
                            match["node"] = node
                            match["name"] = node_name
                            return
                for child in node.GetChildren() or []:
                    if match["node"] is not None:
                        return
                    walk(child, depth + 1)
            except Exception:
                return

        try:
            walk(root)
            if match["node"] is None:
                top = auto.GetRootControl()
                if top is not root:
                    walk(top)
        except Exception as exc:
            return f"error: a11y walk failed: {exc}"

        if match["node"] is None:
            return f"no element matching name={name!r}"

        rect = match["node"].BoundingRectangle
        cx = (rect.left + rect.right) // 2
        cy = (rect.top + rect.bottom) // 2
        pyautogui.moveTo(cx, cy, duration=0.05)
        pyautogui.click(button=button, clicks=clicks)
        return f"clicked {match['name']!r} at {cx},{cy}"

    def _scroll_into_view(self, params: dict[str, Any]) -> str:
        """Scroll until a named element is within the visible area, then stop.

        We locate the element via UI Automation and, if its bounding rect
        lies outside the foreground window's client area, scroll in the
        appropriate direction at the window centre. Small sleep between
        scrolls lets animations catch up.
        """
        name = (params.get("element_name") or params.get("name") or "").strip().lower()
        if not name:
            return "error: no element_name"
        if sys.platform != "win32":
            return "error: scroll_into_view requires Windows"
        try:
            import uiautomation as auto  # type: ignore[import-not-found]
            import win32gui  # type: ignore[import-not-found]
        except ImportError:
            return "error: uiautomation/win32 unavailable"

        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return "error: no foreground window"
        try:
            win_rect = win32gui.GetWindowRect(hwnd)
        except Exception as exc:
            return f"error: GetWindowRect: {exc}"
        wcx = (win_rect[0] + win_rect[2]) // 2
        wcy = (win_rect[1] + win_rect[3]) // 2

        def _find() -> Any:
            root = auto.ControlFromHandle(hwnd)
            holder: dict[str, Any] = {"node": None}

            def walk(node: Any, depth: int = 0) -> None:
                if holder["node"] is not None or depth > 8:
                    return
                try:
                    if name in (getattr(node, "Name", "") or "").lower():
                        holder["node"] = node
                        return
                    for child in node.GetChildren() or []:
                        if holder["node"] is not None:
                            return
                        walk(child, depth + 1)
                except Exception:
                    return

            if root is not None:
                walk(root)
            return holder["node"]

        for _ in range(20):
            node = _find()
            if node is None:
                return f"no element matching name={name!r}"
            try:
                r = node.BoundingRectangle
                if r and r.top >= win_rect[1] and r.bottom <= win_rect[3]:
                    return f"already in view: {name}"
                direction = "down" if (r.top > win_rect[3]) else "up"
            except Exception:
                direction = "down"
            pyautogui.moveTo(wcx, wcy, duration=0.03)
            pyautogui.scroll(-3 if direction == "down" else 3)
            time.sleep(0.15)
        return f"scrolled {name!r} into approximate view"

    def _file_dialog_paste(self, params: dict[str, Any]) -> str:
        """Paste an absolute path into the active File Open/Save dialog."""
        path = params.get("file_path") or params.get("text") or ""
        submit = bool(params.get("submit", True))
        from lucid.executor.file_dialog import navigate_file_dialog

        return navigate_file_dialog(str(path), submit=submit)

    def _solve_captcha(self, params: dict[str, Any]) -> str:
        """Explicit captcha solver call requested by the LLM.

        Usually the Execute loop handles captchas automatically after it
        detects them, but the LLM can also emit ``solve_captcha`` directly
        when it's confident about what it sees. We re-walk the current
        foreground window's accessibility tree to find a captcha element
        and delegate to ``CaptchaSolver``.
        """
        if self.memory_store is None:
            return "error: captcha solver needs memory store (not initialised)"
        try:
            from lucid.capture.a11y import capture_a11y_tree
            from lucid.safety.captcha import CaptchaSolver, detect_captcha
        except ImportError as exc:
            return f"error: captcha deps missing: {exc}"

        tree = capture_a11y_tree()
        detection = detect_captcha(tree)
        if detection is None:
            return "no captcha detected on screen"

        # Provider is resolved via a lightweight import to avoid a circular dep.
        try:
            from lucid.llm.provider import create_provider

            provider = create_provider(self.settings)
        except Exception as exc:
            return f"error: provider init: {exc}"
        solver = CaptchaSolver(self.settings, self.memory_store, provider, self)
        return solver.solve(detection)

    def _focus_monitor(self, params: dict[str, Any]) -> str:
        """Move the mouse cursor to the centre of a specific physical monitor.

        The next ``ContextSnapshot`` will grab that monitor automatically,
        because the grabber selects the display containing the cursor. This
        is how the LLM satisfies prompts like "do X on the right monitor" /
        "go to the left screen and open Chrome": first ``focus_monitor``,
        then continue the task as usual.

        params:
          index:    int — mss monitor index (1..N); preferred
          position: str — alternative semantic hint: 'primary' | 'left' |
                    'right' | 'above' | 'below'. Resolved against the list
                    returned by ContextSnapshot._enumerate_monitors.
        """
        try:
            import mss
        except ImportError as exc:
            return f"error: mss missing: {exc}"

        target_index = params.get("index")
        position = (params.get("position") or "").strip().lower()

        try:
            with mss.mss() as sct:
                mons = sct.monitors
                if len(mons) <= 1:
                    return "only one monitor present; no switching to do"

                # Index path
                if target_index is not None:
                    try:
                        idx = int(target_index)
                    except (TypeError, ValueError):
                        return f"error: 'index' must be an integer, got {target_index!r}"
                    if not (1 <= idx < len(mons)):
                        return (
                            f"error: monitor index {idx} out of range "
                            f"(valid: 1..{len(mons) - 1})"
                        )
                    mon = mons[idx]
                else:
                    # Position path — resolve relative to the primary monitor
                    picks: list[tuple[int, dict]] = []
                    for i, m in enumerate(mons[1:], start=1):
                        left = int(m.get("left", 0))
                        if position == "primary" and left == 0 and int(m.get("top", 0)) == 0:
                            return _move_to_monitor_centre(m, i)
                        picks.append((left, dict(m, _idx=i)))
                    if not position:
                        return (
                            "error: focus_monitor needs either `index` "
                            "or `position` (primary|left|right|above|below)"
                        )
                    if position == "left":
                        pick = min(picks, key=lambda t: t[0])
                    elif position == "right":
                        pick = max(picks, key=lambda t: t[0])
                    elif position in ("above", "top"):
                        pick = min(picks, key=lambda t: int(t[1].get("top", 0)))
                    elif position in ("below", "bottom"):
                        pick = max(picks, key=lambda t: int(t[1].get("top", 0)))
                    else:
                        return f"error: unknown position {position!r}"
                    mon = pick[1]
                    idx = mon["_idx"]

                return _move_to_monitor_centre(mon, idx)
        except Exception as exc:
            return f"error: focus_monitor failed: {exc}"

    def _screenshot_to_clipboard(self, params: dict[str, Any]) -> str:
        """Capture the screen (or a specific monitor) and place the PNG
        bytes on the Windows clipboard in DIB + PNG formats.

        Replaces the brittle ``PrintScreen`` / ``Win+Shift+S`` pattern with
        a deterministic native capture. The pasted image ends up in any
        program that accepts a clipboard image: Photoshop, Word, Outlook,
        Paint, chat apps, etc.

        params:
          monitor: int (default 0 = all monitors). 1..N = specific screen.
          region:  [x, y, w, h] pixels — optional sub-rect crop
        """
        try:
            import io

            import mss
            from PIL import Image
        except ImportError as exc:
            return f"error: screenshot deps missing: {exc}"

        monitor_idx = int(params.get("monitor", 0) or 0)
        region = params.get("region")

        try:
            with mss.mss() as sct:
                if monitor_idx <= 0:
                    mon = sct.monitors[0]  # all monitors
                else:
                    if monitor_idx >= len(sct.monitors):
                        return (
                            f"error: monitor {monitor_idx} out of range "
                            f"(have {len(sct.monitors) - 1})"
                        )
                    mon = sct.monitors[monitor_idx]
                shot = sct.grab(mon)
                img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        except Exception as exc:
            return f"error: capture failed: {exc}"

        if region and isinstance(region, (list, tuple)) and len(region) == 4:
            try:
                x, y, w, h = (int(v) for v in region)
                img = img.crop((x, y, x + w, y + h))
            except Exception as exc:
                log.warning("region crop failed: %s", exc)

        # Encode to PNG + to DIB (BMP without header) for clipboard.
        png_buf = io.BytesIO()
        img.save(png_buf, format="PNG")

        if sys.platform == "win32":
            try:
                import win32clipboard

                bmp_buf = io.BytesIO()
                img.convert("RGB").save(bmp_buf, format="BMP")
                # BMP header is the first 14 bytes; DIB excludes them.
                dib = bmp_buf.getvalue()[14:]
                win32clipboard.OpenClipboard()
                try:
                    win32clipboard.EmptyClipboard()
                    win32clipboard.SetClipboardData(win32clipboard.CF_DIB, dib)
                finally:
                    win32clipboard.CloseClipboard()
            except Exception as exc:
                return f"error: clipboard write failed: {exc}"
        else:
            return "error: screenshot_to_clipboard only supported on Windows"

        w, h = img.size
        return f"screenshot captured {w}×{h} → clipboard (monitor={monitor_idx})"

    def _run_shell(self, params: dict[str, Any]) -> str:
        """Run a short read-only shell command and return its stdout.

        Intended for information-gathering ('does this file exist', 'what
        processes are running'), NOT mutation. The safety layer denies any
        command that smells destructive; time is hard-capped to 10 s.

        params:
          command: str — the literal command (e.g. 'dir E:\\locker')
          shell:   'cmd' | 'powershell' | 'bash' (default: cmd on Windows)
          timeout: int seconds (default 10, max 30)
        """
        import subprocess

        command = (params.get("command") or "").strip()
        if not command:
            return "error: run_shell requires a 'command' string"
        shell = (params.get("shell") or ("cmd" if sys.platform == "win32" else "bash")).lower()
        timeout = min(30, max(1, int(params.get("timeout") or 10)))

        # Deny-list for obvious destructive patterns. Defensive only; Lucid's
        # upstream destructive-modal also intercepts. We fail closed here.
        lower = command.lower()
        deny_tokens = (
            " rm ",
            " rmdir ",
            " del ",
            " remove-item",
            "format ",
            " shutdown",
            " reboot",
            " diskpart",
            "reg delete",
            "cipher /w",
            "takeown ",
            "icacls ",
            " sc delete",
            "wmic ",
            ">",
            ">>",  # no stdout redirection (side effect)
        )
        padded = " " + lower + " "
        for tok in deny_tokens:
            if tok in padded:
                return (
                    f"error: run_shell refused — looks destructive "
                    f"(matched token {tok!r}). Use read-only commands only."
                )

        if shell == "powershell":
            argv = ["powershell.exe", "-NoProfile", "-Command", command]
        elif shell == "bash":
            argv = ["bash", "-lc", command]
        else:
            argv = ["cmd.exe", "/c", command]

        try:
            proc = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=timeout,
                errors="replace",
            )
        except subprocess.TimeoutExpired:
            return f"error: run_shell timed out after {timeout}s"
        except Exception as exc:
            return f"error: run_shell failed: {exc}"

        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        if len(out) > 4000:
            out = out[:4000] + f"\n… (truncated {len(out) - 4000} more chars)"
        if len(err) > 1000:
            err = err[:1000] + "\n… (truncated)"
        pieces = [f"exit={proc.returncode}"]
        if out:
            pieces.append("stdout:\n" + out)
        if err:
            pieces.append("stderr:\n" + err)
        return "\n".join(pieces)


def _move_to_monitor_centre(mon: dict, idx: int) -> str:
    """Jump the mouse cursor to the centre of the given mss monitor entry.

    Used by ``focus_monitor`` to switch which display the next snapshot
    captures. The grabber selects whichever monitor contains the cursor."""
    left = int(mon.get("left", 0))
    top = int(mon.get("top", 0))
    width = int(mon.get("width", 0))
    height = int(mon.get("height", 0))
    cx = left + width // 2
    cy = top + height // 2
    pyautogui.moveTo(cx, cy, duration=0.05)
    return f"cursor moved to monitor #{idx} centre ({cx}, {cy})"


def _summarize_params(params: dict[str, Any]) -> dict[str, Any]:
    out = dict(params)
    if "text" in out and isinstance(out["text"], str) and len(out["text"]) > 40:
        out["text"] = out["text"][:40] + "…"
    return out
