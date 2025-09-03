# cogs/roles_cog.py
from __future__ import annotations
import os
import json
from typing import Optional, Dict, List

import discord
from discord import app_commands
from discord.ext import commands

from config import BotConfig
cfg = BotConfig()

DATA_DIR = "data"
ROLES_PATH = os.path.join(DATA_DIR, "roles_menu.json")

def _load_json(path: str, fallback):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return fallback

def _save_json(path: str, data):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass

def _guild_key(guild: discord.Guild) -> str:
    return str(guild.id)

def _parse_env_roles() -> List[int]:
    raw = (getattr(cfg, "ROLE_MENU_IDS", "") or "").replace(" ", "")
    out: List[int] = []
    for part in raw.split(","):
        if not part:
            continue
        try:
            out.append(int(part))
        except ValueError:
            pass
    return out

class RolesCog(commands.Cog, name="Roles"):
    """
    Consolidated under /roles:
      - add | remove | list | post
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._store: Dict[str, Dict[str, Dict[str, str]]] = _load_json(ROLES_PATH, {})

        # Group
        self.roles = app_commands.Group(name="roles", description="Self-assign roles menu manager")
        self.roles.command(name="add", description="(Admin) Allow a role for self-assign")(self._add)
        self.roles.command(name="remove", description="(Admin) Disallow a role from self-assign")(self._remove)
        self.roles.command(name="list", description="(Admin) List roles in the self-assign menu")(self._list)
        self.roles.command(name="post", description="(Admin) Post the self-assign role selector here")(self._post)

    async def cog_load(self):
        try:
            self.bot.tree.add_command(self.roles)
        except app_commands.CommandAlreadyRegistered:
            pass

    async def cog_unload(self):
        try:
            self.bot.tree.remove_command("roles", type=discord.AppCommandType.chat_input)
        except Exception:
            pass

    # ------- helpers -------
    def _ensure_guild(self, guild: discord.Guild):
        gk = _guild_key(guild)
        if gk not in self._store:
            self._store[gk] = {}
            _save_json(ROLES_PATH, self._store)

    def _set_role_cfg(self, guild: discord.Guild, role_id: int, label: str, desc: str, emoji: str):
        self._ensure_guild(guild)
        self._store[_guild_key(guild)][str(role_id)] = {"label": label, "desc": desc, "emoji": emoji}
        _save_json(ROLES_PATH, self._store)

    def _remove_role_cfg(self, guild: discord.Guild, role_id: int):
        gk = _guild_key(guild)
        self._store.setdefault(gk, {}).pop(str(role_id), None)
        _save_json(ROLES_PATH, self._store)

    def _list_roles(self, guild: discord.Guild) -> List[discord.Role]:
        gmap = self._store.get(_guild_key(guild), {})
        if not gmap:
            env_ids = _parse_env_roles()
            for rid in env_ids:
                role = guild.get_role(rid)
                if role:
                    self._store.setdefault(_guild_key(guild), {})[str(rid)] = {"label": role.name, "desc": "", "emoji": ""}
            if env_ids:
                _save_json(ROLES_PATH, self._store)
        ids = [int(rid) for rid in self._store.get(_guild_key(guild), {}).keys()]
        roles: List[discord.Role] = []
        for rid in ids:
            r = guild.get_role(rid)
            if r:
                roles.append(r)
        return roles

    def _build_view(self, guild: discord.Guild) -> Optional[discord.ui.View]:
        roles = self._list_roles(guild)
        if not roles:
            return None
        gmap = self._store.get(_guild_key(guild), {})
        entries = []
        for r in roles:
            meta = gmap.get(str(r.id), {})
            label = (meta.get("label") or r.name)[:100]
            desc = (meta.get("desc") or f"Toggle {r.name}")[:100]
            emoji = meta.get("emoji") or None
            entries.append((r, label, desc, emoji))

        class _CustomSelect(discord.ui.Select):
            def __init__(self, items):
                options = []
                for role, label, desc, emoji in items[:25]:
                    options.append(discord.SelectOption(
                        label=label, value=str(role.id), description=desc, emoji=emoji if emoji else None
                    ))
                super().__init__(placeholder="Select roles to toggle…",
                                 min_values=0,
                                 max_values=min(25, len(options)) if options else 1,
                                 options=options,
                                 custom_id="role_select_menu")
                self.items_meta = items

            async def callback(self, interaction: discord.Interaction):
                member = interaction.user if isinstance(interaction.user, discord.Member) else interaction.guild.get_member(interaction.user.id)
                if not isinstance(member, discord.Member):
                    await interaction.response.send_message("Could not resolve your member profile.", ephemeral=True)
                    return
                picked_ids = set(int(v) for v in self.values)
                available = {str(role.id): role for role, _, _, _ in self.items_meta}
                added, removed, skipped = [], [], []
                for rid_str, role in available.items():
                    rid = int(rid_str)
                    has = role in member.roles
                    if rid in picked_ids and not has:
                        try:
                            await member.add_roles(role, reason="Self-assign via role menu")
                            added.append(role.name)
                        except discord.Forbidden:
                            skipped.append(role.name)
                    elif rid in picked_ids and has:
                        try:
                            await member.remove_roles(role, reason="Self-remove via role menu")
                            removed.append(role.name)
                        except discord.Forbidden:
                            skipped.append(role.name)
                parts = []
                if added: parts.append(f"✅ Added: {', '.join(added)}")
                if removed: parts.append(f"➖ Removed: {', '.join(removed)}")
                if skipped: parts.append(f"⚠️ Skipped (permissions): {', '.join(skipped)}")
                if not parts: parts.append("No changes.")
                await interaction.response.send_message("\n".join(parts), ephemeral=True)

        class _CustomView(discord.ui.View):
            def __init__(self, items):
                super().__init__(timeout=None)
                self.add_item(_CustomSelect(items))

        return _CustomView(entries)

    # ------- /roles subcommands -------
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(role="Role to allow", label="Custom label (optional)", desc="Description (optional)", emoji="Emoji (optional)")
    async def _add(self, interaction: discord.Interaction, role: discord.Role, label: Optional[str] = None, desc: Optional[str] = None, emoji: Optional[str] = None):
        if interaction.guild is None:
            await interaction.response.send_message("Run this in a server.", ephemeral=True); return
        me = interaction.guild.me
        if me is None or role >= me.top_role:
            await interaction.response.send_message("I can’t assign that role (my role must be higher).", ephemeral=True); return
        self._set_role_cfg(interaction.guild, role.id, label or role.name, desc or "", emoji or "")
        await interaction.response.send_message(f"✅ Added **{role.name}** to the self-assign menu.", ephemeral=True)

    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(role="Role to remove")
    async def _remove(self, interaction: discord.Interaction, role: discord.Role):
        if interaction.guild is None:
            await interaction.response.send_message("Run this in a server.", ephemeral=True); return
        self._remove_role_cfg(interaction.guild, role.id)
        await interaction.response.send_message(f"🗑️ Removed **{role.name}** from the menu.", ephemeral=True)

    @app_commands.checks.has_permissions(manage_guild=True)
    async def _list(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("Run this in a server.", ephemeral=True); return
        roles = self._list_roles(interaction.guild)
        if not roles:
            await interaction.response.send_message("No roles configured yet. Use `/roles add`.", ephemeral=True); return
        gmap = self._store.get(_guild_key(interaction.guild), {})
        lines = []
        for r in roles:
            meta = gmap.get(str(r.id), {})
            lab = meta.get("label") or r.name
            desc = meta.get("desc") or ""
            emo = meta.get("emoji") or ""
            lines.append(f"- {r.mention} (`{r.id}`) — **{lab}** {emo} {('· ' + desc) if desc else ''}")
        await interaction.response.send_message(f"**Self-assign roles:**\n" + "\n".join(lines), ephemeral=True)

    @app_commands.checks.has_permissions(manage_guild=True)
    async def _post(self, interaction: discord.Interaction):
        if interaction.guild is None or interaction.channel is None:
            await interaction.response.send_message("Run this in a server channel.", ephemeral=True); return
        view = self._build_view(interaction.guild)
        if view is None:
            await interaction.response.send_message("No roles configured. Use `/roles add` first.", ephemeral=True); return
        emb = discord.Embed(
            title="Choose Your Roles",
            description="Use the selector below to **toggle** roles on or off.\nChanges are private to you.",
            color=discord.Color.green()
        )
        await interaction.response.send_message("Posted!", ephemeral=True)
        try:
            await interaction.channel.send(embed=emb, view=view)
        except discord.Forbidden:
            await interaction.followup.send("I can’t post here (missing permissions).", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(RolesCog(bot))