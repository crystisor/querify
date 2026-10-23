"""Web search contracts independent of Discord and the search transport."""

from dataclasses import dataclass
from typing import Protocol


class SearchError(RuntimeError):
    """A search failure with a message safe to show in Discord."""


@dataclass(frozen=True)
class SearchQuery:
    value: str

    def __post_init__(self):
        value = self.value.strip()
        if not 1 <= len(value) <= 500 or "\0" in value:
            raise ValueError("Enter a search query between 1 and 500 characters, without null characters.")
        object.__setattr__(self, "value", value)


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str
    providers: tuple[str, ...]


class WebSearch(Protocol):
    def search(self, query: SearchQuery) -> tuple[SearchResult, ...]:
        """Return ranked results, or raise SearchError if the search fails."""
        ...
