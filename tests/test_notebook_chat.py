import unittest
from unittest.mock import Mock

from queryfi.courses import SubjectId
from queryfi.http import ServiceError
from queryfi.notebook_chat import ChatSettings, OpenNotebookChat, select_ollama_model
from queryfi.conversations import NotebookQuestion, SessionId


class NotebookChatTests(unittest.TestCase):
    def setUp(self):
        self.http = Mock()
        self.chat = OpenNotebookChat(self.http, ChatSettings("model:local", 180))
        self.question = NotebookQuestion(SubjectId("notebook:math"), "Explain matrices", SessionId("chat_session:one"))
        self.context = {"sources": [{"id": "source:a", "full_text": "Matrices contain numbers."}], "notes": []}
        self.responses = [
            [{"id": "source:a"}],
            {"context": self.context},
            {"messages": [{"type": "human", "content": "Explain matrices"},
                          {"type": "ai", "content": "They contain numbers. [source:a]"}]},
        ]

    def test_queries_only_bound_sources_with_configured_model(self):
        self.http.request.side_effect = self.responses
        answer = self.chat.answer(self.question)
        self.assertEqual(answer, "They contain numbers. [source:a]")
        calls = self.http.request.call_args_list
        self.assertEqual(calls[0].args, ("GET", "/api/sources?notebook_id=notebook%3Amath&limit=100&offset=0&sort_by=created&sort_order=asc"))
        self.assertEqual(calls[1].args[2], {
            "notebook_id": "notebook:math",
            "context_config": {"sources": {"source:a": "full content"}, "notes": {}},
        })
        self.assertEqual(calls[2].args[2], {
            "session_id": "chat_session:one", "message": "Explain matrices",
            "context": self.context, "model_override": "model:local",
        })
        self.assertEqual(calls[2].kwargs["timeout"], 180)

    def test_all_source_pages_are_included(self):
        page = [{"id": f"source:{index}"} for index in range(100)]
        self.http.request.side_effect = [page, [{"id": "source:a"}], *self.responses[1:]]
        self.chat.answer(self.question)
        calls = self.http.request.call_args_list
        self.assertIn("offset=100", calls[1].args[1])
        self.assertEqual(len(calls[2].args[2]["context_config"]["sources"]), 101)

    def test_empty_notebook_does_not_create_chat_or_call_model(self):
        self.http.request.side_effect = [[]]
        self.assertIn("no readable sources", self.chat.answer(self.question))
        self.http.request.assert_called_once()

    def test_unprocessed_sources_do_not_call_model(self):
        for sources in ([], [{"id": "source:a", "full_text": ""}]):
            with self.subTest(sources=sources):
                self.http.request.reset_mock()
                self.http.request.side_effect = [self.responses[0], {"context": {"sources": sources, "notes": []}}]
                self.assertIn("no readable sources", self.chat.answer(self.question))
                self.assertEqual(self.http.request.call_count, 2)

    def test_unrelated_context_sources_are_rejected(self):
        self.http.request.side_effect = [self.responses[0], {"context": {
            "sources": [{"id": "source:other", "full_text": "Other notebook"}], "notes": [],
        }}]
        with self.assertRaises(ServiceError):
            self.chat.answer(self.question)
        self.assertEqual(self.http.request.call_count, 2)

    def test_malformed_response_or_missing_ai_answer_is_not_success(self):
        for index, replacement in ((0, {}), (0, [{"id": None}]), (1, {}),
                                   (2, {}),
                                   (2, {"messages": [{"type": "human", "content": "Echo"}]}),
                                   (2, {"messages": [{"type": "ai", "content": " "}]})):
            with self.subTest(index=index, replacement=replacement):
                responses = self.responses.copy()
                responses[index] = replacement
                self.http.request.side_effect = responses
                with self.assertRaises(ServiceError):
                    self.chat.answer(self.question)

    def test_followups_execute_in_supplied_session_without_creating_new_sessions(self):
        self.http.request.side_effect = self.responses * 2
        self.chat.answer(self.question)
        self.chat.answer(self.question)
        executions = [call.args[2] for call in self.http.request.call_args_list if call.args[1] == "/api/chat/execute"]
        self.assertEqual([entry["session_id"] for entry in executions], ["chat_session:one"] * 2)
        self.assertNotIn("/api/chat/sessions", [call.args[1] for call in self.http.request.call_args_list])

    def test_create_session_uses_notebook_and_model_without_sending_question(self):
        self.http.request.return_value = {"id": "chat_session:new"}
        self.assertEqual(self.chat.create_session(self.question.subject_id), SessionId("chat_session:new"))
        self.http.request.assert_called_once_with("POST", "/api/chat/sessions", {
            "notebook_id": "notebook:math", "title": "Queryfi Discord conversation",
            "model_override": "model:local",
        })

    def test_invalid_session_creation_responses_are_rejected(self):
        for response in ({}, {"id": ""}, {"id": " "}, {"id": None}):
            with self.subTest(response=response):
                self.http.request.return_value = response
                with self.assertRaises(ServiceError):
                    self.chat.create_session(self.question.subject_id)

    def test_history_response_returns_latest_assistant_answer(self):
        self.responses[-1] = {"messages": [
            {"type": "human", "content": "Old question"}, {"type": "ai", "content": "Old answer"},
            {"type": "human", "content": "Followup"}, {"type": "ai", "content": "New answer"},
        ]}
        self.http.request.side_effect = self.responses
        self.assertEqual(self.chat.answer(self.question), "New answer")


class OllamaSelectionTests(unittest.TestCase):
    def setUp(self):
        self.http = Mock()
        self.models = [{"id": "model:local", "type": "language", "provider": "ollama"},
                       {"id": "model:remote", "type": "language", "provider": "openai"}]

    def test_default_chat_model_must_be_ollama(self):
        self.http.request.side_effect = [{"default_chat_model": "model:local"}, self.models]
        self.assertEqual(select_ollama_model(self.http), "model:local")

    def test_explicit_model_ignores_default_but_must_be_ollama(self):
        self.http.request.return_value = self.models
        self.assertEqual(select_ollama_model(self.http, "model:local"), "model:local")
        self.http.request.assert_called_once_with("GET", "/api/models?type=language")

    def test_missing_non_ollama_and_embedding_models_are_rejected(self):
        for model_id in (None, "model:missing", "model:remote", "model:embedding"):
            self.http.request.side_effect = [
                {"default_chat_model": model_id},
                self.models + [{"id": "model:embedding", "type": "embedding", "provider": "ollama"}],
            ]
            with self.subTest(model_id=model_id), self.assertRaisesRegex(ValueError, "Ollama"):
                select_ollama_model(self.http)

    def test_invalid_timeouts_are_rejected(self):
        for timeout in (0, -1, float("nan"), float("inf")):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                ChatSettings("model:local", timeout)
