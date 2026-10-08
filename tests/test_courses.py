import unittest

from queryfi.courses import ChannelRef, CourseService, Subject, SubjectId, UnknownSubject
from fakes import MemorySubjects, MemoryBindings


class CourseTests(unittest.TestCase):
    def setUp(self):
        self.subjects = MemorySubjects()
        self.subjects.subjects += (Subject(SubjectId("cs"), "Computer Science"),)
        self.bindings = MemoryBindings()
        self.service = self.create_service()
        self.channel = ChannelRef(1, 10)

    def create_service(self):
        return CourseService(self.subjects, self.bindings)

    def test_list_includes_unbound_subjects_and_status_starts_unbound(self):
        self.assertIsNone(self.service.status(self.channel))
        rows = self.service.list_subjects(1)
        self.assertEqual([(row.subject.id.value, row.channel_ids) for row in rows],
                         [("math", ()), ("cs", ())])

    def test_binding_is_visible_in_status_and_list_with_new_service(self):
        self.service.bind(self.channel, SubjectId("math"))
        restarted = self.create_service()
        self.assertEqual(restarted.status(self.channel).name, "Mathematics")
        self.assertEqual(restarted.list_subjects(1)[0].channel_ids, (10,))

    def test_rebinding_changes_only_current_channel(self):
        self.service.bind(self.channel, SubjectId("math"))
        self.service.bind(ChannelRef(1, 11), SubjectId("math"))
        self.service.bind(self.channel, SubjectId("cs"))
        rows = self.service.list_subjects(1)
        self.assertEqual([row.channel_ids for row in rows], [(11,), (10,)])

    def test_unknown_subject_does_not_replace_existing_binding(self):
        self.service.bind(self.channel, SubjectId("math"))
        with self.assertRaises(UnknownSubject):
            self.service.bind(self.channel, SubjectId("missing"))
        self.assertEqual(self.service.status(self.channel).id, SubjectId("math"))

    def test_repeated_bind_is_idempotent_and_servers_are_isolated(self):
        self.service.bind(self.channel, SubjectId("math"))
        self.service.bind(self.channel, SubjectId("math"))
        self.assertEqual(self.service.list_subjects(1)[0].channel_ids, (10,))
        self.assertEqual(self.service.list_subjects(2)[0].channel_ids, ())
        self.assertIsNone(self.service.status(ChannelRef(2, 10)))

    def test_empty_catalog_and_removed_subject_keep_binding_truthful(self):
        self.service.bind(self.channel, SubjectId("math"))
        self.subjects.subjects = ()
        self.assertEqual(self.service.list_subjects(1), ())
        status = self.service.status(self.channel)
        self.assertEqual(status.id, SubjectId("math"))
        self.assertIn("unavailable", status.name.lower())

    def test_source_failure_does_not_change_existing_binding(self):
        self.service.bind(self.channel, SubjectId("math"))
        self.subjects.error = RuntimeError("API unavailable")
        with self.assertRaises(RuntimeError):
            self.service.bind(self.channel, SubjectId("cs"))
        self.assertEqual(self.bindings.for_guild(1), {10: SubjectId("math")})


if __name__ == "__main__":
    unittest.main()
