import base64
import unittest
from unittest.mock import patch

from queryfi.config import create_service


class ConfigTests(unittest.TestCase):
    @patch("queryfi.config.JsonHttp")
    def test_wires_notebook_and_database_connections_separately(self, http):
        create_service({"OPEN_NOTEBOOK_URL": "http://localhost:5055",
                        "OPEN_NOTEBOOK_PASSWORD": "api-password",
                        "SURREAL_URL": "http://localhost:8001",
                        "SURREAL_NAMESPACE": "open_notebook", "SURREAL_DATABASE": "open_notebook",
                        "SURREAL_USER": "root", "SURREAL_PASSWORD": "db-password"})
        notebook, database = http.call_args_list
        self.assertEqual(notebook.args, ("http://localhost:5055", {"Authorization": "Bearer api-password"}))
        self.assertEqual(database.args[0], "http://localhost:8001")
        headers = database.args[1]
        self.assertEqual(headers["surreal-ns"], "open_notebook")
        self.assertEqual(headers["surreal-db"], "open_notebook")
        self.assertEqual(base64.b64decode(headers["Authorization"].split()[1]), b"root:db-password")

    def test_missing_database_configuration_is_actionable(self):
        with self.assertRaisesRegex(ValueError, "SURREAL_URL"):
            create_service({})
