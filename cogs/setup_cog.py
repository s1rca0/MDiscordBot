# cogs/setup_cog.py
from __future__ import annotations
import discord
from discord import app_commands
from discord.ext import commands
from config import cfg

def _yn(v: bool) -> str:
    return "✅ On" if v else "❌ Off"

class SetupCog(commands.Cog):
    """Lightweight /setup that does not require any channel IDs to exist."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="setup", description="Show current bot configuration status.")
    async def setup(self, interaction: discord.Interaction) -> None:
        cfg.validate_core()

        embed = discord.Embed(
            title="M.O.R.P.H.E.U.S. • Setup Overview",
            color=discord.Color.blurple(),
            description=(
                "Here’s the current configuration. Everything is stateless and safe for Railway Hobby.\n"
                "Optional features are disabled when their IDs aren’t set."
            ),
        )
        embed.add_field(name="AI Provider", value=cfg.PROVIDER or "—", inline=True)
        embed.add_field(name="Mode", value=cfg.AI_MODE_DEFAULT, inline=True)
        embed.add_field(name="Logging", value=("stdout only" if not cfg.LOG_FILE else cfg.LOG_FILE), inline=True)

        # Invites
        inv = cfg.SERVER_INVITE_URL or "Not set"
        embed.add_field(name="Invites Enabled", value=_yn(cfg.ALLOW_INVITES), inline=True)
        embed.add_field(name="Server Invite", value=inv, inline=True)

        # Meme feed
        meme_channel = f"<#{cfg.MEME_CHANNEL_ID}>" if cfg.MEME_CHANNEL_ID else "Not set"
        embed.add_field(name="Meme Feed", value=_yn(cfg.MEMES_ENABLED), inline=True)
        embed.add_field(name="Meme Channel", value=meme_channel, inline=True)

        # YT announcements
        yt_channel = f"<#{cfg.YT_ANNOUNCE_CHANNEL_ID}>" if cfg.YT_ANNOUNCE_CHANNEL_ID else "Not set"
        embed.add_field(name="YT Announce Channel", value=yt_channel, inline=True)

        # Tickets
        ticket_home = f"<#{cfg.TICKET_HOME_CHANNEL_ID}>" if cfg.TICKET_HOME_CHANNEL_ID else "Not set"
        embed.add_field(name="Tickets/Home", value=ticket_home, inline=True)

        embed.set_footer(text="Tip: You can run /setup anytime. No filesystem needed.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(SetupCog(bot))