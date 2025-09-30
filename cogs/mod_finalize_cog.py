# cogs/mod_finalize_cog.py
from __future__ import annotations

import re
import datetime as dt
from typing import Iterable, List, Optional

import discord
from discord import app_commands
from discord.ext import commands

# --- System message types we typically want removed during finalization ---
SYSTEM_TYPES = {
    discord.MessageType.pins_add,
    discord.MessageType.channel_name_change,
    discord.MessageType.channel_icon_change,
    discord.MessageType.thread_created,
    discord.MessageType.channel_follow_add,
}

# --- Helper container for a cleanup profile ("preset") ---
class FinalizePreset:
    def __init__(
        self,
        name: str,
        keep_pins: bool = True,
        keep_from_bots: bool = False,
        keep_from_users: Optional[List[int]] = None,
        keep_if_any_substring: Optional[List[str]] = None,
        keep_if_regex: Optional[List[str]] = None,
        keep_message_types: Optional[Iterable[discord.MessageType]] = None,
        delete_system_messages: bool = True,
        keep_last_n_messages: int = 0,   # always keep the most recent N messages
        keep_first_n_messages: int = 0,  # useful for channels with a top banner post
        min_age_days: Optional[int] = None,  # only delete if older than X days (safety)
        max_age_days: Optional[int] = None,  # only delete if newer than X days
    ):
        self.name = name
        self.keep_pins = keep_pins
        self.keep_from_bots = keep_from_bots
        self.keep_from_users = set(keep_from_users or [])
        self.keep_if_any_substring = [s.lower() for s in (keep_if_any_substring or [])]
        self.keep_if_regex = [re.compile(r, re.I) for r in (keep_if_regex or [])]
        self.keep_message_types = set(keep_message_types or [])
        self.delete_system_messages = delete_system_messages
        self.keep_last_n_messages = keep_last_n_messages
        self.keep_first_n_messages = keep_first_n_messages
        self.min_age_days = min_age_days
        self.max_age_days = max_age_days

    def should_keep(
        self,
        m: discord.Message,
        idx_from_top: int,     # 0 is oldest
        idx_from_bottom: int,  # 0 is newest
    ) -> bool:
        # Pins: keep?
        if self.keep_pins and m.pinned:
            return True

        # System messages: drop unless explicitly kept
        if m.type in SYSTEM_TYPES:
            if not self.delete_system_messages:
                return True
            # fall through to delete

        # Keep specific message types (rare)
        if m.type in self.keep_message_types:
            return True

        # Keep messages from certain humans
        if self.keep_from_users and isinstance(m.author, discord.Member):
            if m.author.id in self.keep_from_users:
                return True

        # Keep/Drop bot authored
        if m.author.bot and self.keep_from_bots:
            return True

        # Keep first / last N
        if self.keep_first_n_messages and idx_from_top < self.keep_first_n_messages:
            return True
        if self.keep_last_n_messages and idx_from_bottom < self.keep_last_n_messages:
            return True

        # Keep if content matches substring or regex
        content = (m.content or "").lower()
        if any(s in content for s in self.keep_if_any_substring):
            return True
        if any(r.search(m.content or "") for r in self.keep_if_regex):
            return True

        # Age gates (optional)
        if self.min_age_days is not None:
            if (dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc) - m.created_at).days < self.min_age_days:
                return True  # too new to delete
        if self.max_age_days is not None:
            if (dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc) - m.created_at).days > self.max_age_days:
                return True  # too old (Discord bulk limit or by policy)

        # Default: delete
        return False


def preset_welcome(guild_owner_id: Optional[int]) -> FinalizePreset:
    """
    Keep your banner post(s), pins, and latest announcement-style posts.
    Remove pin notices, setup chatter, test runs.
    """
    keep_users = [guild_owner_id] if guild_owner_id else []
    return FinalizePreset(
        name="welcome",
        keep_pins=True,
        keep_from_bots=False,               # normally remove bot scaffolding in welcome
        keep_from_users=keep_users,         # keep owner-authored posts
        keep_if_any_substring=[
            "welcome", "read #rules", "start here", "quick start", "introductions",
        ],
        keep_if_regex=[r"#\w+"],            # keep posts with channel deeplinks
        delete_system_messages=True,
        keep_first_n_messages=1,            # keep the top banner post
        keep_last_n_messages=2,             # and a little recent context
        max_age_days=None,
    )


def preset_music_hub(guild_owner_id: Optional[int]) -> FinalizePreset:
    """
    Keep protocols + cheatsheet + latest queue-related posts.
    Remove pin notices, bot test spam, command chatter during setup.
    """
    keep_users = [guild_owner_id] if guild_owner_id else []
    return FinalizePreset(
        name="music_hub",
        keep_pins=True,
        keep_from_bots=False,
        keep_from_users=keep_users,
        keep_if_any_substring=[
            "music hub protocols", "quick start", "prime music", "activities", "use #music-hub",
        ],
        keep_if_regex=[r"/(play|pause|skip|queue)\b"],
        delete_system_messages=True,
        keep_first_n_messages=1,    # your anchored protocols post
        keep_last_n_messages=5,     # keep some freshest context
    )


def preset_ops_logs(_: Optional[int]) -> FinalizePreset:
    """
    Keep the newest operational summaries; remove pin notices + old noise.
    """
    return FinalizePreset(
        name="ops_logs",
        keep_pins=True,
        keep_from_bots=True,         # we DO want bot health summaries, but only the newest few
        keep_last_n_messages=10,     # keep the latest 10 entries (newest status)
        delete_system_messages=True,
        # Optionally only delete items older than 7 days:
        # min_age_days=None, max_age_days=None
    )


PRESET_CHOICES = {
    "welcome": preset_welcome,
    "music_hub": preset_music_hub,
    "ops_logs": preset_ops_logs,
}


class FinalizeCog(commands.Cog):
    """Context-aware cleanup with presets + preview."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # Permission: mods with Manage Messages (admins can do everything)
    def is_mod():
        async def predicate(inter: discord.Interaction):
            perms = inter.user.guild_permissions
            return perms.manage_messages
        return app_commands.check(predicate)

    @app_commands.guild_only()
    @app_commands.command(name="finalize", description="Finalize a channel by removing setup noise with smart presets.")
    @is_mod()
    @app_commands.describe(
        preset="Cleanup profile to apply",
        mode="Preview (dry-run) or Run (perform deletion)",
        keep_last_n="Override: always keep the newest N messages (optional)",
        keep_first_n="Override: always keep the first N messages (optional)"
    )
    @app_commands.choices(
        preset=[
            app_commands.Choice(name="Welcome channel", value="welcome"),
            app_commands.Choice(name="Music Hub", value="music_hub"),
            app_commands.Choice(name="Ops Logs", value="ops_logs"),
            app_commands.Choice(name="Custom (minimal rules)", value="custom"),
        ],
        mode=[
            app_commands.Choice(name="Preview", value="preview"),
            app_commands.Choice(name="Run", value="run"),
        ],
    )
    async def finalize(
        self,
        interaction: discord.Interaction,
        preset: app_commands.Choice[str],
        mode: app_commands.Choice[str],
        keep_last_n: Optional[int] = None,
        keep_first_n: Optional[int] = None,
    ):
        await interaction.response.defer(ephemeral=True, thinking=True)
        channel = interaction.channel
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return await interaction.followup.send("❌ Not a text channel or thread.", ephemeral=True)

        # Build preset
        owner_id = interaction.guild.owner_id if interaction.guild else None
        if preset.value == "custom":
            active = FinalizePreset(
                "custom",
                keep_pins=True,
                delete_system_messages=True,
                keep_last_n_messages=keep_last_n or 0,
                keep_first_n_messages=keep_first_n or 0,
            )
        else:
            base = PRESET_CHOICES[preset.value](owner_id)
            if keep_last_n is not None:
                base.keep_last_n_messages = keep_last_n
            if keep_first_n is not None:
                base.keep_first_n_messages = keep_first_n
            active = base

        # Gather messages (limit=None streams the entire channel; this respects rate limits)
        messages: List[discord.Message] = [m async for m in channel.history(limit=None, oldest_first=True)]
        total = len(messages)
        if total == 0:
            return await interaction.followup.send("Nothing to do here.", ephemeral=True)

        # Figure keep/delete sets based on indexes
        to_delete: List[discord.Message] = []
        for i, m in enumerate(messages):
            idx_from_top = i
            idx_from_bottom = total - 1 - i
            keep = active.should_keep(m, idx_from_top, idx_from_bottom)
            if not keep:
                to_delete.append(m)

        # For preview: show stats + first 10 examples
        if mode.value == "preview":
            sample = "\n".join(
                f"• {m.author.display_name}: {truncate(m.content)}" for m in to_delete[:10]
            ) or "No deletions (under current preset)."
            embed = discord.Embed(
                title=f"Preview — {preset.name}",
                description=f"Channel: {channel.mention}\nTotal messages: **{total}**\nWill delete: **{len(to_delete)}**",
                color=discord.Color.gold(),
            )
            embed.add_field(name="Sample (first 10)", value=sample, inline=False)
            embed.set_footer(text="Run /finalize with mode=Run to apply.")
            return await interaction.followup.send(embed=embed, ephemeral=True)

        # Run mode: delete using purge with a check
        # Note: purge() ignores >14-day-old entries. Anything skipped remains.
        def check(m: discord.Message) -> bool:
            return m in to_delete

        deleted = await channel.purge(limit=None, check=check)
        skipped = len(to_delete) - len(deleted)

        embed = discord.Embed(
            title=f"Finalize complete — {preset.name}",
            description=f"Deleted **{len(deleted)}** messages in {channel.mention}.",
            color=discord.Color.brand_green(),
        )
        if skipped:
            embed.add_field(
                name="Skipped",
                value=f"{skipped} (likely older than 14 days or lacked permission).",
                inline=False,
            )
        await interaction.followup.send(embed=embed, ephemeral=True)


def truncate(s: str, n: int = 80) -> str:
    s = s or ""
    return (s[: n - 1] + "…") if len(s) > n else s


async def setup(bot: commands.Bot):
    await bot.add_cog(FinalizeCog(bot))