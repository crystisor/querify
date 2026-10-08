"""Course binding rules, independent of Discord and storage."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class SubjectId:
    value: str

    def __post_init__(self):
        if not isinstance(self.value, str) or not self.value.strip():
            raise ValueError("Subject IDs must be non-empty strings.")
        if len(self.value) > 100 or self.value != self.value.strip():
            raise ValueError("Subject IDs must be at most 100 characters, without outer whitespace.")


@dataclass(frozen=True)
class Subject:
    id: SubjectId
    name: str

    def __post_init__(self):
        if not isinstance(self.name, str) or not self.name.strip() or len(self.name) > 200:
            raise ValueError("Subject names must be non-empty strings of at most 200 characters.")


@dataclass(frozen=True)
class ChannelRef:
    guild_id: int
    channel_id: int


@dataclass(frozen=True)
class SubjectListing:
    subject: Subject
    channel_ids: tuple[int, ...]


class SubjectSource(Protocol):
    def list_subjects(self) -> tuple[Subject, ...]:
        """Return the current catalog with unique, stable subject IDs; raise on failure."""
        ...


class BindingStore(Protocol):
    def for_guild(self, guild_id: int) -> dict[int, SubjectId]:
        """Return channel-to-subject bindings belonging only to this server."""
        ...

    def bind(self, channel: ChannelRef, subject_id: SubjectId) -> None:
        """Atomically replace this channel's binding and persist before returning."""
        ...


class UnknownSubject(ValueError):
    """The requested ID does not exist in the current catalog."""


class CourseService:
    def __init__(self, subjects: SubjectSource, bindings: BindingStore):
        self._subjects = subjects
        self._bindings = bindings

    def list_subjects(self, guild_id: int) -> tuple[SubjectListing, ...]:
        bindings = self._bindings.for_guild(guild_id)
        return tuple(
            SubjectListing(subject, tuple(
                channel_id for channel_id, subject_id in bindings.items()
                if subject_id == subject.id
            ))
            for subject in self._subjects.list_subjects()
        )

    def status(self, channel: ChannelRef) -> Subject | None:
        subject_id = self._bindings.for_guild(channel.guild_id).get(channel.channel_id)
        if subject_id is None:
            return None
        return next(
            (subject for subject in self._subjects.list_subjects() if subject.id == subject_id),
            Subject(subject_id, "Subject unavailable in the current course source"),
        )

    def bind(self, channel: ChannelRef, subject_id: SubjectId) -> Subject:
        subject = next(
            (subject for subject in self._subjects.list_subjects() if subject.id == subject_id),
            None,
        )
        if subject is None:
            raise UnknownSubject("Unknown subject ID. Use /list to see available IDs.")
        self._bindings.bind(channel, subject_id)
        return subject
