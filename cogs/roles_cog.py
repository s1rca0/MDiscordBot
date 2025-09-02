# roles_cog.py
import os
import json
from typing import Optional, Dict, List

import discord
from discord.ext import commands
from discord import app_commands

from config import BotConfig

cfg = BotConfig()

DATA_DIR = "data"
ROLES_PATH = os.path.join(DATA_DIR, "roles_menu.json")

def _load_json(path: str, fallback):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return fallback

def _save_json(path: str, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def _guild_key(guild: discord.Guild) -> str:
    return str(guild.id)

def _parse_env_roles() -> List[int]:
    raw = (cfg.ROLE_MENU_IDS or "").replace(" ", "")
    out: List[int] = []
    for part in raw.split(","):
        if not part:
            continue
        try:
            out.append(int(part))
        except ValueError:
            pass
    return out

class RoleSelect(discord.ui.Select):
    def __init__(self, roles: List[discord.Role]):
        # Build options
        opts = []
        for r in roles[:25]:  # max 25 options
            label = r.name[:100]
            opts.append(discord.SelectOption(label=label, value=str(r.id), description=f"Toggle {r.name}"))
        super().__init__(
            placeholder="Select roles to toggle…",
            min_values=0,
            max_values=min(25, len(opts)) if opts else 1,
            options=opts,
            custom_id="role_select_menu",
        )
        self.roles = roles

    async def callback(self, interaction: discord.Interaction):
        member = interaction.user if isinstance(interaction.user, discord.Member) else interaction.guild.get_member(interaction.user.id)
        if not isinstance(member, discord.Member):
            await interaction.response.send_message("Could not resolve your member profile.", ephemeral=True)
            return

        picked_ids = set(int(v) for v in self.values)
        available = {r.id: r for r in self.roles}
        added, removed, skipped = [], [], []

        # Toggle logic:
        for rid, role in available.items():
            has = role in member.roles
            should_toggle = (rid in picked_ids)
            # We toggle only selected ones; unselected remain unchanged.
            if should_toggle and not has:
                try:
                    await member.add_roles(role, reason="Self-assign via role menu")
                    added.append(role.name)
                except discord.Forbidden:
                    skipped.append(role.name)
            elif should_toggle and has:
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

class RoleMenuView(discord.ui.View):
    def __init__(self, roles: List[discord.Role], *, timeout: Optional[float] = None):
        super().__init__(timeout=timeout)
        self.add_item(RoleSelect(roles))

class RolesCog(commands.Cog, name="Roles"):
    """
    Self-assign roles with a select menu:
      - /roles_menu_add <role> [label] [desc] [emoji]
      - /roles_menu_remove <role>
      - /roles_menu_list
      - /roles_menu_post
    Data is stored per-guild in data/roles_menu.json.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Structure: { guild_id: { role_id: {label, desc, emoji} } }
        self._store: Dict[str, Dict[str, Dict[str, str]]] = _load_json(ROLES_PATH, {})

    # ------- helpers -------
    def _ensure_guild(self, guild: discord.Guild):
        gk = _guild_key(guild)
        if gk not in self._store:
            self._store[gk] = {}
            _save_json(ROLES_PATH, self._store)

    def _role_cfg(self, guild: discord.Guild, role_id: int) -> Optional[Dict[str, str]]:
        return self._store.get(_guild_key(guild), {}).get(str(role_id))

    def _set_role_cfg(self, guild: discord.Guild, role_id: int, label: str, desc: str, emoji: str):
        self._ensure_guild(guild)
        self._store[_guild_key(guild)][str(role_id)] = {
            "label": label, "desc": desc, "emoji": emoji
        }
        _save_json(ROLES_PATH, self._store)

    def _remove_role_cfg(self, guild: discord.Guild, role_id: int):
        gk = _guild_key(guild)
        self._store.setdefault(gk, {}).pop(str(role_id), None)
        _save_json(ROLES_PATH, self._store)

    def _list_roles(self, guild: discord.Guild) -> List[discord.Role]:
        gmap = self._store.get(_guild_key(guild), {})
        # If empty, seed from env ROLE_MENU_IDS if present
        if not gmap:
            env_ids = _parse_env_roles()
            for rid in env_ids:
                role = guild.get_role(rid)
                if role:
                    self._store.setdefault(_guild_key(guild), {})[str(rid)] = {
                        "label": role.name, "desc": "", "emoji": ""
                    }
            if env_ids:
                _save_json(ROLES_PATH, self._store)
        ids = [int(rid) for rid in self._store.get(_guild_key(guild), {}).keys()]
        roles: List[discord.Role] = []
        for rid in ids:
            r = guild.get_role(rid)
            if r:
                roles.append(r)
        return roles

    def _build_view(self, guild: discord.Guild) -> Optional[RoleMenuView]:
        roles = self._list_roles(guild)
        if not roles:
            return None
        # Respect per-role labels/descs if set (display-only; SelectOption supports custom fields)
        # We rebuild Select with those labels/desc by subclassing dynamically:
        entries = []
        gmap = self._store.get(_guild_key(guild), {})
        for r in roles:
            cfg = gmap.get(str(r.id), {}) if gmap else {}
            label = (cfg.get("label") or r.name)[:100]
            desc = (cfg.get("desc") or f"Toggle {r.name}")[:100]
            emoji = cfg.get("emoji") or None
            entries.append((r, label, desc, emoji))

        class _CustomSelect(discord.ui.Select):
            def __init__(self, items):
                options = []
                for role, label, desc, emoji in items[:25]:
                    options.append(discord.SelectOption(
                        label=label, value=str(role.id), description=desc, emoji=emoji if emoji else None
                    ))
                super().__init__(
                    placeholder="Select roles to toggle…",
                    min_values=0,
                    max_values=min(25, len(options)) if options else 1,
                    options=options,
                    custom_id="role_select_menu"
                )
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
                    should_toggle = rid in picked_ids
                    if should_toggle and not has:
                        try:
                            await member.add_roles(role, reason="Self-assign via role menu")
                            added.append(role.name)
                        except discord.Forbidden:
                            skipped.append(role.name)
                    elif should_toggle and has:
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

    # ------- Commands -------
    @app_commands.command(name="roles_menu_add", description="(Admin) Allow a role for self-assign")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(role="Role to allow", label="Custom label (optional)", desc="Description (optional)", emoji="Emoji (optional)")
    async def roles_menu_add(self, interaction: discord.Interaction, role: discord.Role, label: Optional[str] = None, desc: Optional[str] = None, emoji: Optional[str] = None):
        if interaction.guild is None:
            await interaction.response.send_message("Run this in a server.", ephemeral=True)
            return
        # Safety: bot must be above this role to assign it
        me = interaction.guild.me
        if me is None or role >= me.top_role:
            await interaction.response.send_message("I can’t assign that role (my role must be higher).", ephemeral=True)
            return
        self._set_role_cfg(interaction.guild, role.id, label or role.name, desc or "", emoji or "")
        await interaction.response.send_message(f"✅ Added **{role.name}** to the self-assign menu.", ephemeral=True)

    @app_commands.command(name="roles_menu_remove", description="(Admin) Disallow a role from self-assign")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(role="Role to remove")
    async def roles_menu_remove(self, interaction: discord.Interaction, role: discord.Role):
        if interaction.guild is None:
            await interaction.response.send_message("Run this in a server.", ephemeral=True)
            return
        self._remove_role_cfg(interaction.guild, role.id)
        await interaction.response.send_message(f"🗑️ Removed **{role.name}** from the menu.", ephemeral=True)

    @app_commands.command(name="roles_menu_list", description="(Admin) List roles in the self-assign menu")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def roles_menu_list(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("Run this in a server.", ephemeral=True)
            return
        roles = self._list_roles(interaction.guild)
        if not roles:
            await interaction.response.send_message("No roles configured yet. Use `/roles_menu_add`.", ephemeral=True)
            return
        gmap = self._store.get(_guild_key(interaction.guild), {})
        lines = []
        for r in roles:
            meta = gmap.get(str(r.id), {})
            lab = meta.get("label") or r.name
            desc = meta.get("desc") or ""
            emo = meta.get("emoji") or ""
            lines.append(f"- {r.mention} (`{r.id}`) — **{lab}** {emo} {('· ' + desc) if desc else ''}")
        msg = "\n".join(lines)
        await interaction.response.send_message(f"**Self-assign roles:**\n{msg}", ephemeral=True)

    @app_commands.command(name="roles_menu_post", description="(Admin) Post the self-assign role selector here")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def roles_menu_post(self, interaction: discord.Interaction):
        if interaction.guild is None or interaction.channel is None:
            await interaction.response.send_message("Run this in a server channel.", ephemeral=True)
            return
        view = self._build_view(interaction.guild)
        if view is None:
            await interaction.response.send_message("No roles configured. Use `/roles_menu_add` first.", ephemeral=True)
            return
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