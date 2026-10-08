"""Discord slash commands and message presentation."""

import asyncio
import logging
from collections.abc import Callable

import discord
from discord import app_commands

from .courses import ChannelRef, CourseService, Subject, SubjectId, SubjectListing, UnknownSubject

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
    # 950 code points also fit Discord's limit when every character uses two UTF-16 units.
    chunks = []
    while len(content) > 950:
        end = content.rfind("\n", 0, 950) + 1 or 950
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
    def __init__(self, service: CourseService):
        intents = discord.Intents.none()
        intents.guilds = True
        super().__init__(intents=intents, allowed_mentions=discord.AllowedMentions.none())
        self.tree = app_commands.CommandTree(self)
        register_commands(self.tree, service)

    async def setup_hook(self):
        commands = await self.tree.sync()
        logger.info("Synced %s global commands", len(commands))

    async def on_ready(self):
        logger.info("Logged in as %s", self.user)
