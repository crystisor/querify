import unittest
from unittest.mock import AsyncMock, MagicMock, Mock

import discord

from queryfi.courses import ChannelRef
from queryfi.discord_bot import CourseBot


class DiscordMessageTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.prompts = Mock()
        self.prompts.answer.return_value = "Answer from the notebook"
        self.bot = CourseBot(Mock(), self.prompts)
        self.addAsyncCleanup(self.bot.close)
        self.message = Mock()
        self.message.author.bot = False
        self.message.webhook_id = None
        self.message.guild.id = 1
        self.message.channel = Mock(spec=discord.TextChannel)
        self.message.channel.id = 10
        self.message.channel.typing = MagicMock()
        self.message.content = "Explain matrices"
        self.message.type = discord.MessageType.default
        self.message.reply = AsyncMock()

    async def test_message_is_sent_to_prompt_service_and_answer_replies_without_mentions(self):
        await self.bot.on_message(self.message)
        self.prompts.answer.assert_called_once_with(ChannelRef(1, 10), "Explain matrices")
        reply = self.message.reply.call_args
        self.assertEqual(reply.kwargs["content"], "Answer from the notebook")
        self.assertEqual(reply.kwargs["allowed_mentions"].to_dict(), discord.AllowedMentions.none().to_dict())
        self.assertFalse(reply.kwargs["mention_author"])

    async def test_unbound_channel_has_no_reply(self):
        self.prompts.answer.return_value = None
        await self.bot.on_message(self.message)
        self.message.reply.assert_not_awaited()

    async def test_bot_webhook_dm_thread_system_and_empty_messages_are_ignored(self):
        for attribute, value in (("author", Mock(bot=True)), ("webhook_id", 123),
                                 ("guild", None), ("channel", Mock(spec=discord.Thread)),
                                 ("content", "  "), ("type", discord.MessageType.pins_add)):
            with self.subTest(attribute=attribute):
                original = getattr(self.message, attribute)
                setattr(self.message, attribute, value)
                await self.bot.on_message(self.message)
                setattr(self.message, attribute, original)
        self.prompts.answer.assert_not_called()
        self.message.reply.assert_not_awaited()

    async def test_model_failure_returns_generic_error_without_leaking_details(self):
        self.prompts.answer.side_effect = RuntimeError("secret password")
        with self.assertLogs("queryfi.discord_bot", level="ERROR"):
            await self.bot.on_message(self.message)
        reply = self.message.reply.call_args.kwargs["content"]
        self.assertIn("could not", reply)
        self.assertNotIn("secret", reply)

    async def test_long_answer_is_split_without_losing_text(self):
        answer = "A notebook answer \U0001f600\n" * 300
        self.prompts.answer.return_value = answer
        await self.bot.on_message(self.message)
        chunks = [call.kwargs["content"] for call in self.message.reply.call_args_list]
        self.assertEqual("".join(chunks), answer)
        self.assertTrue(all(len(chunk.encode("utf-16-le")) // 2 <= 2000 for chunk in chunks))

    def test_message_intents_are_enabled(self):
        self.assertTrue(self.bot.intents.guild_messages)
        self.assertTrue(self.bot.intents.message_content)
        self.assertFalse(self.bot.intents.dm_messages)
