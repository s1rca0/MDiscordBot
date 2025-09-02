# cogs/backup_clone_cog.py
import json
import os
from typing import Dict, Any, List, Optional

import discord
from discord.ext import commands
from discord import app_commands

def _safe_str(x: Any, limit=256) -> str:
    s = str(x) if x is not None else ""
    return s[:limit]

class BackupCloneCog(commands.Cog, name="Backup / Clone"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _is_admin(self, member: Optional[discord.Member]) -> bool:
        if member is None:
            return False
        if member.guild_permissions.administrator:
            return True
        owner_id = int(os.getenv("OWNER_USER_ID", "0") or "0")
        return int(member.id) == owner_id

    @app_commands.command(name="backup_export", description="(Admin) Export roles/categories/channels as JSON.")
    @app_commands.describe(with_roles="Include role names/colors (no permissions).")
    async def backup_export(self, interaction: discord.Interaction, with_roles: bool = True):
        if interaction.guild is None or not self._is_admin(interaction.user if isinstance(interaction.user, discord.Member) else None):
            await interaction.response.send_message("Insufficient permission.", ephemeral=True)
            return

        g = interaction.guild

        # roles (excluding @everyone)
        roles_dump: List[Dict[str, Any]] = []
        if with_roles:
            for r in sorted(g.roles, key=lambda r: r.position, reverse=False):
                if r.is_default():
                    continue
                roles_dump.append({
                    "name": r.name,
                    "color": r.color.value if isinstance(r.color, discord.Colour) else 0,
                    "hoist": r.hoist,
                    "mentionable": r.mentionable,
                })

        # categories + channels
        cats: List[Dict[str, Any]] = []
        for cat in sorted(g.categories, key=lambda c: c.position):
            item = {
                "name": cat.name,
                "channels": []
            }
            for ch in sorted(cat.channels, key=lambda c: c.position):
                if isinstance(ch, discord.TextChannel):
                    item["channels"].append({
                        "type": "text",
                        "name": ch.name,
                        "topic": _safe_str(ch.topic),
                        "slowmode": ch.slowmode_delay or 0,
                        "nsfw": ch.is_nsfw(),
                    })
                elif isinstance(ch, discord.VoiceChannel):
                    item["channels"].append({
                        "type": "voice",
                        "name": ch.name,
                        "bitrate": ch.bitrate,
                        "user_limit": ch.user_limit or 0,
                    })
            cats.append(item)

        dump = {
            "guild_name": g.name,
            "roles": roles_dump,
            "categories": cats,
        }
        data = json.dumps(dump, indent=2)
        file = discord.File(fp=discord.BytesIO(data.encode("utf-8")), filename="server_template.json")
        await interaction.response.send_message("Template exported.", file=file, ephemeral=True)

    @app_commands.command(name="backup_import", description="(Admin) Import a JSON template to build structure here.")
    async def backup_import(self, interaction: discord.Interaction, template: discord.Attachment):
        if interaction.guild is None or not self._is_admin(interaction.user if isinstance(interaction.user, discord.Member) else None):
            await interaction.response.send_message("Insufficient permission.", ephemeral=True)
            return

        try:
            raw = await template.read()
            payload = json.loads(raw.decode("utf-8"))
        except Exception:
            await interaction.response.send_message("Could not parse template JSON.", ephemeral=True)
            return

        await interaction.response.send_message("Working… I’ll build the framework. This may take a moment.", ephemeral=True)

        # roles first (optional)
        try:
            for r in payload.get("roles", []):
                try:
                    await interaction.guild.create_role(
                        name=r.get("name", "role"),
                        colour=discord.Colour(r.get("color", 0)),
                        hoist=r.get("hoist", False),
                        mentionable=r.get("mentionable", False),
                        reason="Backup import (roles)",
                    )
                except discord.HTTPException:
                    pass
        except Exception:
            pass

        # categories + channels
        for cat in payload.get("categories", []):
            try:
                new_cat = await interaction.guild.create_category(cat.get("name", "category"), reason="Backup import (category)")
            except discord.HTTPException:
                continue

            for ch in cat.get("channels", []):
                t = ch.get("type")
                nm = ch.get("name", "channel")
                try:
                    if t == "text":
                        await interaction.guild.create_text_channel(
                            nm, category=new_cat,
                            topic=ch.get("topic") or None,
                            slowmode_delay=int(ch.get("slowmode", 0) or 0),
                            nsfw=bool(ch.get("nsfw", False)),
                            reason="Backup import (text)",
                        )
                    elif t == "voice":
                        await interaction.guild.create_voice_channel(
                            nm, category=new_cat,
                            bitrate=int(ch.get("bitrate", 64000) or 64000),
                            user_limit=int(ch.get("user_limit", 0) or 0),
                            reason="Backup import (voice)",
                        )
                except discord.HTTPException:
                    continue

        try:
            await interaction.followup.send("Frame established. Flesh it out as needed.", ephemeral=True)
        except Exception:
            pass

async def setup(bot: commands.Bot):
    await bot.add_cog(BackupCloneCog(bot))