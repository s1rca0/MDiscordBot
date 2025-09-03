# cogs/rules_cog.py
from __future__ import annotations
import os
import logging
from typing import Optional, List

import discord
from discord import app_commands
from discord.ext import commands

log = logging.getLogger(__name__)
OWNER_USER_ID = int(os.getenv("OWNER_USER_ID", "0") or 0)
MOD_LOG_CHANNEL_ID = int(os.getenv("MOD_LOG_CHANNEL_ID", "0") or 0)  # optional override

# ---------- helpers ----------

def _find_modlog(guild: discord.Guild) -> Optional[discord.TextChannel]:
    """Resolve #mod-logs (or variants) or use MOD_LOG_CHANNEL_ID if provided."""
    if MOD_LOG_CHANNEL_ID:
        ch = guild.get_channel(MOD_LOG_CHANNEL_ID)
        if isinstance(ch, discord.TextChannel):
            return ch
    # name fallbacks
    name_candidates = ["mod-logs", "modlog", "mod-log", "moderation-logs", "logs"]
    lower_map = {c.name.lower(): c for c in guild.text_channels}
    for n in name_candidates:
        ch = lower_map.get(n)
        if isinstance(ch, discord.TextChannel):
            return ch
    return None

def _tickets_available(bot: commands.Bot) -> bool:
    """Check if Tickets cog is loaded (by class or display name)."""
    # Try by class name
    if bot.get_cog("Tickets"):
        return True
    # Some setups give a display name; check common forms
    for name in ("Tickets", "TicketsCog"):
        if bot.get_cog(name):
            return True
    return False

def _rules_embed(guild: discord.Guild, tickets_ok: bool) -> discord.Embed:
    e = discord.Embed(
        title="📜 Server Rules",
        description=(
            "Welcome to **Legends in Motion HQ**. Keep it sharp, keep it human. "
            "Here’s the short list — use common sense for the rest."
        ),
        color=discord.Color.blurple(),
    )
    lines: List[str] = [
        "1) **Be respectful.** Harassment, hate, or bigotry = no go. 🚫",
        "2) **No *excessive* insults.** Playful roast? Fine. Targeted abuse? **No.** 🧯",
        "3) **Keep it SFW.** No sexual content, gore, or shock. 🧼",
        "4) **No spam.** Flooding, link-dumps, mass pings — don’t. 📵",
        "5) **No external invites.** Don’t advertise other servers. 🔗❌",
        "6) **Privacy matters.** Don’t post dox, private DMs, or personal info. 🔒",
        "7) **Follow Discord ToS & Community Guidelines.** 📘",
    ]
    e.add_field(
        name="The Vibe",
        value=(
            "We like clever, funny, and intense — *not* cruel. "
            "If you’re unsure, **dial it down a notch**."
        ),
        inline=False,
    )
    e.add_field(name="Rules", value="\n".join(lines), inline=False)

    if tickets_ok:
        e.add_field(
            name="Need Help?",
            value="Open a private ticket with **`/ticket_open`** — staff will respond in a thread. 🎫",
            inline=False,
        )

    e.set_footer(text="Moderators may act on spirit, not letter. Don’t test the edges.")
    return e

def _tickets_missing_embed(runner: discord.abc.User) -> discord.Embed:
    e = discord.Embed(
        title="⚠️ Tickets feature not detected",
        description=(
            "The **Tickets** cog wasn’t found when `/rules_post` ran.\n"
            "Members won’t see an error, but ticket commands won’t work."
        ),
        color=discord.Color.orange(),
    )
    e.add_field(
        name="Next steps",
        value=(
            "• Ensure `cogs/tickets_cog.py` is present and loads.\n"
            "• Check `TICKET_HOME_CHANNEL_ID` and `TICKET_STAFF_ROLES` env/secrets.\n"
            "• Watch logs for load errors on restart."
        ),
        inline=False,
    )
    e.set_footer(text=f"Triggered by {runner} • Check deployment logs for details.")
    return e

# ---------- Cog ----------

class RulesCog(commands.Cog, name="Rules"):
    """Post the house rules, and warn mods if Tickets aren’t loaded."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="rules_post", description="(Admin) Post the rules embed here or to a chosen channel.")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(channel="Optional: post the rules to this channel instead of here")
    async def rules_post(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
        if interaction.guild is None:
            await interaction.response.send_message("Run this in a server.", ephemeral=True)
            return

        target = channel or interaction.channel
        if not isinstance(target, (discord.TextChannel, discord.Thread)):
            await interaction.response.send_message("Pick a standard text channel.", ephemeral=True)
            return

        tickets_ok = _tickets_available(self.bot)
        rules_emb = _rules_embed(interaction.guild, tickets_ok)
        await interaction.response.send_message("Posting rules…", ephemeral=True)

        # Post the rules publicly
        try:
            await target.send(embed=rules_emb)
        except discord.Forbidden:
            await interaction.followup.send("I don’t have permission to post in that channel.", ephemeral=True)
            return

        # If Tickets missing, warn staff in mod-logs and ping owner/runner
        if not tickets_ok:
            modlog = _find_modlog(interaction.guild)
            who_ping = f"<@{OWNER_USER_ID}>" if OWNER_USER_ID else interaction.user.mention
            if modlog:
                try:
                    await modlog.send(content=f"{who_ping}", embed=_tickets_missing_embed(interaction.user))
                except Exception as e:
                    log.warning("Failed to send tickets-missing warning to mod-logs: %s", e)
            else:
                # No mod-logs. Let the runner know.
                await interaction.followup.send(
                    content=f"⚠️ Tickets not detected and **#mod-logs** wasn’t found. "
                            f"{who_ping} please check the deployment/logs.",
                    ephemeral=True
                )

        await interaction.followup.send("✅ Rules posted.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(RulesCog(bot))