# cogs/health_cog.py
import os
import time
import platform
from typing import Optional

import discord
from discord.ext import commands
from discord import app_commands

try:
    import psutil  # optional, for memory stats if available
except Exception:
    psutil = None


# Helper: format seconds as human-readable uptime
def _fmt_uptime(seconds: float) -> str:
    seconds = int(seconds)
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours or parts:
        parts.append(f"{hours}h")
    if minutes or parts:
        parts.append(f"{minutes}m")
    parts.append(f"{seconds}s")
    return " ".join(parts)


class HealthCog(commands.Cog):
    """Owner-only health diagnostics and a public /ping."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Use bot attr if already set by other code, otherwise now.
        self.start_ts: float = getattr(bot, "_start_ts", time.time())
        setattr(bot, "_start_ts", self.start_ts)

        # Owner ID from env (or 0 if unset)
        self.owner_id: int = int(os.getenv("OWNER_USER_ID", "0") or 0)

    # ------------------ commands ------------------

    @app_commands.command(name="health", description="(Owner) Bot health & diagnostics")
    async def health(self, interaction: discord.Interaction):
        # Gate: owner only
        if not self.owner_id or int(interaction.user.id) != self.owner_id:
            await interaction.response.send_message(
                "Only the owner can run this.", ephemeral=True
            )
            return

        # Metrics
        latency_ms = int((self.bot.latency or 0.0) * 1000)
        uptime_s = time.time() - self.start_ts
        uptime_str = _fmt_uptime(uptime_s)

        guild_count = len(self.bot.guilds)
        member_count = 0
        try:
            # Sum known member_count per guild; fallback 0 if not available
            member_count = sum((g.member_count or 0) for g in self.bot.guilds)
        except Exception:
            pass

        cog_count = len(self.bot.cogs)

        py_ver = platform.python_version()
        dpy_ver = discord.__version__

        mem_line: Optional[str] = None
        if psutil:
            try:
                proc = psutil.Process()
                rss_mb = proc.memory_info().rss / (1024 * 1024)
                mem_line = f"{rss_mb:.1f} MiB"
            except Exception:
                pass

        embed = discord.Embed(
            title="Morpheus: System Health",
            color=discord.Color.blurple(),
        )
        embed.add_field(name="Latency", value=f"{latency_ms} ms", inline=True)
        embed.add_field(name="Uptime", value=uptime_str, inline=True)
        embed.add_field(name="Cogs Loaded", value=str(cog_count), inline=True)

        embed.add_field(name="Guilds", value=str(guild_count), inline=True)
        embed.add_field(name="Members (cached)", value=str(member_count), inline=True)
        if mem_line:
            embed.add_field(name="Process Memory", value=mem_line, inline=True)

        embed.add_field(name="Python", value=py_ver, inline=True)
        embed.add_field(name="discord.py", value=dpy_ver, inline=True)

        embed.set_footer(text=f"Owner ID: {self.owner_id}")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="ping", description="Check if Morpheus is responsive.")
    async def ping(self, interaction: discord.Interaction):
        latency_ms = int((self.bot.latency or 0.0) * 1000)
        await interaction.response.send_message(f"Pong — {latency_ms} ms.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(HealthCog(bot))