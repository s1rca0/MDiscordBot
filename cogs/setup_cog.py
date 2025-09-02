# cogs/setup_cog.py
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from config import BotConfig

cfg = BotConfig()


def _fmt_bool(v: bool | None) -> str:
    if v is None:
        return "—"
    return "Enabled ✅" if v else "Disabled ⛔"


def _fmt_channel(guild: discord.Guild, chan_id: int | None) -> str:
    if not chan_id:
        return "—"
    ch = guild.get_channel(chan_id)
    if isinstance(ch, (discord.TextChannel, discord.VoiceChannel, discord.StageChannel, discord.ForumChannel)):
        return ch.mention
    # If ID doesn’t resolve in this guild, show the raw ID (helps debug)
    return f"`#{chan_id}` (not found here)"


class SetupCog(commands.Cog):
    """Admin setup/status for M.O.R.P.H.E.U.S."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------- UI helpers ----------
    def _status_embed(self, guild: discord.Guild) -> discord.Embed:
        e = discord.Embed(
            title="M.O.R.P.H.E.U.S. • Setup Status",
            color=cfg.DEFAULT_EMBED_COLOR,
        )
        e.set_thumbnail(url=getattr(guild.icon, "url", discord.Embed.Empty))

        # Core
        e.add_field(
            name="Core",
            value=(
                f"Owner: {f'<@{cfg.OWNER_USER_ID}>' if cfg.OWNER_USER_ID else '—'}\n"
                f"Provider: `{cfg.PROVIDER}`\n"
                f"Default AI mode: `{cfg.AI_MODE_DEFAULT}`"
            ),
            inline=False,
        )

        # Feature flags
        e.add_field(
            name="Features",
            value=(
                f"Invites: {_fmt_bool(cfg.ENABLE_INVITES)}\n"
                f"Meme Feed: {_fmt_bool(cfg.ENABLE_MEME_FEED)}\n"
                f"Disaster Tools: {_fmt_bool(cfg.ENABLE_DISASTER_TOOLS)}"
            ),
            inline=False,
        )

        # Optional channels
        e.add_field(
            name="Channels",
            value=(
                f"Welcome: {_fmt_channel(guild, cfg.WELCOME_CHANNEL_ID)}\n"
                f"YouTube Announcements: {_fmt_channel(guild, cfg.YT_ANNOUNCE_CHANNEL_ID)}\n"
                f"Support: {_fmt_channel(guild, cfg.SUPPORT_CHANNEL_ID)}"
            ),
            inline=False,
        )

        # Invites
        e.add_field(
            name="Server Invite",
            value=cfg.SERVER_INVITE_URL or "—",
            inline=False,
        )

        # VoidPulse snapshot
        e.add_field(
            name="VoidPulse",
            value=(
                f"Cooldown: `{cfg.VOID_COOLDOWN_HOURS}h`\n"
                f"Title: `{cfg.VOID_TITLE}`\n"
                f"Message: `{cfg.VOID_MSG}`"
            ),
            inline=False,
        )

        # Meme feed snapshot
        e.add_field(
            name="Meme Feed",
            value=(
                f"Target: {_fmt_channel(guild, cfg.MEME_CHANNEL_ID)}\n"
                f"Interval: `{cfg.MEME_INTERVAL_MIN} min`"
            ),
            inline=False,
        )

        e.set_footer(text="Tip: Unset values show as — and are perfectly fine.")
        return e

    # ---------- Commands ----------
    @app_commands.command(name="setup", description="Show bot setup status (admin).")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setup_panel(self, interaction: discord.Interaction):
        """Ephemeral admin status panel; works even if optional IDs are unset."""
        await interaction.response.send_message(
            embed=self._status_embed(interaction.guild),
            ephemeral=True,
        )

    # Optional quick test to confirm the bot can reply
    @app_commands.command(name="ping", description="M.O.R.P.H.E.U.S. self-check.")
    async def ping(self, interaction: discord.Interaction):
        await interaction.response.send_message("The grid is awake. ✅", ephemeral=True)

    # ---------- Error handling ----------
    @setup_panel.error
    async def setup_panel_error(self, interaction: discord.Interaction, error: Exception):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "You need **Manage Server** to use `/setup`.", ephemeral=True
            )
            return
        # Fallback
        msg = f"Setup encountered an issue: `{type(error).__name__}`"
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(SetupCog(bot))