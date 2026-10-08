"""Compose the course service from environment configuration."""

import base64
from collections.abc import Mapping

from .courses import CourseService
from .http import JsonHttp
from .storage import OpenNotebookSubjects, SurrealBindings


def required(environment: Mapping[str, str], name: str) -> str:
    value = environment.get(name, "")
    if not value.strip():
        raise ValueError(f"Set {name} in .env before starting Queryfi.")
    return value


def create_service(environment: Mapping[str, str]) -> CourseService:
    database_url = required(environment, "SURREAL_URL")
    database_headers = {
        "surreal-ns": required(environment, "SURREAL_NAMESPACE"),
        "surreal-db": required(environment, "SURREAL_DATABASE"),
        "Authorization": database_authorization(environment),
    }
    notebook_headers = {}
    if password := environment.get("OPEN_NOTEBOOK_PASSWORD"):
        notebook_headers["Authorization"] = f"Bearer {password}"
    subjects = OpenNotebookSubjects(JsonHttp(
        environment.get("OPEN_NOTEBOOK_URL", "http://localhost:5055"), notebook_headers,
    ))
    bindings = SurrealBindings(JsonHttp(database_url, database_headers))
    return CourseService(subjects, bindings)


def database_authorization(environment: Mapping[str, str]) -> str:
    username = required(environment, "SURREAL_USER")
    password = required(environment, "SURREAL_PASSWORD")
    credentials = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    return f"Basic {credentials}"
