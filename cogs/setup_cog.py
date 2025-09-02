# cogs/setup_cog.py
import os
import json
from typing import Dict, Any, Optional, Set, List

import discord
from discord.ext import commands
from discord import app_commands

from config import BotConfig

cfg = BotConfig()

DATA_DIR = "data"
GCFG_PATH = os.path.join(DATA_DIR, "guild_config.json")

# ---------- tiny store ----------
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

# ---------- config getters ----------
def _get_member_role_id(gid: int) -> int:
    g = _get_guild_dict(gid)
    return int(g.get("member_role_id", 0) or 0)

def _set_member_role_id(gid: int, rid: int):
    _set_guild_dict(gid, {"member_role_id": int(rid)})

def _get_trust_role_ids(gid: int) -> Set[int]:
    g = _get_guild_dict(gid)
    return set(int(x) for x in g.get("trust_role_ids", []))

def _set_trust_role_ids(gid: int, ids: List[int]):
    _set_guild_dict(gid, {"trust_role_ids": list(map(int, ids))})

def _get_mission_trust_role_id(gid: int) -> int:
    g = _get_guild_dict(gid)
    return int(g.get("mission_trust_role_id", 0) or 0)

def _set_mission_trust_role_id(gid: int, rid: int):
    _set_guild_dict(gid, {"mission_trust_role_id": int(rid)})

def _get_mission_audit_channel_id(gid: int) -> int:
    g = _get_guild_dict(gid)
    return int(g.get("mission_audit_channel_id", 0) or 0)

def _set_mission_audit_channel_id(gid: int, cid: int):
    _set_guild_dict(gid, {"mission_audit_channel_id": int(cid)})

def _get_mission_audit_access(gid: int) -> bool:
    g = _get_guild_dict(gid)
    return bool(g.get("mission_audit_access", False))

def _set_mission_audit_access(gid: int, val: bool):
    _set_guild_dict(gid, {"mission_audit_access": bool(val)})

def _get_welcome_channel_id(gid: int) -> int:
    g = _get_guild_dict(gid)
    return int(g.get("welcome_channel_id", 0) or 0)

def _set_welcome_channel_id(gid: int, cid: int):
    _set_guild_dict(gid, {"welcome_channel_id": int(cid)})

def _get_modlog_channel_id(gid: int) -> int:
    g = _get_guild_dict(gid)
    return int(g.get("modlog_channel_id", 0) or 0)

def _set_modlog_channel_id(gid: int, cid: int):
    _set_guild_dict(gid, {"modlog_channel_id": int(cid)})

# ---------- auth ----------
def _is_owner(user: discord.abc.User) -> bool:
    return bool(cfg.OWNER_USER_ID) and int(user.id) == int(cfg.OWNER_USER_ID)

def _is_admin_or_owner(inter: discord.Interaction) -> bool:
    if _is_owner(inter.user):
        return True
    if isinstance(inter.user, discord.Member):
        return bool(inter.user.guild_permissions.administrator)
    return False

# ---------- helpers ----------
def _role_name(guild: discord.Guild, rid: int) -> str:
    r = guild.get_role(rid)
    return r.mention if r else f"`{rid}` (missing)"

def _chan_name(guild: discord.Guild, cid: int) -> str:
    ch = guild.get_channel(cid)
    return ch.mention if isinstance(ch, (discord.TextChannel, discord.Thread)) else f"`{cid}` (missing)"

def _ok(x: bool) -> str:
    return "✅" if x else "❌"

def _status_embed(guild: discord.Guild) -> discord.Embed:
    gid = guild.id
    member_rid = _get_member_role_id(gid)
    trust_ids = sorted(_get_trust_role_ids(gid))
    mission_trust_rid = _get_mission_trust_role_id(gid)
    audit_cid = _get_mission_audit_channel_id(gid)
    audit_on = _get_mission_audit_access(gid)
    welcome_cid = _get_welcome_channel_id(gid)
    modlog_cid = _get_modlog_channel_id(gid)

    # env/secret-backed things (read-only from here)
    yt_announce_cid = cfg.YT_ANNOUNCE_CHANNEL_ID
    yt_channel_id = cfg.YT_CHANNEL_ID or "(unset)"
    void_cid = cfg.VOID_CHANNEL_ID or 0

    e = discord.Embed(
        title="M.O.P.H.E.U.S. — Setup Audit",
        color=discord.Color.blurple()
    )
    e.add_field(
        name="Core Roles",
        value=(
            f"Member role (Construct): {_role_name(guild, member_rid) if member_rid else '*(not set)*'}\n"
            f"Trusted roles: " + (", ".join(_role_name(guild, rid) for rid in trust_ids) if trust_ids else "*(none)*") + "\n"
            f"Mission-trust role: {_role_name(guild, mission_trust_rid) if mission_trust_rid else '*(not set)*'}"
        ),
        inline=False
    )
    e.add_field(
        name="Channels",
        value=(
            f"Welcome channel: {_chan_name(guild, welcome_cid) if welcome_cid else '*(not set)*'}\n"
            f"Mod-log channel: {_chan_name(guild, modlog_cid) if modlog_cid else '*(not set)*'}\n"
            f"Mission audit channel: {_chan_name(guild, audit_cid) if audit_cid else '*(not set)*'} "
            f"({ 'ON' if audit_on else 'OFF' })"
        ),
        inline=False
    )
    e.add_field(
        name="YouTube (env)",
        value=(
            f"YT channel ID: `{yt_channel_id}`\n"
            f"YT announce channel: {(_chan_name(guild, yt_announce_cid) if yt_announce_cid else '*(env not set)*')}"
        ),
        inline=False
    )
    e.add_field(
        name="Presence & Void (env)",
        value=(
            f"Presence interval: `{cfg.PRESENCE_INTERVAL_SEC}s`\n"
            f"Void channel: {(_chan_name(guild, void_cid) if void_cid else '*(env not set)*')}\n"
            f"Void cadence (hrs): `{cfg.VOID_BROADCAST_HOURS}`"
        ),
        inline=False
    )
    return e

# ---------- dynamic selects ----------
def _first_n_roles(guild: discord.Guild, n: int = 25) -> List[discord.SelectOption]:
    opts = []
    for r in sorted(guild.roles, key=lambda x: x.position, reverse=True):
        if r.is_default():
            continue
        opts.append(discord.SelectOption(label=r.name, value=str(r.id)))
        if len(opts) >= n:
            break
    return opts

def _first_n_text_channels(guild: discord.Guild, n: int = 25) -> List[discord.SelectOption]:
    opts = []
    for ch in guild.text_channels:
        opts.append(discord.SelectOption(label=f"#{ch.name}", value=str(ch.id)))
        if len(opts) >= n:
            break
    return opts

# ---------- Views ----------
class SetupView(discord.ui.View):
    def __init__(self, bot: commands.Bot, guild: discord.Guild, *, timeout: int = 300):
        super().__init__(timeout=timeout)
        self.bot = bot
        self.guild = guild

    # Member role
    @discord.ui.button(label="Set Member Role (Construct)", style=discord.ButtonStyle.primary, row=0)
    async def btn_member_role(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not _is_admin_or_owner(interaction):
            await interaction.response.send_message("Admin/Owner only.", ephemeral=True)
            return
        options = _first_n_roles(self.guild)
        if not options:
            await interaction.response.send_message("No roles found.", ephemeral=True)
            return

        class RoleSelect(discord.ui.Select):
            def __init__(self):
                super().__init__(placeholder="Choose a Member role", options=options, min_values=1, max_values=1)
            async def callback(self, inter: discord.Interaction):
                rid = int(self.values[0])
                _set_member_role_id(inter.guild.id, rid)
                await inter.response.edit_message(content=f"✅ Member role set to {_role_name(inter.guild, rid)}.", view=None)

        v = discord.ui.View()
        v.add_item(RoleSelect())
        await interaction.response.send_message("Pick the role for **The Construct** (member role):", view=v, ephemeral=True)

    # Trusted roles (multi)
    @discord.ui.button(label="Set Trusted Roles (HAVN)", style=discord.ButtonStyle.primary, row=0)
    async def btn_trusted(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not _is_admin_or_owner(interaction):
            await interaction.response.send_message("Admin/Owner only.", ephemeral=True)
            return
        options = _first_n_roles(self.guild)
        if not options:
            await interaction.response.send_message("No roles found.", ephemeral=True)
            return

        class MultiRole(discord.ui.Select):
            def __init__(self):
                super().__init__(placeholder="Choose trusted roles (multi)", options=options, min_values=0, max_values=min(10, len(options)))
            async def callback(self, inter: discord.Interaction):
                ids = [int(v) for v in self.values]
                _set_trust_role_ids(inter.guild.id, ids)
                names = ", ".join(_role_name(inter.guild, i) for i in ids) if ids else "(none)"
                await inter.response.edit_message(content=f"✅ Trusted roles updated: {names}", view=None)

        v = discord.ui.View()
        v.add_item(MultiRole())
        await interaction.response.send_message("Pick **trusted roles** (HAVN access):", view=v, ephemeral=True)

    # Mission-trust role
    @discord.ui.button(label="Set Mission-Trust Role", style=discord.ButtonStyle.secondary, row=0)
    async def btn_mission_role(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not _is_admin_or_owner(interaction):
            await interaction.response.send_message("Admin/Owner only.", ephemeral=True)
            return
        options = _first_n_roles(self.guild)
        if not options:
            await interaction.response.send_message("No roles found.", ephemeral=True)
            return

        class OneRole(discord.ui.Select):
            def __init__(self):
                super().__init__(placeholder="Choose mission-trust role", options=options, min_values=1, max_values=1)
            async def callback(self, inter: discord.Interaction):
                rid = int(self.values[0])
                _set_mission_trust_role_id(inter.guild.id, rid)
                await inter.response.edit_message(content=f"✅ Mission-trust role set to {_role_name(inter.guild, rid)}.", view=None)

        v = discord.ui.View()
        v.add_item(OneRole())
        await interaction.response.send_message("Pick **mission-trust** role:", view=v, ephemeral=True)

    # Welcome channel
    @discord.ui.button(label="Set Welcome Channel", style=discord.ButtonStyle.success, row=1)
    async def btn_welcome(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not _is_admin_or_owner(interaction):
            await interaction.response.send_message("Admin/Owner only.", ephemeral=True)
            return
        options = _first_n_text_channels(self.guild)
        class ChanSel(discord.ui.Select):
            def __init__(self):
                super().__init__(placeholder="Choose welcome channel", options=options, min_values=1, max_values=1)
            async def callback(self, inter: discord.Interaction):
                cid = int(self.values[0])
                _set_welcome_channel_id(inter.guild.id, cid)
                await inter.response.edit_message(content=f"✅ Welcome channel set to {_chan_name(inter.guild, cid)}.", view=None)
        v = discord.ui.View(); v.add_item(ChanSel())
        await interaction.response.send_message("Pick **welcome channel**:", view=v, ephemeral=True)

    # Mod-log channel
    @discord.ui.button(label="Set Mod-Log Channel", style=discord.ButtonStyle.success, row=1)
    async def btn_modlog(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not _is_admin_or_owner(interaction):
            await interaction.response.send_message("Admin/Owner only.", ephemeral=True)
            return
        options = _first_n_text_channels(self.guild)
        class ChanSel(discord.ui.Select):
            def __init__(self):
                super().__init__(placeholder="Choose mod-log channel", options=options, min_values=1, max_values=1)
            async def callback(self, inter: discord.Interaction):
                cid = int(self.values[0])
                _set_modlog_channel_id(inter.guild.id, cid)
                await inter.response.edit_message(content=f"✅ Mod-log channel set to {_chan_name(inter.guild, cid)}.", view=None)
        v = discord.ui.View(); v.add_item(ChanSel())
        await interaction.response.send_message("Pick **mod-log channel**:", view=v, ephemeral=True)

    # Mission audit channel
    @discord.ui.button(label="Set Mission Audit Channel", style=discord.ButtonStyle.secondary, row=1)
    async def btn_mission_audit(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not _is_admin_or_owner(interaction):
            await interaction.response.send_message("Admin/Owner only.", ephemeral=True)
            return
        options = _first_n_text_channels(self.guild)
        class ChanSel(discord.ui.Select):
            def __init__(self):
                super().__init__(placeholder="Choose mission audit channel", options=options, min_values=1, max_values=1)
            async def callback(self, inter: discord.Interaction):
                cid = int(self.values[0])
                _set_mission_audit_channel_id(inter.guild.id, cid)
                await inter.response.edit_message(content=f"✅ Mission audit channel set to {_chan_name(inter.guild, cid)}.", view=None)
        v = discord.ui.View(); v.add_item(ChanSel())
        await interaction.response.send_message("Pick **mission audit channel**:", view=v, ephemeral=True)

    # Toggle mission access audit
    @discord.ui.button(label="Toggle Mission Access Audit", style=discord.ButtonStyle.secondary, row=2)
    async def btn_toggle_audit(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not _is_admin_or_owner(interaction):
            await interaction.response.send_message("Admin/Owner only.", ephemeral=True)
            return
        gid = interaction.guild.id
        new_val = not _get_mission_audit_access(gid)
        _set_mission_audit_access(gid, new_val)
        await interaction.response.send_message(f"✅ Mission access audit is now **{'ON' if new_val else 'OFF'}**.", ephemeral=True)

    # Bot nickname setter
    @discord.ui.button(label="Set Bot Nickname (this server)", style=discord.ButtonStyle.danger, row=2)
    async def btn_nick(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not _is_admin_or_owner(interaction):
            await interaction.response.send_message("Admin/Owner only.", ephemeral=True)
            return

        class NickModal(discord.ui.Modal, title="Set Bot Nickname"):
            new_nick = discord.ui.TextInput(label="Nickname", placeholder="M.O.P.H.E.U.S.", required=True, max_length=32)
            async def on_submit(self, inter: discord.Interaction):
                me = inter.guild.get_member(inter.client.user.id)  # type: ignore
                if not me:
                    await inter.response.send_message("Could not find my member object.", ephemeral=True)
                    return
                try:
                    await me.edit(nick=str(self.new_nick))
                    await inter.response.send_message(f"✅ Nickname updated to **{self.new_nick}**.", ephemeral=True)
                except discord.Forbidden:
                    await inter.response.send_message("I lack permission to change my nickname (need **Manage Nicknames**).", ephemeral=True)

        await interaction.response.send_modal(NickModal())

    @discord.ui.button(label="Refresh Status", style=discord.ButtonStyle.secondary, row=3)
    async def btn_refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        emb = _status_embed(self.guild)
        await interaction.response.send_message(embed=emb, ephemeral=True)

class SetupCog(commands.Cog, name="Setup"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="setup", description="(Owner/Admin) Review and configure core wiring.")
    async def setup(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("Run in a server.", ephemeral=True)
            return
        if not _is_admin_or_owner(interaction):
            await interaction.response.send_message("Admin/Owner only.", ephemeral=True)
            return

        emb = _status_embed(interaction.guild)
        view = SetupView(self.bot, interaction.guild)
        await interaction.response.send_message(
            content="Use the buttons below to configure items inline. Environment variables are read-only here; set them in your host.",
            embed=emb,
            view=view,
            ephemeral=True
        )

async def setup(bot: commands.Bot):
    await bot.add_cog(SetupCog(bot))