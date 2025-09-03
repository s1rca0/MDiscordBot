# cogs/user_app_cog.py
import os
import json
import asyncio
from typing import List, Dict

import discord
from discord.ext import commands
from discord import app_commands

OPTIN_PATH = "data/user_optins.json"


def _load_optins() -> Dict[str, bool]:
    try:
        with open(OPTIN_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_optins(d: Dict[str, bool]):
    os.makedirs(os.path.dirname(OPTIN_PATH), exist_ok=True)
    with open(OPTIN_PATH, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2)


def _is_owner(user_id: int) -> bool:
    try:
        return int(os.getenv("OWNER_USER_ID", "0")) == int(user_id)
    except Exception:
        return False


class UserAppCog(commands.Cog, name="User App / DMs"):
    """
    User-installable features + safe DM opt-in.
    Works in DMs and in servers.

    NOTE: /helpdm is intentionally NOT defined here to avoid duplicate command
    registration. It lives in cogs/dm_start_cog.py.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.invite_url = os.getenv("SERVER_INVITE_URL", "").strip()
        self.optins = _load_optins()

    # --- Utility ---
    async def _reply_alive(self, interaction: discord.Interaction, text: str, dm_ok=True):
        prefix = "▮ Morpheus: "
        try:
            await interaction.response.send_message(
                prefix + text,
                ephemeral=(interaction.guild is not None)
            )
        except discord.InteractionResponded:
            await interaction.followup.send(
                prefix + text,
                ephemeral=(interaction.guild is not None)
            )
        except discord.Forbidden:
            if dm_ok and interaction.user:
                try:
                    await interaction.user.send(prefix + text)
                except Exception:
                    pass

    # --- Commands ---
    @app_commands.command(name="start", description="Begin in DM or server. I’ll guide you.")
    @app_commands.allowed_installs(guilds=True, users=True)
    async def start(self, interaction: discord.Interaction):
        in_dm = interaction.guild is None
        msg = (
            "I’m awake. If you prefer privacy, you can use my commands here in DMs. "
            "Use **/invite** for the gateway back to HQ, and **/optin** if you want me to ping you with critical updates."
            if in_dm else
            "System check complete. I’m live here. If you’d rather operate in private, DM me and use **/optin** to receive alerts."
        )
        await self._reply_alive(interaction, msg)

    @app_commands.command(name="invite", description="Get the invite to HQ.")
    @app_commands.allowed_installs(guilds=True, users=True)
    async def invite(self, interaction: discord.Interaction):
        if not self.invite_url:
            await self._reply_alive(interaction, "No invite configured yet. Set `SERVER_INVITE_URL` in your env.")
            return
        await self._reply_alive(interaction, f"Door unlocked: {self.invite_url}")

    @app_commands.command(name="optin", description="Opt in to receive DM updates from me.")
    @app_commands.allowed_installs(guilds=True, users=True)
    async def optin(self, interaction: discord.Interaction):
        self.optins[str(interaction.user.id)] = True
        _save_optins(self.optins)
        await self._reply_alive(interaction, "You’re on the list. I’ll DM you when the signal matters.")

    @app_commands.command(name="optout", description="Opt out of DM updates.")
    @app_commands.allowed_installs(guilds=True, users=True)
    async def optout(self, interaction: discord.Interaction):
        self.optins.pop(str(interaction.user.id), None)
        _save_optins(self.optins)
        await self._reply_alive(interaction, "Understood. I’ll keep silent unless you call me.")

    @app_commands.command(name="dm_broadcast", description="(Owner) Broadcast a DM to opted-in users.")
    @app_commands.describe(message="What should I send?")
    async def dm_broadcast(self, interaction: discord.Interaction, message: str):
        if not _is_owner(interaction.user.id):
            await self._reply_alive(interaction, "Access denied.")
            return

        users = [int(uid) for uid, ok in self.optins.items() if ok]
        if not users:
            await self._reply_alive(interaction, "No agents are currently opted in.")
            return

        ok = 0
        for uid in users:
            try:
                u = await self.bot.fetch_user(uid)
                await u.send(f"▮ Morpheus: {message}")
                ok += 1
                await asyncio.sleep(0.3)  # gentle rate limit
            except Exception:
                pass

        await self._reply_alive(interaction, f"Signal transmitted to {ok} agent(s).")


async def setup(bot: commands.Bot):
    await bot.add_cog(UserAppCog(bot))