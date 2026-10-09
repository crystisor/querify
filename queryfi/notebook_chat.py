"""Use Open Notebook's chat API with an explicitly selected Ollama model."""

import math
from dataclasses import dataclass
from urllib.parse import urlencode

from .courses import SubjectId
from .http import JsonHttp, ServiceError
from .prompts import NotebookQuestion

NO_SOURCES = "This notebook has no readable sources yet. Add sources and finish processing them in Open Notebook, then try again."


@dataclass(frozen=True)
class ChatSettings:
    model_id: str
    timeout: float = 180

    def __post_init__(self):
        if not self.model_id.startswith("model:"):
            raise ValueError("OPEN_NOTEBOOK_MODEL_ID must be an Open Notebook model: ID.")
        if not math.isfinite(self.timeout) or self.timeout <= 0:
            raise ValueError("OPEN_NOTEBOOK_CHAT_TIMEOUT must be a finite positive number of seconds.")


def select_ollama_model(http: JsonHttp, model_id: str = "") -> str:
    if not model_id:
        defaults = http.request("GET", "/api/models/defaults")
        model_id = defaults.get("default_chat_model") if isinstance(defaults, dict) else None
    models = http.request("GET", "/api/models?type=language")
    if isinstance(models, list) and model_id:
        for model in models:
            if (isinstance(model, dict) and model.get("id") == model_id
                    and model.get("provider") == "ollama" and model.get("type") == "language"):
                return model_id
    raise ValueError("Choose an Ollama language model as Open Notebook's default chat model, or set OPEN_NOTEBOOK_MODEL_ID to its model: ID.")


class NotebookSourceContext:
    def __init__(self, http: JsonHttp):
        self._http = http

    def build(self, subject_id: SubjectId) -> dict:
        source_ids = self._source_ids(subject_id)
        if not source_ids:
            return {"sources": [], "notes": []}
        response = self._http.request("POST", "/api/chat/context", {
            "notebook_id": subject_id.value,
            "context_config": {"sources": dict.fromkeys(source_ids, "full content"), "notes": {}},
        })
        context = response.get("context") if isinstance(response, dict) else None
        return self._validated_context(context, source_ids)

    def _source_ids(self, subject_id: SubjectId) -> set[str]:
        source_ids = set()
        offset = 0
        while True:
            query = urlencode({"notebook_id": subject_id.value, "limit": 100, "offset": offset,
                               "sort_by": "created", "sort_order": "asc"})
            page = self._http.request("GET", f"/api/sources?{query}")
            if not isinstance(page, list):
                raise ServiceError("Open Notebook returned an invalid source list.")
            source_ids.update(self._source_id(source) for source in page)
            if len(page) < 100:
                return source_ids
            offset += len(page)

    @staticmethod
    def _source_id(source: object) -> str:
        source_id = source.get("id") if isinstance(source, dict) else None
        if not isinstance(source_id, str) or not source_id.startswith("source:"):
            raise ServiceError("Open Notebook returned an invalid source ID.")
        return source_id

    @classmethod
    def _validated_context(cls, context: object, source_ids: set[str]) -> dict:
        if not isinstance(context, dict) or not isinstance(context.get("sources"), list):
            raise ServiceError("Open Notebook returned invalid source context.")
        readable = []
        for source in context["sources"]:
            if cls._source_id(source) not in source_ids:
                raise ServiceError("Open Notebook returned context outside the bound notebook.")
            full_text = source.get("full_text")
            if isinstance(full_text, str) and full_text.strip():
                readable.append(source)
        return {"sources": readable, "notes": []}


class OpenNotebookChat:
    def __init__(self, http: JsonHttp, settings: ChatSettings):
        self._http = http
        self._settings = settings

    def answer(self, question: NotebookQuestion) -> str:
        context = NotebookSourceContext(self._http).build(question.subject_id)
        if not context["sources"]:
            return NO_SOURCES
        session_id = self._create_session(question.subject_id)
        response = self._http.request("POST", "/api/chat/execute", {
            "session_id": session_id, "message": question.prompt,
            "context": context, "model_override": self._settings.model_id,
        }, timeout=self._settings.timeout)
        return self._answer_text(response)

    def _create_session(self, subject_id: SubjectId) -> str:
        session = self._http.request("POST", "/api/chat/sessions", {
            "notebook_id": subject_id.value, "title": "Queryfi Discord question",
            "model_override": self._settings.model_id,
        })
        session_id = session.get("id") if isinstance(session, dict) else None
        if not isinstance(session_id, str) or not session_id.strip():
            raise ServiceError("Open Notebook did not create a chat session.")
        return session_id

    @staticmethod
    def _answer_text(response: object) -> str:
        messages = response.get("messages") if isinstance(response, dict) else None
        if not isinstance(messages, list):
            raise ServiceError("Open Notebook returned invalid chat messages.")
        for message in reversed(messages):
            if isinstance(message, dict) and message.get("type") == "ai":
                content = message.get("content")
                if isinstance(content, str) and content.strip():
                    return content
                break
        raise ServiceError("Open Notebook returned no assistant answer.")
