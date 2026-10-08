"""Opt-in checks against the configured Open Notebook and SurrealDB services."""

import os
from pathlib import Path
import unittest
import uuid

from dotenv import dotenv_values

from queryfi.config import create_service, database_authorization
from queryfi.courses import ChannelRef, UnknownSubject, SubjectId
from queryfi.http import JsonHttp


@unittest.skipUnless(os.environ.get("QUERYFI_LIVE_TEST") == "1", "Set QUERYFI_LIVE_TEST=1 to test live storage")
class LiveStorageTests(unittest.TestCase):
    def test_binding_persists_rebinds_and_isolates_servers(self):
        environment = {**dotenv_values(Path(__file__).resolve().parents[1] / ".env"), **os.environ}
        service = create_service(environment)
        guild_id = uuid.uuid4().int % (2**62) + 1
        channels = (ChannelRef(guild_id, 1), ChannelRef(guild_id, 2), ChannelRef(guild_id + 1, 1))
        http = JsonHttp(environment["SURREAL_URL"], {
            "surreal-ns": environment["SURREAL_NAMESPACE"],
            "surreal-db": environment["SURREAL_DATABASE"],
            "Authorization": database_authorization(environment),
        })
        subjects = service.list_subjects(guild_id)
        self.assertGreaterEqual(len(subjects), 2, "This live check needs two existing notebooks.")
        first, second = (row.subject for row in subjects[:2])
        self.assertIsNone(service.status(channels[0]))
        try:
            service.bind(channels[0], first.id)
            service.bind(channels[0], first.id)
            service.bind(channels[1], first.id)
            service.bind(channels[2], first.id)
            restarted = create_service(environment)
            self.assertEqual(restarted.status(channels[0]), first)
            restarted.bind(channels[0], second.id)
            self.assertEqual(service.status(channels[0]), second)
            self.assertEqual(service.status(channels[1]), first)
            self.assertEqual(service.status(channels[2]), first)
            with self.assertRaises(UnknownSubject):
                restarted.bind(channels[0], SubjectId("notebook:queryfi_missing_" + uuid.uuid4().hex))
            self.assertEqual(service.status(channels[0]), second)
            bindings = {row.subject.id: row.channel_ids for row in restarted.list_subjects(guild_id)}
            self.assertEqual(bindings[first.id], (2,))
            self.assertEqual(bindings[second.id], (1,))
        finally:
            for channel in channels:
                response = http.request("POST", "/rpc", {
                    "id": 1, "method": "query", "params": [
                        "DELETE type::thing('queryfi_channel_binding', $binding_id);",
                        {"binding_id": f"{channel.guild_id}_{channel.channel_id}"},
                    ],
                })
                self.assertEqual(response["result"][0]["status"], "OK")
        self.assertIsNone(create_service(environment).status(channels[0]))
