"""Mode router: dispatch prompts to the Answer, Teach, or Execute mode."""

from __future__ import annotations

import logging
import threading
from enum import Enum

from PySide6.QtCore import QObject, Signal, Slot

from lucid.agent.answer_mode import AnswerMode
from lucid.agent.conversation import Conversation
from lucid.agent.execute_mode import ExecuteMode
from lucid.agent.teach_mode import TeachMode
from lucid.capture import ContextSnapshot
from lucid.config.profile import get_profile
from lucid.llm.provider import create_provider
from lucid.memory.store import MemoryStore

log = logging.getLogger("lucid.agent")


class Mode(str, Enum):
    ANSWER = "answer"
    TEACH = "teach"
    EXECUTE = "execute"


class ModeRouter(QObject):
    stream_chunk = Signal(str)
    stream_done = Signal(str)
    error = Signal(str)
    conversation_changed = Signal()
    # Current pending attachments (list of PIL images) — populated by the
    # controller before calling ``dispatch`` so Execute mode can forward
    # them as reference images in the first user turn.
    pending_attachments: list = []

    def __init__(self, settings) -> None:
        super().__init__()
        self.settings = settings
        self.conversation = Conversation()
        self._cancel = threading.Event()
        self._worker: threading.Thread | None = None
        self._active_mode: Mode | None = None

        self._store: MemoryStore | None = None
        if settings.memory.enabled:
            try:
                self._store = MemoryStore(
                    settings.memory_db_path,
                    max_facts=settings.memory.max_facts,
                    max_files=settings.memory.max_files,
                    max_task_patterns=settings.memory.max_task_patterns,
                )
            except Exception as exc:
                log.warning("memory store disabled (init failed): %s", exc)
                self._store = None

        try:
            self._profile = get_profile(settings)
        except Exception as exc:
            log.debug("profile load failed (using empty): %s", exc)
            self._profile = None

        self._provider = create_provider(settings)
        self._answer = AnswerMode(self._provider)
        self._teach = TeachMode(settings, self._provider)
        self._execute = ExecuteMode(
            settings,
            self._provider,
            memory_store=self._store,
            profile=self._profile,
        )

    @property
    def active_mode(self) -> Mode | None:
        return self._active_mode

    def is_busy(self) -> bool:
        return self._worker is not None and self._worker.is_alive()

    def is_teach_recording(self) -> bool:
        return self._active_mode is Mode.TEACH and self._teach.is_recording()

    def stop_teach(self) -> None:
        if self._active_mode is Mode.TEACH:
            self._teach.stop()

    def new_conversation(self) -> None:
        self.conversation.clear()
        self._execute.reset()
        self.conversation_changed.emit()

    @Slot(str, object, object)
    def dispatch(self, prompt: str, mode: Mode, snapshot: ContextSnapshot | None) -> None:
        if snapshot is None:
            self.error.emit("No context snapshot available.")
            return
        if self._worker and self._worker.is_alive():
            log.warning("Previous worker still running; cancelling before dispatching.")
            self.cancel()

        self._cancel = threading.Event()
        self._worker = threading.Thread(
            target=self._run,
            args=(prompt, mode, snapshot, self._cancel),
            daemon=True,
            name=f"lucid-{mode.value}",
        )
        self._worker.start()

    def cancel(self) -> None:
        self._cancel.set()
        self._execute.cancel()
        self._teach.cancel()

    def _run(
        self,
        prompt: str,
        mode: Mode,
        snapshot: ContextSnapshot,
        cancel: threading.Event,
    ) -> None:
        self._active_mode = mode
        try:
            if mode is Mode.ANSWER:
                self.conversation.append_user(prompt, image=snapshot.image)
                self.conversation_changed.emit()
                buffer = ""
                for chunk in self._answer.run(self.conversation, cancel):
                    if cancel.is_set():
                        break
                    buffer += chunk
                    self.stream_chunk.emit(chunk)
                if buffer.strip():
                    self.conversation.append_assistant(buffer)
                    self.conversation_changed.emit()
            elif mode is Mode.TEACH:
                for chunk in self._teach.run(prompt, snapshot, cancel):
                    if cancel.is_set():
                        break
                    self.stream_chunk.emit(chunk)
            elif mode is Mode.EXECUTE:
                for chunk in self._execute.run(
                    prompt, snapshot, cancel, attachments=list(self.pending_attachments)
                ):
                    if cancel.is_set():
                        break
                    self.stream_chunk.emit(chunk)
                self.pending_attachments = []
            self.stream_done.emit(mode.value)
        except Exception as exc:
            log.exception("Mode %s failed", mode)
            self.error.emit(str(exc))
        finally:
            self._active_mode = None
