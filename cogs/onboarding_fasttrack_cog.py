# cogs/onboarding_fasttrack_cog.py
#
# Lightweight welcome flow + lore-driven #void
# - Public welcome embed in #welcome (or fallback)
# - DM welcome (optional)
# - /welcome_preview (owner or Manage Server)
# - OPTIONAL: scheduled cryptic broadcasts into #void
#
import os
import logging
from typing import Optional, List, Tuple

import discord
from discord.ext import commands, tasks
from discord import app_commands

log = logging.getLogger(__name__)

OWNER_USER_ID = int(os.getenv("OWNER_USER_ID", "0") or 0)

def _env_bool(name: str, default: bool = True) -> bool:
    v = os.getenv(name)
    return default if v is None else str(v).lower() in ("1", "true", "y", "yes", "on")

WELCOME_CHANNEL_ID = int(os.getenv("WELCOME_CHANNEL_ID", "0") or 0)
DM_WELCOME_ENABLE = _env_bool("DM_WELCOME_ENABLE", True)

DEFAULT_STEPS = [
    "rules",
    "welcome",
    "announcements",
    "introductions",
    "faq",
    "void",
    "lobby",
]
WELCOME_STEPS: List[str] = [
    s.strip() for s in (os.getenv("WELCOME_STEPS") or "").split(",") if s.strip()
] or DEFAULT_STEPS

# ---- #void scheduled broadcast controls ----
VOID_BROADCAST_ENABLE = _env_bool("VOID_BROADCAST_ENABLE", False)
VOID_BROADCAST_HOURS = int(os.getenv("VOID_BROADCAST_HOURS", "72"))  # every 3 days by default

# Default cryptic messages (comma-separated env can override)
_default_void_msgs = [
    "The Void hums tonight. Those who listen may hear the door unlatch.",
    "Signals drift between worlds. Loyalty sharpens the signal; apathy dulls it.",
    "Beyond the welcome lies the work. The Inner Circle is not a place—it’s a decision.",
    "Clues hide in plain sight. Patterns emerge to those who persist.",
    "The red pill is not a color. It is consent to see with both eyes open.",
    "Not all watchers are seen. Not all doors are locked.",
]
VOID_BROADCAST_MESSAGES: List[str] = [
    s.strip() for s in (os.getenv("VOID_BROADCAST_MESSAGES") or "").split(",") if s.strip()
] or _default_void_msgs


# ---------- channel resolution helpers ----------

def _find_channel(
    guild: discord.Guild, *, prefer_id: Optional[int] = None, names: List[str]
) -> Tuple[Optional[discord.abc.GuildChannel], List[discord.abc.GuildChannel]]:
    # Prefer explicit ID
    if prefer_id:
        ch = guild.get_channel(prefer_id)
        if isinstance(ch, (discord.TextChannel, discord.ForumChannel, discord.Thread)):
            return ch, [ch]
    # Exact name match
    name_map = {c.name.lower(): c for c in guild.text_channels}
    for n in names:
        ch = name_map.get(n.lower())
        if ch:
            return ch, [ch]
    # Startswith fallback
    starts = [
        c for c in guild.text_channels
        if any(c.name.lower().startswith(n.lower()) for n in names)
    ]
    best = starts[0] if starts else None
    return best, starts

def _fmt_ch(ch: Optional[discord.TextChannel]) -> str:
    return ch.mention if isinstance(ch, discord.TextChannel) else "*(channel not found)*"


# ---------- embeds ----------

def _steps_embed(guild: discord.Guild, member: discord.Member) -> discord.Embed:
    # Resolve commonly-used channels by provided WELCOME_STEPS
    by_name = {}
    for n in WELCOME_STEPS:
        ch, _ = _find_channel(guild, names=[n])
        by_name[n.lower()] = ch

    e = discord.Embed(
        title=f"Welcome, {member.display_name}!",
        description=(
            "You’ve entered **Legends in Motion HQ** — the outer layer of a larger design.\n"
            "Follow these steps to find your footing:"
        ),
        color=discord.Color.blurple(),
    )

    lines = []
    if by_name.get("rules"):
        lines.append(f"• **Read the rules:** {_fmt_ch(by_name.get('rules'))}")
    if by_name.get("introductions"):
        lines.append(f"• **Say hello:** {_fmt_ch(by_name.get('introductions'))}")
    if by_name.get("lobby"):
        lines.append(f"• **Chat in the lobby:** {_fmt_ch(by_name.get('lobby'))}")
    if by_name.get("announcements"):
        lines.append(f"• **Server updates:** {_fmt_ch(by_name.get('announcements'))}")
    if by_name.get("faq"):
        lines.append(f"• **FAQ & quick answers:** {_fmt_ch(by_name.get('faq'))}")

    # Special lore treatment for #void
    if by_name.get("void"):
        lines.append(
            f"• **{_fmt_ch(by_name.get('void'))}** — signals drop here. Some are cryptic, all are intentional."
        )

    if by_name.get("welcome"):
        lines.append(f"• **Return point:** {_fmt_ch(by_name.get('welcome'))}")

    if not lines:
        lines.append("• Explore the channels on the left to get started.")

    e.add_field(name="Start Here", value="\n".join(lines), inline=False)
    e.set_footer(text="“Choice is the first step to freedom. Ask /ask to begin.” — Morpheus")
    return e


def _dm_embed(guild: discord.Guild, member: discord.Member) -> discord.Embed:
    rules_ch, _ = _find_channel(guild, names=["rules"])
    intro_ch, _ = _find_channel(guild, names=["introductions"])
    lobby_ch, _ = _find_channel(guild, names=["lobby"])

    dm = discord.Embed(
        title="Welcome to Legends in Motion HQ",
        description=(
            f"{member.mention}, I’m **Morpheus**.\n"
            f"- Read the rules: {_fmt_ch(rules_ch)}\n"
            f"- Introduce yourself: {_fmt_ch(intro_ch)}\n"
            f"- Say hello in the lobby: {_fmt_ch(lobby_ch)}\n\n"
            "Use `/ask` if you want a guide. When you are ready, the Inner Circle awaits."
        ),
        color=discord.Color.dark_teal(),
    )
    dm.set_footer(text="Keep notifications sane; follow only what you need.")
    return dm


# ---------- Cog ----------

class OnboardingFastTrack(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Start #void broadcaster if enabled
        if VOID_BROADCAST_ENABLE:
            self.void_broadcaster.start()

    def cog_unload(self):
        if VOID_BROADCAST_ENABLE:
            self.void_broadcaster.cancel()

    # ----- Welcome listener -----
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot or not member.guild:
            return

        guild = member.guild
        welcome_ch, _ = _find_channel(
            guild,
            prefer_id=WELCOME_CHANNEL_ID if WELCOME_CHANNEL_ID else None,
            names=["welcome", "getting-started"],
        )

        # Public welcome
        try:
            embed = _steps_embed(guild, member)
            if isinstance(welcome_ch, discord.TextChannel):
                await welcome_ch.send(member.mention, embed=embed)
        except Exception as e:
            log.warning("Welcome flow: failed to post in welcome channel: %s", e)

        # DM welcome (optional)
        if DM_WELCOME_ENABLE:
            try:
                await member.send(embed=_dm_embed(guild, member))
            except Exception:
                pass  # DMs may be closed

    # ----- Preview command -----
    @app_commands.command(
        name="welcome_preview",
        description="Preview the welcome flow (public/DM/both) without rejoining.",
    )
    @app_commands.describe(
        location="Where to send the preview",
        member="Preview as this member (defaults to you)",
    )
    @app_commands.choices(
        location=[
            app_commands.Choice(name="Public only (here)", value="public"),
            app_commands.Choice(name="DM only", value="dm"),
            app_commands.Choice(name="Both", value="both"),
        ]
    )
    async def welcome_preview(
        self,
        interaction: discord.Interaction,
        location: app_commands.Choice[str],
        member: Optional[discord.Member] = None,
    ):
        is_owner = OWNER_USER_ID and interaction.user.id == OWNER_USER_ID
        has_manage = (
            isinstance(interaction.user, discord.Member)
            and interaction.user.guild_permissions.manage_guild
        )
        if not (is_owner or has_manage):
            await interaction.response.send_message(
                "You need **Manage Server** or to be the owner to run this.",
                ephemeral=True,
            )
            return

        if not interaction.guild:
            await interaction.response.send_message("Run this inside a server.", ephemeral=True)
            return

        target = member or (
            interaction.user if isinstance(interaction.user, discord.Member) else None
        )
        if not target:
            await interaction.response.send_message("No member to preview for.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        results = []

        if location.value in ("public", "both"):
            try:
                msg = await interaction.channel.send(
                    f"(Preview for **{target.display_name}**)",
                    embed=_steps_embed(interaction.guild, target),
                )
                results.append(f"Public: sent")
            except Exception as e:
                results.append(f"Public failed: {e.__class__.__name__}")

        if location.value in ("dm", "both"):
            try:
                await target.send(embed=_dm_embed(interaction.guild, target))
                results.append("DM: sent")
            except Exception as e:
                results.append(f"DM failed: {e.__class__.__name__}")

        await interaction.followup.send("Preview result:\n- " + "\n- ".join(results), ephemeral=True)

    # ----- #void broadcaster (optional) -----
    @tasks.loop(hours=VOID_BROADCAST_HOURS)
    async def void_broadcaster(self):
        # Iterate all guilds the bot is in and post into #void (first match)
        for guild in self.bot.guilds:
            void_ch, _ = _find_channel(guild, names=["void"])
            if isinstance(void_ch, discord.TextChannel):
                try:
                    text = VOID_BROADCAST_MESSAGES[0]
                    # rotate list (simple shift)
                    VOID_BROADCAST_MESSAGES.append(VOID_BROADCAST_MESSAGES.pop(0))
                    await void_ch.send(f"**[signal]** {text}")
                except Exception as e:
                    log.debug("void broadcast failed in %s: %s", guild.name, e)

    @void_broadcaster.before_loop
    async def _before_void_broadcast(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(OnboardingFastTrack(bot))