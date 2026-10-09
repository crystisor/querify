"""Discord slash commands and message presentation."""

import asyncio
import logging
from collections.abc import Callable

import discord
from discord import app_commands

from .courses import ChannelRef, CourseService, Subject, SubjectId, SubjectListing, UnknownSubject

from .prompts import ChannelAnswers

logger = logging.getLogger(__name__)


def subject_label(subject: Subject) -> str:
    label = f"{subject.id.value} — {subject.name}"
    return discord.utils.escape_markdown(discord.utils.escape_mentions(label))


def list_text(rows: tuple[SubjectListing, ...]) -> str:
    if not rows:
        return "No course subjects are available yet."
    lines = ["Course subjects:"]
    for row in rows:
        channels = ", ".join(f"<#{channel_id}>" for channel_id in row.channel_ids)
        binding = f"bound to {channels}" if channels else "not bound"
        lines.append(f"{subject_label(row.subject)} — {binding}")
    return "\n".join(lines)


def status_text(channel: ChannelRef, subject: Subject | None) -> str:
    if subject is None:
        return f"<#{channel.channel_id}> is not bound to a course subject."
    return f"<#{channel.channel_id}> is bound to {subject_label(subject)}."


def split_message(content: str) -> list[str]:
    chunks = []
    while len(content) > 1500:
        end = content.rfind("\n", 0, 1500) + 1 or 1500
        chunks.append(content[:end])
        content = content[end:]
    if content:
        chunks.append(content)
    return chunks


async def respond(interaction: discord.Interaction, operation: Callable[[ChannelRef], str]) -> None:
    if interaction.guild_id is None or not isinstance(interaction.channel, discord.TextChannel):
        await interaction.response.send_message("Use this command in a server text channel.", ephemeral=True)
        return
    await interaction.response.defer(thinking=True)
    channel = ChannelRef(interaction.guild_id, interaction.channel.id)
    try:
        content = await asyncio.to_thread(operation, channel)
    except UnknownSubject as error:
        content = str(error)
    except Exception:
        logger.exception("Course command failed in guild %s, channel %s", channel.guild_id, channel.channel_id)
        content = "I could not complete that command. Please try again or ask the bot owner to check the logs."
    chunks = split_message(content)
    await interaction.edit_original_response(content=chunks[0], allowed_mentions=discord.AllowedMentions.none())
    for chunk in chunks[1:]:
        await interaction.followup.send(content=chunk, allowed_mentions=discord.AllowedMentions.none())


def register_commands(tree: app_commands.CommandTree, service: CourseService) -> None:
    @tree.command(name="list", description="List course subjects and their bound text channels.")
    @app_commands.guild_only()
    async def list_subjects(interaction: discord.Interaction):
        await respond(interaction, lambda channel: list_text(service.list_subjects(channel.guild_id)))

    @tree.command(name="status", description="Show the course binding of this text channel.")
    @app_commands.guild_only()
    async def status(interaction: discord.Interaction):
        await respond(interaction, lambda channel: status_text(channel, service.status(channel)))

    @tree.command(name="bind", description="Bind this text channel to a course subject by ID.")
    @app_commands.guild_only()
    @app_commands.describe(subject_id="The course subject ID shown by /list")
    async def bind(interaction: discord.Interaction, subject_id: app_commands.Range[str, 1, 100]):
        if not subject_id.strip():
            await interaction.response.send_message("Enter a subject ID from /list.", ephemeral=True)
            return
        await respond(interaction, lambda channel: status_text(
            channel, service.bind(channel, SubjectId(subject_id.strip()))
        ))


class CourseBot(discord.Client):
    def __init__(self, service: CourseService, prompts: ChannelAnswers):
        intents = discord.Intents.none()
        intents.guilds = True
        intents.guild_messages = True
        intents.message_content = True
        super().__init__(intents=intents, allowed_mentions=discord.AllowedMentions.none())
        self.tree = app_commands.CommandTree(self)
        register_commands(self.tree, service)
        self._prompts = prompts

    async def setup_hook(self):
        commands = await self.tree.sync()
        logger.info("Synced %s global commands", len(commands))

    async def on_ready(self):
        logger.info("Logged in as %s", self.user)

    async def on_message(self, message: discord.Message) -> None:
        if (message.author.bot or message.webhook_id is not None or message.guild is None
                or not isinstance(message.channel, discord.TextChannel)
                or message.type not in (discord.MessageType.default, discord.MessageType.reply)
                or not message.content.strip()):
            return
        channel = ChannelRef(message.guild.id, message.channel.id)
        try:
            async with message.channel.typing():
                content = await asyncio.to_thread(self._prompts.answer, channel, message.content)
        except Exception:
            logger.exception("Notebook question failed in guild %s, channel %s", channel.guild_id, channel.channel_id)
            content = "I could not query this notebook. Please try again or ask the bot owner to check Open Notebook and Ollama."
        if content is None:
            return
        for chunk in split_message(content):
            await message.reply(content=chunk, mention_author=False, allowed_mentions=discord.AllowedMentions.none())
