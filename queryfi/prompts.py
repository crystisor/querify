"""Route channel questions to the currently bound notebook."""

from typing import Protocol

from .conversations import ConversationLifecycle, ConversationOwner
from .courses import ChannelRef, Subject


class ChannelSubjects(Protocol):
    def status(self, channel: ChannelRef) -> Subject | None:
        """Return the bound subject, or None for an unbound channel."""
        ...


class ChannelAnswers(Protocol):
    def answer(self, owner: ConversationOwner, prompt: str) -> str | None:
        """Answer a bound-channel prompt, or return None when it is ignored."""
        ...

    def start(self, owner: ConversationOwner) -> str:
        """Start the caller's conversation in a bound channel, or explain why not."""
        ...

    def end(self, owner: ConversationOwner) -> str:
        """End only the caller's active conversation in this channel."""
        ...


class PromptService:
    def __init__(self, courses: ChannelSubjects, conversations: ConversationLifecycle):
        self._courses = courses
        self._conversations = conversations

    def answer(self, owner: ConversationOwner, prompt: str) -> str | None:
        if not prompt.strip():
            return None
        subject = self._courses.status(owner.channel)
        if subject is None:
            return None
        return self._conversations.answer(owner, subject.id, prompt)

    def start(self, owner: ConversationOwner) -> str:
        subject = self._courses.status(owner.channel)
        if subject is None:
            return "This channel is not bound to a course subject."
        if not self._conversations.start(owner, subject.id):
            return "You already have an active conversation in this channel. Use /end first."
        return "Your conversation has started. Send a message here, or use /end to finish it."

    def end(self, owner: ConversationOwner) -> str:
        if not self._conversations.end(owner):
            return "You have no active conversation in this channel."
        return "Your conversation has ended. Its history remains in Open Notebook."
