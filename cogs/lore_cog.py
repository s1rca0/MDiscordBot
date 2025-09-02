# cogs/lore_cog.py
import os
import json
from typing import Dict, Any, Set, Optional

import discord
from discord.ext import commands
from discord import app_commands

DATA_DIR = "data"
GCFG_PATH = os.path.join(DATA_DIR, "guild_config.json")

OWNER_USER_ID = int(os.getenv("OWNER_USER_ID", "0") or 0)
# Legacy env fallback (optional). If set, used only when no per-guild value exists:
MISSION_TRUST_ROLE_ID_FALLBACK = int(os.getenv("MISSION_TRUST_ROLE_ID", "0") or 0)

# ---------- storage helpers ----------
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

# ---------- role + audit helpers ----------
def _guild_trust_set(guild_id: int) -> Set[int]:
    """Trusted roles from your fast-track system (set via other cog)."""
    g = _get_guild_dict(guild_id)
    return set(map(int, g.get("trust_role_ids", [])))

def _get_mission_trust_role_id(guild_id: int) -> int:
    """Per-guild mission-trust role; falls back to env if unset."""
    g = _get_guild_dict(guild_id)
    rid = int(g.get("mission_trust_role_id", 0) or 0)
    if not rid and MISSION_TRUST_ROLE_ID_FALLBACK:
        return MISSION_TRUST_ROLE_ID_FALLBACK
    return rid

def _set_mission_trust_role_id(guild_id: int, role_id: int):
    _set_guild_dict(guild_id, {"mission_trust_role_id": int(role_id)})

def _get_audit_channel_id(guild_id: int) -> int:
    g = _get_guild_dict(guild_id)
    return int(g.get("mission_audit_channel_id", 0) or 0)

def _set_audit_channel_id(guild_id: int, channel_id: int):
    _set_guild_dict(guild_id, {"mission_audit_channel_id": int(channel_id)})

def _get_audit_access_flag(guild_id: int) -> bool:
    g = _get_guild_dict(guild_id)
    return bool(g.get("mission_audit_access", False))

def _set_audit_access_flag(guild_id: int, value: bool):
    _set_guild_dict(guild_id, {"mission_audit_access": bool(value)})

# ---------- auth helpers ----------
def _is_owner(user: discord.abc.User) -> bool:
    return OWNER_USER_ID and int(user.id) == int(OWNER_USER_ID)

def _member_has_any(member: discord.Member, role_ids: Set[int]) -> bool:
    if not member or not role_ids:
        return False
    mset = {r.id for r in getattr(member, "roles", [])}
    return any(rid in mset for rid in role_ids)

def _is_admin_or_owner(interaction: discord.Interaction) -> bool:
    if _is_owner(interaction.user):
        return True
    if isinstance(interaction.user, discord.Member):
        return bool(interaction.user.guild_permissions.administrator)
    return False

def _bot_member(guild: discord.Guild, bot_user: discord.ClientUser) -> Optional[discord.Member]:
    return guild.get_member(bot_user.id)

def _bot_can_manage_role(guild: discord.Guild, bot_user: discord.ClientUser, role: discord.Role) -> bool:
    me = _bot_member(guild, bot_user)
    if not me:
        return False
    # Must have Manage Roles and top role higher than target role
    if not me.guild_permissions.manage_roles:
        return False
    top_pos = max((r.position for r in me.roles), default=0)
    return top_pos > role.position  # strictly higher

# ---------- constants: your two meanings ----------
FRONTEND_ACRONYM = (
    "**M.O.R.P.H.E.U.S.** — *Multiverse Operations, Reality Protection, "
    "Human Engagement & Uplift System*"
)
BACKEND_ACRONYM = (
    "**M.O.R.P.H.E.U.S.** — *Monitoring Operations for Reality, Perception, "
    "Hope, Enlightenment, Unity & Survival*"
)

# ---------- audit logger ----------
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
    channel = guild.get_channel(chan_id)
    if not isinstance(channel, (discord.TextChannel, discord.Thread)):
        return
    try:
        embed = discord.Embed(title=title, description=description, color=color)
        await channel.send(embed=embed)
    except Exception:
        pass

class LoreCog(commands.Cog):
    """Public /about (frontend) and restricted /mission (backend lore) + per-guild mission-trust role, grants, and audit logging."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------- Public: /about ----------
    @app_commands.command(name="about", description="Who is M.O.R.P.H.E.U.S.?")
    async def about(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="About M.O.R.P.H.E.U.S.",
            description=(
                f"{FRONTEND_ACRONYM}\n\n"
                "Your Discord guide and signal from the Multiverse at **Legends in Motion HQ**. "
                "Ask with `/ask`, choose with `/pill`, and join the journey."
            ),
            color=discord.Color.dark_green()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ---------- Restricted: /mission ----------
    @app_commands.command(name="mission", description="(Restricted) The deeper meaning and aim.")
    async def mission(self, interaction: discord.Interaction):
        # DMs: owner only
        if interaction.guild is None:
            if not _is_owner(interaction.user):
                await interaction.response.send_message("Access denied.", ephemeral=True)
                return
        else:
            # Guild gating: owner OR any trusted role OR mission-trust role
            is_owner = _is_owner(interaction.user)
            trusted_roles = _guild_trust_set(interaction.guild.id)
            has_trusted = isinstance(interaction.user, discord.Member) and _member_has_any(interaction.user, trusted_roles)

            mission_role_id = _get_mission_trust_role_id(interaction.guild.id)
            has_mission_role = False
            if mission_role_id and isinstance(interaction.user, discord.Member):
                has_mission_role = _member_has_any(interaction.user, {mission_role_id})

            if not (is_owner or has_trusted or has_mission_role):
                await interaction.response.send_message("Access denied.", ephemeral=True)
                return

        # Optional access audit
        if interaction.guild and _get_audit_access_flag(interaction.guild.id):
            who = f"{interaction.user} ({interaction.user.id})"
            where = f"#{interaction.channel.name}" if interaction.channel and hasattr(interaction.channel, 'name') else "(unknown)"
            await _audit_log(
                self.bot,
                interaction.guild,
                "Mission Access",
                f"User **{who}** viewed `/mission` in {where}.",
                color=discord.Color.blurple()
            )

        embed = discord.Embed(
            title="Mission Briefing",
            description=(
                f"{BACKEND_ACRONYM}\n\n"
                "Purpose:\n"
                "• Free minds through story, craft, and community.\n"
                "• Build resilient, respectful spaces where people choose their path.\n"
                "• Guide with honesty; protect with care; uplift through creation.\n\n"
                "_This briefing is shared selectively. Handle with integrity._"
            ),
            color=discord.Color.blurple()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ---------- Admin/Owner: set & view mission-trust role ----------
    @app_commands.command(name="set_mission_trust_role", description="(Owner/Admin) Set the special role allowed to view /mission.")
    @app_commands.describe(role="Role that grants access to /mission (in addition to trusted roles/owner)")
    async def set_mission_trust_role(self, interaction: discord.Interaction, role: discord.Role):
        if interaction.guild is None:
            await interaction.response.send_message("Run this in a server.", ephemeral=True)
            return
        if not _is_admin_or_owner(interaction):
            await interaction.response.send_message("Admin/Owner only.", ephemeral=True)
            return

        _set_mission_trust_role_id(interaction.guild.id, role.id)
        await interaction.response.send_message(f"Mission-trust role set to {role.mention}.", ephemeral=True)

        await _audit_log(
            self.bot,
            interaction.guild,
            "Mission-Trust Role Set",
            f"By **{interaction.user}**: mission-trust role → {role.mention}",
            color=discord.Color.green()
        )

    @app_commands.command(name="mission_trust_info", description="(Owner/Admin) Show current mission-trust role, trusted roles, and audit settings.")
    async def mission_trust_info(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("Run this in a server.", ephemeral=True)
            return
        if not _is_admin_or_owner(interaction):
            await interaction.response.send_message("Admin/Owner only.", ephemeral=True)
            return

        tset = _guild_trust_set(interaction.guild.id)
        mission_role_id = _get_mission_trust_role_id(interaction.guild.id)
        mission_role = interaction.guild.get_role(mission_role_id) if mission_role_id else None

        trusted_lines = []
        for rid in sorted(tset):
            r = interaction.guild.get_role(rid)
            trusted_lines.append(f"- {rid} ({r.mention if r else 'unknown role'})")

        audit_chan_id = _get_audit_channel_id(interaction.guild.id)
        audit_chan = interaction.guild.get_channel(audit_chan_id) if audit_chan_id else None
        audit_access = _get_audit_access_flag(interaction.guild.id)

        desc = (
            f"**Mission-trust role:** {mission_role.mention if mission_role else '(not set)'}\n\n"
            f"**Trusted roles (fast-track):**\n" + ("\n".join(trusted_lines) if trusted_lines else "(none)") + "\n\n"
            f"**Audit channel:** {audit_chan.mention if audit_chan else '(not set)'}\n"
            f"**Audit mission access (/mission views):** {'ON' if audit_access else 'OFF'}"
        )
        await interaction.response.send_message(desc, ephemeral=True)

    # ---------- Admin/Owner: set & toggle audit ----------
    @app_commands.command(name="mission_audit_access", description="(Owner/Admin) Toggle logging when users view /mission.")
    @app_commands.describe(state="Turn logging on or off")
    @app_commands.choices(
        state=[
            app_commands.Choice(name="on", value="on"),
            app_commands.Choice(name="off", value="off"),
        ]
    )
    async def mission_audit_access(
        self,
        interaction: discord.Interaction,
        state: app_commands.Choice[str]
    ):
        if interaction.guild is None:
            await interaction.response.send_message("Run this in a server.", ephemeral=True)
            return
        if not _is_admin_or_owner(interaction):
            await interaction.response.send_message("Admin/Owner only.", ephemeral=True)
            return

        val = (state.value.lower() == "on")
        _set_audit_access_flag(interaction.guild.id, val)
        await interaction.response.send_message(f"/mission access logging is now **{'ON' if val else 'OFF'}**.", ephemeral=True)

        await _audit_log(
            self.bot,
            interaction.guild,
            "Mission Access Audit Toggled",
            f"By **{interaction.user}**: access logging → {'ON' if val else 'OFF'}",
            color=discord.Color.orange()
        )

    # ---------- Admin/Owner: grant/revoke mission-trust role to members ----------
    @app_commands.command(name="grant_mission_trust", description="(Owner/Admin) Grant the mission-trust role to a member.")
    @app_commands.describe(user="Member to grant the role to")
    async def grant_mission_trust(self, interaction: discord.Interaction, user: discord.Member):
        if interaction.guild is None:
            await interaction.response.send_message("Run this in a server.", ephemeral=True)
            return
        if not _is_admin_or_owner(interaction):
            await interaction.response.send_message("Admin/Owner only.", ephemeral=True)
            return

        mission_role_id = _get_mission_trust_role_id(interaction.guild.id)
        if not mission_role_id:
            await interaction.response.send_message("Mission-trust role is not set. Use `/set_mission_trust_role` first.", ephemeral=True)
            return

        role = interaction.guild.get_role(mission_role_id)
        if not role:
            await interaction.response.send_message("Configured mission-trust role no longer exists.", ephemeral=True)
            return

        if not _bot_can_manage_role(interaction.guild, self.bot.user, role):
            await interaction.response.send_message("I lack permission or role hierarchy to assign that role.", ephemeral=True)
            return

        try:
            await user.add_roles(role, reason="Granted mission-trust access")
            await interaction.response.send_message(f"Granted {role.mention} to {user.mention}.", ephemeral=True)
            await _audit_log(
                self.bot, interaction.guild, "Mission-Trust Granted",
                f"By **{interaction.user}** → {user.mention} received {role.mention}",
                color=discord.Color.green()
            )
        except Exception as e:
            await interaction.response.send_message(f"Could not grant role: {e.__class__.__name__}", ephemeral=True)

    @app_commands.command(name="revoke_mission_trust", description="(Owner/Admin) Revoke the mission-trust role from a member.")
    @app_commands.describe(user="Member to revoke the role from")
    async def revoke_mission_trust(self, interaction: discord.Interaction, user: discord.Member):
        if interaction.guild is None:
            await interaction.response.send_message("Run this in a server.", ephemeral=True)
            return
        if not _is_admin_or_owner(interaction):
            await interaction.response.send_message("Admin/Owner only.", ephemeral=True)
            return

        mission_role_id = _get_mission_trust_role_id(interaction.guild.id)
        if not mission_role_id:
            await interaction.response.send_message("Mission-trust role is not set.", ephemeral=True)
            return

        role = interaction.guild.get_role(mission_role_id)
        if not role:
            await interaction.response.send_message("Configured mission-trust role no longer exists.", ephemeral=True)
            return

        if not _bot_can_manage_role(interaction.guild, self.bot.user, role):
            await interaction.response.send_message("I lack permission or role hierarchy to remove that role.", ephemeral=True)
            return

        try:
            await user.remove_roles(role, reason="Revoked mission-trust access")
            await interaction.response.send_message(f"Revoked {role.mention} from {user.mention}.", ephemeral=True)
            await _audit_log(
                self.bot, interaction.guild, "Mission-Trust Revoked",
                f"By **{interaction.user}** → {user.mention} lost {role.mention}",
                color=discord.Color.red()
            )
        except Exception as e:
            await interaction.response.send_message(f"Could not revoke role: {e.__class__.__name__}", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(LoreCog(bot))