# tickets_cog.py
# top of cogs/tickets_cog.py
import os
from typing import List
from config import cfg

def _parse_roles(env: str) -> List[int]:
    out = []
    for p in (env or "").replace(" ", "").split(","):
        if p.isdigit():
            out.append(int(p))
    return out

TICKET_STAFF_ROLES = getattr(cfg, "TICKET_STAFF_ROLES", None)
if TICKET_STAFF_ROLES is None:
    TICKET_STAFF_ROLES = _parse_roles(os.getenv("TICKET_STAFF_ROLES", ""))  # [] if unset
import os
import io
import json
import time
from typing import Optional, List

import discord
from discord.ext import commands
from discord import app_commands

from config import BotConfig

cfg = BotConfig()

DATA_DIR = "data"
TICKET_CFG_PATH = os.path.join(DATA_DIR, "ticket_config.json")

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

def _parse_role_ids(s: str) -> List[int]:
    ids = []
    for part in (s or "").replace(" ", "").split(","):
        if not part:
            continue
        try:
            ids.append(int(part))
        except ValueError:
            continue
    return ids

class TicketsCog(commands.Cog, name="Tickets"):
    """
    Private-thread ticket system:
      - /ticket open [subject]
      - /ticket add @user
      - /ticket remove @user
      - /ticket close
      - /ticket transcript [limit]
      - /ticket_sethome  (admin)
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._cfg = _load_json(TICKET_CFG_PATH, {
            "home_channel_id": int(cfg.TICKET_HOME_CHANNEL_ID or 0),
            "staff_role_ids": _parse_role_ids(cfg.TICKET_STAFF_ROLES),
        })

    # ------------- helpers -------------
    def _home_channel(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        ch_id = int(self._cfg.get("home_channel_id") or 0)
        if ch_id:
            ch = guild.get_channel(ch_id)
            if isinstance(ch, discord.TextChannel):
                return ch
        # fallback: system channel or first text channel
        if guild.system_channel:
            return guild.system_channel
        for ch in guild.text_channels:
            return ch
        return None

    def _staff_roles(self, guild: discord.Guild) -> List[discord.Role]:
        ids = list(map(int, self._cfg.get("staff_role_ids", [])))
        roles = []
        for rid in ids:
            r = guild.get_role(rid)
            if r:
                roles.append(r)
        return roles

    async def _ping_staff_text(self, guild: discord.Guild) -> str:
        roles = self._staff_roles(guild)
        if not roles:
            return "(No staff roles configured)"
        return " ".join(r.mention for r in roles)

    def _pretty_ts(self) -> str:
        return time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())

    # ------------- commands -------------
    @app_commands.command(name="ticket", description="Ticket actions: open/add/remove/close/transcript")
    @app_commands.describe(
        action="open | add | remove | close | transcript",
        subject_or_user="If open: subject; If add/remove: @user; If transcript: number of messages (e.g., 200)"
    )
    async def ticket_entry(self, interaction: discord.Interaction, action: str, subject_or_user: Optional[str] = None):
        """
        Convenience single entry; equivalent to the dedicated sub-commands below.
        """
        action = (action or "").lower().strip()
        if action == "open":
            await self.open(interaction, subject_or_user or "Support request")
        elif action == "add":
            await self.add(interaction, subject_or_user or "")
        elif action == "remove":
            await self.remove(interaction, subject_or_user or "")
        elif action == "close":
            await self.close(interaction)
        elif action == "transcript":
            # subject_or_user used as limit
            try:
                limit = int(subject_or_user) if subject_or_user else 500
            except Exception:
                limit = 500
            await self.transcript(interaction, limit)
        else:
            await interaction.response.send_message(
                "Usage: `/ticket action:<open|add|remove|close|transcript> [subject_or_user]`",
                ephemeral=True
            )

    # --- Dedicated sub-commands (easier UX) ---
    @app_commands.command(name="ticket_open", description="Open a private support ticket")
    @app_commands.describe(subject="Short subject/topic")
    async def open(self, interaction: discord.Interaction, subject: Optional[str] = "Support request"):
        if interaction.guild is None:
            await interaction.response.send_message("Run this in a server.", ephemeral=True)
            return

        home = self._home_channel(interaction.guild) or interaction.channel
        if not isinstance(home, discord.TextChannel):
            await interaction.response.send_message("No suitable home channel to create a thread.", ephemeral=True)
            return

        base_name = f"ticket-{interaction.user.name}".lower().replace(" ", "-")[:64]
        thread_name = f"{base_name}-{int(time.time())%100000}"
        await interaction.response.defer(ephemeral=True)

        # Try private thread first (best for tickets). Fall back to public thread if needed.
        thread = None
        try:
            thread = await home.create_thread(
                name=thread_name,
                type=discord.ChannelType.private_thread,
                invitable=False
            )
        except Exception:
            try:
                thread = await home.create_thread(
                    name=thread_name,
                    type=discord.ChannelType.public_thread
                )
            except Exception:
                thread = None

        if thread is None:
            await interaction.followup.send("Couldn’t create a thread here. Do I have Manage Threads permission?", ephemeral=True)
            return

        # Add the requester (for private threads you must add)
        try:
            await thread.add_user(interaction.user)
        except Exception:
            pass  # public threads don’t need it

        staff_ping = await self._ping_staff_text(interaction.guild)
        emb = discord.Embed(
            title="New Ticket",
            description=f"**Subject:** {subject}\nOpened by {interaction.user.mention}\nTime: `{self._pretty_ts()}`",
            color=discord.Color.blurple()
        )
        emb.set_footer(text="Use /ticket_close when resolved. Use /ticket_add to invite others.")

        # First message in the ticket thread
        try:
            await thread.send(content=staff_ping, embed=emb)
        except Exception:
            await thread.send(embed=emb)

        await interaction.followup.send(f"✅ Ticket created: {thread.mention}", ephemeral=True)

    @app_commands.command(name="ticket_add", description="Add a user to this private ticket")
    @app_commands.describe(user="User to add (mention)")
    async def add(self, interaction: discord.Interaction, user: str):
        if interaction.channel is None or interaction.channel.type not in (
            discord.ChannelType.private_thread,
            discord.ChannelType.public_thread,
        ):
            await interaction.response.send_message("Use this inside a ticket thread.", ephemeral=True)
            return

        # Resolve user mention or ID
        target = None
        if interaction.guild:
            if interaction.data and "resolved" in interaction.data:
                # (Some clients provide resolved users; but we’ll parse mention/ID safely)
                pass
            try:
                # Try mention like <@123>
                if user.startswith("<@") and user.endswith(">"):
                    uid = int(user.strip("<@!>"))
                    target = await interaction.client.fetch_user(uid)
                else:
                    uid = int(user)
                    target = await interaction.client.fetch_user(uid)
            except Exception:
                # Last resort: try member name lookup
                target = discord.utils.get(interaction.guild.members, name=user) or \
                         discord.utils.get(interaction.guild.members, display_name=user)

        if target is None:
            await interaction.response.send_message("Couldn’t resolve that user.", ephemeral=True)
            return

        try:
            await interaction.channel.add_user(target)
            await interaction.response.send_message(f"✅ Added {target.mention} to this ticket.", ephemeral=True)
            await interaction.channel.send(f"{target.mention} has been added to the ticket.")
        except Exception:
            await interaction.response.send_message("I couldn’t add that user here (need Manage Threads).", ephemeral=True)

    @app_commands.command(name="ticket_remove", description="Remove a user from this private ticket")
    @app_commands.describe(user="User to remove (mention)")
    async def remove(self, interaction: discord.Interaction, user: str):
        if interaction.channel is None or interaction.channel.type not in (
            discord.ChannelType.private_thread,
            discord.ChannelType.public_thread,
        ):
            await interaction.response.send_message("Use this inside a ticket thread.", ephemeral=True)
            return

        target = None
        if interaction.guild:
            try:
                if user.startswith("<@") and user.endswith(">"):
                    uid = int(user.strip("<@!>"))
                    target = await interaction.client.fetch_user(uid)
                else:
                    uid = int(user)
                    target = await interaction.client.fetch_user(uid)
            except Exception:
                pass

        if target is None:
            await interaction.response.send_message("Couldn’t resolve that user.", ephemeral=True)
            return

        try:
            await interaction.channel.remove_user(target)
            await interaction.response.send_message(f"✅ Removed {target.mention} from this ticket.", ephemeral=True)
            await interaction.channel.send(f"{target.mention} has been removed from the ticket.")
        except Exception:
            await interaction.response.send_message("I couldn’t remove that user here (need Manage Threads).", ephemeral=True)

    @app_commands.command(name="ticket_close", description="Close (archive & lock) this ticket")
    async def close(self, interaction: discord.Interaction):
        ch = interaction.channel
        if ch is None or ch.type not in (discord.ChannelType.private_thread, discord.ChannelType.public_thread):
            await interaction.response.send_message("Use this inside a ticket thread.", ephemeral=True)
            return
        try:
            await ch.edit(archived=True, locked=True)
            await interaction.response.send_message("🗃️ Ticket archived & locked. Thanks!", ephemeral=True)
            try:
                await ch.send("This ticket is now closed. A moderator can reopen if needed.")
            except Exception:
                pass
        except Exception:
            await interaction.response.send_message("I couldn’t close this ticket (need Manage Threads).", ephemeral=True)

    @app_commands.command(name="ticket_transcript", description="Save a text transcript of recent messages")
    @app_commands.describe(limit="Number of recent messages to include (default 500)")
    async def transcript(self, interaction: discord.Interaction, limit: Optional[int] = 500):
        ch = interaction.channel
        if ch is None or ch.type not in (discord.ChannelType.private_thread, discord.ChannelType.public_thread):
            await interaction.response.send_message("Use this inside a ticket thread.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        limit = max(10, min(int(limit or 500), 5000))
        lines = []
        try:
            async for m in ch.history(limit=limit, oldest_first=True):
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
        filename = f"transcript-{ch.name}-{int(time.time())}.txt"
        await interaction.followup.send(
            content=f"Here’s the transcript for **#{ch.name}** ({len(lines)} messages).",
            file=discord.File(buf, filename=filename),
            ephemeral=True
        )

    # ----- Admin: set home channel -----
    @app_commands.command(name="ticket_sethome", description="(Admin) Set this channel as the ticket home")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ticket_sethome(self, interaction: discord.Interaction):
        if interaction.guild is None or interaction.channel is None:
            await interaction.response.send_message("Run this in a server channel.", ephemeral=True)
            return
        if interaction.channel.type != discord.ChannelType.text:
            await interaction.response.send_message("Please run this in a standard text channel.", ephemeral=True)
            return
        self._cfg["home_channel_id"] = interaction.channel.id
        _save_json(TICKET_CFG_PATH, self._cfg)
        await interaction.response.send_message(f"✅ Set ticket home to {interaction.channel.mention}", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(TicketsCog(bot))