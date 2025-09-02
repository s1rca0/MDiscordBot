# cogs/layer_cog.py
import os
import json
from typing import Dict, Any, Optional, Set

import discord
from discord.ext import commands
from discord import app_commands

DATA_DIR = "data"
GCFG_PATH = os.path.join(DATA_DIR, "guild_config.json")

# ----------------- tiny store helpers (shared style) -----------------
def _ensure_store():
    if not os.path.isdir(DATA_DIR):
        os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.isfile(GCFG_PATH):
        with open(GCFG_PATH, "w", encoding="utf-8") as f:
            json.dump({}, f)

def _load_gcfg() -> Dict[str, Any]:
    _ensure_store()
    with open(GCFG_PATH, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except Exception:
            return {}

def _save_gcfg(db: Dict[str, Any]):
    _ensure_store()
    with open(GCFG_PATH, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

def _get_guild_dict(guild_id: int) -> Dict[str, Any]:
    db = _load_gcfg()
    return db.get(str(guild_id), {})

def _set_guild_dict(guild_id: int, partial: Dict[str, Any]):
    db = _load_gcfg()
    key = str(guild_id)
    g = db.get(key, {})
    g.update(partial)
    db[key] = g
    _save_gcfg(db)

# ----------------- config readers -----------------
def _get_member_role_id(guild_id: int) -> int:
    """Set by your existing /set_member_role command elsewhere."""
    g = _get_guild_dict(guild_id)
    return int(g.get("member_role_id", 0) or 0)

def _get_trust_role_ids(guild_id: int) -> Set[int]:
    """Trusted roles set by your fast-track (/trust_addrole etc.)."""
    g = _get_guild_dict(guild_id)
    return set(int(x) for x in g.get("trust_role_ids", []))

def _get_mission_trust_role_id(guild_id: int) -> int:
    """Optional special mission-trust role (if you set it via lore/mission cog)."""
    g = _get_guild_dict(guild_id)
    return int(g.get("mission_trust_role_id", 0) or 0)

# ----------------- layer logic -----------------
# Layers:
# - MAINFRAME: everyone by default
# - CONSTRUCT: has your configured "Members" role (you can rename that role to “The Construct”)
# - HAVN: any trusted role OR mission-trust role OR owner (handled by other cogs’ commands)

LAYER_MAINFRAME = "MAINFRAME"
LAYER_CONSTRUCT = "CONSTRUCT"
LAYER_HAVN = "HAVN"

class LayerCog(commands.Cog):
    """
    Determines a member's layer based on roles stored in guild_config.json:
      - member_role_id           -> CONSTRUCT
      - trust_role_ids or mission_trust_role_id -> HAVN
    Everyone else -> MAINFRAME.

    Provides:
      /mylayer      : user’s layer (minimal info for non-owners)
      /layer_info   : owner/admin summary of current role wiring
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # --------- public util for other cogs ----------
    def get_user_layer(self, member: Optional[discord.Member]) -> str:
        """
        Return one of: HAVN, CONSTRUCT, MAINFRAME.
        Safe if member is None (DMs) -> MAINFRAME by default.
        """
        if member is None or member.guild is None:
            return LAYER_MAINFRAME

        gid = member.guild.id
        member_role_id = _get_member_role_id(gid)
        trust_ids = _get_trust_role_ids(gid)
        mission_trust_id = _get_mission_trust_role_id(gid)

        role_ids = {r.id for r in getattr(member, "roles", [])}

        # HAVN first (highest clearance)
        if (trust_ids and role_ids.intersection(trust_ids)) or (mission_trust_id and mission_trust_id in role_ids):
            return LAYER_HAVN

        # CONSTRUCT (inner circle)
        if member_role_id and member_role_id in role_ids:
            return LAYER_CONSTRUCT

        # default
        return LAYER_MAINFRAME

    # --------- commands ----------
    @app_commands.command(name="mylayer", description="See which layer you’re in.")
    async def mylayer(self, interaction: discord.Interaction):
        # Work in DMs or Guilds
        member = interaction.user if isinstance(interaction.user, discord.Member) else None
        if interaction.guild and not isinstance(interaction.user, discord.Member):
            # Convert to Member if possible (rare edge case)
            member = interaction.guild.get_member(interaction.user.id)

        layer = self.get_user_layer(member)

        # Minimal info for everyone; no internal role IDs shown
        descriptions = {
            LAYER_MAINFRAME: "You’re in **MAINFRAME** — the public plaza. Explore, chat, and get a feel for the flow.",
            LAYER_CONSTRUCT: "You’re in **THE CONSTRUCT** — inner circle access. More channels, deeper collaboration.",
            LAYER_HAVN: "You’re in **HAVN** — trusted access. Signals, briefings, and the quiet work.",
        }
        embed = discord.Embed(
            title="Your Layer",
            description=descriptions.get(layer, f"You’re in **{layer}**."),
            color=discord.Color.blurple()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="layer_info", description="(Owner/Admin) Show how layers are wired to roles.")
    async def layer_info(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("Run this in a server.", ephemeral=True)
            return

        is_admin = False
        if isinstance(interaction.user, discord.Member):
            is_admin = bool(interaction.user.guild_permissions.administrator)

        if not is_admin:
            await interaction.response.send_message("Admin only.", ephemeral=True)
            return

        gid = interaction.guild.id
        member_role_id = _get_member_role_id(gid)
        trust_ids = sorted(_get_trust_role_ids(gid))
        mission_trust_id = _get_mission_trust_role_id(gid)

        member_role = interaction.guild.get_role(member_role_id) if member_role_id else None
        trust_lines = []
        for rid in trust_ids:
            r = interaction.guild.get_role(rid)
            trust_lines.append(f"- {rid} ({r.mention if r else 'unknown role'})")

        mission_role = interaction.guild.get_role(mission_trust_id) if mission_trust_id else None

        desc = (
            f"**CONSTRUCT:** member_role_id = "
            f"{member_role.mention if member_role else '(not set)'}\n\n"
            f"**HAVN:**\n"
            f"- trust roles: \n{('\n'.join(trust_lines) if trust_lines else '(none)')}\n"
            f"- mission-trust role: "
            f"{mission_role.mention if mission_role else '(not set)'}\n\n"
            "_Everyone else is MAINFRAME by default._"
        )
        await interaction.response.send_message(desc, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(LayerCog(bot))