"""Run searxNcrawl's documented JSON search CLI without a shell."""

import json
import math
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlsplit

from .search import SearchError, SearchQuery, SearchResult

PACKAGE = "searxncrawl==0.32.0"
MAX_RESULTS = 5


@dataclass(frozen=True)
class SearchSettings:
    timeout: float = 60

    def __post_init__(self):
        if not math.isfinite(self.timeout) or not 0 < self.timeout <= 600:
            raise ValueError("SEARXNCRAWL_TIMEOUT must be a finite number greater than 0 and at most 600 seconds.")


class SearxNCrawlSearch:
    def __init__(self, settings: SearchSettings, environment: Mapping[str, str]):
        self._settings = settings
        self._environment = dict(environment)

    def search(self, query: SearchQuery) -> tuple[SearchResult, ...]:
        if not any(self._environment.get(name, "").strip() for name in ("SEARXNG_URL", "YDC_API_KEY")):
            raise SearchError("Web search is not configured. Ask the bot owner to set SEARXNG_URL or YDC_API_KEY.")
        output = self._run(query)
        return parse_results(output)

    def _run(self, query: SearchQuery) -> str:
        command = ["uvx", "--from", PACKAGE, "search", "--json",
                   "--max-results", str(MAX_RESULTS), "--", query.value]
        environment = {**self._environment, "PYTHONIOENCODING": "utf-8",
                       "SEARXNG_URL": self._environment.get("SEARXNG_URL", "").strip(),
                       "YDC_API_KEY": self._environment.get("YDC_API_KEY", "").strip(),
                       "SEARCH_RESULT_FIELDS": "title,url,content,providers",
                       "PLAYWRIGHT_AUTO_INSTALL": "false"}
        try:
            process = subprocess.run(
                command, shell=False, capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=self._settings.timeout, env=environment,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except FileNotFoundError:
            raise SearchError("Web search requires uv. Ask the bot owner to install uv and make uvx available on PATH.") from None
        except subprocess.TimeoutExpired:
            raise SearchError("Web search timed out. Please try again or ask the bot owner to check searxNcrawl.") from None
        except OSError:
            raise SearchError("Web search could not start. Ask the bot owner to check the searxNcrawl installation.") from None
        if process.returncode:
            raise SearchError("I could not search the web. Ask the bot owner to check searxNcrawl and its search providers.")
        return process.stdout


def parse_results(output: str) -> tuple[SearchResult, ...]:
    try:
        payload = json.loads(output)
        if not isinstance(payload, dict) or "error" in payload or not isinstance(payload.get("results"), list):
            raise ValueError("Invalid search response")
        return tuple(parse_result(row) for row in payload["results"][:MAX_RESULTS])
    except (ValueError, TypeError):
        raise SearchError("The search service returned an invalid response. Ask the bot owner to check searxNcrawl.") from None


def parse_result(row: object) -> SearchResult:
    if not isinstance(row, dict):
        raise ValueError("Invalid search result")
    url = row.get("url")
    if not isinstance(url, str):
        raise ValueError("Missing search URL")
    parsed = urlsplit(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Invalid search URL")
    title, snippet, providers = row.get("title", ""), row.get("content", ""), row.get("providers", [])
    if not isinstance(title, str) or not isinstance(snippet, str):
        raise ValueError("Invalid search text")
    if not isinstance(providers, list) or not all(isinstance(provider, str) for provider in providers):
        raise ValueError("Invalid search providers")
    return SearchResult(title or url, url, snippet, tuple(providers))
