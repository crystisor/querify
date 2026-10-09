import unittest
from unittest.mock import Mock

from queryfi.conversations import ConversationOwner, ConversationService, NotebookQuestion, SessionId
from queryfi.courses import ChannelRef, Subject, SubjectId
from queryfi.notebook_chat import ChatSettings, OpenNotebookChat
from queryfi.prompts import PromptService
from queryfi.storage import SurrealSessionOwners


class ConversationTests(unittest.TestCase):
    def setUp(self):
        self.notebooks = Mock()
        self.notebooks.create_session.side_effect = [SessionId(f"chat_session:{i}") for i in range(10)]
        self.notebooks.answer.return_value = "Answer"
        self.owners = Mock()
        self.conversations = ConversationService(self.notebooks, self.owners)
        self.owner = ConversationOwner(ChannelRef(1, 10), 1234567890123456789)
        self.subject = SubjectId("notebook:math")

    def ask(self, owner=None, service=None):
        return (service or self.conversations).answer(owner or self.owner, self.subject, "Question")

    def test_first_message_starts_session_and_followups_reuse_it(self):
        self.assertEqual(self.ask(), "Answer")
        self.ask()
        self.notebooks.create_session.assert_called_once_with(self.subject)
        self.owners.record.assert_called_once_with(SessionId("chat_session:0"), self.owner, self.subject)
        self.assertEqual([call.args[0].session_id for call in self.notebooks.answer.call_args_list],
                         [SessionId("chat_session:0")] * 2)

    def test_start_creates_session_without_question_and_does_not_replace_active_session(self):
        self.assertTrue(self.conversations.start(self.owner, self.subject))
        self.assertFalse(self.conversations.start(self.owner, self.subject))
        self.notebooks.answer.assert_not_called()
        self.ask()
        self.notebooks.create_session.assert_called_once()

    def test_users_channels_and_servers_have_separate_sessions(self):
        owners = [self.owner, ConversationOwner(ChannelRef(1, 10), 2),
                  ConversationOwner(ChannelRef(1, 11), self.owner.user_id),
                  ConversationOwner(ChannelRef(2, 10), self.owner.user_id)]
        for owner in owners:
            self.ask(owner)
        sessions = [call.args[0].session_id for call in self.notebooks.answer.call_args_list]
        self.assertEqual(len(set(sessions)), 4)
        self.assertEqual(self.owners.record.call_count, 4)

    def test_end_only_clears_callers_session_in_this_channel_and_next_message_starts_fresh(self):
        other = ConversationOwner(ChannelRef(1, 10), 2)
        another_channel = ConversationOwner(ChannelRef(1, 11), self.owner.user_id)
        for owner in (self.owner, other, another_channel):
            self.ask(owner)
        self.assertTrue(self.conversations.end(self.owner))
        self.assertFalse(self.conversations.end(self.owner))
        for owner in (self.owner, other, another_channel):
            self.ask(owner)
        sessions = [call.args[0].session_id.value for call in self.notebooks.answer.call_args_list]
        self.assertEqual(sessions, [f"chat_session:{i}" for i in (0, 1, 2, 3, 1, 2)])
        self.assertEqual(self.owners.record.call_count, 4)

    def test_new_service_does_not_resume_database_sessions(self):
        self.ask()
        restarted = ConversationService(self.notebooks, self.owners)
        self.ask(service=restarted)
        self.assertEqual(self.notebooks.create_session.call_count, 2)
        self.assertEqual([call[0] for call in self.owners.method_calls], ["record", "record"])

    def test_ownership_write_failure_does_not_activate_session_or_send_question(self):
        self.owners.record.side_effect = RuntimeError("database offline")
        with self.assertRaises(RuntimeError):
            self.ask()
        self.assertFalse(self.conversations.end(self.owner))
        self.notebooks.answer.assert_not_called()
        self.owners.record.side_effect = None
        self.ask()
        self.notebooks.answer.assert_called_once_with(
            NotebookQuestion(self.subject, "Question", SessionId("chat_session:1")))

    def test_session_creation_failure_does_not_record_ownership(self):
        self.notebooks.create_session.side_effect = RuntimeError("notebook offline")
        with self.assertRaises(RuntimeError):
            self.conversations.start(self.owner, self.subject)
        self.owners.record.assert_not_called()
        self.assertFalse(self.conversations.end(self.owner))

    def test_failed_question_keeps_active_session_for_next_message(self):
        self.notebooks.answer.side_effect = RuntimeError("model offline")
        with self.assertRaises(RuntimeError):
            self.ask()
        self.notebooks.answer.side_effect = None
        self.ask()
        self.notebooks.create_session.assert_called_once()


class ConversationIntegrationTests(unittest.TestCase):
    def test_commands_and_messages_use_recorded_sessions_and_restart_starts_fresh(self):
        notebook_http, database_http = Mock(), Mock()
        created, executed = [], []

        def notebook_request(method, path, payload=None, **kwargs):
            if path == "/api/chat/sessions":
                session_id = f"chat_session:{len(created)}"
                created.append(session_id)
                return {"id": session_id}
            if path.startswith("/api/sources?"):
                return [{"id": "source:math"}]
            if path == "/api/chat/context":
                return {"context": {"sources": [{"id": "source:math", "full_text": "Matrices"}]}}
            if path == "/api/chat/execute":
                executed.append(payload["session_id"])
                return {"messages": [{"type": "ai", "content": "Answer"}]}
            self.fail(f"Unexpected notebook request: {method} {path}")

        notebook_http.request.side_effect = notebook_request
        database_http.request.side_effect = lambda method, path, payload: {
            "result": [{"status": "OK", "result": [payload["params"][1]]}],
        }
        backend = OpenNotebookChat(notebook_http, ChatSettings("model:local"))
        ownership = SurrealSessionOwners(database_http)
        courses = Mock()
        courses.status.return_value = Subject(SubjectId("notebook:math"), "Math")
        prompts = PromptService(courses, ConversationService(backend, ownership))
        owner = ConversationOwner(ChannelRef(1, 10), 42)
        other = ConversationOwner(owner.channel, 43)

        self.assertIn("has started", prompts.start(owner))
        self.assertEqual(executed, [])
        self.assertIn("/end first", prompts.start(owner))
        prompts.answer(owner, "First question")
        prompts.answer(owner, "Followup")
        prompts.answer(other, "Another user's question")
        self.assertIn("has ended", prompts.end(owner))
        self.assertIn("no active", prompts.end(owner))
        prompts.answer(other, "Another user's followup")
        prompts.answer(owner, "Fresh question")
        restarted = PromptService(courses, ConversationService(backend, ownership))
        restarted.answer(owner, "After restart")

        self.assertEqual(executed, [f"chat_session:{i}" for i in (0, 0, 1, 1, 2, 3)])
        self.assertEqual(created, [f"chat_session:{i}" for i in range(4)])
        records = [call.args[2]["params"][1] for call in database_http.request.call_args_list]
        self.assertEqual([row["session_id"] for row in records], created)
        self.assertEqual([row["user_id"] for row in records], ["42", "43", "42", "42"])
        self.assertTrue(all(row["channel_id"] == "10" and row["notebook_id"] == "notebook:math"
                            for row in records))
        self.assertTrue(all(call.args[0] != "DELETE" for call in notebook_http.request.call_args_list))
