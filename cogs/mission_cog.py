# cogs/mission_cog.py
import os
import json
from typing import Dict, Any, Optional, Set

import discord
from discord.ext import commands
from discord import app_commands

from config import BotConfig

cfg = BotConfig()

DATA_DIR = "data"
GCFG_PATH = os.path.join(DATA_DIR, "guild_config.json")

# ----------------- tiny store helpers -----------------
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

# ----------------- role & audit readers/writers -----------------
def _guild_trust_set(guild_id: int) -> Set[int]:
    """Trusted roles set by your fast-track (/trust_addrole etc.)."""
    g = _get_guild_dict(guild_id)
    return set(int(x) for x in g.get("trust_role_ids", []))

def _get_mission_trust_role_id(guild_id: int) -> int:
    g = _get_guild_dict(guild_id)
    return int(g.get("mission_trust_role_id", 0) or 0)

def _set_mission_trust_role_id(guild_id: int, rid: int):
    _set_guild_dict(guild_id, {"mission_trust_role_id": int(rid)})

def _get_audit_channel_id(guild_id: int) -> int:
    g = _get_guild_dict(guild_id)
    return int(g.get("mission_audit_channel_id", 0) or 0)

def _set_audit_channel_id(guild_id: int, cid: int):
    _set_guild_dict(guild_id, {"mission_audit_channel_id": int(cid)})

def _get_audit_access_flag(guild_id: int) -> bool:
    g = _get_guild_dict(guild_id)
    return bool(g.get("mission_audit_access", False))

def _set_audit_access_flag(guild_id: int, val: bool):
    _set_guild_dict(guild_id, {"mission_audit_access": bool(val)})

# ----------------- auth helpers -----------------
def _is_owner(user: discord.abc.User) -> bool:
    return bool(cfg.OWNER_USER_ID) and int(user.id) == int(cfg.OWNER_USER_ID)

def _member_has_any(member: Optional[discord.Member], role_ids: Set[int]) -> bool:
    if not member or not role_ids:
        return False
    have = {r.id for r in getattr(member, "roles", [])}
    return any(rid in have for rid in role_ids)

def _is_admin_or_owner(inter: discord.Interaction) -> bool:
    if _is_owner(inter.user):
        return True
    if isinstance(inter.user, discord.Member):
        return bool(inter.user.guild_permissions.administrator)
    return False

async def _audit_log(
    bot: commands.Bot,
    guild: Optional[discord.Guild],
    title: str,
    description: str,
    color: discord.Color = discord.Color.dark_green(),
):
    if guild is None:
        return
    chan_id = _get_audit_channel_id(guild.id)
    if not chan_id:
        return
    ch = guild.get_channel(chan_id)
    if not isinstance(ch, (discord.TextChannel, discord.Thread)):
        return
    try:
        emb = discord.Embed(title=title, description=description, color=color)
        await ch.send(embed=emb)
    except Exception:
        pass

# ----------------- content -----------------
BACKEND_ACRONYM = (
    "**M.O.R.P.H.E.U.S.** — *Monitoring Operations for Reality, Perception, "
    "Hope, Enlightenment, Unity & Survival*"
)

MISSION_TEXT = (
    "Purpose:\n"
    "• Free minds through story, craft, and community.\n"
    "• Build resilient, respectful spaces where people choose their path.\n"
    "• Guide with honesty; protect with care; uplift through creation.\n\n"
    "_This briefing is shared selectively. Handle with integrity._"
)

# ----------------- Cog -----------------
class MissionCog(commands.Cog, name="Mission"):
    """Restricted /mission briefing + simple role/audit admin."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # --- Restricted: /mission ---
    @app_commands.command(name="mission", description="(Restricted) The deeper briefing.")
    async def mission(self, interaction: discord.Interaction):
        # Gate access
        if interaction.guild is None:
            if not _is_owner(interaction.user):
                await interaction.response.send_message("Access denied.", ephemeral=True)
                return
        else:
            is_owner = _is_owner(interaction.user)
            trusted = _guild_trust_set(interaction.guild.id)
            has_trusted = isinstance(interaction.user, discord.Member) and _member_has_any(interaction.user, trusted)
            mission_rid = _get_mission_trust_role_id(interaction.guild.id)
            has_mission = isinstance(interaction.user, discord.Member) and _member_has_any(interaction.user, {mission_rid}) if mission_rid else False
            if not (is_owner or has_trusted or has_mission):
                await interaction.response.send_message("Access denied.", ephemeral=True)
                return

        # Optional audit of access
        if interaction.guild and _get_audit_access_flag(interaction.guild.id):
            who = f"{interaction.user} ({interaction.user.id})"
            where = f"#{interaction.channel.name}" if getattr(interaction.channel, 'name', None) else "(unknown)"
            await _audit_log(
                self.bot,
                interaction.guild,
                "Mission Access",
                f"User **{who}** viewed `/mission` in {where}.",
                color=discord.Color.blurple()
            )

        embed = discord.Embed(
            title="Mission Briefing",
            description=f"{BACKEND_ACRONYM}\n\n{MISSION_TEXT}",
            color=discord.Color.blurple()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # --- Admin: mission-trust role ---
    @app_commands.command(name="set_mission_trust_role", description="(Owner/Admin) Set the role that grants access to /mission.")
    async def set_mission_trust_role(self, interaction: discord.Interaction, role: discord.Role):
        if interaction.guild is None:
            await interaction.response.send_message("Run this in a server.", ephemeral=True)
            return
        if not _is_admin_or_owner(interaction):
            await interaction.response.send_message("Admin/Owner only.", ephemeral=True)
            return
        _set_mission_trust_role_id(interaction.guild.id, role.id)
        await interaction.response.send_message(f"Mission-trust role set to {role.mention}.", ephemeral=True)
        await _audit_log(self.bot, interaction.guild, "Mission-Trust Role Set", f"By **{interaction.user}** → {role.mention}", color=discord.Color.green())

    @app_commands.command(name="mission_trust_info", description="(Owner/Admin) Show trust wiring & audit settings.")
    async def mission_trust_info(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("Run this in a server.", ephemeral=True)
            return
        if not _is_admin_or_owner(interaction):
            await interaction.response.send_message("Admin/Owner only.", ephemeral=True)
            return

        gid = interaction.guild.id
        trusted = sorted(_guild_trust_set(gid))
        mission_rid = _get_mission_trust_role_id(gid)
        audit_chan_id = _get_audit_channel_id(gid)
        audit_on = _get_audit_access_flag(gid)

        tlines = []
        for rid in trusted:
            r = interaction.guild.get_role(rid)
            tlines.append(f"- {rid} ({r.mention if r else 'unknown'})")

        desc = (
            f"**Trusted roles (fast-track):**\n" + ("\n".join(tlines) if tlines else "(none)") + "\n\n"
            f"**Mission-trust role:** {interaction.guild.get_role(mission_rid).mention if mission_rid and interaction.guild.get_role(mission_rid) else '(not set)'}\n"
            f"**Audit channel:** {interaction.guild.get_channel(audit_chan_id).mention if audit_chan_id and interaction.guild.get_channel(audit_chan_id) else '(not set)'}\n"
            f"**Audit /mission access:** {'ON' if audit_on else 'OFF'}"
        )
        await interaction.response.send_message(desc, ephemeral=True)

    # --- Admin: audit controls ---
    @app_commands.command(name="set_mission_audit_channel", description="(Owner/Admin) Set audit channel for mission events.")
    async def set_mission_audit_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if interaction.guild is None:
            await interaction.response.send_message("Run this in a server.", ephemeral=True)
            return
        if not _is_admin_or_owner(interaction):
            await interaction.response.send_message("Admin/Owner only.", ephemeral=True)
            return
        _set_audit_channel_id(interaction.guild.id, channel.id)
        await interaction.response.send_message(f"Mission audit channel set to {channel.mention}.", ephemeral=True)
        await _audit_log(self.bot, interaction.guild, "Mission Audit Channel Set", f"By **{interaction.user}** → {channel.mention}", color=discord.Color.green())

    @app_commands.command(name="mission_audit_access", description="(Owner/Admin) Toggle logging when users view /mission.")
    async def mission_audit_access(self, interaction: discord.Interaction, state: bool):
        if interaction.guild is None:
            await interaction.response.send_message("Run this in a server.", ephemeral=True)
            return
        if not _is_admin_or_owner(interaction):
            await interaction.response.send_message("Admin/Owner only.", ephemeral=True)
            return
        _set_audit_access_flag(interaction.guild.id, state)
        await interaction.response.send_message(f"/mission access logging is now **{'ON' if state else 'OFF'}**.", ephemeral=True)
        await _audit_log(self.bot, interaction.guild, "Mission Access Audit Toggled", f"By **{interaction.user}** → {'ON' if state else 'OFF'}", color=discord.Color.orange())

async def setup(bot: commands.Bot):
    await bot.add_cog(MissionCog(bot))