# cogs/memory_bridge.py
import os, json, time, asyncio
from typing import Dict, Any, List, Optional

import discord
from discord.ext import commands, tasks
from discord import app_commands

DATA_DIR = "data"
MEM_PATH = os.path.join(DATA_DIR, "mission_memory.json")
MISSION_NOTES_PATH = os.path.join(DATA_DIR, "mission.json")  # optional external notes file

def _env_bool(name: str, default: bool=False) -> bool:
    v = os.getenv(name, str(default))
    return str(v).lower() in ("1","true","yes","y","on")

def _csv_ids(name: str) -> List[int]:
    raw = os.getenv(name, "") or ""
    out: List[int] = []
    for tok in raw.replace(" ", "").split(","):
        if tok.isdigit():
            out.append(int(tok))
    return out

def _safe_int(name: str, default: int = 0) -> int:
    val = os.getenv(name, "")
    try:
        return int(val) if val and val.isdigit() else default
    except Exception:
        return default

def _ensure_dirs():
    if not os.path.isdir(DATA_DIR):
        os.makedirs(DATA_DIR, exist_ok=True)

def _read_json(path: str, default: Any) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def _write_json(path: str, payload: Any):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

class MemoryBridge(commands.Cog):
    """
    Consolidates mission + lore + infra into data/mission_memory.json
    Owner-only slash commands:
      /memory_dump  -> write now + return file
      /memory_sync  -> write now (no file)
      /memory_show  -> short summary (ephemeral)
      /memory_note  -> append a quick owner note
    Auto-saves every 6h and on_ready.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        _ensure_dirs()
        # cache last snapshot to reduce churn
        self._last: Dict[str, Any] = {}
        self.autosave.start()

    def cog_unload(self):
        self.autosave.cancel()

    # ---------- data collection ----------

    async def _collect(self) -> Dict[str, Any]:
        # 1) Infra (guild, channels, roles)
        guilds_payload: List[Dict[str, Any]] = []
        for g in self.bot.guilds:
            try:
                channels = [{
                    "id": c.id,
                    "name": c.name,
                    "type": str(c.type),
                    "category": (c.category.name if getattr(c, "category", None) else None)
                } for c in g.channels]

                roles = [{
                    "id": r.id,
                    "name": r.name,
                    "position": r.position
                } for r in g.roles]

                guilds_payload.append({
                    "id": g.id,
                    "name": g.name,
                    "member_count": g.member_count,
                    "owner_id": g.owner_id,
                    "system_channel_id": (g.system_channel.id if g.system_channel else None),
                    "rules_channel_id": (g.rules_channel.id if g.rules_channel else None),
                    "public_updates_channel_id": (g.public_updates_channel.id if g.public_updates_channel else None),
                    "channels": channels,
                    "roles": roles,
                })
            except Exception:
                # continue gracefully if a guild object has perms issues
                pass

        # 2) Config from env / secrets
        owner_id = _safe_int("OWNER_USER_ID", 0)

        greeter_enabled   = _env_bool("GREETER_ENABLED", True)
        greeter_channel   = _safe_int("GREETER_CHANNEL_ID", 0)
        greeter_rule      = os.getenv("GREETER_RULE", "first-message")

        # prompts (may be missing)
        greeter_public = os.getenv("GREETER_PUBLIC_PROMPT", "") or os.getenv("GREETER_PUBLIC_MSG", "")
        greeter_dm     = os.getenv("GREETER_DM_PROMPT", "") or os.getenv("GREETER_DM_MSG", "")
        greeter_sys    = os.getenv("GREETER_SYSTEM_PROMPT", "")

        # layer/channel IDs if you set them as secrets (optional)
        mainframe_ids  = _csv_ids("MAINFRAME_CHANNEL_IDS")
        construct_ids  = _csv_ids("CONSTRUCT_CHANNEL_IDS")
        havn_ids       = _csv_ids("HAVN_CHANNEL_IDS")

        # YouTube / RSS
        yt_channel_id  = os.getenv("YT_CHANNEL_ID", "")
        yt_rss_url     = os.getenv("YT_RSS_URL", "")
        yt_announce_id = _safe_int("YT_ANNOUNCE_CHANNEL_ID", 0)

        # Roles
        trusted_roles   = _csv_ids("TRUST_ROLE_IDS")
        yt_verified_id  = _safe_int("YT_VERIFIED_ROLE_ID", 0)

        # AI provider/model
        provider   = os.getenv("PROVIDER", "groq").lower()
        hf_model   = os.getenv("HF_MODEL", "")
        groq_model = os.getenv("GROQ_MODEL", "")
        openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        system_prompt = os.getenv("SYSTEM_PROMPT", "") or os.getenv("OWNER_SYSTEM_FRONT", "")

        # Mission/Lore inputs
        mission_notes = _read_json(MISSION_NOTES_PATH, default={"notes": []})

        # Lore layer prompts (optional secrets you may have set earlier)
        front_prompt  = os.getenv("OWNER_SYSTEM_FRONT", "")
        back_prompt   = os.getenv("OWNER_SYSTEM_BACK", "")
        owner_prompt  = os.getenv("OWNER_PROMPT", "")

        # 3) Existing memory file (to retain audit trail)
        mem = _read_json(MEM_PATH, default={})
        audit = mem.get("audit", [])[-50:]  # keep last 50 entries

        snapshot: Dict[str, Any] = {
            "meta": {
                "generated_ts": int(time.time()),
                "bot_user_id": (self.bot.user.id if self.bot.user else None),
                "bot_user_name": (self.bot.user.name if self.bot.user else None),
                "version": 2  # bump if structure changes later
            },
            "owner": {
                "owner_user_id": owner_id
            },
            "infra": {
                "guilds": guilds_payload,
                "mainframe_channel_ids": mainframe_ids,
                "construct_channel_ids": construct_ids,
                "havn_channel_ids": havn_ids,
                "trusted_role_ids": trusted_roles,
                "yt_verified_role_id": yt_verified_id
            },
            "greeter": {
                "enabled": greeter_enabled,
                "greeter_channel_id": greeter_channel,
                "rule": greeter_rule,
                "public_prompt": greeter_public,
                "dm_prompt": greeter_dm,
                "system_prompt": greeter_sys
            },
            "youtube": {
                "channel_id": yt_channel_id,
                "rss_url": yt_rss_url,
                "announce_channel_id": yt_announce_id
            },
            "ai": {
                "provider": provider,
                "hf_model": hf_model,
                "groq_model": groq_model,
                "openai_model": openai_model,
                "system_prompt": system_prompt
            },
            "lore_layers": {
                "front_persona_prompt": front_prompt,   # public-facing Morpheus
                "back_persona_prompt": back_prompt,     # trusted/mission-facing Morpheus
                "owner_persona_prompt": owner_prompt     # your private control voice
            },
            "mission": mission_notes,
            "audit": audit
        }
        return snapshot

    def _append_audit(self, mem: Dict[str, Any], event: str):
        audit = mem.setdefault("audit", [])
        audit.append({"ts": int(time.time()), "event": event})
        # keep last 200
        if len(audit) > 200:
            del audit[:-200]

    async def _save_now(self, event: str) -> Dict[str, Any]:
        payload = await self._collect()
        # only write if changed meaningfully or if forced event
        if payload != self._last or event == "manual-sync":
            self._append_audit(payload, event)
            _write_json(MEM_PATH, payload)
            self._last = payload
        return payload

    # ---------- background tasks ----------

    @tasks.loop(hours=6)
    async def autosave(self):
        await self._save_now("autosave-6h")

    @autosave.before_loop
    async def before_autosave(self):
        await self.bot.wait_until_ready()
        await self._save_now("startup")

    # ---------- slash commands (owner-only) ----------

    def _owner_check(self, user_id: int) -> bool:
        owner = os.getenv("OWNER_USER_ID", "")
        return owner and owner.isdigit() and int(owner) == int(user_id)

    @app_commands.command(name="memory_sync", description="(Owner) Force a memory sync to mission_memory.json")
    async def memory_sync(self, interaction: discord.Interaction):
        if not self._owner_check(interaction.user.id):
            return await interaction.response.send_message("Owner only.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        payload = await self._save_now("manual-sync")
        await interaction.followup.send(f"Synced. Size: ~{len(json.dumps(payload))} bytes.", ephemeral=True)

    @app_commands.command(name="memory_dump", description="(Owner) Dump mission_memory.json as a file")
    async def memory_dump(self, interaction: discord.Interaction):
        if not self._owner_check(interaction.user.id):
            return await interaction.response.send_message("Owner only.", ephemeral=True)
        payload = await self._save_now("manual-dump")
        try:
            await interaction.response.send_message(
                content="Here’s the current snapshot:",
                file=discord.File(MEM_PATH, filename="mission_memory.json"),
                ephemeral=True
            )
        except Exception:
            # fallback: send a short summary if file attach fails
            await interaction.response.send_message(
                f"Snapshot ready. Bytes: ~{len(json.dumps(payload))}. Couldn’t attach file.",
                ephemeral=True
            )

    @app_commands.command(name="memory_show", description="(Owner) Show a concise summary of current memory")
    async def memory_show(self, interaction: discord.Interaction):
        if not self._owner_check(interaction.user.id):
            return await interaction.response.send_message("Owner only.", ephemeral=True)
        mem = _read_json(MEM_PATH, default={})
        guilds = mem.get("infra", {}).get("guilds", [])
        yt = mem.get("youtube", {})
        ai = mem.get("ai", {})
        desc = (
            f"**Guilds:** {len(guilds)}\n"
            f"**Trusted roles:** {len(mem.get('infra',{}).get('trusted_role_ids', []))}\n"
            f"**YT channel:** {yt.get('channel_id') or '—'}  •  **RSS set:** {bool(yt.get('rss_url'))}\n"
            f"**AI:** {ai.get('provider','?')} • model={ai.get('groq_model') or ai.get('hf_model') or ai.get('openai_model')}\n"
            f"**Greeter on:** {mem.get('greeter',{}).get('enabled')}\n"
            f"**Audit entries:** {len(mem.get('audit', []))}\n"
        )
        embed = discord.Embed(title="Memory Summary", description=desc, color=discord.Color.blurple())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="memory_note", description="(Owner) Append a short mission note into the snapshot")
    @app_commands.describe(text="A short note (kept inside mission_memory.json → mission.notes)")
    async def memory_note(self, interaction: discord.Interaction, text: str):
        if not self._owner_check(interaction.user.id):
            return await interaction.response.send_message("Owner only.", ephemeral=True)
        mem = _read_json(MEM_PATH, default={})
        mission = mem.setdefault("mission", {})
        notes = mission.setdefault("notes", [])
        notes.append({"ts": int(time.time()), "text": text})
        self._append_audit(mem, "note-add")
        _write_json(MEM_PATH, mem)
        await interaction.response.send_message("Noted.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(MemoryBridge(bot))