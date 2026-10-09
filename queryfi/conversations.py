"""Per-user conversation lifecycle; Open Notebook owns message history."""

from dataclasses import dataclass
from typing import Protocol

from .courses import ChannelRef, SubjectId


@dataclass(frozen=True)
class SessionId:
    value: str

    def __post_init__(self):
        if not isinstance(self.value, str) or not self.value.strip():
            raise ValueError("A conversation requires a non-empty session ID.")


@dataclass(frozen=True)
class ConversationOwner:
    channel: ChannelRef
    user_id: int


@dataclass(frozen=True)
class NotebookQuestion:
    subject_id: SubjectId
    prompt: str
    session_id: SessionId

    def __post_init__(self):
        if not self.prompt.strip():
            raise ValueError("A notebook question needs a text prompt.")


class NotebookConversations(Protocol):
    def create_session(self, subject_id: SubjectId) -> SessionId:
        """Create a notebook chat session without sending a question."""
        ...

    def answer(self, question: NotebookQuestion) -> str:
        """Answer in the supplied session using the notebook's sources."""
        ...


class SessionOwners(Protocol):
    def record(self, session_id: SessionId, owner: ConversationOwner, subject_id: SubjectId) -> None:
        """Persist session ownership before returning; never used to resume chats."""
        ...


class ConversationLifecycle(Protocol):
    def start(self, owner: ConversationOwner, subject_id: SubjectId) -> bool:
        """Create and record a session; return False if one is already active."""
        ...

    def end(self, owner: ConversationOwner) -> bool:
        """Forget only this owner's active session; return False if none exists."""
        ...

    def answer(self, owner: ConversationOwner, subject_id: SubjectId, prompt: str) -> str:
        """Start a session if needed and answer using its Open Notebook history."""
        ...


class ConversationService:
    def __init__(self, notebooks: NotebookConversations, owners: SessionOwners):
        self._notebooks = notebooks
        self._owners = owners
        self._active: dict[ConversationOwner, SessionId] = {}

    def start(self, owner: ConversationOwner, subject_id: SubjectId) -> bool:
        if owner in self._active:
            return False
        session_id = self._notebooks.create_session(subject_id)
        self._owners.record(session_id, owner, subject_id)
        self._active[owner] = session_id
        return True

    def end(self, owner: ConversationOwner) -> bool:
        return self._active.pop(owner, None) is not None

    def answer(self, owner: ConversationOwner, subject_id: SubjectId, prompt: str) -> str:
        self.start(owner, subject_id)
        return self._notebooks.answer(NotebookQuestion(subject_id, prompt, self._active[owner]))
