# cogs/disaster_recovery_cog.py
# M.O.P.H.E.U.S. – Disaster Recovery (Snapshot + Bridge)
#
# What this cog does:
# 1) /dr_snapshot_export  -> save server layout (roles, categories, channels, overwrites) to data/dr_snapshot_<guild>.json
# 2) /dr_clone_from <source_guild_id> -> recreate roles/cats/channels in *current* guild from a saved snapshot
# 3) Simple channel bridges across servers:
#    /dr_bridge_add <source_channel_id> <dest_channel_id>
#    /dr_bridge_remove <source_channel_id> <dest_channel_id>
#    /dr_bridge_list
#    (mirrors messages forward-time only; avoids loops; forwards attachments)
#
# Notes & limits:
# - Cannot migrate members or message history (Discord API limitation).
# - Snapshot captures structure + overwrites; role positions are best-effort.
# - You must invite the bot with permission to Manage Roles/Channels/Webhooks.
# - Bridges start relaying *after* you add them. They don’t backfill history.

import os
import io
import json
import asyncio
from typing import Dict, Any, List, Tuple, Optional

import discord
from discord.ext import commands
from discord import app_commands

DATA_DIR = "data"
SNAP_DIR = os.path.join(DATA_DIR, "dr_snapshots")
BRIDGES_PATH = os.path.join(DATA_DIR, "dr_bridges.json")

def _ensure_dirs():
    os.makedirs(SNAP_DIR, exist_ok=True)
    os.makedirs(DATA_DIR, exist_ok=True)

def _load_json(path: str, fallback):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return fallback

def _save_json(path: str, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def _snap_path(gid: int) -> str:
    return os.path.join(SNAP_DIR, f"dr_snapshot_{gid}.json")

def _safe_name(s: str, fallback: str = "untitled"):
    s = (s or "").strip()
    return s if s else fallback

class DisasterRecoveryCog(commands.Cog, name="Disaster Recovery"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        _ensure_dirs()
        # bridges: list of {"src": int, "dst": int}
        self.bridges: List[Dict[str, int]] = _load_json(BRIDGES_PATH, [])
        # quick lookup maps to avoid loops
        self._src_to_dst = {(b["src"], b["dst"]) for b in self.bridges}
        self._dst_set = {b["dst"] for b in self.bridges}

    # -------------------------
    # Snapshot (export)
    # -------------------------
    @app_commands.command(name="dr_snapshot_export", description="Export this server's structure to a local snapshot.")
    @app_commands.checks.has_permissions(administrator=True)
    async def dr_snapshot_export(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("Run this in a server.", ephemeral=True)
            return

        await interaction.response.send_message("📦 Collecting snapshot…", ephemeral=True)

        guild: discord.Guild = interaction.guild
        # Roles: store in display order (from bottom to top). We'll recreate in order.
        roles_data = []
        for r in guild.roles:
            # skip @everyone position quirks; we still capture it but won't try to move it
            roles_data.append({
                "id": r.id,  # original ID for mapping perms
                "name": r.name,
                "colour": r.colour.value if r.colour else 0,
                "hoist": r.hoist,
                "mentionable": r.mentionable,
                "permissions": r.permissions.value,
                "position": r.position,
                "managed": r.managed,
            })

        # Categories
        cats_data = []
        for c in sorted(guild.categories, key=lambda c: c.position):
            cats_data.append({
                "id": c.id,
                "name": c.name,
                "position": c.position,
                "overwrites": self._pack_overwrites(c.overwrites),
            })

        # Channels (text + voice + forum etc.)
        chans_data = []
        for ch in sorted(guild.channels, key=lambda x: x.position):
            # Only recreate user-visible guild channels (not categories again)
            if isinstance(ch, (discord.TextChannel, discord.VoiceChannel, discord.ForumChannel, discord.StageChannel)):
                parent_id = ch.category.id if ch.category else None
                base: Dict[str, Any] = {
                    "id": ch.id,
                    "name": ch.name,
                    "type": int(ch.type.value),
                    "position": ch.position,
                    "nsfw": getattr(ch, "nsfw", False),
                    "topic": getattr(ch, "topic", None),
                    "bitrate": getattr(ch, "bitrate", None),
                    "user_limit": getattr(ch, "user_limit", None),
                    "slowmode_delay": getattr(ch, "slowmode_delay", 0),
                    "parent_id": parent_id,
                    "overwrites": self._pack_overwrites(ch.overwrites),
                }
                # Forum specific
                if isinstance(ch, discord.ForumChannel):
                    base["default_thread_slowmode_delay"] = ch.default_thread_slowmode_delay
                    base["default_auto_archive_duration"] = ch.default_auto_archive_duration
                chans_data.append(base)

        snap = {
            "guild": {
                "id": guild.id,
                "name": guild.name,
                "icon": str(guild.icon) if guild.icon else None,
            },
            "roles": roles_data,
            "categories": cats_data,
            "channels": chans_data,
            "version": 1,
        }

        _save_json(_snap_path(guild.id), snap)
        await interaction.followup.send(f"✅ Snapshot saved: `data/dr_snapshots/dr_snapshot_{guild.id}.json`", ephemeral=True)

    # -------------------------
    # Clone (import) – run in DESTINATION guild
    # -------------------------
    @app_commands.command(name="dr_clone_from", description="Clone structure here from a saved snapshot of another guild.")
    @app_commands.describe(source_guild_id="Guild ID we previously exported from with /dr_snapshot_export")
    @app_commands.checks.has_permissions(administrator=True)
    async def dr_clone_from(self, interaction: discord.Interaction, source_guild_id: str):
        if interaction.guild is None:
            await interaction.response.send_message("Run this in a server.", ephemeral=True)
            return

        try:
            src_id = int(source_guild_id)
        except Exception:
            await interaction.response.send_message("Invalid guild ID.", ephemeral=True)
            return

        path = _snap_path(src_id)
        snap = _load_json(path, None)
        if not snap:
            await interaction.response.send_message(f"Snapshot not found at `{path}`. Run /dr_snapshot_export in the source server first.", ephemeral=True)
            return

        await interaction.response.send_message("🛠️ Cloning roles, categories, and channels… (this can take a minute)", ephemeral=True)

        dest: discord.Guild = interaction.guild
        # 1) Create roles (skip @everyone)
        # Build role map: original_role_id -> new_role
        role_map: Dict[int, discord.Role] = {}
        roles_sorted = sorted([r for r in snap["roles"] if r["name"] != "@everyone"], key=lambda r: r["position"])
        for r in roles_sorted:
            # Create or find if exists
            existing = discord.utils.get(dest.roles, name=r["name"])
            if existing:
                role_map[r["id"]] = existing
                continue
            perms = discord.Permissions(r["permissions"])
            try:
                new_r = await dest.create_role(
                    name=_safe_name(r["name"]),
                    permissions=perms,
                    colour=discord.Colour(r["colour"]),
                    hoist=r["hoist"],
                    mentionable=r["mentionable"],
                    reason="DR clone: create role"
                )
                role_map[r["id"]] = new_r
                await asyncio.sleep(0.4)  # gentle on rate limits
            except discord.Forbidden:
                continue

        # 2) Create categories
        cat_map: Dict[int, discord.CategoryChannel] = {}
        for c in sorted(snap["categories"], key=lambda c: c["position"]):
            name = _safe_name(c["name"])
            ow = self._unpack_overwrites(dest, c["overwrites"], role_map)
            existing = discord.utils.get(dest.categories, name=name)
            if existing:
                cat_map[c["id"]] = existing
                # Apply overwrites
                try:
                    await existing.edit(overwrites=ow, reason="DR clone: set category overwrites")
                except discord.Forbidden:
                    pass
                continue

            try:
                new_cat = await dest.create_category(name=name, overwrites=ow, reason="DR clone: create category")
                cat_map[c["id"]] = new_cat
                await asyncio.sleep(0.4)
            except discord.Forbidden:
                continue

        # 3) Create channels
        for ch in sorted(snap["channels"], key=lambda x: x["position"]):
            name = _safe_name(ch["name"])
            parent = cat_map.get(ch["parent_id"]) if ch.get("parent_id") else None
            ow = self._unpack_overwrites(dest, ch["overwrites"], role_map)

            # detect existence
            maybe = discord.utils.get(dest.channels, name=name, category=parent)
            if maybe:
                try:
                    await maybe.edit(
                        overwrites=ow,
                        topic=ch.get("topic"),
                        slowmode_delay=ch.get("slowmode_delay", 0),
                        nsfw=ch.get("nsfw", False),
                        reason="DR clone: update channel",
                    )
                except Exception:
                    pass
                continue

            try:
                ctype = discord.ChannelType(ch["type"])
                created = None
                if ctype is discord.ChannelType.text:
                    created = await dest.create_text_channel(
                        name=name, category=parent, overwrites=ow,
                        topic=ch.get("topic"),
                        slowmode_delay=ch.get("slowmode_delay", 0),
                        nsfw=ch.get("nsfw", False),
                        reason="DR clone: create text channel"
                    )
                elif ctype is discord.ChannelType.voice:
                    created = await dest.create_voice_channel(
                        name=name, category=parent, overwrites=ow,
                        bitrate=ch.get("bitrate") or 64000,
                        user_limit=ch.get("user_limit") or 0,
                        reason="DR clone: create voice channel"
                    )
                elif ctype is discord.ChannelType.forum:
                    # Minimal forum creation (discord.py API requires defaults)
                    created = await dest.create_forum(
                        name=name, category=parent, overwrites=ow,
                        reason="DR clone: create forum"
                    )
                elif ctype is discord.ChannelType.stage_voice:
                    created = await dest.create_stage_channel(
                        name=name, category=parent, overwrites=ow,
                        reason="DR clone: create stage channel"
                    )
                # else: skip other exotic types for simplicity

                if created:
                    await asyncio.sleep(0.5)
            except discord.Forbidden:
                continue

        await interaction.followup.send("✅ Clone completed. Review perms & ordering, then flip your bridges and invite members.", ephemeral=True)

    # -------------------------
    # Bridges (message mirroring)
    # -------------------------
    @app_commands.command(name="dr_bridge_add", description="Start mirroring messages from a source channel to a destination channel.")
    @app_commands.describe(source_channel_id="Channel ID to read", dest_channel_id="Channel ID to write")
    @app_commands.checks.has_permissions(administrator=True)
    async def dr_bridge_add(self, interaction: discord.Interaction, source_channel_id: str, dest_channel_id: str):
        try:
            s = int(source_channel_id); d = int(dest_channel_id)
        except Exception:
            await interaction.response.send_message("IDs must be integers.", ephemeral=True)
            return

        if (s, d) in self._src_to_dst:
            await interaction.response.send_message("That bridge already exists.", ephemeral=True)
            return

        # sanity checks
        s_ch = self.bot.get_channel(s)
        d_ch = self.bot.get_channel(d)
        if not isinstance(s_ch, (discord.TextChannel, discord.Thread, discord.ForumChannel)):
            await interaction.response.send_message("Source must be a text/thread/forum channel I can read.", ephemeral=True)
            return
        if not isinstance(d_ch, (discord.TextChannel, discord.Thread, discord.ForumChannel)):
            await interaction.response.send_message("Destination must be a text/thread/forum channel I can write to.", ephemeral=True)
            return

        self.bridges.append({"src": s, "dst": d})
        _save_json(BRIDGES_PATH, self.bridges)
        self._src_to_dst.add((s, d))
        self._dst_set.add(d)
        await interaction.response.send_message(f"🔗 Bridge added: `{s}` → `{d}`. I’ll mirror new messages forward from now on.", ephemeral=True)

    @app_commands.command(name="dr_bridge_remove", description="Remove a mirror bridge.")
    @app_commands.describe(source_channel_id="Channel ID to read", dest_channel_id="Channel ID to write")
    @app_commands.checks.has_permissions(administrator=True)
    async def dr_bridge_remove(self, interaction: discord.Interaction, source_channel_id: str, dest_channel_id: str):
        try:
            s = int(source_channel_id); d = int(dest_channel_id)
        except Exception:
            await interaction.response.send_message("IDs must be integers.", ephemeral=True)
            return

        before = len(self.bridges)
        self.bridges = [b for b in self.bridges if not (b["src"] == s and b["dst"] == d)]
        _save_json(BRIDGES_PATH, self.bridges)
        self._src_to_dst = {(b["src"], b["dst"]) for b in self.bridges}
        self._dst_set = {b["dst"] for b in self.bridges}

        if len(self.bridges) < before:
            await interaction.response.send_message("🛈 Bridge removed.", ephemeral=True)
        else:
            await interaction.response.send_message("No matching bridge found.", ephemeral=True)

    @app_commands.command(name="dr_bridge_list", description="List active mirror bridges.")
    @app_commands.checks.has_permissions(administrator=True)
    async def dr_bridge_list(self, interaction: discord.Interaction):
        if not self.bridges:
            await interaction.response.send_message("No active bridges.", ephemeral=True)
            return
        lines = [f"- `{b['src']}` → `{b['dst']}`" for b in self.bridges]
        await interaction.response.send_message("**Active Bridges:**\n" + "\n".join(lines), ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Don’t relay DMs / bots / commands / webhooks / our own echoes
        if not message.guild or message.author.bot:
            return
        if message.webhook_id is not None:
            # messages coming from webhooks (incl. our own) – skip to prevent loops
            return
        if message.content.startswith(("/", "!", ".")):  # crude guard: don't replicate commands
            pass  # still allowed if you want; we can choose to skip commands to reduce spam

        # Find bridges starting from this channel
        pairs = [b for b in self.bridges if b["src"] == message.channel.id]
        if not pairs:
            return

        # Prepare attachments (download -> re-upload)
        files: List[discord.File] = []
        for a in message.attachments:
            try:
                b = await a.read(use_cached=True)
                files.append(discord.File(io.BytesIO(b), filename=a.filename))
            except Exception:
                continue

        content = message.content
        # Add light provenance footer so people know it's mirrored
        if content:
            content += f"\n\n— _mirrored from **#{message.channel.name}** ({message.guild.name})_"

        embeds = []
        for e in message.embeds:
            # Shallow copy; we don’t mutate author’s embeds
            try:
                embeds.append(e)
            except Exception:
                pass

        # Fan-out to destinations
        for b in pairs:
            dest = self.bot.get_channel(b["dst"])
            if not isinstance(dest, (discord.TextChannel, discord.Thread, discord.ForumChannel)):
                continue
            try:
                await dest.send(content=content or None, embeds=embeds or None, files=files or None, allowed_mentions=discord.AllowedMentions.none())
                await asyncio.sleep(0.3)
            except discord.Forbidden:
                continue
            except Exception:
                continue
        # cleanup file buffers
        for f in files:
            try:
                f.close()
            except Exception:
                pass

    # -------------------------
    # Helpers
    # -------------------------
    def _pack_overwrites(self, ov: Dict[discord.abc.Snowflake, discord.PermissionOverwrite]) -> List[Dict[str, Any]]:
        """Serialize overwrites to JSON: {target_type, target_id, allow, deny}."""
        out = []
        for target, perms in ov.items():
            t_type = "role" if isinstance(target, discord.Role) else "member"
            out.append({
                "type": t_type,
                "target_id": target.id,
                "allow": perms.pair()[0].value,
                "deny": perms.pair()[1].value,
            })
        return out

    def _unpack_overwrites(self, guild: discord.Guild, packed: List[Dict[str, Any]], role_map: Dict[int, discord.Role]):
        """Rebuild Overwrites using role_map for role targets; ignore member-target OVs for safety."""
        out: Dict[discord.abc.Snowflake, discord.PermissionOverwrite] = {}
        for item in packed or []:
            if item["type"] == "role":
                orig_id = int(item["target_id"])
                role = role_map.get(orig_id)
                if role:
                    allow = discord.Permissions(item.get("allow", 0))
                    deny = discord.Permissions(item.get("deny", 0))
                    out[role] = discord.PermissionOverwrite.from_pair(allow, deny)
            # Member-specific overwrites are intentionally skipped (users differ across servers)
        return out


async def setup(bot: commands.Bot):
    await bot.add_cog(DisasterRecoveryCog(bot))