"""Named-workflow registry.

Flat JSON index of every recorded workflow so ``lucid run fatura_kes`` can
locate the right file without the user remembering paths. Stored alongside
the workflow files themselves at ``data/workflows/_registry.json``.

Schema::

    {
      "entries": [
        {
          "slug": "create_invoice",
          "name": "Create a new invoice",
          "aliases": ["create invoice", "new invoice", "bill"],
          "path": "create_invoice.json",
          "target_app": "accounting.exe",
          "variables": [
              {"name": "customer", "description": "Customer name", "example": "Acme Inc.", "required": true}
          ],
          "tags": ["finance", "daily"],
          "created_at": 1713500000.0,
          "updated_at": 1713500000.0
        }
      ]
    }

Lookup is intentionally simple: exact slug wins, then case-insensitive alias
hit, then whole-word substring search on name+aliases. Anything fancier
(embeddings) lives in future work — this covers 99% of real prompts.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from lucid.recorder.workflow import Workflow, WorkflowVariable, slugify

REGISTRY_FILENAME = "_registry.json"


@dataclass
class WorkflowEntry:
    slug: str
    name: str
    path: str
    aliases: list[str] = field(default_factory=list)
    target_app: str = ""
    variables: list[WorkflowVariable] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    created_at: float = 0.0
    updated_at: float = 0.0

    def to_dict(self) -> dict:
        return {
            "slug": self.slug,
            "name": self.name,
            "path": self.path,
            "aliases": list(self.aliases),
            "target_app": self.target_app,
            "variables": [asdict(v) for v in self.variables],
            "tags": list(self.tags),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> WorkflowEntry:
        variables_raw = data.get("variables") or []
        return cls(
            slug=str(data.get("slug", "")),
            name=str(data.get("name", "")),
            path=str(data.get("path", "")),
            aliases=list(data.get("aliases") or []),
            target_app=str(data.get("target_app", "")),
            variables=[
                WorkflowVariable(
                    name=str(v.get("name", "")),
                    description=str(v.get("description", "")),
                    example=str(v.get("example", "")),
                    required=bool(v.get("required", True)),
                )
                for v in variables_raw
                if isinstance(v, dict) and v.get("name")
            ],
            tags=list(data.get("tags") or []),
            created_at=float(data.get("created_at", 0.0)),
            updated_at=float(data.get("updated_at", 0.0)),
        )

    def all_handles(self) -> list[str]:
        return [self.slug, self.name, *self.aliases]


class WorkflowRegistry:
    def __init__(self, workflows_dir: Path) -> None:
        self.workflows_dir = Path(workflows_dir)
        self.workflows_dir.mkdir(parents=True, exist_ok=True)
        self._path = self.workflows_dir / REGISTRY_FILENAME

    # ---------- persistence ----------

    def _load(self) -> list[WorkflowEntry]:
        if not self._path.exists():
            return []
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
        raw = data.get("entries") if isinstance(data, dict) else None
        if not isinstance(raw, list):
            return []
        return [WorkflowEntry.from_dict(entry) for entry in raw if isinstance(entry, dict)]

    def _save(self, entries: list[WorkflowEntry]) -> None:
        payload = {"entries": [e.to_dict() for e in entries]}
        self._path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    # ---------- operations ----------

    def list_all(self) -> list[WorkflowEntry]:
        return self._load()

    def add(
        self, workflow: Workflow, path: Path, aliases: list[str] | None = None
    ) -> WorkflowEntry:
        workflow.ensure_slug()
        entries = self._load()
        entry = self._entry_for_slug(entries, workflow.slug)
        now = time.time()
        merged_aliases = _unique_case_insensitive([*(aliases or []), *workflow.aliases])
        rel = path.name if path.parent == self.workflows_dir else str(path)
        if entry is None:
            entry = WorkflowEntry(
                slug=workflow.slug,
                name=workflow.name,
                path=rel,
                aliases=merged_aliases,
                target_app=workflow.target_app,
                variables=list(workflow.variables),
                tags=list(workflow.tags),
                created_at=workflow.created_at or now,
                updated_at=now,
            )
            entries.append(entry)
        else:
            entry.name = workflow.name or entry.name
            entry.path = rel or entry.path
            entry.aliases = merged_aliases or entry.aliases
            entry.target_app = workflow.target_app or entry.target_app
            if workflow.variables:
                entry.variables = list(workflow.variables)
            if workflow.tags:
                entry.tags = list(workflow.tags)
            entry.updated_at = now
        self._save(entries)
        return entry

    def remove(self, slug: str) -> bool:
        entries = self._load()
        filtered = [e for e in entries if e.slug != slug]
        if len(filtered) == len(entries):
            return False
        self._save(filtered)
        return True

    def get(self, slug: str) -> WorkflowEntry | None:
        slug = (slug or "").strip().lower()
        if not slug:
            return None
        for entry in self._load():
            if entry.slug.lower() == slug:
                return entry
        return None

    # ---------- fuzzy lookup ----------

    def find(self, query: str) -> WorkflowEntry | None:
        """Match ``query`` to a workflow by slug / alias / name / substring."""
        q = (query or "").strip()
        if not q:
            return None
        entries = self._load()
        if not entries:
            return None

        # 1. Exact slug (case-insensitive).
        ql = q.lower()
        for e in entries:
            if e.slug.lower() == ql:
                return e

        # 2. Exact alias/name.
        for e in entries:
            for handle in e.all_handles():
                if handle.strip().lower() == ql:
                    return e

        # 3. Prefix match on any handle.
        for e in entries:
            for handle in e.all_handles():
                h = handle.strip().lower()
                if h and (ql.startswith(h) or h.startswith(ql)):
                    return e

        # 4. Whole-word match: tokenise both sides, require every alias word to
        #    appear in the query in order (loose).
        q_tokens = _tokens(q)
        best: tuple[int, WorkflowEntry | None] = (0, None)
        for e in entries:
            for handle in e.all_handles():
                h_tokens = _tokens(handle)
                if not h_tokens:
                    continue
                score = sum(1 for tok in h_tokens if tok in q_tokens)
                if score == len(h_tokens) and score > best[0]:
                    best = (score, e)
        return best[1]

    # ---------- helpers ----------

    @staticmethod
    def _entry_for_slug(entries: list[WorkflowEntry], slug: str) -> WorkflowEntry | None:
        slug_lower = (slug or "").lower()
        for e in entries:
            if e.slug.lower() == slug_lower:
                return e
        return None


_STOP = {"bir", "ve", "için", "ile", "de", "da", "bu", "şu", "to", "a", "an", "the"}


def _tokens(text: str) -> list[str]:
    return [
        t for t in re.split(r"\W+", (text or "").lower()) if t and t not in _STOP and len(t) > 1
    ]


def _unique_case_insensitive(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for v in values:
        key = (v or "").strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(v.strip())
    return out


__all__ = ["WorkflowEntry", "WorkflowRegistry", "REGISTRY_FILENAME", "slugify"]
