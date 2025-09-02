# cogs/mod_recommender_cog.py
import asyncio
import os
import time
import json
from typing import Dict, List, Tuple, Optional, Set

import discord
from discord.ext import commands
from discord import app_commands

DATA_DIR = "data"
GCFG_PATH = os.path.join(DATA_DIR, "guild_config.json")
MODLOG_PATH = os.path.join(DATA_DIR, "modlog.json")  # optional, read-only

OWNER_USER_ID = int(os.getenv("OWNER_USER_ID", "0") or 0)

# ---------- ENV DEFAULTS (used only if guild has no override) ----------
def _parse_ids(env_name: str) -> List[int]:
    v = os.getenv(env_name, "") or ""
    parts = [p.strip() for p in v.split(",") if p.strip()]
    out: List[int] = []
    for p in parts:
        try:
            out.append(int(p))
        except Exception:
            pass
    return out

ENV_CHANNEL_IDS = _parse_ids("MODREC_CHANNEL_IDS")             # empty => all
ENV_TRUST_ROLE_IDS = set(_parse_ids("MODREC_TRUST_ROLE_IDS"))  # optional
ENV_EXCLUDED_ROLE_IDS = set(_parse_ids("MODREC_EXCLUDED_ROLE_IDS"))  # optional
ENV_TRUST_BONUS = float(os.getenv("MODREC_TRUST_BONUS", "0.6") or 0.6)

# ---------- tiny store helpers (re-use guild_config.json) ----------
def _ensure_store():
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.isfile(GCFG_PATH):
        with open(GCFG_PATH, "w", encoding="utf-8") as f:
            json.dump({}, f)

def _load_gcfg() -> Dict:
    _ensure_store()
    with open(GCFG_PATH, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except Exception:
            return {}

def _save_gcfg(db: Dict):
    _ensure_store()
    with open(GCFG_PATH, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

def _get_guild(gid: int) -> Dict:
    return _load_gcfg().get(str(gid), {})

def _set_guild(gid: int, partial: Dict):
    db = _load_gcfg()
    g = db.get(str(gid), {})
    g.update(partial)
    db[str(gid)] = g
    _save_gcfg(db)

# ---- read existing audit channel from shared store (used by other cogs) ----
def _get_audit_channel_id(gid: int) -> int:
    g = _get_guild(gid)
    return int(g.get("mission_audit_channel_id", 0) or 0)

# ---- modscan config for this cog (per-guild overrides) ----
def _get_modscan_channels(gid: int) -> List[int]:
    g = _get_guild(gid)
    ids = g.get("modscan_channel_ids")
    if isinstance(ids, list) and ids:
        return list(map(int, ids))
    return list(ENV_CHANNEL_IDS)  # fallback to env (may be empty -> all)

def _set_modscan_channels(gid: int, ids: List[int]):
    _set_guild(gid, {"modscan_channel_ids": list(map(int, ids))})

def _get_volunteer_role_id(gid: int) -> int:
    g = _get_guild(gid)
    return int(g.get("modscan_volunteer_role_id", 0) or 0)

def _set_volunteer_role_id(gid: int, rid: int):
    _set_guild(gid, {"modscan_volunteer_role_id": int(rid)})

def _get_trial_role_id(gid: int) -> int:
    g = _get_guild(gid)
    return int(g.get("modscan_trial_role_id", 0) or 0)

def _set_trial_role_id(gid: int, rid: int):
    _set_guild(gid, {"modscan_trial_role_id": int(rid)})

# ---------- auth helpers ----------
def _is_owner(u: discord.abc.User) -> bool:
    return OWNER_USER_ID and int(u.id) == int(OWNER_USER_ID)

def _is_admin_or_owner(inter: discord.Interaction) -> bool:
    if _is_owner(inter.user):
        return True
    if isinstance(inter.user, discord.Member):
        return bool(inter.user.guild_permissions.administrator)
    return False

def _bot_can_manage_role(guild: discord.Guild, bot_user: discord.ClientUser, role: discord.Role) -> bool:
    me = guild.get_member(bot_user.id)
    if not me or not me.guild_permissions.manage_roles:
        return False
    top_pos = max((r.position for r in me.roles), default=0)
    return top_pos > role.position

# ---------- transparent scoring rubric ----------
WEIGHTS = {
    "msgs": 0.4,                 # participation
    "replies": 0.8,              # engagement/helpfulness
    "thanks": 0.6,               # “thanks/thank you/ty”
    "reactions_received": 0.8,   # positive reception proxy
    "links": -0.2,               # slight noise penalty
    "spam_burst": -1.0,          # rapid-fire bursts
    "age_bonus": 0.5,            # joined > N days
    "trust_bonus": 0.0,          # set dynamically if user has trusted roles
    "infractions": -1.5,         # optional (from mod log)
}

THANK_TOKENS = {"thanks", "thank you", "ty", "appreciate it"}
LINK_HINTS = ("http://", "https://")
TENOR_GIF_DOMAIN = "tenor.com"

SPAM_WINDOW_SECONDS = 15
SPAM_BURST_THRESHOLD = 5

INFRACTION_TYPES = {"warn", "mute", "kick", "ban", "timeout"}

def _count_infractions(user_id: int) -> int:
    """Read-only, ephemeral. Returns 0 if modlog doesn’t exist."""
    try:
        with open(MODLOG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        entries = data.get("entries", [])
        return sum(
            1 for e in entries
            if int(e.get("user_id", 0)) == int(user_id)
            and str(e.get("type", "")).lower() in INFRACTION_TYPES
        )
    except Exception:
        return 0

# ---------- Promote UI ----------
class PromoteView(discord.ui.View):
    def __init__(self, bot: commands.Bot, guild: discord.Guild, trial_role: discord.Role, candidate_ids: List[int], owner_id: int, *, timeout: int = 180):
        super().__init__(timeout=timeout)
        self.bot = bot
        self.guild = guild
        self.trial_role = trial_role
        self.owner_id = owner_id

        for uid in candidate_ids[:5]:
            label = f"Promote {uid}"
            self.add_item(PromoteButton(uid=uid, label=label))

    async def on_timeout(self):
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True

class PromoteButton(discord.ui.Button):
    def __init__(self, uid: int, label: str):
        super().__init__(style=discord.ButtonStyle.success, label=label, custom_id=f"promote:{uid}")
        self.uid = uid

    async def callback(self, interaction: discord.Interaction):
        view: PromoteView = self.view  # type: ignore
        if not view:
            await interaction.response.send_message("No view.", ephemeral=True)
            return

        if not (_is_owner(interaction.user) or (isinstance(interaction.user, discord.Member) and interaction.user.guild_permissions.administrator)):
            await interaction.response.send_message("Admin/Owner only.", ephemeral=True)
            return

        member = view.guild.get_member(self.uid)
        if not member:
            await interaction.response.send_message("User not found in guild.", ephemeral=True)
            return

        if not _bot_can_manage_role(view.guild, view.bot.user, view.trial_role):
            await interaction.response.send_message("I cannot assign that role (permissions/hierarchy).", ephemeral=True)
            return

        try:
            await member.add_roles(view.trial_role, reason="Promoted via modscan")
            await interaction.response.send_message(f"Granted {view.trial_role.mention} to {member.mention}.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Failed: {e.__class__.__name__}", ephemeral=True)
            return

        chan_id = _get_audit_channel_id(view.guild.id)
        if chan_id:
            chan = view.guild.get_channel(chan_id)
            if isinstance(chan, discord.TextChannel):
                owner_ping = f"<@{view.owner_id}>" if view.owner_id else ""
                emb = discord.Embed(
                    title="Trial Mod Granted",
                    description=f"{member.mention} received {view.trial_role.mention} by **{interaction.user}**.",
                    color=discord.Color.green()
                )
                try:
                    await chan.send(content=owner_ping, embed=emb)
                except Exception:
                    pass

# ---------- Cog ----------
class ModRecommenderCog(commands.Cog):
    """Privacy-friendly moderator candidate recommender with one-click promote."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ----- Setup commands -----
    @app_commands.command(name="modscan_set_channels", description="(Owner/Admin) Choose which channels to scan (comma-separated IDs). Empty to use all.")
    async def modscan_set_channels(self, inter: discord.Interaction, channels: str):
        if inter.guild is None:
            await inter.response.send_message("Run in a server.", ephemeral=True)
            return
        if not _is_admin_or_owner(inter):
            await inter.response.send_message("Admin/Owner only.", ephemeral=True)
            return
        channels = channels.strip()
        if not channels:
            _set_modscan_channels(inter.guild.id, [])
            await inter.response.send_message("Cleared override. Will scan **all** readable text channels.", ephemeral=True)
            return
        try:
            ids = [int(x.strip()) for x in channels.split(",") if x.strip().isdigit()]
        except Exception:
            await inter.response.send_message("Could not parse channel IDs.", ephemeral=True)
            return
        _set_modscan_channels(inter.guild.id, ids)
        names = []
        for cid in ids:
            ch = inter.guild.get_channel(cid)
            if ch:
                names.append(ch.mention)
        await inter.response.send_message(f"Mod-scan channels set: {', '.join(names) if names else '(none)'}", ephemeral=True)

    @app_commands.command(name="modscan_set_volunteer_role", description="(Owner/Admin) Only consider members with this role.")
    async def modscan_set_volunteer_role(self, inter: discord.Interaction, role: discord.Role):
        if inter.guild is None:
            await inter.response.send_message("Run in a server.", ephemeral=True)
            return
        if not _is_admin_or_owner(inter):
            await inter.response.send_message("Admin/Owner only.", ephemeral=True)
            return
        _set_volunteer_role_id(inter.guild.id, role.id)
        await inter.response.send_message(f"Volunteer role set to {role.mention}.", ephemeral=True)

    @app_commands.command(name="modscan_set_trial_role", description="(Owner/Admin) Set the Trial Mod role to grant with buttons.")
    async def modscan_set_trial_role(self, inter: discord.Interaction, role: discord.Role):
        if inter.guild is None:
            await inter.response.send_message("Run in a server.", ephemeral=True)
            return
        if not _is_admin_or_owner(inter):
            await inter.response.send_message("Admin/Owner only.", ephemeral=True)
            return
        _set_trial_role_id(inter.guild.id, role.id)
        await inter.response.send_message(f"Trial role set to {role.mention}.", ephemeral=True)

    @app_commands.command(name="modscan_info", description="(Owner/Admin) Show current modscan settings and rubric.")
    async def modscan_info(self, inter: discord.Interaction):
        if inter.guild is None:
            await inter.response.send_message("Run in a server.", ephemeral=True)
            return
        if not _is_admin_or_owner(inter):
            await inter.response.send_message("Admin/Owner only.", ephemeral=True)
            return
        ch_ids = _get_modscan_channels(inter.guild.id)
        volunteer_rid = _get_volunteer_role_id(inter.guild.id)
        trial_rid = _get_trial_role_id(inter.guild.id)

        ch_list = []
        if ch_ids:
            for cid in ch_ids:
                ch = inter.guild.get_channel(cid)
                ch_list.append(ch.mention if ch else f"`{cid}`")
        else:
            ch_list = ["(all readable text channels)"]

        rubric = "\n".join(f"• {k.replace('_',' ').title()}: {v:+.1f}" for k, v in WEIGHTS.items())
        env_hint = (
            f"\n\n**Env defaults** — Trust roles: "
            f"{', '.join(f'<@&{rid}>' for rid in ENV_TRUST_ROLE_IDS) if ENV_TRUST_ROLE_IDS else '(none)'}; "
            f"Excluded roles: {', '.join(f'<@&{rid}>' for rid in ENV_EXCLUDED_ROLE_IDS) if ENV_EXCLUDED_ROLE_IDS else '(none)'}; "
            f"Trust bonus: {ENV_TRUST_BONUS:+.1f}"
        )
        await inter.response.send_message(
            f"**Channels:** {', '.join(ch_list)}\n"
            f"**Volunteer role:** {inter.guild.get_role(volunteer_rid).mention if volunteer_rid else '(none)'}\n"
            f"**Trial role:** {inter.guild.get_role(trial_rid).mention if trial_rid else '(not set)'}\n\n"
            f"**Scoring rubric** (additive):\n{rubric}{env_hint}\n\n"
            "_No message content is stored. Counts are computed per run and discarded._",
            ephemeral=True
        )

    # ----- Main: /modscan with one-click promote -----
    @app_commands.command(name="modscan", description="(Owner/Admin) Suggest moderator candidates and optionally promote.")
    @app_commands.describe(
        days="Look back N days (1–14, default 7)",
        max_messages="Per channel cap (200–1500, default 800)",
        min_messages="Minimum messages for a candidate (default 15)",
        min_days_in_server="Minimum days in server (default 14)"
    )
    async def modscan(
        self,
        inter: discord.Interaction,
        days: app_commands.Range[int, 1, 14] = 7,
        max_messages: app_commands.Range[int, 200, 1500] = 800,
        min_messages: app_commands.Range[int, 1, 200] = 15,
        min_days_in_server: app_commands.Range[int, 0, 365] = 14,
    ):
        if inter.guild is None:
            await inter.response.send_message("Run in a server.", ephemeral=True)
            return
        if not _is_admin_or_owner(inter):
            await inter.response.defer(ephemeral=True)
            await inter.followup.send("Admin/Owner only.", ephemeral=True)
            return

        await inter.response.defer(ephemeral=True)

        # Channels to scan (override -> env -> all)
        ch_ids = _get_modscan_channels(inter.guild.id)
        channels: List[discord.TextChannel] = []
        if ch_ids:
            for cid in ch_ids:
                ch = inter.guild.get_channel(cid)
                if isinstance(ch, discord.TextChannel):
                    channels.append(ch)
        else:
            channels = [c for c in inter.guild.text_channels]

        cutoff_ts = time.time() - days * 86400

        stats: Dict[int, Dict[str, float]] = {}
        last_times: Dict[int, List[float]] = {}

        volunteer_rid = _get_volunteer_role_id(inter.guild.id)
        volunteer_role = inter.guild.get_role(volunteer_rid) if volunteer_rid else None

        excluded_roles = {inter.guild.get_role(rid) for rid in ENV_EXCLUDED_ROLE_IDS if inter.guild.get_role(rid)}
        trust_roles = {inter.guild.get_role(rid) for rid in ENV_TRUST_ROLE_IDS if inter.guild.get_role(rid)}

        def inc(uid: int, key: str, amt: float = 1.0):
            d = stats.setdefault(uid, {})
            d[key] = d.get(key, 0.0) + amt

        # Scan
        for ch in channels:
            if not isinstance(ch, discord.TextChannel):
                continue
            perms = ch.permissions_for(inter.guild.me)
            if not perms.read_message_history:
                continue
            try:
                async for msg in ch.history(limit=max_messages, oldest_first=False):
                    if msg.created_at.timestamp() < cutoff_ts:
                        break
                    if msg.author.bot:
                        continue

                    member = msg.author if isinstance(msg.author, discord.Member) else None
                    if not member:
                        continue

                    # Exclusions
                    if excluded_roles and any(r in excluded_roles for r in getattr(member, "roles", [])):
                        continue

                    # Volunteer filter (if set)
                    if volunteer_role and volunteer_role not in getattr(member, "roles", []):
                        continue

                    uid = member.id
                    inc(uid, "msgs", 1)

                    if msg.reference is not None or (msg.mentions and not msg.mention_everyone):
                        inc(uid, "replies", 1)

                    content_lower = (msg.content or "").lower()
                    if any(tok in content_lower for tok in THANK_TOKENS):
                        inc(uid, "thanks", 1)

                    if any(h in content_lower for h in LINK_HINTS):
                        if TENOR_GIF_DOMAIN not in content_lower:
                            inc(uid, "links", 1)

                    if msg.reactions:
                        total_reacts = sum(r.count for r in msg.reactions)
                        if total_reacts > 0:
                            inc(uid, "reactions_received", float(total_reacts))

                    ts = msg.created_at.timestamp()
                    lt = last_times.setdefault(uid, [])
                    lt.append(ts)
                    if len(lt) > 10:
                        lt.pop(0)
                    burst_count = sum(1 for t in lt if ts - t <= SPAM_WINDOW_SECONDS)
                    if burst_count >= SPAM_BURST_THRESHOLD:
                        inc(uid, "spam_burst", 1)

            except (discord.Forbidden, discord.HTTPException):
                continue

        # Build candidates
        now = time.time()
        candidates: List[Tuple[int, float, Dict[str, float]]] = []
        for uid, d in stats.items():
            member = inter.guild.get_member(uid)
            if not member:
                continue
            if d.get("msgs", 0) < min_messages:
                continue

            # Age bonus
            age_days = 0
            if member.joined_at:
                age_days = (now - member.joined_at.timestamp()) / 86400.0
            if age_days >= min_days_in_server:
                d["age_bonus"] = 1.0

            # Trust bonus (env roles only; no storage)
            if trust_roles and any(r in trust_roles for r in getattr(member, "roles", [])):
                d["trust_bonus"] = ENV_TRUST_BONUS

            # Optional infractions bridge
            infra = _count_infractions(uid)
            if infra > 0:
                d["infractions"] = float(infra)

            score = 0.0
            for k, w in WEIGHTS.items():
                weight = w
                if k == "trust_bonus":
                    weight = 1.0  # apply direct amount
                score += weight * float(d.get(k, 0.0))
            candidates.append((uid, score, d))

        candidates.sort(key=lambda t: t[1], reverse=True)
        top = candidates[:5]

        if not top:
            await inter.followup.send(
                "No suitable candidates found. Try a longer window, more channels, or lower thresholds.",
                ephemeral=True
            )
            return

        # Prepare lines
        lines = []
        top_ids = []
        for rank, (uid, score, d) in enumerate(top, 1):
            m = inter.guild.get_member(uid)
            if not m:
                continue
            top_ids.append(uid)
            breakdown = (
                f"msgs:{int(d.get('msgs',0))} repl:{int(d.get('replies',0))} "
                f"ty:{int(d.get('thanks',0))} reacts:{int(d.get('reactions_received',0))} "
                f"links:{int(d.get('links',0))} burst:{int(d.get('spam_burst',0))} "
                f"age+:{'Y' if d.get('age_bonus') else 'N'} "
                f"trust+:{d.get('trust_bonus',0)} "
                f"inf:{int(d.get('infractions',0))}"
            )
            lines.append(f"**{rank}.** {m.mention} — **{score:.2f}**  ({breakdown})")

        rubric = " / ".join(
            f"{k.replace('_',' ')}:{(ENV_TRUST_BONUS if k=='trust_bonus' else v):+}" for k, v in WEIGHTS.items()
        )

        # Promote controls (if trial role set & bot can manage it)
        trial_rid = _get_trial_role_id(inter.guild.id)
        trial_role = inter.guild.get_role(trial_rid) if trial_rid else None
        view: Optional[discord.ui.View] = None
        if trial_role and _bot_can_manage_role(inter.guild, self.bot.user, trial_role):
            view = PromoteView(self.bot, inter.guild, trial_role, top_ids, OWNER_USER_ID)

        await inter.followup.send(
            f"**Moderator candidate suggestions** (last {days}d, ≤{max_messages}/ch, min_msgs {min_messages}, min_age {min_days_in_server}d):\n"
            + "\n".join(lines)
            + f"\n\n**Rubric:** {rubric}\n_No message content stored; per-run counts only._",
            view=view,
            ephemeral=True
        )

        # Audit ping (if you’ve set it elsewhere)
        chan_id = _get_audit_channel_id(inter.guild.id)
        if chan_id:
            chan = inter.guild.get_channel(chan_id)
            if isinstance(chan, discord.TextChannel):
                owner_ping = f"<@{OWNER_USER_ID}>" if OWNER_USER_ID else ""
                emb = discord.Embed(
                    title="Mod Candidate Suggestions",
                    description=(
                        f"Requested by **{inter.user}** in {inter.channel.mention}\n"
                        f"Window: **{days}d**, cap **{max_messages}/ch**, min_msgs **{min_messages}**, min_age **{min_days_in_server}d**\n\n"
                        + "\n".join(lines)
                    ),
                    color=discord.Color.gold()
                )
                try:
                    await chan.send(content=owner_ping, embed=emb)
                except Exception:
                    pass

async def setup(bot: commands.Bot):
    await bot.add_cog(ModRecommenderCog(bot))