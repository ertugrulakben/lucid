"""Load + expand the ship-in template JSON files."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class TemplateError(ValueError):
    """Raised when a template is missing, malformed, or called with bad vars."""


@dataclass
class TemplateSpec:
    name: str
    description: str
    prompt: str
    defaults: dict[str, Any] = field(default_factory=dict)
    required_vars: list[str] = field(default_factory=list)


def _templates_dir() -> Path:
    return Path(__file__).parent


def list_templates() -> list[TemplateSpec]:
    specs: list[TemplateSpec] = []
    for path in sorted(_templates_dir().glob("*.json")):
        try:
            specs.append(load_template(path.stem))
        except TemplateError:
            continue
    return specs


def load_template(name: str) -> TemplateSpec:
    path = _templates_dir() / f"{name}.json"
    if not path.exists():
        raise TemplateError(f"template not found: {name}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise TemplateError(f"template {name!r} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict) or "prompt" not in data:
        raise TemplateError(f"template {name!r} is missing the 'prompt' field")
    return TemplateSpec(
        name=str(data.get("name", name)),
        description=str(data.get("description", "")),
        prompt=str(data["prompt"]),
        defaults=dict(data.get("defaults") or {}),
        required_vars=list(data.get("required") or []),
    )


_VAR_PATTERN = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


def expand_template(name: str, variables: dict[str, Any]) -> str:
    """Return the template's prompt with ``{{var}}`` placeholders substituted."""
    spec = load_template(name)
    merged = dict(spec.defaults)
    merged.update({k: v for k, v in variables.items() if v is not None})

    missing = [k for k in spec.required_vars if not merged.get(k)]
    if missing:
        raise TemplateError(f"template {name!r} missing required var(s): {', '.join(missing)}")

    def _sub(match: re.Match) -> str:
        key = match.group(1)
        return str(merged.get(key, ""))

    return _VAR_PATTERN.sub(_sub, spec.prompt).strip()
