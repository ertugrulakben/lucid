"""Retrieve memory slices to seed Execute / Answer prompts."""

from __future__ import annotations

from lucid.memory.store import MemoryStore


def context_block(
    store: MemoryStore,
    query: str,
    target_app: str | None = None,
    max_facts: int = 4,
    max_patterns: int = 2,
) -> str:
    """Return a compact, prompt-ready context block for ``query``.

    Empty string when nothing useful is found; callers should skip inclusion
    in that case rather than sending a header with no body.
    """
    facts = store.search_facts(query, limit=max_facts)
    patterns = store.search_task_patterns(query, limit=max_patterns, target_app=target_app)
    if not facts and not patterns:
        return ""

    lines: list[str] = ["Relevant memory from past sessions:"]
    for f in facts:
        origin = f" (from {f.source})" if f.source else ""
        lines.append(f"- fact [{f.topic}]: {f.content}{origin}")
    for p in patterns:
        status = "✓" if p.succeeded else "✗"
        app = f" in {p.target_app}" if p.target_app else ""
        lines.append(f"- past task{app} ({status}, {p.step_count} steps): {p.goal} → {p.summary}")
    return "\n".join(lines)


def file_answer_block(store: MemoryStore, query: str, limit: int = 8) -> str:
    """Answer-mode helper: format file matches into a bulleted list."""
    files = store.find_files(query, limit=limit)
    if not files:
        return ""
    lines = ["Files I've seen that might match:"]
    for f in files:
        ts = int(f.last_accessed_at)
        lines.append(f"- {f.path}  (last seen: {ts}, kind: {f.kind or '?'})")
    return "\n".join(lines)
