"""Workflow data model and JSON persistence.

A ``Workflow`` represents a named, replay-able desktop task: the user
teaches it once, Lucid records semantic steps, and later the same task is
re-executed by slug (``fatura_kes``) with variables filled in
(``musteri="Ahmet Emre"``).

Schema v1.1 adds the named-task fields (``slug``, ``aliases``,
``variables``, ``tags``). Files written with v1.0 still load cleanly.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.1"


@dataclass
class WorkflowStep:
    index: int
    action: str
    intent: str = ""
    selector: dict[str, Any] = field(default_factory=dict)
    fallback_coord: list[int] | None = None
    text: str | None = None
    keys: list[str] | None = None
    timestamp_ms: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowVariable:
    """A placeholder the user fills in at replay time."""

    name: str
    description: str = ""
    example: str = ""
    required: bool = True


@dataclass
class Workflow:
    name: str
    target_app: str = ""
    steps: list[WorkflowStep] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    version: str = SCHEMA_VERSION
    notes: str = ""
    slug: str = ""
    aliases: list[str] = field(default_factory=list)
    variables: list[WorkflowVariable] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    def append(self, step: WorkflowStep) -> None:
        step.index = len(self.steps)
        self.steps.append(step)

    def ensure_slug(self) -> str:
        """Populate ``slug`` from ``name`` if empty; always returns the slug."""
        if not self.slug:
            self.slug = slugify(self.name) or f"workflow-{int(self.created_at)}"
        return self.slug

    def all_handles(self) -> list[str]:
        """Every string a user might type to trigger this workflow."""
        handles: list[str] = []
        if self.slug:
            handles.append(self.slug)
        if self.name:
            handles.append(self.name)
        handles.extend(self.aliases)
        seen: set[str] = set()
        unique: list[str] = []
        for handle in handles:
            key = (handle or "").strip().lower()
            if key and key not in seen:
                seen.add(key)
                unique.append(handle)
        return unique

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "name": self.name,
            "slug": self.slug,
            "aliases": list(self.aliases),
            "variables": [asdict(v) for v in self.variables],
            "tags": list(self.tags),
            "target_app": self.target_app,
            "created_at": self.created_at,
            "notes": self.notes,
            "steps": [asdict(s) for s in self.steps],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def save(self, directory: Path) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        self.ensure_slug()
        stem = self.slug
        path = directory / f"{stem}.json"
        counter = 1
        while path.exists():
            path = directory / f"{stem}-{counter}.json"
            counter += 1
        path.write_text(self.to_json(), encoding="utf-8")
        return path


def load_workflow(path: Path) -> Workflow:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    steps_raw = data.get("steps", [])
    steps = [WorkflowStep(**s) for s in steps_raw]
    variables_raw = data.get("variables") or []
    variables = [
        WorkflowVariable(
            name=str(v.get("name", "")),
            description=str(v.get("description", "")),
            example=str(v.get("example", "")),
            required=bool(v.get("required", True)),
        )
        for v in variables_raw
        if isinstance(v, dict) and v.get("name")
    ]
    return Workflow(
        name=data.get("name", "workflow"),
        target_app=data.get("target_app", ""),
        created_at=data.get("created_at", time.time()),
        version=data.get("version", SCHEMA_VERSION),
        notes=data.get("notes", ""),
        steps=steps,
        slug=str(data.get("slug", "")),
        aliases=list(data.get("aliases") or []),
        variables=variables,
        tags=list(data.get("tags") or []),
    )


def slugify(name: str) -> str:
    """ASCII-safe slug: lowercase, non-alphanum → ``_``, Turkish letters preserved as closest ASCII."""
    translit = str.maketrans(
        {
            "ç": "c",
            "Ç": "c",
            "ğ": "g",
            "Ğ": "g",
            "ı": "i",
            "I": "i",
            "İ": "i",
            "ö": "o",
            "Ö": "o",
            "ş": "s",
            "Ş": "s",
            "ü": "u",
            "Ü": "u",
        }
    )
    lowered = (name or "").strip().translate(translit).lower()
    cleaned = re.sub(r"[^a-z0-9]+", "_", lowered).strip("_")
    return cleaned[:60]


def _safe_filename(name: str) -> str:
    """Legacy helper kept for back-compat with older callers."""
    return slugify(name) or re.sub(r"[^\w\- ]+", "", name).strip().replace(" ", "_")[:60]
