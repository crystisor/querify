"""Small JSON transport shared by the two service adapters."""

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


class ServiceError(RuntimeError):
    """A remote service could not complete the requested operation."""


class JsonHttp:
    def __init__(self, base_url: str, headers: dict[str, str] | None = None):
        parsed = urlsplit(base_url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ValueError("Service URLs must start with http:// or https://.")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("Service URLs must not contain credentials, queries, or fragments.")
        self._base_url = base_url.rstrip("/")
        self._headers = {"Accept": "application/json", **(headers or {})}

    def request(self, method: str, path: str, payload: object = None, *, timeout: float = 15) -> object:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {**self._headers, "Content-Type": "application/json"}
        request = Request(self._base_url + path, data=body, headers=headers, method=method)
        try:
            with urlopen(request, timeout=timeout) as response:
                return json.loads(response.read())
        except HTTPError as error:
            raise ServiceError(f"Service request to {path} failed (HTTP {error.code}).") from None
        except (URLError, OSError, ValueError):
            raise ServiceError(f"Service request to {path} failed; check connection and configuration.") from None
