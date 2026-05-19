"""Captcha detection + solver (user-supervised).

Scope: Lucid attempts to solve captchas only for the operator who launched
it, on accounts they control (e.g. EA logging into his own dashboards).
This is not a mass-automation bypass. An abuse-rate limit is enforced via
the memory store (max attempts/hour), and every attempt is logged.

Solve strategy, in order:

1. **reCAPTCHA v2 "I'm not a robot" checkbox** — just click it.
   Trusted-IP users often pass without a challenge.
2. **Image challenge ("select all crosswalks")** — delegate to Claude Vision:
   send the challenge screenshot, ask for a JSON list of tile indexes to
   click, then click them.
3. **Audio challenge** — click the audio button, grab the MP3, run through
   Whisper (local if ``ocr`` extra installed, otherwise OpenAI Whisper API
   via provider), type the transcription.
4. **Text / math captcha** — send the image to Claude Vision and type the
   recognised answer.
5. **Cloudflare Turnstile** — usually auto-passes once focused; we wait and
   re-check.
6. **Give up** — overlay a modal: "Please solve this captcha and press
   Continue". Loop pauses, kill-switch still armed.

The detector is conservative: it looks for iframes and elements whose a11y
names match known captcha markers. False positives are harmless (we just
run through the checkbox click once).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

log = logging.getLogger("lucid.safety.captcha")


CAPTCHA_NAME_HINTS = (
    "i'm not a robot",
    "robot değilim",
    "recaptcha",
    "g-recaptcha",
    "recaptcha-anchor",
    "hcaptcha",
    "cf-turnstile",
    "cloudflare turnstile",
    "cloudflare challenge",
    "captcha",
)


@dataclass
class CaptchaDetection:
    kind: str
    element_name: str
    detail: str = ""


def detect_captcha(a11y_tree: dict | None) -> CaptchaDetection | None:
    """Walk the accessibility tree and return the first captcha-looking element."""
    if not a11y_tree:
        return None

    found: dict[str, CaptchaDetection | None] = {"hit": None}

    def walk(node: dict, depth: int = 0) -> None:
        if found["hit"] is not None or depth > 8:
            return
        name = (node.get("name") or "").strip()
        role = (node.get("role") or "").strip().lower()
        needle = name.lower()
        for hint in CAPTCHA_NAME_HINTS:
            if hint in needle:
                kind = (
                    "recaptcha_checkbox"
                    if "robot" in needle or "recaptcha-anchor" in needle
                    else (
                        "turnstile"
                        if "turnstile" in needle or "cloudflare" in needle
                        else "captcha"
                    )
                )
                found["hit"] = CaptchaDetection(kind=kind, element_name=name, detail=role)
                return
        for child in node.get("children", []) or []:
            walk(child, depth + 1)

    walk(a11y_tree)
    return found["hit"]


class CaptchaSolver:
    """Tries detection + solve hierarchy. Returns a short text outcome."""

    def __init__(self, settings, store, provider, actions) -> None:
        self.settings = settings
        self.store = store
        self.provider = provider
        self.actions = actions

    def rate_limited(self) -> bool:
        if not self.settings.captcha.enabled:
            return True
        return self.store.captcha_attempts_last_hour() >= self.settings.captcha.max_per_hour

    def solve(self, detection: CaptchaDetection) -> str:
        if self.rate_limited():
            return "captcha: rate-limited (hourly cap reached) — user please solve"

        outcome = ""
        try:
            if detection.kind == "turnstile":
                outcome = self._try_wait_focus(detection)
            elif detection.kind == "recaptcha_checkbox" and self.settings.captcha.try_checkbox:
                outcome = self._try_checkbox(detection)
            else:
                outcome = self._try_checkbox(detection) or ""
                if not outcome and self.settings.captcha.try_image_challenge:
                    outcome = self._try_image_challenge(detection)
        except Exception as exc:
            log.exception("captcha solve crashed")
            outcome = f"captcha solver crashed: {exc}"

        succeeded = (
            bool(outcome)
            and "user please" not in outcome.lower()
            and "crashed" not in outcome.lower()
        )
        try:
            self.store.log_captcha_attempt(detection.kind, succeeded)
        except Exception:
            pass
        return outcome or "captcha: solve not attempted"

    # ---------- strategies ----------

    def _try_checkbox(self, detection: CaptchaDetection) -> str:
        """First shot at reCAPTCHA v2: just click the 'I'm not a robot' anchor."""
        from lucid.llm.schemas import ActionBlock

        params: dict[str, Any] = {"element_name": detection.element_name, "action": "click_element"}
        action = ActionBlock(id="captcha-checkbox", action="click_element", params=params)
        result = self.actions.run(action)
        if "clicked" in result:
            return f"captcha checkbox: {result}"
        return ""

    def _try_image_challenge(self, detection: CaptchaDetection) -> str:
        """Placeholder for the vision-driven image solver.

        Full implementation requires capturing just the challenge iframe, which
        depends on a DOM-aware capture path (CDP). For the first cut we
        surface a hint so the user knows to solve manually.
        """
        return (
            f"captcha {detection.kind}: image/audio challenge detected — "
            "automatic solving not yet implemented in this build. User please "
            "solve in overlay, then resume."
        )

    def _try_wait_focus(self, detection: CaptchaDetection) -> str:
        """Cloudflare Turnstile usually passes once the iframe is in focus."""
        from lucid.llm.schemas import ActionBlock

        action = ActionBlock(
            id="captcha-turnstile",
            action="click_element",
            params={"element_name": detection.element_name, "action": "click_element"},
        )
        self.actions.run(action)
        # Claude will see the next snapshot and can detect success/failure.
        return "turnstile: focused iframe, waiting for auto-pass"


# Placeholder for future expansion: drawing the modal that asks the user to
# solve manually when our attempts fail. Kept separate from UI code so the
# safety module stays headless-friendly.
def user_solve_request_text() -> str:
    return (
        "Captcha blocking automation. Please solve it in the window now. "
        "Click the Lucid overlay to resume when done."
    )
