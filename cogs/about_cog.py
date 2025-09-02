# cogs/about_cog.py
import os
import io
import json
import time
import platform
from typing import Optional

import discord
from discord.ext import commands
from discord import app_commands

# ---- read env for transparency (kept generic if you swap providers/models) ----
PROVIDER             = os.getenv("PROVIDER", "").lower() or "unknown"
OPENAI_MODEL         = os.getenv("OPENAI_MODEL", "")       # if you set one
HF_MODEL             = os.getenv("HF_MODEL", "")
GROQ_MODEL           = os.getenv("GROQ_MODEL", "")
OWNER_USER_ID        = int(os.getenv("OWNER_USER_ID", "0") or 0)

# wellbeing (if you installed that cog)
SUPPORT_ENABLED          = (os.getenv("SUPPORT_ENABLED", "true").lower() in ("1","true","yes","on"))
SUPPORT_RETENTION_DAYS   = int(os.getenv("SUPPORT_RETENTION_DAYS", "30"))
DATA_DIR                 = "data"
WELLBEING_PATH           = os.path.join(DATA_DIR, "wellbeing.json")
MISSION_JSON_PATH        = "mission.json"
MISSION_MEMO_PATH        = "mission_memory.json"
MODLOG_JSON_PATH         = os.path.join(DATA_DIR, "modlog.json")
GCFG_PATH                = os.path.join(DATA_DIR, "guild_config.json")

def _exists(p: str) -> bool:
    try:
        return os.path.isfile(p)
    except Exception:
        return False

def _file_count(path: str, key: str) -> Optional[int]:
    """Best-effort small counter (does not load giant files)."""
    try:
        if not os.path.isfile(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and key in data and isinstance(data[key], list):
            return len(data[key])
        return None
    except Exception:
        return None

def _provider_line() -> str:
    if PROVIDER == "openai" and OPENAI_MODEL:
        return f"OpenAI · `{OPENAI_MODEL}`"
    if PROVIDER == "hf" and HF_MODEL:
        return f"HuggingFace Inference · `{HF_MODEL}`"
    if PROVIDER == "groq" and GROQ_MODEL:
        return f"Groq · `{GROQ_MODEL}`"
    # fallback hints
    model = OPENAI_MODEL or GROQ_MODEL or HF_MODEL or "(model unspecified)"
    return f"{PROVIDER or 'unknown'} · `{model}`"

def _policy_text(guild: Optional[discord.Guild]) -> str:
    lines = []
    lines.append("Morpheus — Transparency & Data Practices")
    lines.append("=======================================")
    lines.append("")
    lines.append("What I store by default")
    lines.append("-----------------------")
    lines.append("• I do **not** persist regular chat content.")
    lines.append("• Slash command inputs are handled transiently to answer your request.")
    lines.append("")
    lines.append("Optional features (consent-based)")
    lines.append("-------------------------------")
    if SUPPORT_ENABLED:
        lines.append(f"• Wellbeing check-ins are **opt-in** only (`/pill` → Red Pill).")
        lines.append(f"• Stored: your **check-in answers** + timestamps. No diagnosis or profiling.")
        lines.append(f"• Retention: entries auto-delete after **{SUPPORT_RETENTION_DAYS} days**.")
        lines.append("• You can view or erase with `/my_data` and `/delete_my_data` anytime.")
    else:
        lines.append("• Wellbeing features are currently disabled on this server.")
    lines.append("")
    lines.append("Where data lives (server files)")
    lines.append("-------------------------------")
    lines.append(f"• {WELLBEING_PATH} — wellbeing entries (only if you opt in)")
    lines.append(f"• {MISSION_JSON_PATH} — owner-provided server/mission notes")
    lines.append(f"• {MISSION_MEMO_PATH} — owner export/import of planning notes")
    lines.append(f"• {MODLOG_JSON_PATH} — optional moderation log (if enabled)")
    lines.append(f"• {GCFG_PATH} — guild configuration (channel IDs, role IDs, etc.)")
    lines.append("")
    lines.append("Capabilities & model")
    lines.append("--------------------")
    lines.append(f"• Provider/Model: {_provider_line()}")
    lines.append("• I follow server rules and defer to moderators.")
    lines.append("• I avoid medical/legal/financial advice and provide crisis resources when needed.")
    lines.append("")
    lines.append("Your controls")
    lines.append("-------------")
    lines.append("• Use `/about` to read this summary.")
    if SUPPORT_ENABLED:
        lines.append("• Use `/pill`, `/support_optin`, `/support_optout`, `/checkin` for wellbeing flow.")
        lines.append("• Use `/my_data` and `/delete_my_data` for data access/erasure.")
    lines.append("• Owner/Admin can adjust features via server-side commands.")
    lines.append("")
    lines.append("Limits & notes")
    lines.append("--------------")
    lines.append("• I am not a replacement for professional help.")
    lines.append("• Crisis resources: 988 (US) / findahelpline.com (global).")
    if guild:
        lines.append(f"• This policy is scoped to: {guild.name} (ID {guild.id}).")
    return "\n".join(lines)


class DownloadPolicyView(discord.ui.View):
    def __init__(self, text_fn, *, timeout: int = 120):
        super().__init__(timeout=timeout)
        self._text_fn = text_fn

    @discord.ui.button(label="Download Policy (TXT)", style=discord.ButtonStyle.secondary, emoji="📄")
    async def _dl(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            txt = self._text_fn(interaction.guild)
            buff = io.StringIO(txt)
            file = discord.File(fp=io.BytesIO(buff.getvalue().encode("utf-8")), filename="morpheus_transparency.txt")
            await interaction.response.send_message(file=file, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Couldn’t prepare file: {e.__class__.__name__}", ephemeral=True)


class AboutCog(commands.Cog):
    """Transparency & data-practices info surface."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="about", description="How Morpheus handles data, privacy, and what’s stored.")
    @app_commands.describe(public="If true, post publicly. Defaults to private (ephemeral).")
    async def about(self, interaction: discord.Interaction, public: Optional[bool] = False):
        """User-facing transparency summary."""
        embed = discord.Embed(
            title="Morpheus — Transparency",
            description=(
                f"**Provider/Model:** {_provider_line()}\n"
                f"**Wellbeing:** {'Enabled' if SUPPORT_ENABLED else 'Disabled'}"
                f"{f' · Retention: {SUPPORT_RETENTION_DAYS} days' if SUPPORT_ENABLED else ''}\n"
                f"**Storage:** Only opt-in check-ins + server config files; regular chats aren’t persisted."
            ),
            color=discord.Color.blurple()
        )
        embed.add_field(
            name="Your controls",
            value=(
                "• `/about` — see this summary\n"
                + ("• `/pill`, `/support_optin`, `/support_optout`, `/checkin`, `/my_data`, `/delete_my_data`\n" if SUPPORT_ENABLED else "")
                + "• Contact mods for concerns"
            ),
            inline=False
        )
        embed.set_footer(text="This is a support/utility bot. It is not a medical or legal service.")

        view = DownloadPolicyView(_policy_text)

        # ephemeral by default
        if public:
            await interaction.response.send_message(embed=embed, view=view)
        else:
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="about_owner", description="(Owner) Deep details: file presence, sizes, runtime info.")
    async def about_owner(self, interaction: discord.Interaction):
        if not OWNER_USER_ID or int(interaction.user.id) != int(OWNER_USER_ID):
            await interaction.response.send_message("Owner only.", ephemeral=True)
            return

        def _size(path: str) -> str:
            try:
                if os.path.isfile(path):
                    b = os.path.getsize(path)
                    if b < 1024: return f"{b} B"
                    if b < 1024**2: return f"{b/1024:.1f} KB"
                    if b < 1024**3: return f"{b/1024**2:.1f} MB"
                    return f"{b/1024**3:.1f} GB"
            except Exception:
                pass
            return "—"

        wb_count = _file_count(WELLBEING_PATH, "entries")
        modlog_count = _file_count(MODLOG_JSON_PATH, "entries")

        desc = (
            f"**Provider/Model:** {_provider_line()}\n"
            f"**Python:** {platform.python_version()}\n"
            f"**Files present:**\n"
            f"• `{WELLBEING_PATH}`: {'yes' if _exists(WELLBEING_PATH) else 'no'}"
            f"{f' · entries: {wb_count}' if wb_count is not None else ''} · size: {_size(WELLBEING_PATH)}\n"
            f"• `{MISSION_JSON_PATH}`: {'yes' if _exists(MISSION_JSON_PATH) else 'no'} · size: {_size(MISSION_JSON_PATH)}\n"
            f"• `{MISSION_MEMO_PATH}`: {'yes' if _exists(MISSION_MEMO_PATH) else 'no'} · size: {_size(MISSION_MEMO_PATH)}\n"
            f"• `{MODLOG_JSON_PATH}`: {'yes' if _exists(MODLOG_JSON_PATH) else 'no'}"
            f"{f' · entries: {modlog_count}' if modlog_count is not None else ''} · size: {_size(MODLOG_JSON_PATH)}\n"
            f"• `{GCFG_PATH}`: {'yes' if _exists(GCFG_PATH) else 'no'} · size: {_size(GCFG_PATH)}\n"
        )

        embed = discord.Embed(
            title="Morpheus — Owner Transparency",
            description=desc,
            color=discord.Color.dark_teal()
        )
        embed.set_footer(text="Counts are best-effort. Large files are not fully parsed here.")
        view = DownloadPolicyView(_policy_text)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(AboutCog(bot))