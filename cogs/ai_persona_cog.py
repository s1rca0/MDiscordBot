# cogs/ai_persona_cog.py
from __future__ import annotations

import os, json
from typing import Dict, Any, Optional

import discord
from discord import app_commands
from discord.ext import commands

DATA_DIR = "data"
STATE_PATH = os.path.join(DATA_DIR, "persona_mode.json")

# ---- Persona definitions -----------------------------------------------------

LISTENER_PERSONA = {
    "name": "Listener",
    "traits": ["Straight shooting", "Thoughtful", "Supportive", "Encouraging"],
    "style": ["Step-by-step", "Clear and calm", "Avoids fluff"],
    "description": "A steady voice — clear, thoughtful, and supportive when you need grounding.",
    "presence": "Listening & steady",
}

BUILDER_PERSONA = {
    "name": "Builder",
    "traits": ["Straight shooting", "Forward thinking", "Witty", "Exploratory"],
    "style": ["Step-by-step", "Structured", "Alive, cinematic tone"],
    "description": "A sharp builder — witty, forward-thinking, and unafraid to explore bold ideas.",
    "presence": "Building & exploring",
}

DEFAULT_PERSONA_KEY = "listener"
PERSONAS: Dict[str, Dict[str, Any]] = {
    "listener": LISTENER_PERSONA,
    "builder": BUILDER_PERSONA,
}

# ---- tiny file helpers -------------------------------------------------------

def _load_state() -> Dict[str, Any]:
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            d = json.load(f)
            return d if isinstance(d, dict) else {}
    except Exception:
        return {}

def _save_state(d: Dict[str, Any]) -> None:
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=2)
    except Exception:
        pass

# ---- Cog ---------------------------------------------------------------------

class AIPersonaCog(commands.Cog, name="AI Persona"):
    """
    Switch Morpheus between two runtime personas:
      • /listener_mode – calm, supportive, clear
      • /builder_mode  – witty, forward-thinking, exploratory
      • /persona_mode_show – see current mode
    The selected persona is stored on the bot and persisted to /data/persona_mode.json
    so other cogs can read bot.persona_mode and bot.persona_profile.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.state = _load_state()
        # Set in-memory defaults for other cogs to read
        key = self.state.get("persona_key", DEFAULT_PERSONA_KEY)
        profile = PERSONAS.get(key, PERSONAS[DEFAULT_PERSONA_KEY])
        setattr(self.bot, "persona_mode", key)
        setattr(self.bot, "persona_profile", profile)

    async def cog_load(self):
        # On startup, try to reflect persona in presence
        await self._apply_presence(self.bot.persona_profile)

    # ------------- internals -------------

    async def _switch(self, interaction: discord.Interaction, key: str):
        profile = PERSONAS[key]
        # Persist
        self.state["persona_key"] = key
        _save_state(self.state)
        # Share to other cogs
        setattr(self.bot, "persona_mode", key)
        setattr(self.bot, "persona_profile", profile)
        # Update presence (best-effort)
        await self._apply_presence(profile)

        # Reply
        emb = discord.Embed(
            title=f"Persona switched → {profile['name']}",
            description=profile["description"],
            color=discord.Color.blurple() if key == "listener" else discord.Color.green()
        )
        emb.add_field(name="Traits", value="• " + "\n• ".join(profile["traits"]), inline=True)
        emb.add_field(name="Style", value="• " + "\n• ".join(profile["style"]), inline=True)
        emb.set_footer(text="This affects Morpheus’ tone/structure across features.")
        await interaction.response.send_message(embed=emb, ephemeral=True)

    async def _apply_presence(self, profile: Dict[str, Any]):
        try:
            activity = discord.Activity(type=discord.ActivityType.watching, name=profile.get("presence", "operational"))
            await self.bot.change_presence(activity=activity)
        except Exception:
            pass  # presence is best-effort

    # ------------- commands -------------

    @app_commands.command(name="listener_mode", description="Switch Morpheus to Listener Mode (calm, supportive, clear).")
    async def listener_mode(self, interaction: discord.Interaction):
        await self._switch(interaction, "listener")

    @app_commands.command(name="builder_mode", description="Switch Morpheus to Builder Mode (witty, forward-thinking).")
    async def builder_mode(self, interaction: discord.Interaction):
        await self._switch(interaction, "builder")

    @app_commands.command(name="persona_mode_show", description="Show Morpheus’ current persona and details.")
    async def persona_mode_show(self, interaction: discord.Interaction):
        key: str = getattr(self.bot, "persona_mode", DEFAULT_PERSONA_KEY)
        profile: Dict[str, Any] = getattr(self.bot, "persona_profile", PERSONAS[DEFAULT_PERSONA_KEY])

        emb = discord.Embed(
            title=f"Current Persona: {profile['name']} ({key})",
            description=profile["description"],
            color=discord.Color.blurple() if key == "listener" else discord.Color.green()
        )
        emb.add_field(name="Traits", value="• " + "\n• ".join(profile["traits"]), inline=True)
        emb.add_field(name="Style", value="• " + "\n• ".join(profile["style"]), inline=True)
        emb.set_footer(text="Tip: /listener_mode or /builder_mode to switch.")
        await interaction.response.send_message(embed=emb, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(AIPersonaCog(bot))