# cogs/user_app_cog.py
from __future__ import annotations
import os
import json
import asyncio
from typing import Dict, List

import discord
from discord import app_commands
from discord.ext import commands

OPTIN_PATH = "data/user_optins.json"

def _load_optins() -> Dict[str, bool]:
    try:
        with open(OPTIN_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_optins(d: Dict[str, bool]):
    try:
        os.makedirs(os.path.dirname(OPTIN_PATH), exist_ok=True)
        with open(OPTIN_PATH, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=2)
    except Exception:
        pass

def _is_owner(user_id: int) -> bool:
    try:
        return int(os.getenv("OWNER_USER_ID", "0")) == int(user_id)
    except Exception:
        return False

class UserAppCog(commands.Cog, name="User App / DMs"):
    """
    Consolidated under /user:
      - start | invite | optin | optout | broadcast (owner)
    Also keeps the context menu "DM: Start with Morpheus".
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.invite_url = os.getenv("SERVER_INVITE_URL", "").strip()
        self.optins = _load_optins()

        # /user group
        self.user = app_commands.Group(name="user", description="User-facing tools & DM options")
        self.user.command(name="start", description="Begin in DMs or server. I’ll guide you.")(self._user_start)
        self.user.command(name="invite", description="Get the invite to HQ.")(self._user_invite)
        self.user.command(name="optin", description="Opt in to receive DM updates from me.")(self._user_optin)
        self.user.command(name="optout", description="Opt out of DM updates.")(self._user_optout)
        self.user.command(name="broadcast", description="(Owner) Broadcast a DM to all opted-in users.")(self._user_broadcast)

    # ---------- helpers ----------
    async def _reply_alive(self, interaction: discord.Interaction, text: str, dm_ok=True):
        prefix = "▮ Morpheus: "
        try:
            await interaction.response.send_message(prefix + text, ephemeral=(interaction.guild is not None))
        except discord.InteractionResponded:
            await interaction.followup.send(prefix + text, ephemeral=(interaction.guild is not None))
        except discord.Forbidden:
            if dm_ok and interaction.user:
                try:
                    await interaction.user.send(prefix + text)
                except Exception:
                    pass

    # ---------- /user subcommands ----------
    async def _user_start(self, interaction: discord.Interaction):
        in_dm = interaction.guild is None
        msg = (
            "I’m awake. If you prefer privacy, you can use my commands here in DMs. "
            "Use **/user invite** for the gateway back to HQ, and **/user optin** if you want me to ping you with critical updates."
            if in_dm else
            "System check complete. I’m live here. If you’d rather operate in private, DM me and use **/user optin** to receive alerts."
        )
        await self._reply_alive(interaction, msg)

    async def _user_invite(self, interaction: discord.Interaction):
        if not self.invite_url:
            await self._reply_alive(interaction, "No invite configured yet. Set `SERVER_INVITE_URL` in your env.")
            return
        await self._reply_alive(interaction, f"Door unlocked: {self.invite_url}")

    async def _user_optin(self, interaction: discord.Interaction):
        self.optins[str(interaction.user.id)] = True
        _save_optins(self.optins)
        await self._reply_alive(interaction, "You’re on the list. I’ll DM you when the signal matters.")

    async def _user_optout(self, interaction: discord.Interaction):
        self.optins.pop(str(interaction.user.id), None)
        _save_optins(self.optins)
        await self._reply_alive(interaction, "Understood. I’ll keep silent unless you call me.")

    async def _user_broadcast(self, interaction: discord.Interaction, message: str):
        if not _is_owner(interaction.user.id):
            await self._reply_alive(interaction, "Access denied.")
            return
        users: List[int] = [int(uid) for uid, ok in self.optins.items() if ok]
        if not users:
            await self._reply_alive(interaction, "No agents are currently opted in.")
            return
        ok = 0
        for uid in users:
            try:
                u = await self.bot.fetch_user(uid)
                await u.send(f"▮ Morpheus: {message}")
                ok += 1
                await asyncio.sleep(0.3)
            except Exception:
                pass
        await self._reply_alive(interaction, f"Signal transmitted to {ok} agent(s).")

    # ---------- Context menu (unchanged) ----------
    async def _dm_start_context(self, interaction: discord.Interaction, member: discord.Member):
        try:
            await member.send(
                "▮ Morpheus: I'm here.\n"
                "You can use **/user start**, **/ask**, **/helpdm** here in DMs.\n"
                f"{'(This DM was opened from ' + interaction.guild.name + '.)' if interaction.guild else ''}"
            )
            msg = "Sent. Check your DMs."
        except Exception:
            msg = "I couldn't DM them (privacy settings?)."
        await interaction.response.send_message(msg, ephemeral=True)

    async def cog_load(self):
        # Register /user group
        try:
            self.bot.tree.add_command(self.user)
        except app_commands.CommandAlreadyRegistered:
            pass

        # Register context menu “DM: Start with Morpheus”
        self._ctx_menu = app_commands.ContextMenu(
            name="DM: Start with Morpheus",
            callback=self._dm_start_context
        )
        try:
            self.bot.tree.add_command(self._ctx_menu)
        except app_commands.CommandAlreadyRegistered:
            pass

    async def cog_unload(self):
        try:
            self.bot.tree.remove_command("user", type=discord.AppCommandType.chat_input)
        except Exception:
            pass
        try:
            self.bot.tree.remove_command("DM: Start with Morpheus", type=discord.AppCommandType.user)
        except Exception:
            pass

    # Keep /helpdm as a quick reminder:
    @app_commands.command(name="helpdm", description="Quick reminder of what you can do in DMs with Morpheus.")
    @app_commands.allowed_installs(guilds=True, users=True)
    async def helpdm(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "In DMs you can use:\n"
            "• **/user start** – basic intro\n"
            "• **/ask** – ask questions\n"
            "• **/user optin / user optout** – toggle DM updates",
            ephemeral=(interaction.guild is not None)
        )

async def setup(bot: commands.Bot):
    await bot.add_cog(UserAppCog(bot))