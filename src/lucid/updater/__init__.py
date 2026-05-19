"""Lightweight auto-updater that polls GitHub Releases."""

from __future__ import annotations

from .check import UpdateInfo, check_for_update

__all__ = ["UpdateInfo", "check_for_update"]
