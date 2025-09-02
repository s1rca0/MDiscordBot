# cogs/wellbeing_cog.py
import os
import json
import time
import asyncio
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Tuple

import discord
from discord.ext import commands, tasks
from discord import app_commands
from pathlib import Path

# ---------- env helpers / config ----------

def _env_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name, str(default))
    return str(v).lower() in ("1", "true", "yes", "y", "on")

SUPPORT_ENABLED = _env_bool("SUPPORT_ENABLED", True)
SUPPORT_RETENTION_DAYS = int(os.getenv("SUPPORT_RETENTION_DAYS", "30"))

# Optional: give a role to opted-in users (display-only / easy filtering)
SUPPORT_ROLE_ID = int(os.getenv("SUPPORT_ROLE_ID", "0") or 0)

# Optional: only show “soft nudges” in these channels (comma-separated IDs)
SUPPORT_CHANNEL_IDS = [
    int(x.strip()) for x in os.getenv("SUPPORT_CHANNEL_IDS", "").split(",") if x.strip().isdigit()
]

# Optional: alert owner privately on strong crisis signals (default: off)
SUPPORT_ALERT_OWNER_ON_CRISIS = _env_bool("SUPPORT_ALERT_OWNER_ON_CRISIS", False)

# Optional minimal owner heads-up when a user might be open to opt-in
SUPPORT_NOTIFY_OWNER_INTEREST = _env_bool("SUPPORT_NOTIFY_OWNER_INTEREST", True)
INTEREST_COOLDOWN_MIN = int(os.getenv("SUPPORT_INTEREST_COOLDOWN_MIN", "45"))  # minutes

OWNER_USER_ID = int(os.getenv("OWNER_USER_ID", "0") or 0)

# Custom emoji IDs for pills (set in Secrets). If omitted, we fall back to 🟥 / 🟦.
RED_PILL_EMOJI_ID  = int(os.getenv("RED_PILL_EMOJI_ID", "0") or 0)
BLUE_PILL_EMOJI_ID = int(os.getenv("BLUE_PILL_EMOJI_ID", "0") or 0)

DATA_DIR = "data"
DB_PATH = os.path.join(DATA_DIR, "wellbeing.json")

# Reflective, non-medical, rotating question pool
QUESTION_POOL = [
    "On a scale of 1–5, how motivated do you feel right now?",
    "How connected do you feel to others today (1–5)?",
    "Did scrolling or news feel overwhelming today (yes/no)?",
    "Are you getting enough breaks from screens (yes/no)?",
    "Name one small thing that would help you feel lighter.",
    "Would you like fewer notifications for a while (yes/no)?",
    "Did anything inspire you today (yes/no)?",
    "Do you want a short grounding exercise (yes/no)?",
    "Is there something you’d like to ask or share privately?",
    "What’s one task you can complete in the next hour?",
]
ROTATE_COUNT = 5  # questions per check-in

# Lightweight, high-signal crisis trigger phrases
CRISIS_TRIGGERS = [
    "want to die",
    "want to kill myself",
    "kill myself",
    "suicide",
    "suicidal",
    "self harm",
    "self-harm",
    "hurt myself",
    "end my life",
]

# Softer “offer a check-in” triggers (non-crisis)
NUDGE_TRIGGERS = [
    "i feel sad",
    "i'm so tired",
    "im so tired",
    "overwhelmed",
    "burned out",
    "burnt out",
    "lonely",
    "anxious",
]

# ---------- storage ----------

@dataclass
class Entry:
    user_id: int
    ts: float
    answers: List[str]
    note: Optional[str] = None
    shared_with_owner: bool = False

def _ensure_db() -> Dict:
    if not os.path.isdir(DATA_DIR):
        os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.isfile(DB_PATH):
        with open(DB_PATH, "w", encoding="utf-8") as f:
            json.dump({"entries": [], "optin": [], "last_purge_ts": 0.0}, f)
    with open(DB_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def _save_db(db: Dict):
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

def _is_opted_in(db: Dict, user_id: int) -> bool:
    return any(int(uid) == int(user_id) for uid in db.get("optin", []))

def _opt_in(db: Dict, user_id: int):
    if not _is_opted_in(db, user_id):
        db["optin"].append(int(user_id))
        _save_db(db)

def _opt_out(db: Dict, user_id: int):
    db["optin"] = [int(uid) for uid in db.get("optin", []) if int(uid) != int(user_id)]
    db["entries"] = [e for e in db.get("entries", []) if int(e.get("user_id", 0)) != int(user_id)]
    _save_db(db)

def _append_entry(db: Dict, entry: Entry):
    arr = db.get("entries", [])
    arr.append(asdict(entry))
    db["entries"] = arr
    _save_db(db)

def _purge_old(db: Dict, days: int):
    cutoff = time.time() - days * 86400
    db["entries"] = [e for e in db.get("entries", []) if float(e.get("ts", 0)) >= cutoff]
    db["last_purge_ts"] = time.time()
    _save_db(db)

# ---------- embeds / messages ----------

def crisis_embed() -> discord.Embed:
    e = discord.Embed(
        title="You’re not alone.",
        description=(
            "If you’re thinking about harming yourself or someone else, please consider reaching out now:\n\n"
            "• **United States:** Call or text **988**, or chat via 988lifeline.org\n"
            "• **If outside the US:** Call your local emergency number or visit findahelpline.com\n\n"
            "You can also DM me `/checkin` for a private reflection. You choose."
        ),
        color=discord.Color.red()
    )
    e.set_footer(text="This is supportive information, not a substitute for professional help.")
    return e

def resources_embed() -> discord.Embed:
    e = discord.Embed(
        title="Helpful resources",
        description=(
            "**General well-being**\n"
            "• Short breaks: a 5–10 minute walk or stretch\n"
            "• Reduce overwhelm: silence notifications for 1 hour\n"
            "• One small step: pick a single doable task\n\n"
            "**If you’re in crisis**\n"
            "• **US:** Call/Text **988** or visit 988lifeline.org\n"
            "• **Global:** findahelpline.com or your local emergency number\n\n"
            "Use `/checkin` to reflect privately. You’re in control."
        ),
        color=discord.Color.teal()
    )
    return e

def privacy_embed(retention_days: int) -> discord.Embed:
    e = discord.Embed(
        title="Privacy & Consent",
        description=(
            f"• Participation is optional. Opt in with `/pill` (Red Pill) and opt out anytime with `/support_optout`.\n"
            f"• Stored items: your check-in answers + timestamps (no diagnosis).\n"
            f"• Retention: entries auto-delete after **{retention_days} days**.\n"
            "• Nothing is shared unless you explicitly choose to share."
        ),
        color=discord.Color.dark_teal()
    )
    return e

# ---------- custom emoji utilities ----------

def _pill_emoji(emoji_id: int, name: str):
    """Return a PartialEmoji if ID provided; otherwise None (we’ll use unicode fallback)."""
    try:
        return discord.PartialEmoji(name=name, id=emoji_id) if emoji_id else None
    except Exception:
        return None

# ---------- UI: Red Pill / Blue Pill (buttons) ----------

class PillView(discord.ui.View):
    def __init__(self, *, timeout: int = 120, on_decide=None):
        super().__init__(timeout=timeout)
        self.on_decide = on_decide

        # Resolve custom emoji or fall back to colored squares
        self._red_emoji  = _pill_emoji(RED_PILL_EMOJI_ID,  "redpill")  or "🟥"
        self._blue_emoji = _pill_emoji(BLUE_PILL_EMOJI_ID, "bluepill") or "🟦"

        # After decorator-built buttons exist, assign emojis dynamically
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                if "Red Pill" in (child.label or ""):
                    child.emoji = self._red_emoji
                elif "Blue Pill" in (child.label or ""):
                    child.emoji = self._blue_emoji

    @discord.ui.button(label="Red Pill (opt in)", style=discord.ButtonStyle.danger)
    async def red(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.on_decide:
            await self.on_decide(interaction, True)

    @discord.ui.button(label="Blue Pill (decline)", style=discord.ButtonStyle.primary)
    async def blue(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.on_decide:
            await self.on_decide(interaction, False)

# ---------- Cog ----------

class WellbeingCog(commands.Cog):
    """Opt-in wellbeing with Matrix-style consent + optional soft nudges + crisis support + owner interest ping."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        if SUPPORT_ENABLED:
            self.purger.start()
        self._interest_last: Dict[Tuple[int,int], float] = {}

    def cog_unload(self):
        if SUPPORT_ENABLED and self.purger.is_running():
            self.purger.cancel()

    @tasks.loop(hours=12)
    async def purger(self):
        db = _ensure_db()
        _purge_old(db, SUPPORT_RETENTION_DAYS)

    # ---------- Slash Commands ----------

    @app_commands.command(name="pill", description="Choose: Red (opt in) or Blue (decline).")
    async def pill(self, interaction: discord.Interaction):
        if not SUPPORT_ENABLED:
            await interaction.response.send_message("Support features are currently disabled.", ephemeral=True)
        else:
            view = PillView(on_decide=self._pill_decision)
            await interaction.response.send_message(
                embeds=[privacy_embed(SUPPORT_RETENTION_DAYS)],
                view=view,
                ephemeral=True
            )

    async def _pill_decision(self, interaction: discord.Interaction, opt_in: bool):
        db = _ensure_db()
        if opt_in:
            _opt_in(db, interaction.user.id)
            if SUPPORT_ROLE_ID and isinstance(interaction.user, discord.Member):
                role = interaction.guild.get_role(SUPPORT_ROLE_ID) if interaction.guild else None
                if role:
                    try:
                        await interaction.user.add_roles(role, reason="Opted into wellbeing support")
                    except Exception:
                        pass
            await interaction.response.edit_message(
                content="You chose **Red Pill**. You're opted in. Use `/checkin` anytime.",
                embeds=[], view=None
            )
        else:
            _opt_out(db, interaction.user.id)
            if SUPPORT_ROLE_ID and isinstance(interaction.user, discord.Member):
                role = interaction.guild.get_role(SUPPORT_ROLE_ID)
                if role:
                    try:
                        await interaction.user.remove_roles(role, reason="Declined wellbeing support")
                    except Exception:
                        pass
            await interaction.response.edit_message(
                content="You chose **Blue Pill**. Support is off. Change later with `/pill` or `/support_optin`.",
                embeds=[], view=None
            )

    @app_commands.command(name="support_optin", description="Opt in to private check-ins and gentle support.")
    async def support_optin(self, interaction: discord.Interaction):
        db = _ensure_db()
        _opt_in(db, interaction.user.id)
        if SUPPORT_ROLE_ID and isinstance(interaction.user, discord.Member):
            role = interaction.guild.get_role(SUPPORT_ROLE_ID)
            if role:
                try:
                    await interaction.user.add_roles(role, reason="Opted into wellbeing support")
                except Exception:
                    pass
        await interaction.response.send_message("Opt-in complete. Use `/checkin` anytime.", ephemeral=True)

    @app_commands.command(name="support_optout", description="Opt out and erase stored entries.")
    async def support_optout(self, interaction: discord.Interaction):
        db = _ensure_db()
        _opt_out(db, interaction.user.id)
        if SUPPORT_ROLE_ID and isinstance(interaction.user, discord.Member):
            role = interaction.guild.get_role(SUPPORT_ROLE_ID)
            if role:
                try:
                    await interaction.user.remove_roles(role, reason="Opted out of wellbeing support")
                except Exception:
                    pass
        await interaction.response.send_message("Opt-out complete. Your entries were deleted.", ephemeral=True)

    @app_commands.command(name="checkin", description="Private reflection check-in (ephemeral).")
    async def checkin(self, interaction: discord.Interaction):
        if not SUPPORT_ENABLED:
            await interaction.response.send_message("Support features are currently disabled.", ephemeral=True)
            return
        db = _ensure_db()
        if not _is_opted_in(db, interaction.user.id):
            await interaction.response.send_message(
                "You’re not opted in. Use `/pill` and choose the **Red Pill** to begin.",
                ephemeral=True
            )
            return

        start = int(time.time()) % max(1, len(QUESTION_POOL) - ROTATE_COUNT + 1)
        qs = QUESTION_POOL[start:start + ROTATE_COUNT]
        prompt = "\n".join(f"{i+1}. {q}" for i, q in enumerate(qs))
        await interaction.response.send_message(
            f"**Check-in**\nReply with your answers as a single message, numbered 1–{len(qs)}.\n\n{prompt}",
            ephemeral=True
        )

        def check(m: discord.Message):
            return m.author.id == interaction.user.id and m.channel.id == interaction.channel.id

        try:
            msg = await interaction.client.wait_for("message", timeout=180.0, check=check)
        except asyncio.TimeoutError:
            await interaction.followup.send("Timed out. Try `/checkin` again anytime.", ephemeral=True)
            return

        answers_blob = msg.content.strip()
        entry = Entry(
            user_id=interaction.user.id,
            ts=time.time(),
            answers=[answers_blob],
        )
        _append_entry(db, entry)

        feedback = (
            "Noted. Consider a short break, some water, and one small task you can complete now. "
            "You can view or erase your data with `/my_data` and `/delete_my_data`."
        )
        await interaction.followup.send(feedback, ephemeral=True)

    @app_commands.command(name="my_data", description="View what’s stored for you.")
    async def my_data(self, interaction: discord.Interaction):
        db = _ensure_db()
        entries = [e for e in db.get("entries", []) if int(e.get("user_id", 0)) == int(interaction.user.id)]
        if not entries:
            await interaction.response.send_message("No entries found.", ephemeral=True)
            return
        latest = sorted(entries, key=lambda e: e["ts"], reverse=True)[:3]
        desc = "\n\n".join(
            f"**{i+1}.** <t:{int(e['ts'])}:R>\n{e['answers'][0][:300]}"
            for i, e in enumerate(latest)
        )
        embed = discord.Embed(
            title="Your recent check-ins",
            description=desc,
            color=discord.Color.teal()
        )
        embed.set_footer(text=f"Auto-deletes after {SUPPORT_RETENTION_DAYS} days. Use /delete_my_data to purge now.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="delete_my_data", description="Erase all stored entries for you.")
    async def delete_my_data(self, interaction: discord.Interaction):
        db = _ensure_db()
        before = len(db.get("entries", []))
        db["entries"] = [e for e in db.get("entries", []) if int(e.get("user_id", 0)) != int(interaction.user.id)]
        _save_db(db)
        after = len(db.get("entries", []))
        await interaction.response.send_message(
            f"Deleted {before - after} entries. You’re clear.",
            ephemeral=True
        )

    @app_commands.command(name="resources", description="Show well-being and crisis resources.")
    async def resources(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=resources_embed(), ephemeral=True)

    @app_commands.command(name="support_status", description="(Owner) Show support feature status and counts.")
    async def support_status(self, interaction: discord.Interaction):
        if not OWNER_USER_ID or int(interaction.user.id) != int(OWNER_USER_ID):
            await interaction.response.send_message("Owner only.", ephemeral=True)
            return
        db = _ensure_db()
        optins = len(db.get("optin", []))
        total_entries = len(db.get("entries", []))
        last_purge_ts = db.get("last_purge_ts", 0.0)
        desc = (
            f"**Enabled:** {SUPPORT_ENABLED}\n"
            f"**Retention (days):** {SUPPORT_RETENTION_DAYS}\n"
            f"**Opt-ins:** {optins}\n"
            f"**Entries stored:** {total_entries}\n"
            f"**Soft-nudge channels set:** {len(SUPPORT_CHANNEL_IDS)}\n"
            f"**Crisis owner alerts:** {SUPPORT_ALERT_OWNER_ON_CRISIS}\n"
            f"**Interest owner nudges:** {SUPPORT_NOTIFY_OWNER_INTEREST}\n"
        )
        if last_purge_ts:
            desc += f"**Last purge:** <t:{int(last_purge_ts)}:R>"
        else:
            desc += "**Last purge:** (not yet run)"
        embed = discord.Embed(title="Support Status", description=desc, color=discord.Color.blurple())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="suggest_pill", description="(Owner) Politely suggest /pill to a user (consent-first).")
    @app_commands.describe(user="User to suggest /pill to")
    async def suggest_pill(self, interaction: discord.Interaction, user: discord.Member):
        if not OWNER_USER_ID or int(interaction.user.id) != int(OWNER_USER_ID):
            await interaction.response.send_message("Owner only.", ephemeral=True)
            return
        try:
            embed = discord.Embed(
                title="A choice awaits you.",
                description=(
                    "If you’d like private check-ins and gentle support, you can opt in with `/pill` and choose the **Red Pill**. "
                    "If not, choose the **Blue Pill**—no data will be kept.\n\n"
                    f"Entries auto-delete after **{SUPPORT_RETENTION_DAYS} days**, and you can remove them anytime with `/delete_my_data`."
                ),
                color=discord.Color.dark_green()
            )
            await user.send(embed=embed)
            await interaction.response.send_message(f"Sent a suggestion to {user.mention}.", ephemeral=True)
        except Exception:
            await interaction.response.send_message(f"Could not DM {user.mention}.", ephemeral=True)

    # ---------- Listeners: soft nudges, crisis handling, interest ping ----------

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        content = (message.content or "").lower()

        # CRISIS handling — share resources privately; optional owner heads-up
        if any(kw in content for kw in CRISIS_TRIGGERS):
            try:
                try:
                    await message.author.send(embed=crisis_embed())
                except Exception:
                    if message.guild is not None:
                        await message.reply(
                            "I’m sharing some resources with you—please check your DMs. "
                            "If DMs are closed, consider visiting 988lifeline.org (US) or findahelpline.com.",
                            mention_author=False,
                            silent=True
                        )
                if SUPPORT_ALERT_OWNER_ON_CRISIS and OWNER_USER_ID and message.guild is not None:
                    owner = message.guild.get_member(OWNER_USER_ID) or self.bot.get_user(OWNER_USER_ID)
                    if owner:
                        txt = (
                            "⚠️ **Crisis keyword detected** (minimal notice).\n"
                            f"User: {message.author} ({message.author.id})"
                        )
                        if getattr(message, "jump_url", None):
                            txt += f"\nLink: {message.jump_url}"
                        try:
                            await owner.send(txt)
                        except Exception:
                            pass
            except Exception:
                pass

        # Soft nudges (allowed channels only)
        if not SUPPORT_ENABLED or message.guild is None:
            return
        if SUPPORT_CHANNEL_IDS and message.channel.id not in SUPPORT_CHANNEL_IDS:
            return

        if any(t in content for t in NUDGE_TRIGGERS):
            try:
                await message.reply(
                    "I’m hearing some weight there. If you want a private moment, try `/pill` and choose the Red Pill — or DM me. You choose.",
                    mention_author=False,
                    silent=True
                )
            except Exception:
                pass

            # Owner interest heads-up (cooldown)
            if SUPPORT_NOTIFY_OWNER_INTEREST and OWNER_USER_ID:
                key = (message.guild.id, message.author.id)
                now = time.time()
                last = self._interest_last.get(key, 0.0)
                if now - last >= INTEREST_COOLDOWN_MIN * 60:
                    self._interest_last[key] = now
                    try:
                        owner = message.guild.get_member(OWNER_USER_ID) or self.bot.get_user(OWNER_USER_ID)
                        if owner:
                            msg = "💡 Someone may be open to support. Consider a friendly nudge about `/pill`."
                            if getattr(message, "jump_url", None):
                                msg += f"\nLink: {message.jump_url}"
                            await owner.send(msg)
                    except Exception:
                        pass


async def setup(bot: commands.Bot):
    await bot.add_cog(WellbeingCog(bot))