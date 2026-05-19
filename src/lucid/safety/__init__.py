"""Safety subsystem: captcha solving, destructive action guards, kill switch bridge."""

from lucid.safety.captcha import CaptchaSolver, detect_captcha

__all__ = ["CaptchaSolver", "detect_captcha"]
