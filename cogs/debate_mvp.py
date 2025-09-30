from __future__ import annotations
from typing import Optional, Iterable, List
import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext.commands import Cog

# config / store imports
from config import DEFAULT_BRAND_NICK
from config_store import (
    get_debate,
    set_debate_flag,
    get_channel as _get_channel_id,
)

log = logging.getLogger("morpheus.debate")

# ---- async wrappers around blocking store calls (avoid heartbeat stalls)

async def _get_flags_safe(guild_id: int) -> dict:
    try:
        return await asyncio.to_thread(get_debate, guild_id)
    except Exception as e:
        log.warning("get_debate failed: %s; using defaults", e)
        # sensible defaults
        return {"terms_on": False, "coach_on": False}

async def _set_flag_safe(guild_id: int, key: str, value: bool) -> None:
    try:
        await asyncio.to_thread(set_debate_flag, guild_id, key, value)
    except Exception as e:
        log.warning("set_debate_flag(%s) failed: %s", key, e)

async def _get_channel_id_safe(guild_id: int, key: str, default: Optional[int] = None) -> Optional[int]:
    try:
        return await asyncio.to_thread(_get_channel_id, guild_id, key, default)
    except Exception as e:
        log.warning("get_channel_id(%s) failed: %s; using default %s", key, e, default)
        return default


class DebateMVP(Cog):
    """Debate tools (MVP).

    Final stable schema:
      - Group: /debate
      - /debate start topic:<str> [terms:<bool>] [coach:<bool>] [channel:<#text>]
      - /debate terms [on|off]
      - /debate coach [on|off]
      - /debate end  (manual end marker; just posts a wrap-up card for now)
    """

    # Slash command group root: /debate (final name)
    group = app_commands.Group(name="debate", description="Debate tools")

    @group.command(
        name="start",
        description="Announce debate start; optionally set terms/coach flags and choose a channel ✨",
    )
    @app_commands.describe(
        topic="Short topic for the debate",
        terms="Turn terms nudges on/off for this server",
        coach="Turn coaching nudges on/off for this server",
        channel="Channel to announce in (defaults to configured/open/current)",
    )
    async def start(
        self,
        interaction: discord.Interaction,
        topic: str,
        terms: Optional[bool] = None,
        coach: Optional[bool] = None,
        channel: Optional[discord.TextChannel] = None,
    ):
        """Start a debate announcement with optional flag overrides."""
        await interaction.response.defer(ephemeral=True)
        try:
            # Optional flag overrides
            if terms is not None:
                await _set_flag_safe(interaction.guild_id, "terms_on", terms)
            if coach is not None:
                await _set_flag_safe(interaction.guild_id, "coach_on", coach)

            # Determine destination channel
            chan: Optional[discord.TextChannel] = channel or interaction.channel  # type: ignore[assignment]
            if isinstance(chan, discord.Thread):
                chan = chan.parent  # type: ignore[assignment]
            if chan is None or not isinstance(chan, discord.TextChannel):
                cfg_id = await _get_channel_id_safe(interaction.guild_id, "open_chat", None)
                if cfg_id and interaction.guild:
                    fetched = interaction.guild.get_channel(cfg_id)
                    if isinstance(fetched, discord.TextChannel):
                        chan = fetched

            # Permission check
            if not isinstance(chan, discord.TextChannel):
                await interaction.followup.send("No suitable text channel to announce in.", ephemeral=True)
                return
            me = interaction.guild.get_member(interaction.client.user.id) if interaction.guild else None
            if not me or not chan.permissions_for(me).send_messages:
                await interaction.followup.send("I can't post in that channel.", ephemeral=True)
                return

            flags = await _get_flags_safe(interaction.guild_id)
            brand = (interaction.guild.name if interaction.guild else None) or DEFAULT_BRAND_NICK

            embed = discord.Embed(
                title=f"🗣️ Debate Started — {brand}",
                description=(
                    f"**Topic:** {topic}\n\n"
                    f"Terms: **{flags.get('terms_on', False)}** · "
                    f"Coach: **{flags.get('coach_on', False)}**"
                ),
                color=discord.Color.blurple(),
            )
            await chan.send(embed=embed)
            await interaction.followup.send(f"Debate announced in {chan.mention}.", ephemeral=True)
        except Exception as e:
            log.exception("/debate start failed: %s", e)
            msg = (str(e) or "unknown error")[:1800]
            try:
                await interaction.followup.send(f"Something went wrong starting the debate: `{msg}`", ephemeral=True)
            except Exception:
                pass

    # --- simple toggles remain for convenience

    @group.command(name="terms", description="Enable/disable debate terms nudges for this server.")
    @app_commands.describe(value="Set True to enable, False to disable. If omitted, flips the current state.")
    async def terms(self, interaction: discord.Interaction, value: Optional[bool] = None):
        await interaction.response.defer(ephemeral=True)
        flags = await _get_flags_safe(interaction.guild_id)
        new_val = (not flags.get("terms_on", False)) if value is None else bool(value)
        await _set_flag_safe(interaction.guild_id, "terms_on", new_val)
        await interaction.followup.send(f"Terms nudges set to **{new_val}**.", ephemeral=True)

    @group.command(name="coach", description="Enable/disable coaching nudges for this server.")
    @app_commands.describe(value="Set True to enable, False to disable. If omitted, flips the current state.")
    async def coach(self, interaction: discord.Interaction, value: Optional[bool] = None):
        await interaction.response.defer(ephemeral=True)
        flags = await _get_flags_safe(interaction.guild_id)
        new_val = (not flags.get("coach_on", False)) if value is None else bool(value)
        await _set_flag_safe(interaction.guild_id, "coach_on", new_val)
        await interaction.followup.send(f"Coach nudges set to **{new_val}**.", ephemeral=True)

    @group.command(name="end", description="Post an end-of-debate marker card.")
    async def end(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        brand = (interaction.guild.name if interaction.guild else None) or DEFAULT_BRAND_NICK
        embed = discord.Embed(title=f"🏁 Debate Ended — {brand}", color=discord.Color.dark_gray())
        await interaction.channel.send(embed=embed)
        await interaction.followup.send("Debate closed.", ephemeral=True)