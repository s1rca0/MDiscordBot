# cogs/hackin_cog.py
import os
import random
from typing import Optional, List

import discord
from discord import app_commands
from discord.ext import commands


def _env_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name, str(default))
    return str(v).lower() in ("1", "true", "yes", "y", "on")


# ---------- Configuration (via env) ----------

# Comma-separated list of local file paths to animated GIFs for transmissions.
# Example: "attached_assets/morpheus_transmission.gif,attached_assets/m_code.gif"
HACKIN_GIF_PATHS: List[str] = [
    p.strip() for p in os.getenv("HACKIN_GIF_PATHS", "").split(",") if p.strip()
]

# Fallback still image(s) if no GIF found/available.
HACKIN_IMAGE_PATHS: List[str] = [
    p.strip() for p in os.getenv("HACKIN_IMAGE_PATHS", "attached_assets/morpheus_pfp.png").split(",") if p.strip()
]

# Who can run hack-ins:
OWNER_USER_ID = int(os.getenv("OWNER_USER_ID", "0") or 0)
ALLOW_MANAGE_GUILD = _env_bool("HACKIN_ALLOW_MANAGE_GUILD", True)  # allow server mods with Manage Guild


# ---------- UI bits ----------

class PillPromptView(discord.ui.View):
    """Simple Red/Blue choice that nudges the user toward /pill (consent-first)."""

    def __init__(self, *, timeout: int = 120):
        super().__init__(timeout=timeout)

    @discord.ui.button(label="Red Pill (opt in)", style=discord.ButtonStyle.danger, emoji="🟥")
    async def red(self, interaction: discord.Interaction, button: discord.ui.Button):
        # We don't toggle state here to avoid cross-cog coupling; we nudge user to run /pill.
        await interaction.response.send_message(
            "Choose it explicitly with `/pill` and pick **Red Pill** to opt in. Your choice, always.",
            ephemeral=True
        )

    @discord.ui.button(label="Blue Pill (decline)", style=discord.ButtonStyle.primary, emoji="🟦")
    async def blue(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "Understood. If you change your mind later, run `/pill` anytime.",
            ephemeral=True
        )


def _attach_best_file() -> Optional[discord.File]:
    """Pick a random GIF if available, otherwise fall back to a still image. Return None if nothing exists."""
    # Try GIFs first
    random.shuffle(HACKIN_GIF_PATHS)
    for path in HACKIN_GIF_PATHS:
        if os.path.isfile(path):
            try:
                return discord.File(path, filename=os.path.basename(path))
            except Exception:
                pass

    # Fallback stills
    random.shuffle(HACKIN_IMAGE_PATHS)
    for path in HACKIN_IMAGE_PATHS:
        if os.path.isfile(path):
            try:
                return discord.File(path, filename=os.path.basename(path))
            except Exception:
                pass
    return None


def _embed_for(style: str, title: Optional[str], body: str) -> discord.Embed:
    """Cinematic embed presets."""
    style = (style or "system").lower()
    if style == "construct":
        color = discord.Color.dark_teal()
        heading = title or "TRANSMISSION // CONSTRUCT LINK"
    elif style == "havn":
        color = discord.Color.dark_green()
        heading = title or "TRANSMISSION // HAVN ACCESS"
    else:
        color = discord.Color.dark_theme()
        heading = title or "TRANSMISSION // SYSTEM"

    e = discord.Embed(title=heading, description=body, color=color)
    e.set_footer(text="Signal stabilized • Morpheus")
    return e


def _default_body(template: str, url: Optional[str], mention: Optional[str], include_pill: bool) -> str:
    """Short cinematic copy blocks."""
    template = (template or "custom").lower()
    lines: List[str] = []

    if template == "new_video":
        lines.append("A new frame has been forged.")
        if url:
            lines.append(f"▶️ **Watch now:** {url}")
    elif template == "invite_construct":
        lines.append("Your curiosity has not gone unnoticed.")
        lines.append("The Construct stands by—training, tools, and a path forward.")
    elif template == "invite_havn":
        lines.append("You’ve seen through the static. Access can be expanded.")
        lines.append("HAVN is a place for the awake—enter if you mean it.")
    else:
        lines.append("A signal cuts through the noise.")
        if url:
            lines.append(url)

    if include_pill:
        lines.append("")
        lines.append("Choose with intent: **/pill** → Red or Blue.")

    if mention:
        lines.insert(0, f"{mention}")

    return "\n".join(lines)


# ---------- Cog ----------

class HackInCog(commands.Cog):
    """Manual cinematic transmissions for channels or DMs."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---- permission check ----
    def _is_authorized(self, inter: discord.Interaction) -> bool:
        if OWNER_USER_ID and inter.user.id == OWNER_USER_ID:
            return True
        if ALLOW_MANAGE_GUILD and inter.guild is not None:
            perms = inter.user.guild_permissions  # type: ignore
            return getattr(perms, "manage_guild", False)
        return False

    # ---- /hackin ----
    @app_commands.command(
        name="hackin",
        description="Post a cinematic transmission (channel + optional DM)."
    )
    @app_commands.describe(
        style="Visual theme: system / construct / havn",
        template="Message preset: custom / new_video / invite_construct / invite_havn",
        body="If template=custom, provide your message here (Markdown allowed).",
        url="Optional link to include (e.g., YouTube).",
        target_channel="Channel to post in. Defaults to the current one.",
        target_user="Optionally also DM this user the same transmission.",
        include_pill="Append Red/Blue Pill prompt (consent-first)."
    )
    @app_commands.choices(
        style=[
            app_commands.Choice(name="system", value="system"),
            app_commands.Choice(name="construct", value="construct"),
            app_commands.Choice(name="havn", value="havn"),
        ],
        template=[
            app_commands.Choice(name="custom", value="custom"),
            app_commands.Choice(name="new_video", value="new_video"),
            app_commands.Choice(name="invite_construct", value="invite_construct"),
            app_commands.Choice(name="invite_havn", value="invite_havn"),
        ],
    )
    async def hackin(
        self,
        interaction: discord.Interaction,
        style: app_commands.Choice[str],
        template: app_commands.Choice[str],
        body: Optional[str] = None,
        url: Optional[str] = None,
        target_channel: Optional[discord.TextChannel] = None,
        target_user: Optional[discord.Member] = None,
        include_pill: bool = False,
    ):
        if not self._is_authorized(interaction):
            await interaction.response.send_message("Insufficient permission.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        # Compose message
        if template.value == "custom":
            final_body = body or "…"
        else:
            mention = target_user.mention if target_user else None
            final_body = _default_body(template.value, url, mention, include_pill)

        embed = _embed_for(style.value, None, final_body)
        file = _attach_best_file()

        # Target channel
        ch = target_channel or (interaction.channel if isinstance(interaction.channel, discord.TextChannel) else None)
        chan_ok = False
        if ch:
            try:
                view = PillPromptView() if include_pill else None
                await ch.send(embed=embed, file=file if file else discord.utils.MISSING, view=view)  # type: ignore
                chan_ok = True
            except Exception:
                chan_ok = False

        # Optional DM
        dm_ok = False
        if target_user:
            try:
                view = PillPromptView() if include_pill else None
                if file:
                    # Re-open file stream for DM (file objects are single-use)
                    file2 = discord.File(file.fp.name, filename=os.path.basename(file.fp.name))  # type: ignore
                else:
                    file2 = None
                await target_user.send(embed=embed, file=file2 if file2 else discord.utils.MISSING, view=view)  # type: ignore
                dm_ok = True
            except Exception:
                dm_ok = False

        # Acknowledge
        parts = []
        parts.append("Channel ✅" if chan_ok else "Channel ❌")
        if target_user:
            parts.append(f"DM to {target_user.mention} " + ("✅" if dm_ok else "❌"))
        await interaction.followup.send("Transmission sent: " + " • ".join(parts), ephemeral=True)

    # ---- /transmission (DM only, simpler) ----
    @app_commands.command(
        name="transmission",
        description="Send a cinematic DM to a user."
    )
    @app_commands.describe(
        style="Visual theme: system / construct / havn",
        template="Message preset: custom / new_video / invite_construct / invite_havn",
        body="If template=custom, provide your message here.",
        url="Optional link to include.",
        user="Who to DM.",
        include_pill="Append Red/Blue Pill prompt."
    )
    @app_commands.choices(
        style=[
            app_commands.Choice(name="system", value="system"),
            app_commands.Choice(name="construct", value="construct"),
            app_commands.Choice(name="havn", value="havn"),
        ],
        template=[
            app_commands.Choice(name="custom", value="custom"),
            app_commands.Choice(name="new_video", value="new_video"),
            app_commands.Choice(name="invite_construct", value="invite_construct"),
            app_commands.Choice(name="invite_havn", value="invite_havn"),
        ],
    )
    async def transmission(
        self,
        interaction: discord.Interaction,
        style: app_commands.Choice[str],
        template: app_commands.Choice[str],
        user: discord.Member,
        body: Optional[str] = None,
        url: Optional[str] = None,
        include_pill: bool = False,
    ):
        if not self._is_authorized(interaction):
            await interaction.response.send_message("Insufficient permission.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        if template.value == "custom":
            final_body = body or "…"
        else:
            final_body = _default_body(template.value, url, None, include_pill)

        embed = _embed_for(style.value, None, final_body)
        file = _attach_best_file()

        ok = False
        try:
            view = PillPromptView() if include_pill else None
            if file:
                file2 = discord.File(file.fp.name, filename=os.path.basename(file.fp.name))  # type: ignore
            else:
                file2 = None
            await user.send(embed=embed, file=file2 if file2 else discord.utils.MISSING, view=view)  # type: ignore
            ok = True
        except Exception:
            ok = False

        await interaction.followup.send(
            f"DM to {user.mention}: " + ("✅ sent" if ok else "❌ failed (DMs closed?)"), ephemeral=True
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(HackInCog(bot))