# cogs/digest_cog.py
import os, io, re, json, time, asyncio
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any

import discord
from discord.ext import commands
from discord import app_commands

from config import BotConfig
from ai_provider import ai_reply

cfg = BotConfig()

DATA_DIR = "data"
CFG_PATH = os.path.join(DATA_DIR, "digest.json")

def _ensure_dir():
    if not os.path.isdir(DATA_DIR):
        os.makedirs(DATA_DIR, exist_ok=True)

def _load_cfg() -> Dict[str, Any]:
    _ensure_dir()
    if not os.path.isfile(CFG_PATH):
        with open(CFG_PATH, "w", encoding="utf-8") as f:
            json.dump({"enabled": False, "channel_ids": [], "summarize": False}, f)
    with open(CFG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def _save_cfg(d: Dict[str, Any]):
    _ensure_dir()
    with open(CFG_PATH, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)

_SANITIZE_URLS = re.compile(r"https?://\S+")
_SANITIZE_PINGS = re.compile(r"<@!?(\d+)>|<#[0-9]+>|<@&[0-9]+>")

def _redact(text: str) -> str:
    text = _SANITIZE_URLS.sub("[link]", text)
    text = _SANITIZE_PINGS.sub("[ref]", text)
    return text.strip()

class DigestCog(commands.Cog):
    """Owner-controlled, privacy-first digest exporter."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------------- Owner toggles ----------------

    @app_commands.command(name="digest_on", description="(Owner) Enable digest collection and set summarize mode.")
    @app_commands.describe(summarize="Paraphrase topics with AI (no PII). Default: off.")
    async def digest_on(self, interaction: discord.Interaction, summarize: bool = False):
        if not cfg.OWNER_USER_ID or interaction.user.id != int(cfg.OWNER_USER_ID):
            return await interaction.response.send_message("Owner only.", ephemeral=True)

        d = _load_cfg()
        d["enabled"] = True
        d["summarize"] = bool(summarize or (str(os.getenv("DIGEST_SUMMARIZE","false")).lower() in ("1","true","yes","on")))
        _save_cfg(d)
        await interaction.response.send_message(
            f"Digest **enabled**. Summarize = `{d['summarize']}`.\n"
            "Use `/digest_channels_add` to select safe channels, then `/export_digest` when you want a file.",
            ephemeral=True
        )

    @app_commands.command(name="digest_off", description="(Owner) Disable digest collection.")
    async def digest_off(self, interaction: discord.Interaction):
        if not cfg.OWNER_USER_ID or interaction.user.id != int(cfg.OWNER_USER_ID):
            return await interaction.response.send_message("Owner only.", ephemeral=True)
        d = _load_cfg()
        d["enabled"] = False
        _save_cfg(d)
        await interaction.response.send_message("Digest **disabled**.", ephemeral=True)

    @app_commands.command(name="digest_channels_add", description="(Owner) Add this channel to the digest allow-list.")
    async def digest_channels_add(self, interaction: discord.Interaction):
        if not cfg.OWNER_USER_ID or interaction.user.id != int(cfg.OWNER_USER_ID):
            return await interaction.response.send_message("Owner only.", ephemeral=True)
        if not isinstance(interaction.channel, discord.TextChannel):
            return await interaction.response.send_message("Use this in a text channel.", ephemeral=True)
        d = _load_cfg()
        cid = interaction.channel.id
        if cid not in d["channel_ids"]:
            d["channel_ids"].append(cid)
            _save_cfg(d)
            await interaction.response.send_message(f"Added <#{cid}> to digest scope.", ephemeral=True)
        else:
            await interaction.response.send_message(f"<#{cid}> is already in scope.", ephemeral=True)

    @app_commands.command(name="digest_channels_list", description="(Owner) List channels in the digest allow-list.")
    async def digest_channels_list(self, interaction: discord.Interaction):
        if not cfg.OWNER_USER_ID or interaction.user.id != int(cfg.OWNER_USER_ID):
            return await interaction.response.send_message("Owner only.", ephemeral=True)
        d = _load_cfg()
        names = []
        for cid in d.get("channel_ids", []):
            ch = interaction.guild.get_channel(cid) if interaction.guild else None
            names.append(f"<#{cid}>" if ch else f"`{cid}` (not found here)")
        if not names:
            msg = "No channels selected yet. Run `/digest_channels_add` in each safe room."
        else:
            msg = "In scope: " + ", ".join(names)
        await interaction.response.send_message(msg, ephemeral=True)

    # ---------------- Export digest ----------------

    @app_commands.command(name="export_digest", description="(Owner) Build a redacted JSON digest and DM it to you.")
    @app_commands.describe(days="How many days back to include (default 7).")
    async def export_digest(self, interaction: discord.Interaction, days: int = 7):
        if not cfg.OWNER_USER_ID or interaction.user.id != int(cfg.OWNER_USER_ID):
            return await interaction.response.send_message("Owner only.", ephemeral=True)

        d = _load_cfg()
        if not d.get("enabled"):
            return await interaction.response.send_message("Digest is **disabled**. Run `/digest_on` first.", ephemeral=True)
        channel_ids: List[int] = d.get("channel_ids", [])
        if not channel_ids:
            return await interaction.response.send_message(
                "No channels in scope. Run `/digest_channels_add` in the rooms you want included.",
                ephemeral=True
            )

        await interaction.response.defer(ephemeral=True, thinking=True)

        since = datetime.now(timezone.utc) - timedelta(days=max(1, days))
        report = await self._build_digest(interaction.guild, channel_ids, since, summarize=d.get("summarize", False))

        # DM the owner the JSON file and a short summary
        js = json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8")
        filename = f"digest_{interaction.guild.id}_{int(time.time())}.json"
        file = discord.File(io.BytesIO(js), filename=filename)

        try:
            await interaction.user.send(
                content=f"Here’s your digest for **{interaction.guild.name}** ({days}d).",
                file=file
            )
            await interaction.followup.send("Sent you the digest via DM. ✅", ephemeral=True)
        except Exception:
            # Fallback: attach in-channel but ephemeral (not visible to others)
            await interaction.followup.send(
                content="Couldn’t DM you; attaching here.",
                files=[file],
                ephemeral=True
            )

    # ---------------- internals ----------------

    async def _build_digest(self, guild: discord.Guild, cids: List[int], since: datetime, summarize: bool) -> Dict[str, Any]:
        report: Dict[str, Any] = {
            "guild": {"id": guild.id, "name": guild.name},
            "window": {"from": since.isoformat(), "to": datetime.now(timezone.utc).isoformat()},
            "metrics": {"msgs_total": 0, "msgs_by_channel": {}, "active_members": 0, "new_members": 0},
            "events": {"pins_now": 0},
            "topics": [],
            "notes": [],
        }

        # Members
        active_user_ids = set()
        new_members = [m for m in guild.members if m.joined_at and m.joined_at >= since]
        report["metrics"]["new_members"] = len(new_members)

        # Per-channel message counts + sample for summaries
        for cid in cids:
            ch = guild.get_channel(cid)
            if not isinstance(ch, discord.TextChannel):
                continue

            msgs = 0
            sample_texts: List[str] = []
            async for m in ch.history(limit=200, after=since, oldest_first=False):
                if m.author.bot:
                    continue
                msgs += 1
                active_user_ids.add(m.author.id)
                if len(sample_texts) < 40 and m.content:
                    sample_texts.append(_redact(m.content))

            report["metrics"]["msgs_by_channel"][ch.name] = msgs
            report["metrics"]["msgs_total"] += msgs

            # pins snapshot (now, not historical)
            try:
                pins = await ch.pins()
                report["events"]["pins_now"] += len(pins)
            except Exception:
                pass

            # Optional AI summary
            if summarize and sample_texts:
                blob = "\n".join(f"- {t}" for t in sample_texts[:40])
                prompt = (
                    "Summarize the main non-personal discussion themes in neutral language, 3 bullet points max. "
                    "Do NOT include names, quotes, or links. Keep it under 60 words."
                )
                try:
                    summary = await ai_reply(
                        "You are a redaction-safe summarizer. No PII. No quotes. No links.",
                        [{"role": "user", "content": prompt + "\n\n" + blob}],
                        max_new_tokens=140,
                        temperature=0.2
                    )
                    if summary:
                        report["topics"].append({"channel": ch.name, "summary": summary.strip()[:280]})
                except Exception:
                    # If the AI fails, just skip summaries
                    pass

        report["metrics"]["active_members"] = len(active_user_ids)

        return report

async def setup(bot: commands.Bot):
    await bot.add_cog(DigestCog(bot))