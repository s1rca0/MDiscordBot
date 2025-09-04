# cogs/command_hub_cog.py
from __future__ import annotations
import discord
from discord import app_commands
from discord.ext import commands

def _no_cog(itx: discord.Interaction, name: str):
    return itx.response.send_message(
        f"⛔ Required module `{name}` isn’t loaded. Check logs or /setup.", ephemeral=True
    )

class CommandHubCog(commands.Cog, name="Command Hub"):
    """
    Collapses scattered root slash commands into grouped roots to stay under the 100-cmd cap.
    Each subcommand delegates to existing cogs so you don’t have to rewrite them.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # -------------------- MEMES --------------------
    memes = app_commands.Group(name="memes", description="Meme feed controls")

    @memes.command(name="config", description="Show meme feed settings")
    async def memes_config(self, itx: discord.Interaction):
        cog = self.bot.get_cog("Meme Feed")
        if not cog: return await _no_cog(itx, "Meme Feed")
        await cog.memes_config(itx)  # delegate

    @memes.command(name="start", description="Enable scheduled memes in a channel")
    @app_commands.describe(channel="Channel to post in", interval_min="Minutes between posts (>=15)")
    async def memes_start(self, itx: discord.Interaction, channel: discord.TextChannel, interval_min: int = 120):
        cog = self.bot.get_cog("Meme Feed")
        if not cog: return await _no_cog(itx, "Meme Feed")
        await cog.memes_start(itx, channel, interval_min)

    @memes.command(name="stop", description="Disable scheduled memes")
    async def memes_stop(self, itx: discord.Interaction):
        cog = self.bot.get_cog("Meme Feed")
        if not cog: return await _no_cog(itx, "Meme Feed")
        await cog.memes_stop(itx)

    @memes.command(name="now", description="Post one meme now")
    async def memes_now(self, itx: discord.Interaction):
        cog = self.bot.get_cog("Meme Feed")
        if not cog: return await _no_cog(itx, "Meme Feed")
        await cog.memes_now(itx)

    # -------------------- VOID PULSE --------------------
    voidpulse = app_commands.Group(name="voidpulse", description="#void cryptic pulse")

    @voidpulse.command(name="status", description="Show current #void pulse status")
    async def voidpulse_status(self, itx: discord.Interaction):
        cog = self.bot.get_cog("Void Pulse")
        if not cog: return await _no_cog(itx, "Void Pulse")
        await cog.voidpulse_status(itx)

    @voidpulse.command(name="set_channel", description="Set target channel for #void pulse")
    async def voidpulse_set_channel(self, itx: discord.Interaction, channel: discord.TextChannel):
        cog = self.bot.get_cog("Void Pulse")
        if not cog: return await _no_cog(itx, "Void Pulse")
        await cog.voidpulse_set_channel(itx, channel)

    @voidpulse.command(name="toggle", description="Enable/disable the scheduled #void pulse")
    async def voidpulse_toggle(self, itx: discord.Interaction):
        cog = self.bot.get_cog("Void Pulse")
        if not cog: return await _no_cog(itx, "Void Pulse")
        await cog.voidpulse_toggle(itx)

    @voidpulse.command(name="nudge", description="Send a one-off #void pulse now")
    async def voidpulse_nudge(self, itx: discord.Interaction):
        cog = self.bot.get_cog("Void Pulse")
        if not cog: return await _no_cog(itx, "Void Pulse")
        await cog.voidpulse_nudge(itx)

    # -------------------- CHAT --------------------
    chat = app_commands.Group(name="chat", description="Channel-chat controls")

    @chat.command(name="status", description="Show channel chat status")
    async def chat_status(self, itx: discord.Interaction):
        cog = self.bot.get_cog("Chat Control")
        if not cog: return await _no_cog(itx, "Chat Control")
        await cog.chat_status.callback(cog, itx)  # hybrid wrappers use .callback

    @chat.command(name="on", description="Enable channel chat")
    async def chat_on(self, itx: discord.Interaction):
        cog = self.bot.get_cog("Chat Control")
        if not cog: return await _no_cog(itx, "Chat Control")
        await cog.chat_on.callback(cog, itx)

    @chat.command(name="off", description="Disable channel chat")
    async def chat_off(self, itx: discord.Interaction):
        cog = self.bot.get_cog("Chat Control")
        if not cog: return await _no_cog(itx, "Chat Control")
        await cog.chat_off.callback(cog, itx)

    @chat.command(name="set_channel", description="Set the channel for Morpheus chat")
    async def chat_set_channel(self, itx: discord.Interaction, channel: discord.TextChannel):
        cog = self.bot.get_cog("Chat Control")
        if not cog: return await _no_cog(itx, "Chat Control")
        await cog.chat_set_channel.callback(cog, itx, channel)

    @chat.command(name="clear", description="Clear the configured chat channel")
    async def chat_clear(self, itx: discord.Interaction):
        cog = self.bot.get_cog("Chat Control")
        if not cog: return await _no_cog(itx, "Chat Control")
        await cog.chat_channel_clear.callback(cog, itx)

    # -------------------- PRESENCE --------------------
    presence = app_commands.Group(name="presence", description="Presence/status cycles")

    @presence.command(name="on", description="Turn presence cycle on")
    async def presence_on(self, itx: discord.Interaction):
        cog = self.bot.get_cog("Presence")
        if not cog: return await _no_cog(itx, "Presence")
        await cog.presence_on(itx)

    @presence.command(name="off", description="Turn presence cycle off")
    async def presence_off(self, itx: discord.Interaction):
        cog = self.bot.get_cog("Presence")
        if not cog: return await _no_cog(itx, "Presence")
        await cog.presence_off(itx)

    @presence.command(name="mode", description="Set presence mode (cycle/static)")
    async def presence_mode(self, itx: discord.Interaction, mode: str):
        cog = self.bot.get_cog("Presence")
        if not cog: return await _no_cog(itx, "Presence")
        await cog.presence_mode(itx, mode)

    @presence.command(name="add", description="Add a status line to rotation")
    async def presence_add(self, itx: discord.Interaction, text: str):
        cog = self.bot.get_cog("Presence")
        if not cog: return await _no_cog(itx, "Presence")
        await cog.presence_add(itx, text)

    @presence.command(name="show", description="Show current presence config")
    async def presence_show(self, itx: discord.Interaction):
        cog = self.bot.get_cog("Presence")
        if not cog: return await _no_cog(itx, "Presence")
        await cog.presence_show(itx)

    # -------------------- DIGEST --------------------
    digest = app_commands.Group(name="digest", description="Channel digest")

    @digest.command(name="on", description="Enable digest")
    async def digest_on(self, itx: discord.Interaction):
        cog = self.bot.get_cog("Digest")
        if not cog: return await _no_cog(itx, "Digest")
        await cog.digest_on(itx)

    @digest.command(name="off", description="Disable digest")
    async def digest_off(self, itx: discord.Interaction):
        cog = self.bot.get_cog("Digest")
        if not cog: return await _no_cog(itx, "Digest")
        await cog.digest_off(itx)

    channels = app_commands.Group(parent=digest, name="channels", description="Digest channels")
    @channels.command(name="add", description="Add a channel to the digest")
    async def digest_channels_add(self, itx: discord.Interaction, channel: discord.TextChannel):
        cog = self.bot.get_cog("Digest")
        if not cog: return await _no_cog(itx, "Digest")
        await cog.digest_channels_add(itx, channel)

    @channels.command(name="list", description="List digest channels")
    async def digest_channels_list(self, itx: discord.Interaction):
        cog = self.bot.get_cog("Digest")
        if not cog: return await _no_cog(itx, "Digest")
        await cog.digest_channels_list(itx)

    @digest.command(name="export", description="Export digest data")
    async def export_digest(self, itx: discord.Interaction):
        cog = self.bot.get_cog("Digest")
        if not cog: return await _no_cog(itx, "Digest")
        await cog.export_digest(itx)

    # -------------------- YOUTUBE --------------------
    yt = app_commands.Group(name="yt", description="YouTube tools")

    @yt.command(name="force_check", description="Force a check for new uploads")
    async def yt_force_check(self, itx: discord.Interaction):
        cog = self.bot.get_cog("YouTube")
        if not cog: return await _no_cog(itx, "YouTube")
        await cog.yt_force_check(itx)

    @yt.command(name="overview", description="Show current YT config")
    async def yt_overview(self, itx: discord.Interaction):
        cog = self.bot.get_cog("YouTube")
        if not cog: return await _no_cog(itx, "YouTube")
        await cog.yt_overview(itx)

    @yt.command(name="watch", description="Watch a channel id/url for latest")
    async def yt_watch(self, itx: discord.Interaction, channel: str):
        cog = self.bot.get_cog("YouTube")
        if not cog: return await _no_cog(itx, "YouTube")
        await cog.yt_watch(itx, channel)

    @yt.command(name="post_latest", description="Post latest video now")
    async def yt_post_latest(self, itx: discord.Interaction):
        cog = self.bot.get_cog("YouTube")
        if not cog: return await _no_cog(itx, "YouTube")
        await cog.yt_post_latest(itx)

    # -------------------- ADMIN (light) --------------------
    admin = app_commands.Group(name="admin", description="Light admin shortcuts")

    @admin.command(name="rules_post", description="Post rules (shortcut)")
    async def admin_rules_post(self, itx: discord.Interaction):
        cog = self.bot.get_cog("Rules")
        if not cog: return await _no_cog(itx, "Rules")
        await cog.rules_post(itx)

    @admin.command(name="set_log_channel", description="Set current channel as mod log")
    async def admin_set_log_channel(self, itx: discord.Interaction):
        cog = self.bot.get_cog("Moderation")
        if not cog: return await _no_cog(itx, "Moderation")
        # call the hybrid command's callback directly
        await cog.setlogchannel.callback(cog, await commands.Context.from_interaction(itx))

async def setup(bot: commands.Bot):
    await bot.add_cog(CommandHubCog(bot))