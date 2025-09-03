# cogs/tickets_cog.py
# Private-thread ticket system consolidated into a single /ticket command (subcommands).
from __future__ import annotations
import io
import os
import time
import json
from typing import Optional, List

import discord
from discord import app_commands
from discord.ext import commands

DATA_DIR = "data"
CFG_PATH  = os.path.join(DATA_DIR, "ticket_config.json")

def _ensure_data():
    os.makedirs(DATA_DIR, exist_ok=True)

def _load_json(path: str, fallback):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return fallback

def _save_json(path: str, data):
    _ensure_data()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def _parse_role_ids_from_env(name: str) -> List[int]:
    raw = (os.getenv(name, "") or "").replace(" ", "")
    out: List[int] = []
    for part in raw.split(","):
        if not part:
            continue
        try:
            out.append(int(part))
        except ValueError:
            pass
    return out

# ---- in-file config (no direct cfg attr access) ----
DEFAULT = {
    "home_channel_id": int(os.getenv("TICKET_HOME_CHANNEL_ID", "0") or 0),
    "staff_role_ids": _parse_role_ids_from_env("TICKET_STAFF_ROLES"),
}

def _pretty_ts() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())

# Make a top-level group so it only counts as ONE application command
ticket = app_commands.Group(name="ticket", description="Support ticket operations")

class TicketsCog(commands.Cog, name="Tickets"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.cfg = _load_json(CFG_PATH, DEFAULT.copy())

    # ---------- helpers ----------
    def _home_channel(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        ch_id = int(self.cfg.get("home_channel_id") or 0)
        if ch_id:
            ch = guild.get_channel(ch_id)
            if isinstance(ch, discord.TextChannel):
                return ch
        # fallback: system channel or first text channel
        if guild.system_channel:
            return guild.system_channel
        return guild.text_channels[0] if guild.text_channels else None

    def _staff_roles(self, guild: discord.Guild) -> List[discord.Role]:
        ids = [int(x) for x in self.cfg.get("staff_role_ids", [])]
        roles: List[discord.Role] = []
        for rid in ids:
            r = guild.get_role(rid)
            if r:
                roles.append(r)
        return roles

    async def _staff_ping_text(self, guild: discord.Guild) -> str:
        roles = self._staff_roles(guild)
        return " ".join(r.mention for r in roles) if roles else "(no staff roles configured)"

    # ---------- admin: set home ----------
    @app_commands.command(name="ticket_sethome", description="(Admin) Set this channel as the ticket home")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ticket_sethome(self, interaction: discord.Interaction):
        if interaction.guild is None or interaction.channel is None or interaction.channel.type != discord.ChannelType.text:
            await interaction.response.send_message("Run in a normal text channel.", ephemeral=True)
            return
        self.cfg["home_channel_id"] = interaction.channel.id
        _save_json(CFG_PATH, self.cfg)
        await interaction.response.send_message(f"✅ Ticket home set to {interaction.channel.mention}", ephemeral=True)

    # ---------- /ticket subcommands ----------
    @ticket.command(name="open", description="Open a private support ticket")
    @app_commands.describe(subject="Short subject/topic")
    async def ticket_open(self, interaction: discord.Interaction, subject: Optional[str] = "Support request"):
        if interaction.guild is None:
            await interaction.response.send_message("Run this in the server.", ephemeral=True)
            return

        home = self._home_channel(interaction.guild) or interaction.channel
        if not isinstance(home, discord.TextChannel):
            await interaction.response.send_message("No suitable home channel here.", ephemeral=True)
            return

        base = f"ticket-{interaction.user.name}".lower().replace(" ", "-")[:64]
        thread_name = f"{base}-{int(time.time())%100000}"

        await interaction.response.defer(ephemeral=True)
        thread = None
        try:
            thread = await home.create_thread(name=thread_name, type=discord.ChannelType.private_thread, invitable=False)
        except Exception:
            try:
                thread = await home.create_thread(name=thread_name, type=discord.ChannelType.public_thread)
            except Exception:
                thread = None

        if thread is None:
            await interaction.followup.send("Couldn't create a thread (need **Manage Threads**).", ephemeral=True)
            return

        try:
            await thread.add_user(interaction.user)  # needed for private threads
        except Exception:
            pass

        staff_ping = await self._staff_ping_text(interaction.guild)
        emb = discord.Embed(
            title="New Ticket",
            description=f"**Subject:** {subject}\nOpened by {interaction.user.mention}\nTime: `{_pretty_ts()}`",
            color=discord.Color.blurple()
        )
        emb.set_footer(text="Use /ticket close when resolved. Use /ticket add to invite others.")
        try:
            await thread.send(content=staff_ping, embed=emb)
        except Exception:
            await thread.send(embed=emb)

        await interaction.followup.send(f"✅ Ticket created: {thread.mention}", ephemeral=True)

    @ticket.command(name="add", description="Add a user to this ticket")
    @app_commands.describe(user="Mention or ID")
    async def ticket_add(self, interaction: discord.Interaction, user: str):
        ch = interaction.channel
        if ch is None or ch.type not in (discord.ChannelType.private_thread, discord.ChannelType.public_thread):
            await interaction.response.send_message("Use this inside a ticket thread.", ephemeral=True)
            return

        target = None
        try:
            if user.startswith("<@") and user.endswith(">"):
                uid = int(user.strip("<@!>"))
            else:
                uid = int(user)
            target = await interaction.client.fetch_user(uid)
        except Exception:
            pass

        if target is None:
            await interaction.response.send_message("Couldn't resolve that user.", ephemeral=True)
            return

        try:
            await ch.add_user(target)
            await interaction.response.send_message(f"✅ Added {target.mention}.", ephemeral=True)
            await ch.send(f"{target.mention} has been added to the ticket.")
        except Exception:
            await interaction.response.send_message("I couldn't add that user (need **Manage Threads**).", ephemeral=True)

    @ticket.command(name="remove", description="Remove a user from this ticket")
    @app_commands.describe(user="Mention or ID")
    async def ticket_remove(self, interaction: discord.Interaction, user: str):
        ch = interaction.channel
        if ch is None or ch.type not in (discord.ChannelType.private_thread, discord.ChannelType.public_thread):
            await interaction.response.send_message("Use this inside a ticket thread.", ephemeral=True)
            return

        target = None
        try:
            if user.startswith("<@") and user.endswith(">"):
                uid = int(user.strip("<@!>"))
            else:
                uid = int(user)
            target = await interaction.client.fetch_user(uid)
        except Exception:
            pass

        if target is None:
            await interaction.response.send_message("Couldn't resolve that user.", ephemeral=True)
            return

        try:
            await ch.remove_user(target)
            await interaction.response.send_message(f"✅ Removed {target.mention}.", ephemeral=True)
            await ch.send(f"{target.mention} has been removed from the ticket.")
        except Exception:
            await interaction.response.send_message("I couldn't remove that user (need **Manage Threads**).", ephemeral=True)

    @ticket.command(name="close", description="Archive & lock this ticket")
    async def ticket_close(self, interaction: discord.Interaction):
        ch = interaction.channel
        if ch is None or ch.type not in (discord.ChannelType.private_thread, discord.ChannelType.public_thread):
            await interaction.response.send_message("Use this inside a ticket thread.", ephemeral=True)
            return
        try:
            await ch.edit(archived=True, locked=True)
            await interaction.response.send_message("🗃️ Ticket archived & locked.", ephemeral=True)
            try:
                await ch.send("This ticket is now closed. A moderator can reopen if needed.")
            except Exception:
                pass
        except Exception:
            await interaction.response.send_message("I couldn't close this ticket (need **Manage Threads**).", ephemeral=True)

    @ticket.command(name="transcript", description="Export a text transcript of recent messages")
    @app_commands.describe(limit="Number of recent messages to include (default 500)")
    async def ticket_transcript(self, interaction: discord.Interaction, limit: Optional[int] = 500):
        ch = interaction.channel
        if ch is None or ch.type not in (discord.ChannelType.private_thread, discord.ChannelType.public_thread):
            await interaction.response.send_message("Use this inside a ticket thread.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        n = max(10, min(int(limit or 500), 5000))
        lines: List[str] = []
        try:
            async for m in ch.history(limit=n, oldest_first=True):
                ts = m.created_at.strftime("%Y-%m-%d %H:%M:%S")
                author = f"{m.author} ({m.author.id})"
                content = m.content or ""
                if m.attachments:
                    content += " " + " ".join(f"[attachment:{a.filename}]({a.url})" for a in m.attachments)
                lines.append(f"[{ts}] {author}: {content}")
        except Exception as e:
            await interaction.followup.send(f"Failed to collect messages: {e}", ephemeral=True)
            return

        buf = io.BytesIO("\n".join(lines).encode("utf-8"))
        await interaction.followup.send(
            content=f"Transcript for **#{ch.name}** ({len(lines)} messages).",
            file=discord.File(buf, filename=f"transcript-{ch.name}-{int(time.time())}.txt"),
            ephemeral=True
        )

async def setup(bot: commands.Bot):
    # Register the single top-level /ticket command
    if bot.tree.get_command("ticket") is None:
        bot.tree.add_command(ticket)
    await bot.add_cog(TicketsCog(bot))