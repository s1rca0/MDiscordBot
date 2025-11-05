# cogs/align_cog.py
from __future__ import annotations

import logging
from typing import Dict, List, Tuple

import discord
from discord import app_commands
from discord.ext import commands

# ---- config hooks (safe fallbacks) --------------------------
try:
    import config as _cfg
except Exception:
    _cfg = object()  # sentinel

from typing import Dict  # keep typing happy

ROLE_IDS: Dict[str, int]        = getattr(_cfg, "ROLE_IDS", {})
MAINFRAME_ROLE_ID: int          = getattr(_cfg, "MAINFRAME_ROLE_ID", 0)
REVIEW_CHANNEL_ID: int          = getattr(_cfg, "REVIEW_CHANNEL_ID", 0)
COLOR: int                      = getattr(_cfg, "COLOR", 0x00FF88)

log = logging.getLogger("morpheus")


# ---- simple scoring rubric ---------------------------------------------------
# Light-weight keyword scoring: we’re not “psychoanalyzing”, just nudging.
ROLE_KEYWORDS: Dict[str, List[str]] = {
    "architect": ["system", "design", "strategy", "structure", "map", "model", "plan", "spec"],
    "cipher":    ["story", "signal", "language", "decode", "verify", "source", "frame", "rhetoric"],
    "operator":  ["ops", "pipeline", "deploy", "automate", "script", "monitor", "integrate", "route"],
    "enforcer":  ["moderation", "safety", "rules", "protocol", "guard", "triage", "resolve", "enforce"],
    "shade":     ["opsec", "privacy", "proxy", "mask", "ghost", "intel", "recon", "stealth"],
}

ROLE_PRETTY: Dict[str, str] = {
    "architect": "The Architect",
    "cipher":    "The Cipher",
    "operator":  "The Operator",
    "enforcer":  "The Enforcer",
    "shade":     "The Shade",
}


def score_answers(answers: List[str]) -> Tuple[str, Dict[str, int]]:
    scores: Dict[str, int] = {k: 0 for k in ROLE_KEYWORDS}
    text = " ".join(answers).lower()

    # keyword hits
    for role, words in ROLE_KEYWORDS.items():
        for w in words:
            if w in text:
                scores[role] += 1

    # light tie-break: longer/denser answers → small bump to “architect” / “operator”
    length = len(text)
    if length > 400:
        scores["architect"] += 1
        scores["operator"] += 1

    # pick max; deterministic order via ROLE_KEYWORDS keys
    winner = max(scores.items(), key=lambda kv: (kv[1], list(ROLE_KEYWORDS.keys()).index(kv[0])))[0]
    return winner, scores


# ---- Modal -------------------------------------------------------------------
class IntakeModal(discord.ui.Modal, title="ALIGNMENT • Signal Intake"):
    def __init__(self, bot: commands.Bot, user_id: int):
        super().__init__(timeout=300)
        self.bot = bot
        self.user_id = user_id

        self.q1 = discord.ui.TextInput(
            label="1) Where do you create the most leverage for a mission?",
            style=discord.TextStyle.long,
            max_length=500,
            required=True,
        )
        self.q2 = discord.ui.TextInput(
            label="2) Tools of choice (stack, workflows, superpowers)?",
            style=discord.TextStyle.long,
            max_length=500,
            required=True,
        )
        self.q3 = discord.ui.TextInput(
            label="3) A time you solved chaos with order—how?",
            style=discord.TextStyle.long,
            max_length=500,
            required=True,
        )
        self.q4 = discord.ui.TextInput(
            label="4) Guardrails you won’t cross (ethics / privacy)?",
            style=discord.TextStyle.long,
            max_length=500,
            required=True,
        )
        self.q5 = discord.ui.TextInput(
            label="5) In a team of five, which seat do you take—and why?",
            style=discord.TextStyle.long,
            max_length=500,
            required=True,
        )

        self.add_item(self.q1)
        self.add_item(self.q2)
        self.add_item(self.q3)
        self.add_item(self.q4)
        self.add_item(self.q5)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        # safety: only the requesting user can submit
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Not your intake.", ephemeral=True)
            return

        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("This only works in a server.", ephemeral=True)
            return

        answers = [self.q1.value, self.q2.value, self.q3.value, self.q4.value, self.q5.value]
        winner_key, scores = score_answers(answers)

        # resolve role
        role_id = ROLE_IDS.get(winner_key, 0)
        role = guild.get_role(role_id) if role_id else None

        # assign
        added = False
        try:
            if isinstance(interaction.user, discord.Member) and role:
                await interaction.user.add_roles(role, reason="Alignment calibration")
                added = True
        except Exception:
            added = False

        # optional: remove MAINFRAME
        if MAINFRAME_ROLE_ID and isinstance(interaction.user, discord.Member):
            mf = guild.get_role(MAINFRAME_ROLE_ID)
            if mf and mf in interaction.user.roles:
                try:
                    await interaction.user.remove_roles(mf, reason="Entered The Construct")
                except Exception:
                    pass

        # DM/ephemeral confirmation
        pretty = ROLE_PRETTY.get(winner_key, winner_key.title())
        outcome = "granted ✅" if added else "suggested (role missing?) ⚠️"
        embed = discord.Embed(
            title="ALIGNMENT • Calibration Complete",
            description=f"**Recommended role:** **{pretty}**\nResult: {outcome}",
            color=COLOR,
        )
        embed.add_field(
            name="Scores",
            value=" • ".join(f"{ROLE_PRETTY[k]}: {v}" for k, v in scores.items()),
            inline=False,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

        # optional: review log
        chan = None
        if REVIEW_CHANNEL_ID:
            chan = guild.get_channel(REVIEW_CHANNEL_ID) or self.bot.get_channel(REVIEW_CHANNEL_ID)

        if isinstance(chan, (discord.TextChannel, discord.Thread)):
            review = discord.Embed(
                title="ALIGNMENT • Intake Submitted",
                description=f"User: {interaction.user.mention}\nWinner: **{pretty}**",
                color=COLOR,
            )
            review.add_field(
                name="Q1", value=(self.q1.value[:512] + ("…" if len(self.q1.value) > 512 else "")), inline=False
            )
            review.add_field(
                name="Q2", value=(self.q2.value[:512] + ("…" if len(self.q2.value) > 512 else "")), inline=False
            )
            review.add_field(
                name="Q3", value=(self.q3.value[:512] + ("…" if len(self.q3.value) > 512 else "")), inline=False
            )
            review.add_field(
                name="Q4", value=(self.q4.value[:512] + ("…" if len(self.q4.value) > 512 else "")), inline=False
            )
            review.add_field(
                name="Q5", value=(self.q5.value[:512] + ("…" if len(self.q5.value) > 512 else "")), inline=False
            )
            review.add_field(
                name="Scores",
                value=" • ".join(f"{ROLE_PRETTY[k]}: {v}" for k, v in scores.items()),
                inline=False,
            )
            await chan.send(embed=review)

        log.info("[ALIGN] %s -> %s (added=%s)", interaction.user.id, winner_key, added)


# ---- Cog ---------------------------------------------------------------------
class AlignCog(commands.Cog):
    """Role alignment intake + assignment."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="align_start", description="Open alignment intake to calibrate your ops role.")
    async def align_start(self, interaction: discord.Interaction):
        """Opens the modal directly (no view/button dance needed)."""
        await interaction.response.send_modal(IntakeModal(self.bot, interaction.user.id))

    @app_commands.command(name="align_verify", description="Re-send your current alignment summary (ephemeral).")
    async def align_verify(self, interaction: discord.Interaction):
        member = interaction.user
        if not isinstance(member, discord.Member):
            return await interaction.response.send_message("Run this in a server.", ephemeral=True)

        # find any of the alignment roles the member already has
        have: List[str] = []
        for key, rid in ROLE_IDS.items():
            role = interaction.guild.get_role(rid) if interaction.guild else None
            if role and role in member.roles:
                have.append(ROLE_PRETTY.get(key, key.title()))

        if have:
            msg = " • ".join(have)
        else:
            msg = "No alignment role assigned yet."

        embed = discord.Embed(title="ALIGNMENT • Verify", description=msg, color=COLOR)
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(AlignCog(bot))
    log.info("[COGS] Loaded cogs.align_cog")