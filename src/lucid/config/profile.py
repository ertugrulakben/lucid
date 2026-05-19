"""User profile loader.

Profile is a free-form YAML describing the human behind the keyboard: name,
email, website, frequent folders, pinned apps, signatures, notes. Lucid feeds
these into Execute/Answer prompts so the LLM can act like "your" assistant
without anything being hard-coded into the Python source.

The source of truth is ``<data_dir>/profile.yaml`` (gitignored). If absent,
``profile.example.yaml`` at the project root is used as a read-only fallback,
so a fresh clone still has something meaningful (placeholders).
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger("lucid.profile")


SECRET_HINT = re.compile(r"(?i)\b(password|şifre|sifre|token|secret|api.?key|gizli)\b")


@dataclass
class Profile:
    name: str = ""
    email: str = ""
    website: str = ""
    default_browser: str = "chrome"
    signatures: dict[str, str] = field(default_factory=dict)
    frequent_folders: list[str] = field(default_factory=list)
    pinned_apps: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=lambda: ["tr", "en"])
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, settings) -> Profile:
        candidates = [settings.profile_path, settings.profile_example_path]
        for path in candidates:
            if path and path.exists():
                try:
                    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
                except yaml.YAMLError as exc:
                    log.warning("profile yaml parse error at %s: %s", path, exc)
                    continue
                return cls._from_dict(data)
        return cls._from_dict(cls._auto_detect_defaults())

    @classmethod
    def _from_dict(cls, data: dict[str, Any]) -> Profile:
        return cls(
            name=str(data.get("name", "")).strip(),
            email=str(data.get("email", "")).strip(),
            website=str(data.get("website", "")).strip(),
            default_browser=str(data.get("default_browser", "chrome")).lower(),
            signatures=dict(data.get("signatures") or {}),
            frequent_folders=list(data.get("frequent_folders") or []),
            pinned_apps=list(data.get("pinned_apps") or []),
            notes=list(data.get("notes") or []),
            languages=list(data.get("languages") or ["tr", "en"]),
            raw=data,
        )

    @staticmethod
    def _auto_detect_defaults() -> dict[str, Any]:
        """Best-effort defaults when neither profile.yaml nor example exists."""
        home = Path.home()
        return {
            "name": os.environ.get("USERNAME") or home.name or "User",
            "email": "",
            "website": "",
            "default_browser": "chrome",
            "signatures": {},
            "frequent_folders": [
                str(home / "Desktop"),
                str(home / "Documents"),
                str(home / "Downloads"),
            ],
            "pinned_apps": ["chrome", "notepad"],
            "notes": [],
            "languages": ["tr", "en"],
        }

    def is_complete(self) -> bool:
        """True if the user has customised the profile (not the shipped example)."""
        return bool(self.name and self.email and "@" in self.email)

    def to_prompt_block(self) -> str:
        """Render a short, LLM-friendly context block.

        Redacts any note that mentions a password/token/secret, so the LLM
        doesn't accidentally leak them in its reasoning.
        """
        parts: list[str] = ["User profile:"]
        if self.name:
            parts.append(f"- Name: {self.name}")
        if self.email:
            parts.append(f"- Email: {self.email}")
        if self.website:
            parts.append(f"- Website: {self.website}")
        if self.default_browser:
            parts.append(f"- Preferred browser: {self.default_browser}")
        if self.frequent_folders:
            joined = ", ".join(self.frequent_folders[:6])
            parts.append(f"- Frequent folders: {joined}")
        if self.pinned_apps:
            parts.append(f"- Pinned apps: {', '.join(self.pinned_apps[:8])}")
        if self.languages:
            parts.append(f"- Languages: {', '.join(self.languages)}")
        safe_notes = [n for n in self.notes if not SECRET_HINT.search(n or "")]
        if safe_notes:
            parts.append("- Notes:")
            for note in safe_notes[:6]:
                parts.append(f"    * {note}")
        email_sig = (self.signatures or {}).get("email")
        if email_sig:
            parts.append("- Email signature available (use when drafting mail).")

        # Knowledge sources + assistant chain — these tell the agent WHERE to
        # find extra context, WHO to notify, WHAT external tools exist.
        # Injected so Lucid can act on prompts like "when done, tell my other
        # assistant" or "open VS Code and continue the thread".
        ks = self.raw.get("knowledge_sources") or []
        if ks:
            parts.append("- External knowledge sources (reference only, not auto-opened):")
            for src in ks[:5]:
                if not isinstance(src, dict):
                    continue
                name = src.get("name", "").strip()
                path = src.get("path", "").strip()
                desc = (src.get("description") or "").strip().replace("\n", " ")
                desc = desc[:140] + "…" if len(desc) > 140 else desc
                bits = [f"* {name}"]
                if path:
                    bits.append(f"path={path}")
                if desc:
                    bits.append(desc)
                parts.append("    " + " — ".join(bits))
        chain = self.raw.get("assistant_chain") or {}
        if isinstance(chain, dict) and chain.get("upstream"):
            note = (chain.get("note") or "").strip()
            parts.append(
                f"- Upstream assistant: {chain['upstream']}" + (f" — {note}" if note else "")
            )

        if len(parts) == 1:
            return ""
        return "\n".join(parts)


def ensure_profile_file(settings) -> Path:
    """Make sure ``data/profile.yaml`` exists; seed from example if missing."""
    target = settings.profile_path
    if target.exists():
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    example = settings.profile_example_path
    if example and example.exists():
        target.write_bytes(example.read_bytes())
    else:
        defaults = Profile._auto_detect_defaults()
        target.write_text(
            yaml.safe_dump(defaults, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
    return target


def get_profile(settings) -> Profile:
    return Profile.load(settings)


def set_profile_value(settings, key: str, value: Any) -> None:
    """Update a single top-level key in profile.yaml without rewriting the whole file."""
    path = ensure_profile_file(settings)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    data[key] = value
    path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def pick_profile_snippet(profile: Profile, context_hint: str | None = None) -> str:
    """Return a focused snippet when the full block would be overkill.

    If the prompt is about email, show the email + signature; if about a file
    operation, show frequent folders; otherwise the full block.
    """
    if context_hint:
        hint = context_hint.lower()
        if any(w in hint for w in ["mail", "gmail", "outlook", "e-posta", "eposta"]):
            pieces = []
            if profile.name:
                pieces.append(f"Sender: {profile.name}")
            if profile.email:
                pieces.append(f"From: {profile.email}")
            sig = (profile.signatures or {}).get("email")
            if sig:
                pieces.append(f"Signature:\n{sig}")
            return "\n".join(pieces)
        if any(w in hint for w in ["kaydet", "save", "open", "aç", "dosya", "file"]):
            if profile.frequent_folders:
                return "Frequent folders: " + ", ".join(profile.frequent_folders[:6])
    return profile.to_prompt_block()
