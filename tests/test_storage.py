import json
import unittest
from unittest.mock import Mock, patch

from queryfi.courses import ChannelRef, SubjectId
from queryfi.http import JsonHttp, ServiceError
from queryfi.storage import OpenNotebookSubjects, SurrealBindings


class NotebookTests(unittest.TestCase):
    def setUp(self):
        self.http = Mock()
        self.subjects = OpenNotebookSubjects(self.http)

    def test_notebook_ids_are_preserved_and_names_can_change(self):
        self.http.request.return_value = [{"id": "notebook:abc", "name": "Algebra"}]
        before = self.subjects.list_subjects()[0]
        self.http.request.return_value[0]["name"] = "Linear Algebra"
        after = self.subjects.list_subjects()[0]
        self.assertEqual(before.id, SubjectId("notebook:abc"))
        self.assertEqual(before.id, after.id)
        self.assertEqual(after.name, "Linear Algebra")
        self.http.request.assert_called_with("GET", "/api/notebooks")

    def test_empty_catalog_is_valid_but_malformed_or_duplicate_catalog_is_rejected(self):
        self.http.request.return_value = []
        self.assertEqual(self.subjects.list_subjects(), ())
        for response in ({}, [None], [{"id": "notebook:a"}],
                         [{"id": 1, "name": "A"}], [{"id": "notebook:a", "name": ""}],
                         [{"id": "notebook:a", "name": "A"}] * 2):
            with self.subTest(response=response):
                self.http.request.return_value = response
                with self.assertRaises(ValueError):
                    self.subjects.list_subjects()


class SurrealTests(unittest.TestCase):
    def setUp(self):
        self.http = Mock()
        self.store = SurrealBindings(self.http)

    def reply(self, result):
        self.http.request.return_value = {"result": [{"status": "OK", "result": result}]}

    def test_lists_only_requested_guild_and_preserves_snowflake_precision(self):
        self.reply([{"channel_id": "1234567890123456789", "notebook_id": "notebook:abc"}])
        self.assertEqual(self.store.for_guild(42), {1234567890123456789: SubjectId("notebook:abc")})
        query, variables = self.http.request.call_args.args[2]["params"]
        self.assertIn("WHERE guild_id = $guild_id", query)
        self.assertEqual(variables, {"guild_id": "42"})

    def test_binding_uses_one_atomic_upsert_with_parameterized_notebook_id(self):
        self.reply([{"notebook_id": "notebook:abc"}])
        self.store.bind(ChannelRef(42, 1234567890123456789), SubjectId("notebook:abc"))
        method, path, payload = self.http.request.call_args.args
        self.assertEqual((method, path, payload["method"]), ("POST", "/rpc", "query"))
        query, variables = payload["params"]
        self.assertIn("UPSERT", query)
        self.assertNotIn("notebook:abc", query)
        self.assertEqual(variables["binding_id"], "42_1234567890123456789")
        self.assertEqual(variables["notebook_id"], "notebook:abc")
        self.http.request.assert_called_once()

    def test_rpc_and_statement_errors_and_empty_writes_are_not_success(self):
        for response in ({"error": {"message": "denied"}},
                         {"result": [{"status": "ERR", "result": "denied"}]},
                         {"result": []}, {"result": [{"status": "OK", "result": []}]}):
            with self.subTest(response=response):
                self.http.request.return_value = response
                with self.assertRaises(ServiceError):
                    self.store.bind(ChannelRef(1, 10), SubjectId("notebook:a"))


class HttpTests(unittest.TestCase):
    @patch("queryfi.http.urlopen")
    def test_sends_headers_json_and_timeout(self, open_url):
        open_url.return_value.__enter__.return_value.read.return_value = b'{"result": []}'
        client = JsonHttp("http://localhost:8000/", {"Authorization": "Basic test", "surreal-ns": "n"})
        self.assertEqual(client.request("POST", "/rpc", {"method": "query"}), {"result": []})
        request = open_url.call_args.args[0]
        self.assertEqual(request.full_url, "http://localhost:8000/rpc")
        self.assertEqual(json.loads(request.data), {"method": "query"})
        self.assertEqual(request.get_header("Authorization"), "Basic test")
        self.assertEqual(open_url.call_args.kwargs["timeout"], 15)

    @patch("queryfi.http.urlopen")
    def test_timeout_is_reported_without_credentials(self, open_url):
        open_url.side_effect = TimeoutError("secret")
        with self.assertRaises(ServiceError) as caught:
            JsonHttp("http://localhost:5055").request("GET", "/api/notebooks")
        self.assertNotIn("secret", str(caught.exception))
