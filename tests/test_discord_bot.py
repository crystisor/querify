import unittest
from unittest.mock import AsyncMock, Mock, patch

import discord

from queryfi.courses import ChannelRef, CourseService, Subject, SubjectId
from queryfi.conversations import ConversationOwner
from queryfi.discord_bot import CourseBot, split_message
from queryfi.search import SearchError, SearchQuery, SearchResult
from fakes import MemorySubjects, MemoryBindings


class DiscordCommandTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.subjects = MemorySubjects()
        self.bindings = MemoryBindings()
        self.service = CourseService(self.subjects, self.bindings)
        self.prompts = Mock()
        self.search = Mock()
        self.bot = CourseBot(self.service, self.prompts, self.search)
        self.addAsyncCleanup(self.bot.close)
        self.interaction = Mock()
        self.interaction.guild_id = 1
        self.interaction.user.id = 1234567890123456789
        self.interaction.channel = Mock(spec=discord.TextChannel)
        self.interaction.channel.id = 10
        self.interaction.response.defer = AsyncMock()
        self.interaction.response.send_message = AsyncMock()
        self.interaction.edit_original_response = AsyncMock()
        self.interaction.followup.send = AsyncMock()

    async def invoke(self, name, *args):
        command = self.bot.tree.get_command(name)
        await command.callback(self.interaction, *args)

    def response_text(self):
        return self.interaction.edit_original_response.call_args.kwargs["content"]

    async def test_all_three_commands_work_for_regular_members(self):
        await self.invoke("status")
        self.assertIn("not bound", self.response_text())
        await self.invoke("bind", "math")
        self.assertIn("Mathematics", self.response_text())
        await self.invoke("status")
        self.assertIn("math", self.response_text())
        await self.invoke("list")
        self.assertIn("<\u002310>", self.response_text())
        self.assertIn("Mathematics", self.response_text())
        self.interaction.response.defer.assert_awaited()

    async def test_unknown_id_explains_how_to_find_valid_ids(self):
        await self.invoke("bind", "unknown")
        self.assertIn("/list", self.response_text())
        self.assertIsNone(self.service.status(ChannelRef(1, 10)))

    async def test_blank_subject_id_gives_actionable_private_response(self):
        await self.invoke("bind", "   ")
        response = self.interaction.response.send_message.call_args
        self.assertIn("/list", response.args[0])
        self.assertTrue(response.kwargs["ephemeral"])
        self.assertIsNone(self.service.status(ChannelRef(1, 10)))

    async def test_dm_and_non_text_channels_cannot_bind(self):
        for channel in (None, Mock(spec=discord.VoiceChannel), Mock(spec=discord.Thread)):
            self.interaction.channel = channel
            await self.invoke("bind", "math")
        self.assertIsNone(self.service.status(ChannelRef(1, 10)))
        self.interaction.response.defer.assert_not_awaited()
        self.assertTrue(self.interaction.response.send_message.call_args.kwargs["ephemeral"])

    async def test_commands_are_synced_globally_but_only_usable_in_servers(self):
        self.bot.tree.sync = AsyncMock()
        await self.bot.setup_hook()
        self.bot.tree.sync.assert_awaited_once_with()
        commands = self.bot.tree.get_commands()
        self.assertEqual({command.name for command in commands}, {"list", "status", "bind", "start", "end", "search"})
        self.assertTrue(all(command.guild_only for command in commands))
        self.assertEqual(self.bot.tree.get_commands(guild=discord.Object(id=1)), [])

    async def test_global_commands_use_invoking_server_for_bindings(self):
        await self.invoke("bind", "math")
        self.interaction.guild_id = 2
        await self.invoke("status")
        self.assertIn("not bound", self.response_text())
        await self.invoke("bind", "math")
        self.assertEqual(self.service.status(ChannelRef(1, 10)).id, SubjectId("math"))
        self.assertEqual(self.service.status(ChannelRef(2, 10)).id, SubjectId("math"))

    async def test_source_failure_returns_error_and_preserves_binding(self):
        self.service.bind(ChannelRef(1, 10), SubjectId("math"))
        self.subjects.error = RuntimeError("API unavailable")
        with self.assertLogs("queryfi.discord_bot", level="ERROR"):
            await self.invoke("bind", "math")
        self.assertIn("could not", self.response_text())
        self.subjects.error = None
        self.assertEqual(self.service.status(ChannelRef(1, 10)).id, SubjectId("math"))

    async def test_long_lists_are_split_without_dropping_subjects(self):
        self.subjects.subjects = tuple(
            Subject(SubjectId(str(index)), "A course subject") for index in range(150)
        )
        await self.invoke("list")
        messages = [self.response_text()] + [
            call.kwargs["content"] for call in self.interaction.followup.send.call_args_list
        ]
        self.assertTrue(all(len(message) <= 2000 for message in messages))
        combined = "".join(messages)
        self.assertIn("149", combined)
        self.assertEqual(combined.count("not bound"), 150)

    async def test_database_write_failure_never_reports_success(self):
        with patch.object(self.bindings, "bind", side_effect=RuntimeError("Database unavailable")):
            with self.assertLogs("queryfi.discord_bot", level="ERROR"):
                await self.invoke("bind", "math")
        self.assertIn("could not", self.response_text())
        self.assertIsNone(self.service.status(ChannelRef(1, 10)))

    async def test_conversation_commands_use_callers_user_and_channel(self):
        owner = ConversationOwner(ChannelRef(1, 10), 1234567890123456789)
        for command, method in (("start", self.prompts.start), ("end", self.prompts.end)):
            method.return_value = "Conversation response"
            await self.invoke(command)
            method.assert_called_once_with(owner)
            self.assertEqual(self.response_text(), "Conversation response")

    async def test_conversation_commands_reject_dms_and_threads(self):
        self.interaction.channel = Mock(spec=discord.Thread)
        for command in ("start", "end"):
            await self.invoke(command)
        self.prompts.start.assert_not_called()
        self.prompts.end.assert_not_called()

    async def test_conversation_command_failure_never_reports_success(self):
        self.prompts.start.side_effect = RuntimeError("database offline")
        with self.assertLogs("queryfi.discord_bot", level="ERROR"):
            await self.invoke("start")
        self.assertIn("could not", self.response_text())

    def test_unicode_splitting_preserves_content_within_character_threshold(self):
        content = "\U0001f600" * 3000
        chunks = split_message(content)
        self.assertEqual("".join(chunks), content)
        self.assertTrue(all(len(chunk) <= 1500 for chunk in chunks))

    async def test_search_works_in_unbound_channel_without_touching_conversations(self):
        self.search.search.return_value = (
            SearchResult("Python tutorial", "https://docs.python.org/3/", "Learn Python", ("searxng", "youcom")),
        )
        await self.invoke("search", "  Python tutorials  ")
        self.search.search.assert_called_once_with(SearchQuery("Python tutorials"))
        content = self.response_text()
        for expected in ("Python tutorials", "Python tutorial", "https://docs.python.org/3/", "Learn Python", "searxng", "youcom"):
            self.assertIn(expected, content)
        self.interaction.response.defer.assert_awaited_once_with(thinking=True)
        self.assertEqual(self.prompts.mock_calls, [])
        self.assertIsNone(self.service.status(ChannelRef(1, 10)))

    async def test_search_option_is_required_and_limits_query_length(self):
        parameter, = self.bot.tree.get_command("search").parameters
        self.assertEqual(parameter.name, "query")
        self.assertTrue(parameter.required)
        self.assertEqual((parameter.min_value, parameter.max_value), (1, 500))

    async def test_search_rejects_invalid_query_before_calling_provider(self):
        for query in ("  ", "x" * 501, "bad\0query"):
            await self.invoke("search", query)
        self.search.search.assert_not_called()
        self.interaction.response.defer.assert_not_awaited()
        self.assertTrue(self.interaction.response.send_message.call_args.kwargs["ephemeral"])

    async def test_search_rejects_dms_and_non_text_channels(self):
        for channel in (None, Mock(spec=discord.Thread), Mock(spec=discord.VoiceChannel)):
            self.interaction.channel = channel
            await self.invoke("search", "Python")
        self.interaction.channel = Mock(spec=discord.TextChannel)
        self.interaction.guild_id = None
        await self.invoke("search", "Python")
        self.search.search.assert_not_called()
        self.interaction.response.defer.assert_not_awaited()

    async def test_search_empty_results_are_explained(self):
        self.search.search.return_value = ()
        await self.invoke("search", "rare phrase")
        self.assertIn("No web results", self.response_text())

    async def test_search_expected_failures_are_actionable_and_unexpected_failures_are_private(self):
        self.search.search.side_effect = SearchError("Web search timed out. Please try again.")
        await self.invoke("search", "Python")
        self.assertIn("timed out", self.response_text())
        self.search.search.side_effect = RuntimeError("secret key")
        with self.assertLogs("queryfi.discord_bot", level="ERROR"):
            await self.invoke("search", "Python")
        self.assertIn("could not", self.response_text())
        self.assertNotIn("secret key", self.response_text())

    async def test_search_splits_long_results_escapes_markdown_and_suppresses_mentions(self):
        self.search.search.return_value = tuple(
            SearchResult(f"**Title {index}** @everyone", f"https://example.com/{index}?q=<@123>",
                         "A long snippet " * 100, ("searxng",)) for index in range(5)
        )
        await self.invoke("search", "**query** @everyone")
        calls = [self.interaction.edit_original_response.call_args, *self.interaction.followup.send.call_args_list]
        self.assertGreater(len(calls), 1)
        for call in calls:
            self.assertLessEqual(len(call.kwargs["content"]), 2000)
            self.assertEqual(call.kwargs["allowed_mentions"].to_dict(), discord.AllowedMentions.none().to_dict())
        combined = "".join(call.kwargs["content"] for call in calls)
        self.assertIn(r"\*\*Title 4\*\*", combined)
        self.assertNotIn("@everyone", combined)
        self.assertNotIn("<@123>", combined)


if __name__ == "__main__":
    unittest.main()
