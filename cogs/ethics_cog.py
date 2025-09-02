# cogs/ethics_cog.py
import os
import io
import json
import time
import hashlib
from typing import Dict, Any, List, Tuple, Optional

import discord
from discord.ext import commands
from discord import app_commands

DATA_DIR = "data"
GCFG_PATH = os.path.join(DATA_DIR, "guild_config.json")
WELLBEING_PATH = os.path.join(DATA_DIR, "wellbeing.json")
MODLOG_PATH = os.path.join(DATA_DIR, "modlog.json")

OWNER_USER_ID = int(os.getenv("OWNER_USER_ID", "0") or 0)

# --------- helpers ---------
def _ensure_store():
    if not os.path.isdir(DATA_DIR):
        os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.isfile(GCFG_PATH):
        with open(GCFG_PATH, "w", encoding="utf-8") as f:
            json.dump({}, f)

def _load_json(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _file_info(path: str) -> Tuple[bool, int, str]:
    """(exists, size_bytes, sha256) — sha256 over raw bytes for attestation."""
    if not os.path.isfile(path):
        return (False, 0, "")
    try:
        data = open(path, "rb").read()
        return (True, len(data), hashlib.sha256(data).hexdigest())
    except Exception:
        return (False, 0, "")

def _code_hashes() -> List[Tuple[str, str]]:
    """Hash a small set of relevant files for proof-of-code-state."""
    candidates = [
        "bot.py",
        "config.py",
        "ai_provider.py",
        "cogs/wellbeing_cog.py",
        "cogs/mod_recommender_cog.py",
        "cogs/ethics_cog.py",
        "cogs/greeter_cog.py",
        "cogs/pin_react_cog.py",
        "cogs/owner_guard_cog.py",
        "cogs/lore_cog.py",
        "cogs/faq_cog.py",
        "cogs/tickets_cog.py",
        "cogs/roles_cog.py",
        "cogs/youtube_cog.py",
    ]
    out = []
    for p in candidates:
        if os.path.isfile(p):
            try:
                b = open(p, "rb").read()
                out.append((p, hashlib.sha256(b).hexdigest()))
            except Exception:
                out.append((p, ""))
    return out

def _env_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name, str(default))
    return str(v).lower() in ("1", "true", "yes", "y", "on")

# Mirror of your wellbeing settings if present
SUPPORT_ENABLED = _env_bool("SUPPORT_ENABLED", True)
SUPPORT_RETENTION_DAYS = int(os.getenv("SUPPORT_RETENTION_DAYS", "30"))
SUPPORT_ALERT_OWNER_ON_CRISIS = _env_bool("SUPPORT_ALERT_OWNER_ON_CRISIS", False)
SUPPORT_NOTIFY_OWNER_INTEREST = _env_bool("SUPPORT_NOTIFY_OWNER_INTEREST", True)

# --------- report builder ---------
def build_ethics_snapshot(guild: discord.Guild, bot: commands.Bot) -> Dict[str, Any]:
    _ensure_store()

    # Guild config (channels/ids only; no secrets)
    gcfg = _load_json(GCFG_PATH)
    gentry = gcfg.get(str(guild.id), {})

    # Wellbeing (counts only)
    wb = _load_json(WELLBEING_PATH)
    wb_entries = wb.get("entries", []) if isinstance(wb, dict) else []
    wb_optin = wb.get("optin", []) if isinstance(wb, dict) else []
    wb_last_purge = wb.get("last_purge_ts", 0.0) if isinstance(wb, dict) else 0.0

    # Mod log (counts only, optional)
    ml = _load_json(MODLOG_PATH)
    ml_entries = ml.get("entries", []) if isinstance(ml, dict) else []

    # File attestations
    files = {
        "guild_config.json": _file_info(GCFG_PATH),
        "wellbeing.json": _file_info(WELLBEING_PATH),
        "modlog.json": _file_info(MODLOG_PATH),
    }
    code = _code_hashes()

    # Bot permission view
    me = guild.get_member(bot.user.id)
    perms = guild.me.guild_permissions if guild.me else None
    perm_map = {}
    if perms:
        perm_map = {k: getattr(perms, k) for k in dir(perms) if not k.startswith("_") and isinstance(getattr(perms, k), bool)}

    # Public commitments (what the bot does NOT do)
    commitments = [
        "No long-lived per-member behavioral profiles.",
        "No storage of message content from scans; only ephemeral counts per /modscan run.",
        "Wellbeing entries are opt-in and auto-purged after retention window.",
        "Private check-ins are user-initiated and stored only as their own answers.",
        "No protected-class inference, no psychoanalysis.",
        "Clear owner controls; audit logs for sensitive actions.",
    ]

    now = int(time.time())
    snapshot = {
        "generated_at_unix": now,
        "guild": {"id": guild.id, "name": guild.name},
        "bot_user": {"id": bot.user.id if bot.user else None, "name": bot.user.name if bot.user else None},
        "owner_user_id": OWNER_USER_ID,
        "features": {
            "wellbeing_enabled": SUPPORT_ENABLED,
            "wellbeing_retention_days": SUPPORT_RETENTION_DAYS,
            "crisis_owner_alerts": SUPPORT_ALERT_OWNER_ON_CRISIS,
            "interest_owner_nudges": SUPPORT_NOTIFY_OWNER_INTEREST,
            "mod_recommender": True,
        },
        "wellbeing_counts": {
            "optins": len(wb_optin),
            "entries": len(wb_entries),
            "last_purge_ts": int(wb_last_purge) if wb_last_purge else 0,
        },
        "modlog_counts": {
            "entries": len(ml_entries),
        },
        "configured_channels": {
            "mission_audit_channel_id": gentry.get("mission_audit_channel_id", 0),
            "welcome_channel_id": gentry.get("welcome_channel_id", 0),
            "greeter_channel_id": gentry.get("greeter_channel_id", 0),
            "modscan_channel_ids": gentry.get("modscan_channel_ids", []),
        },
        "roles": {
            "modscan_volunteer_role_id": gentry.get("modscan_volunteer_role_id", 0),
            "modscan_trial_role_id": gentry.get("modscan_trial_role_id", 0),
            "trusted_role_ids": gentry.get("trusted_role_ids", []),
            "yt_verified_role_id": gentry.get("yt_verified_role_id", 0),
        },
        "bot_permissions": perm_map,  # boolean flags (manage_roles, view_audit_log, etc.)
        "files": {
            "guild_config.json": {"exists": files["guild_config.json"][0], "size": files["guild_config.json"][1], "sha256": files["guild_config.json"][2]},
            "wellbeing.json": {"exists": files["wellbeing.json"][0], "size": files["wellbeing.json"][1], "sha256": files["wellbeing.json"][2]},
            "modlog.json": {"exists": files["modlog.json"][0], "size": files["modlog.json"][1], "sha256": files["modlog.json"][2]},
        },
        "code_hashes": [{"path": p, "sha256": h} for (p, h) in code],
        "commitments": commitments,
        "notes": "Counts only; no message bodies included. This report is generated on demand.",
    }
    return snapshot

def _policy_embed(snapshot: Dict[str, Any]) -> discord.Embed:
    g = snapshot["guild"]["name"]
    wb = snapshot["wellbeing_counts"]
    feats = snapshot["features"]

    desc = (
        f"**Server:** {g}\n"
        f"**Wellbeing (opt-in):** {wb['optins']} opted in, {wb['entries']} entries (retention {feats['wellbeing_retention_days']}d)\n"
        f"**Crisis alerts to owner:** {feats['crisis_owner_alerts']}\n"
        f"**Interest nudges to owner:** {feats['interest_owner_nudges']}\n"
        f"**Mod recommender:** {feats['mod_recommender']} (counts only, no content stored)"
    )
    e = discord.Embed(
        title="Ethics & Transparency",
        description=desc,
        color=discord.Color.blurple()
    )
    e.add_field(
        name="Commitments",
        value="• No long-lived profiles\n• No content storage from scans\n• Opt-in wellbeing only\n• Auto-purge after retention\n• No protected-class inference",
        inline=False
    )
    e.set_footer(text=f"Generated • <t:{snapshot['generated_at_unix']}:R>")
    return e

# --------- signature helpers ---------
def _compact_json(obj: Any) -> bytes:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

def _verify_bundle(bundle: Dict[str, Any]) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """
    Returns (ok, message, report_dict_or_none)
    """
    try:
        sig = bundle.get("signature_sha256")
        report = bundle.get("report")
        if not sig or not report:
            return (False, "Missing 'signature_sha256' or 'report' fields.", None)
        calc = hashlib.sha256(_compact_json(report)).hexdigest()
        if calc != sig:
            return (False, "Signature mismatch.", report)
        return (True, "Valid signature.", report)
    except Exception as e:
        return (False, f"Verification error: {e.__class__.__name__}: {str(e)[:140]}", None)

# --------- Cog ---------
class EthicsCog(commands.Cog):
    """Provides an ethics/transparency report to build user trust."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="ethics_report", description="Private ethics/transparency report (ephemeral).")
    async def ethics_report(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("Run this in a server.", ephemeral=True)
            return
        snap = build_ethics_snapshot(interaction.guild, self.bot)
        await interaction.response.send_message(embed=_policy_embed(snap), ephemeral=True)

    @app_commands.command(name="ethics_public", description="Post a public ethics summary to this channel.")
    async def ethics_public(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("Run this in a server.", ephemeral=True)
            return
        if not (interaction.user.guild_permissions.manage_guild or (OWNER_USER_ID and interaction.user.id == OWNER_USER_ID)):
            await interaction.response.send_message("Manage Server (or Owner) required.", ephemeral=True)
            return

        snap = build_ethics_snapshot(interaction.guild, self.bot)
        embed = _policy_embed(snap)
        await interaction.response.send_message("Posting public ethics summary…", ephemeral=True)
        await interaction.channel.send(embed=embed)

    @app_commands.command(name="ethics_export", description="DM a signed JSON ethics report (owner/admin).")
    async def ethics_export(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("Run this in a server.", ephemeral=True)
            return
        if not (interaction.user.guild_permissions.manage_guild or (OWNER_USER_ID and interaction.user.id == OWNER_USER_ID)):
            await interaction.response.send_message("Manage Server (or Owner) required.", ephemeral=True)
            return

        snap = build_ethics_snapshot(interaction.guild, self.bot)
        payload = _compact_json(snap)
        sig = hashlib.sha256(payload).hexdigest()
        bundle = {"report": snap, "signature_sha256": sig}
        buf = io.BytesIO(json.dumps(bundle, ensure_ascii=False, indent=2).encode("utf-8"))
        buf.seek(0)

        try:
            await interaction.user.send(
                content="Here’s your signed ethics report JSON. You can share this publicly.",
                file=discord.File(buf, filename="ethics_report.json")
            )
            await interaction.response.send_message("Sent via DM.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("I can’t DM you. Please open DMs and try again.", ephemeral=True)

    @app_commands.command(
        name="ethics_verify",
        description="Verify a signed ethics_report.json (attach file or paste JSON)."
    )
    @app_commands.describe(
        bundle_json="Paste the JSON bundle (optional if you attach a file)."
    )
    async def ethics_verify(
        self,
        interaction: discord.Interaction,
        bundle_json: Optional[str] = None,
        attachment: Optional[discord.Attachment] = None
    ):
        """
        Anyone can run this. Result is ephemeral.
        Priority: attachment > pasted JSON.
        """
        if interaction.guild is None:
            await interaction.response.send_message("Run this in a server.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        # Prefer attachment if present
        raw: Optional[str] = None
        if isinstance(attachment, discord.Attachment):
            try:
                if attachment.size > 2_000_000:
                    await interaction.followup.send("File too large (>2 MB).", ephemeral=True)
                    return
                data = await attachment.read()
                raw = data.decode("utf-8", errors="replace")
            except Exception as e:
                await interaction.followup.send(f"Could not read attachment: {e.__class__.__name__}", ephemeral=True)
                return
        elif bundle_json and bundle_json.strip():
            raw = bundle_json.strip()

        if not raw:
            await interaction.followup.send("Please attach `ethics_report.json` or paste its JSON.", ephemeral=True)
            return

        try:
            bundle = json.loads(raw)
        except Exception as e:
            await interaction.followup.send(f"Invalid JSON: {e.__class__.__name__}", ephemeral=True)
            return

        ok, msg, report = _verify_bundle(bundle)

        color = discord.Color.green() if ok else discord.Color.red()
        emb = discord.Embed(
            title="Ethics Report Verification",
            description=msg,
            color=color
        )
        if report:
            try:
                gname = str(report.get("guild", {}).get("name", "unknown"))
                ts = int(report.get("generated_at_unix", 0) or 0)
                emb.add_field(name="Server", value=gname or "unknown", inline=True)
                if ts:
                    emb.add_field(name="Generated", value=f"<t:{ts}:R>", inline=True)
            except Exception:
                pass

        await interaction.followup.send(embed=emb, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(EthicsCog(bot))