"""Route channel questions to the currently bound notebook."""

from dataclasses import dataclass
from typing import Protocol

from .courses import ChannelRef, Subject, SubjectId


@dataclass(frozen=True)
class NotebookQuestion:
    subject_id: SubjectId
    prompt: str

    def __post_init__(self):
        if not self.prompt.strip():
            raise ValueError("A notebook question needs a text prompt.")


class ChannelSubjects(Protocol):
    def status(self, channel: ChannelRef) -> Subject | None:
        """Return the bound subject, or None for an unbound channel."""
        ...


class NotebookAnswers(Protocol):
    def answer(self, question: NotebookQuestion) -> str:
        """Answer using this notebook's sources; raise on service failure."""
        ...


class ChannelAnswers(Protocol):
    def answer(self, channel: ChannelRef, prompt: str) -> str | None:
        """Answer a bound-channel prompt, or return None when it is ignored."""
        ...


class PromptService:
    def __init__(self, courses: ChannelSubjects, notebooks: NotebookAnswers):
        self._courses = courses
        self._notebooks = notebooks

    def answer(self, channel: ChannelRef, prompt: str) -> str | None:
        if not prompt.strip():
            return None
        subject = self._courses.status(channel)
        if subject is None:
            return None
        return self._notebooks.answer(NotebookQuestion(subject.id, prompt))
