import unittest
from unittest.mock import Mock

from queryfi.courses import ChannelRef, CourseService, Subject, SubjectId
from queryfi.prompts import NotebookQuestion, PromptService
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

    def test_bound_prompt_uses_current_notebook_and_preserves_prompt(self):
        self.courses.bind(self.channel, SubjectId("math"))
        self.assertEqual(self.prompts.answer(self.channel, "Explain matrices"), "A source-based answer")
        self.answers.answer.assert_called_once_with(NotebookQuestion(SubjectId("math"), "Explain matrices"))

    def test_unbound_channel_and_other_server_do_not_query_notebooks(self):
        self.courses.bind(self.channel, SubjectId("math"))
        for channel in (ChannelRef(1, 11), ChannelRef(2, 10)):
            self.assertIsNone(self.prompts.answer(channel, "Explain matrices"))
        self.answers.answer.assert_not_called()

    def test_rebinding_changes_notebook_on_next_prompt(self):
        self.courses.bind(self.channel, SubjectId("math"))
        self.prompts.answer(self.channel, "First")
        self.subjects.subjects += (Subject(SubjectId("physics"), "Physics"),)
        self.courses.bind(self.channel, SubjectId("physics"))
        self.prompts.answer(self.channel, "Second")
        self.answers.answer.assert_called_with(NotebookQuestion(SubjectId("physics"), "Second"))

    def test_blank_prompts_are_ignored_before_accessing_services(self):
        self.subjects.error = RuntimeError("offline")
        self.assertIsNone(self.prompts.answer(self.channel, "   "))
        self.answers.answer.assert_not_called()

    def test_service_failures_propagate_without_changing_binding(self):
        self.courses.bind(self.channel, SubjectId("math"))
        self.answers.answer.side_effect = RuntimeError("offline")
        with self.assertRaises(RuntimeError):
            self.prompts.answer(self.channel, "Question")
        self.assertEqual(self.courses.status(self.channel).id, SubjectId("math"))
