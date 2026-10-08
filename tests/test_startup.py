import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bot import main


class StartupTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        root_patch = patch("bot.ROOT", self.root)
        root_patch.start()
        self.addCleanup(root_patch.stop)
        service_patch = patch("bot.create_service")
        self.create_service = service_patch.start()
        self.addCleanup(service_patch.stop)

    def test_loads_discord_settings_from_dotenv_beside_script(self):
        (self.root / ".env").write_text(
            '# Discord settings\nDISCORD_TOKEN="file-token"\n',
            encoding="utf-8",
        )
        with patch.dict("os.environ", {}, clear=True), patch("bot.CourseBot") as bot:
            main()
        self.assertEqual(len(bot.call_args.args), 1)
        bot.return_value.run.assert_called_once_with("file-token", log_handler=None)
        self.create_service.return_value.list_subjects.assert_called_once_with(0)

    def test_existing_environment_takes_precedence_over_dotenv(self):
        (self.root / ".env").write_text(
            "DISCORD_TOKEN=file-token\n", encoding="utf-8",
        )
        environment = {"DISCORD_TOKEN": "environment-token"}
        with patch.dict("os.environ", environment, clear=True), patch("bot.CourseBot") as bot:
            main()
        bot.return_value.run.assert_called_once_with("environment-token", log_handler=None)

    def test_missing_token_exits_before_connecting(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(SystemExit, "DISCORD_TOKEN"):
                main()

    def test_service_failure_exits_before_discord_login(self):
        self.create_service.return_value.list_subjects.side_effect = RuntimeError("SurrealDB unavailable")
        with patch.dict("os.environ", {"DISCORD_TOKEN": "token"}, clear=True), patch("bot.CourseBot") as bot:
            with self.assertRaisesRegex(SystemExit, "SurrealDB unavailable"):
                main()
        bot.assert_not_called()
