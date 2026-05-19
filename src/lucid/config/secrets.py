"""Secret storage via the OS keyring.

We never persist API keys to disk in plaintext. The fallback is an environment
variable (`LUCID_ANTHROPIC_API_KEY`), used primarily in CI.
"""

from __future__ import annotations

import getpass
import logging
import os

import keyring

log = logging.getLogger("lucid.config.secrets")

SERVICE = "lucid"
ANTHROPIC_KEY = "anthropic_api_key"
ENV_FALLBACK = {
    "anthropic_api_key": "LUCID_ANTHROPIC_API_KEY",
}


def get_secret(name: str) -> str | None:
    try:
        value = keyring.get_password(SERVICE, name)
        if value:
            return value
    except keyring.errors.KeyringError as exc:
        log.warning("keyring read failed for %s: %s", name, exc)
    env_var = ENV_FALLBACK.get(name)
    if env_var:
        return os.environ.get(env_var)
    return None


def set_secret(name: str, value: str) -> None:
    keyring.set_password(SERVICE, name, value)


def delete_secret(name: str) -> None:
    try:
        keyring.delete_password(SERVICE, name)
    except keyring.errors.PasswordDeleteError:
        pass


def run_setup_wizard() -> int:
    print("Lucid setup — configure API keys.\n")
    existing = get_secret(ANTHROPIC_KEY)
    if existing:
        masked = existing[:6] + "..." + existing[-4:] if len(existing) > 10 else "***"
        print(f"Anthropic key already set ({masked}).")
        choice = input("Replace? [y/N]: ").strip().lower()
        if choice != "y":
            print("Keeping existing key.")
            return 0
    key = getpass.getpass("Anthropic API key: ").strip()
    if not key:
        print("No key entered, aborting.")
        return 1
    set_secret(ANTHROPIC_KEY, key)
    print("Saved to OS keyring.")
    return 0
