import unittest
from unittest.mock import Mock

from queryfi.courses import ChannelRef, CourseService, Subject, SubjectId
from queryfi.conversations import ConversationOwner
from queryfi.prompts import PromptService
from fakes import MemoryBindings, MemorySubjects


class PromptTests(unittest.TestCase):
    def setUp(self):
        self.bindings = MemoryBindings()
        self.subjects = MemorySubjects()
        self.courses = CourseService(self.subjects, self.bindings)
        self.answers = Mock()
        self.answers.answer.return_value = "A source-based answer"
        self.prompts = PromptService(self.courses, self.answers)
        self.channel = ChannelRef(1, 10)
        self.owner = ConversationOwner(self.channel, 42)

    def test_bound_prompt_uses_current_notebook_and_preserves_prompt(self):
        self.courses.bind(self.channel, SubjectId("math"))
        self.assertEqual(self.prompts.answer(self.owner, "Explain matrices"), "A source-based answer")
        self.answers.answer.assert_called_once_with(self.owner, SubjectId("math"), "Explain matrices")

    def test_unbound_channel_and_other_server_do_not_query_notebooks(self):
        self.courses.bind(self.channel, SubjectId("math"))
        for channel in (ChannelRef(1, 11), ChannelRef(2, 10)):
            self.assertIsNone(self.prompts.answer(ConversationOwner(channel, 42), "Explain matrices"))
        self.answers.answer.assert_not_called()

    def test_rebinding_changes_notebook_on_next_prompt(self):
        self.courses.bind(self.channel, SubjectId("math"))
        self.prompts.answer(self.owner, "First")
        self.subjects.subjects += (Subject(SubjectId("physics"), "Physics"),)
        self.courses.bind(self.channel, SubjectId("physics"))
        self.prompts.answer(self.owner, "Second")
        self.answers.answer.assert_called_with(self.owner, SubjectId("physics"), "Second")

    def test_blank_prompts_are_ignored_before_accessing_services(self):
        self.subjects.error = RuntimeError("offline")
        self.assertIsNone(self.prompts.answer(self.owner, "   "))
        self.answers.answer.assert_not_called()

    def test_service_failures_propagate_without_changing_binding(self):
        self.courses.bind(self.channel, SubjectId("math"))
        self.answers.answer.side_effect = RuntimeError("offline")
        with self.assertRaises(RuntimeError):
            self.prompts.answer(self.owner, "Question")
        self.assertEqual(self.courses.status(self.channel).id, SubjectId("math"))

    def test_start_requires_bound_channel(self):
        self.assertIn("not bound", self.prompts.start(self.owner))
        self.answers.start.assert_not_called()

    def test_start_reports_created_or_already_active_conversation(self):
        self.courses.bind(self.channel, SubjectId("math"))
        self.answers.start.return_value = True
        self.assertIn("has started", self.prompts.start(self.owner))
        self.answers.start.assert_called_with(self.owner, SubjectId("math"))
        self.answers.start.return_value = False
        self.assertIn("/end first", self.prompts.start(self.owner))

    def test_end_reports_only_callers_result_without_accessing_courses(self):
        self.subjects.error = RuntimeError("offline")
        self.answers.end.return_value = True
        self.assertIn("has ended", self.prompts.end(self.owner))
        self.answers.end.assert_called_once_with(self.owner)
        self.answers.end.return_value = False
        self.assertIn("no active conversation", self.prompts.end(self.owner))
