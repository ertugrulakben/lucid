"""Extract short "what I learned" notes from finished Execute runs.

The recorder is optional — it only runs when ``memory.auto_fact_extract`` is
enabled in settings. At the end of a successful Execute run we ask the LLM
to compress the interaction into at most three one-sentence lessons (key
shortcuts, pitfalls, or selectors that worked). Those lines get stored as
``facts`` and as one ``task_pattern`` summary, so the next similar task
starts with recent hard-won knowledge in its prompt.

Design goal: **never leak secrets**. Passwords, tokens, or any value typed
into a password field must not reach the recorder, and any note mentioning
"password/token/secret" is dropped defensively before persisting.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from lucid.memory.store import MemoryStore

log = logging.getLogger("lucid.memory.recorder")


FACT_EXTRACT_PROMPT = (
    "You just helped the user complete a desktop task. Write between 0 and 3 "
    "one-sentence lessons future runs can use. Only include things that are "
    "NOT already obvious from a basic read of the Lucid manual: app-specific "
    "shortcuts, surprising element names, pitfalls you hit and recovered from, "
    "stable selectors, file paths, or workflow patterns that worked. "
    "NEVER include passwords, tokens, emails, or any value typed into a "
    "password field. Output ONLY the lessons, one per line. If there is "
    "nothing novel to record, output the single word SKIP."
)


SECRET_PATTERN = re.compile(r"(?i)\b(password|şifre|sifre|token|secret|api.?key|auth|bearer)\b")


@dataclass
class FactCandidate:
    topic: str
    content: str


class FactRecorder:
    def __init__(self, store: MemoryStore, provider, settings) -> None:
        self.store = store
        self.provider = provider
        self.settings = settings

    def record_task(
        self,
        *,
        goal: str,
        target_app: str | None,
        transcript: str,
        step_count: int,
        succeeded: bool,
    ) -> int:
        """Persist a task pattern summary and, when allowed, extract facts."""
        summary = transcript.strip().splitlines()[-1][:400] if transcript.strip() else ""
        pattern_id = self.store.add_task_pattern(
            goal=goal,
            summary=summary or goal,
            target_app=target_app,
            step_count=step_count,
            succeeded=succeeded,
        )

        if not succeeded or not self.settings.memory.auto_fact_extract:
            return pattern_id

        try:
            candidates = self._llm_extract(goal, target_app, transcript)
        except Exception as exc:
            log.debug("fact extraction failed: %s", exc)
            return pattern_id

        saved = 0
        for cand in candidates:
            if SECRET_PATTERN.search(cand.content):
                log.debug("dropping fact candidate (secret-like content)")
                continue
            if self.store.add_fact(cand.topic, cand.content, source=f"task#{pattern_id}"):
                saved += 1
        log.info("recorded %d fact(s) from task#%d", saved, pattern_id)
        return pattern_id

    def _llm_extract(
        self,
        goal: str,
        target_app: str | None,
        transcript: str,
    ) -> list[FactCandidate]:
        from lucid.llm.provider import Message

        user_text = (
            f"Goal: {goal}\n"
            f"Target app: {target_app or 'unknown'}\n"
            f"Transcript:\n{transcript[:4000]}"
        )
        messages = [Message(role="user", content=[self.provider.text_block(user_text)])]
        buffer: list[str] = []
        for ev in self.provider.stream(messages, system=FACT_EXTRACT_PROMPT, max_tokens=400):
            if ev.kind == "text_delta":
                buffer.append(ev.text)
            elif ev.kind == "done":
                break
            elif ev.kind == "error":
                log.debug("fact extract stream error: %s", ev.error)
                return []
        raw = "".join(buffer).strip()
        if not raw or raw.strip().upper().startswith("SKIP"):
            return []
        candidates: list[FactCandidate] = []
        for line in raw.splitlines():
            line = line.strip(" -•\t")
            if not line or len(line) < 10:
                continue
            topic = (target_app or "general").lower()
            candidates.append(FactCandidate(topic=topic, content=line[:280]))
            if len(candidates) == 3:
                break
        return candidates
