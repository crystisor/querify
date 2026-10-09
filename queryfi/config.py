"""Compose the course service from environment configuration."""

import base64
from collections.abc import Mapping

from .courses import CourseService
from .conversations import ConversationService
from .http import JsonHttp
from .notebook_chat import ChatSettings, OpenNotebookChat, select_ollama_model
from .prompts import PromptService
from .storage import OpenNotebookSubjects, SurrealBindings, SurrealSessionOwners


def required(environment: Mapping[str, str], name: str) -> str:
    value = environment.get(name, "")
    if not value.strip():
        raise ValueError(f"Set {name} in .env before starting Queryfi.")
    return value


def create_service(environment: Mapping[str, str]) -> CourseService:
    subjects = OpenNotebookSubjects(notebook_http(environment))
    bindings = SurrealBindings(database_http(environment))
    return CourseService(subjects, bindings)


def database_http(environment: Mapping[str, str]) -> JsonHttp:
    database_url = required(environment, "SURREAL_URL")
    headers = {
        "surreal-ns": required(environment, "SURREAL_NAMESPACE"),
        "surreal-db": required(environment, "SURREAL_DATABASE"),
        "Authorization": database_authorization(environment),
    }
    return JsonHttp(database_url, headers)


def database_authorization(environment: Mapping[str, str]) -> str:
    username = required(environment, "SURREAL_USER")
    password = required(environment, "SURREAL_PASSWORD")
    credentials = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    return f"Basic {credentials}"


def notebook_http(environment: Mapping[str, str]) -> JsonHttp:
    headers = {}
    if password := environment.get("OPEN_NOTEBOOK_PASSWORD"):
        headers["Authorization"] = f"Bearer {password}"
    return JsonHttp(environment.get("OPEN_NOTEBOOK_URL", "http://localhost:5055"), headers)


def create_prompt_service(environment: Mapping[str, str], courses: CourseService) -> PromptService:
    try:
        timeout = float(environment.get("OPEN_NOTEBOOK_CHAT_TIMEOUT", "180"))
    except ValueError:
        raise ValueError("OPEN_NOTEBOOK_CHAT_TIMEOUT must be a number of seconds.") from None
    http = notebook_http(environment)
    model_id = select_ollama_model(http, environment.get("OPEN_NOTEBOOK_MODEL_ID", "").strip())
    settings = ChatSettings(model_id, timeout)
    conversations = ConversationService(
        OpenNotebookChat(http, settings), SurrealSessionOwners(database_http(environment)),
    )
    return PromptService(courses, conversations)
