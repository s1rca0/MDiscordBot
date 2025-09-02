import os
import random
import asyncio
from typing import List, Optional

import discord
from discord.ext import commands, tasks
from discord import app_commands

def _env_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name, str(default))
    return str(v).lower() in ("1","true","yes","y","on")

def _env_list(name: str, fallback: List[str]) -> List[str]:
    raw = os.getenv(name, "")
    xs = [x.strip() for x in raw.split("|") if x.strip()]
    return xs or fallback

# --- Env knobs (all optional) ---
PRESENCE_ENABLE       = _env_bool("PRESENCE_ENABLE", True)
PRESENCE_INTERVAL_SEC = int(os.getenv("PRESENCE_INTERVAL_SEC", "300"))  # 5 minutes
# Pipe-separated lines for each layer tone
PRESENCE_MAINFRAME    = _env_list("PRESENCE_MAINFRAME",
    ["calibrating systems", "mapping entry points", "observing the grid"])
PRESENCE_CONSTRUCT    = _env_list("PRESENCE_CONSTRUCT",
    ["loading training routines", "syncing fight choreography", "rendering storyboards"])
PRESENCE_HAVN         = _env_list("PRESENCE_HAVN",
    ["shielding signals", "guarding the last light", "watching the horizon"])

# activity types to choose from (Playing, Watching, Listening)
ACTIVITY_TYPES = [
    discord.ActivityType.playing,
    discord.ActivityType.watching,
    discord.ActivityType.listening,
]

class PresenceCog(commands.Cog):
    """Rotating, layer-aware presence for Morpheus."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._enabled = PRESENCE_ENABLE
        self._mode: str = "MAINFRAME"  # default
        self._task.start()

    def cog_unload(self):
        try:
            self._task.cancel()
        except Exception:
            pass

    # ------------ internals ------------
    def _pool(self) -> List[str]:
        if self._mode.upper() == "HAVN":
            return PRESENCE_HAVN
        if self._mode.upper() == "CONSTRUCT":
            return PRESENCE_CONSTRUCT
        return PRESENCE_MAINFRAME

    def _pick_line(self) -> str:
        choices = self._pool()
        if not choices:
            return "standing by"
        return random.choice(choices)

    def _pick_activity(self) -> discord.Activity:
        atype = random.choice(ACTIVITY_TYPES)
        line = self._pick_line()
        return discord.Activity(type=atype, name=line)

    @tasks.loop(seconds=PRESENCE_INTERVAL_SEC)
    async def _task(self):
        if not self._enabled or not self.bot.is_ready():
            return
        try:
            await self.bot.change_presence(
                activity=self._pick_activity(),
                status=discord.Status.online
            )
        except Exception:
            pass

    @_task.before_loop
    async def _before(self):
        await self.bot.wait_until_ready()

    # ------------ slash commands ------------
    @app_commands.command(name="presence_on", description="Enable rotating presence.")
    async def presence_on(self, inter: discord.Interaction):
        if not (inter.user.guild_permissions.administrator or inter.user.id == int(os.getenv("OWNER_USER_ID", "0") or 0)):
            await inter.response.send_message("Admin/Owner only.", ephemeral=True)
            return
        self._enabled = True
        self._task.change_interval(seconds=PRESENCE_INTERVAL_SEC)
        await inter.response.send_message("Presence rotation **enabled**.", ephemeral=True)

    @app_commands.command(name="presence_off", description="Disable rotating presence.")
    async def presence_off(self, inter: discord.Interaction):
        if not (inter.user.guild_permissions.administrator or inter.user.id == int(os.getenv("OWNER_USER_ID", "0") or 0)):
            await inter.response.send_message("Admin/Owner only.", ephemeral=True)
            return
        self._enabled = False
        try:
            await self.bot.change_presence(activity=None)
        except Exception:
            pass
        await inter.response.send_message("Presence rotation **disabled**.", ephemeral=True)

    @app_commands.command(name="presence_mode", description="Set presence tone: MAINFRAME, CONSTRUCT, or HAVN.")
    @app_commands.describe(mode="MAINFRAME | CONSTRUCT | HAVN")
    async def presence_mode(self, inter: discord.Interaction, mode: str):
        if not (inter.user.guild_permissions.administrator or inter.user.id == int(os.getenv("OWNER_USER_ID", "0") or 0)):
            await inter.response.send_message("Admin/Owner only.", ephemeral=True)
            return
        mode_up = mode.strip().upper()
        if mode_up not in {"MAINFRAME", "CONSTRUCT", "HAVN"}:
            await inter.response.send_message("Use: MAINFRAME, CONSTRUCT, or HAVN.", ephemeral=True)
            return
        self._mode = mode_up
        await inter.response.send_message(f"Presence mode set to **{mode_up}**.", ephemeral=True)

    @app_commands.command(name="presence_add", description="Add a new status line to the current mode.")
    async def presence_add(self, inter: discord.Interaction, line: str):
        if not (inter.user.guild_permissions.administrator or inter.user.id == int(os.getenv("OWNER_USER_ID", "0") or 0)):
            await inter.response.send_message("Admin/Owner only.", ephemeral=True)
            return
        line = line.strip()
        if not line:
            await inter.response.send_message("Provide a non-empty line.", ephemeral=True)
            return
        # ephemeral in-memory add (session-scale). For durability, set env later.
        pool = self._pool()
        pool.append(line)
        await inter.response.send_message(f"Added to **{self._mode}**: “{line}”.", ephemeral=True)

    @app_commands.command(name="presence_show", description="Show current mode and sample lines.")
    async def presence_show(self, inter: discord.Interaction):
        examples = "\n".join(f"• {s}" for s in self._pool()[:6])
        await inter.response.send_message(
            f"Mode: **{self._mode}**\nInterval: **{PRESENCE_INTERVAL_SEC}s**\nEnabled: **{self._enabled}**\n\n"
            f"Sample lines:\n{examples or '(none)'}",
            ephemeral=True
        )

async def setup(bot: commands.Bot):
    await bot.add_cog(PresenceCog(bot))