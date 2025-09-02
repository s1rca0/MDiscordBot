# cogs/mission_cog.py
import os
import json
import time
import base64
import secrets
import string
import glob
import shutil
from functools import wraps
from typing import Dict, Any, List, Optional

import discord
from discord.ext import commands, tasks
from discord import app_commands

from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from cryptography.hazmat.backends import default_backend
from cryptography.fernet import Fernet, InvalidToken

from config import BotConfig

CFG = BotConfig()  # read auto-export settings & owner ID
OWNER_USER_ID = int(CFG.OWNER_USER_ID or 0)

DATA_DIR = "data"
PLAINTEXT_PATH = os.path.join(DATA_DIR, "mission.json")
ENCRYPTED_PATH = os.path.join(DATA_DIR, "mission.enc")

# ---------- Encryption helpers ----------

def _derive_key(passphrase: str, salt: bytes) -> bytes:
    kdf = Scrypt(salt=salt, length=32, n=2**14, r=8, p=1, backend=default_backend())
    key = kdf.derive(passphrase.encode("utf-8"))
    return base64.urlsafe_b64encode(key)

def _encrypt_json(obj: Dict[str, Any], passphrase: str) -> Dict[str, Any]:
    salt = os.urandom(16)
    key = _derive_key(passphrase, salt)
    f = Fernet(key)
    data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    token = f.encrypt(data)
    return {
        "salt_b64": base64.b64encode(salt).decode("ascii"),
        "cipher_b64": base64.b64encode(token).decode("ascii"),
        "updated_ts": time.time(),
        "version": 1,
    }

def _decrypt_json(bundle: Dict[str, Any], passphrase: str) -> Dict[str, Any]:
    salt = base64.b64decode(bundle["salt_b64"])
    token = base64.b64decode(bundle["cipher_b64"])
    key = _derive_key(passphrase, salt)
    f = Fernet(key)
    plaintext = f.decrypt(token)
    return json.loads(plaintext.decode("utf-8"))

def _has_passphrase() -> bool:
    val = os.getenv("MISSION_PASSPHRASE", CFG.MISSION_PASSPHRASE).strip()
    return len(val) >= 8

def _get_passphrase() -> str:
    return os.getenv("MISSION_PASSPHRASE", CFG.MISSION_PASSPHRASE).strip()

# ---------- Storage ----------

def _ensure_dir():
    os.makedirs(DATA_DIR, exist_ok=True)

def _default_doc() -> Dict[str, Any]:
    return {"mission": {}, "backups": [], "updated_ts": time.time()}

def _load_mission() -> Dict[str, Any]:
    _ensure_dir()
    if _has_passphrase() and os.path.isfile(ENCRYPTED_PATH):
        with open(ENCRYPTED_PATH, "r", encoding="utf-8") as f:
            bundle = json.load(f)
        doc = _decrypt_json(bundle, _get_passphrase())
        doc.setdefault("backups", [])
        return doc
    if os.path.isfile(PLAINTEXT_PATH):
        with open(PLAINTEXT_PATH, "r", encoding="utf-8") as f:
            doc = json.load(f)
        doc.setdefault("backups", [])
        return doc
    return _default_doc()

def _save_mission(doc: Dict[str, Any]):
    _ensure_dir()
    doc["updated_ts"] = time.time()
    if _has_passphrase():
        bundle = _encrypt_json(doc, _get_passphrase())
        with open(ENCRYPTED_PATH, "w", encoding="utf-8") as f:
            json.dump(bundle, f, ensure_ascii=False, indent=2)
        try:
            if os.path.isfile(PLAINTEXT_PATH):
                os.remove(PLAINTEXT_PATH)
        except Exception:
            pass
    else:
        with open(PLAINTEXT_PATH, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)

def _migrate_plaintext_to_encrypted():
    if not _has_passphrase() or not os.path.isfile(PLAINTEXT_PATH):
        return False
    with open(PLAINTEXT_PATH, "r", encoding="utf-8") as f:
        doc = json.load(f)
    _save_mission(doc)
    return True

# ---------- Backup envelopes ----------

def _derive_code_key(code: str, salt: bytes) -> bytes:
    kdf = Scrypt(salt=salt, length=32, n=2**14, r=8, p=1, backend=default_backend())
    key = kdf.derive(code.encode("utf-8"))
    return base64.urlsafe_b64encode(key)

def _make_backup_envelope(passphrase: str, code: str) -> Dict[str, Any]:
    salt = os.urandom(16)
    key = _derive_code_key(code, salt)
    token = Fernet(key).encrypt(passphrase.encode("utf-8"))
    return {
        "salt_b64": base64.b64encode(salt).decode("ascii"),
        "cipher_b64": base64.b64encode(token).decode("ascii"),
        "created_ts": time.time(),
        "used": False,
        "version": 1,
    }

def _try_open_envelope(envelope: Dict[str, Any], code: str) -> Optional[str]:
    try:
        salt = base64.b64decode(envelope["salt_b64"])
        cipher = base64.b64decode(envelope["cipher_b64"])
        key = _derive_code_key(code, salt)
        plain = Fernet(key).decrypt(cipher)
        return plain.decode("utf-8")
    except Exception:
        return None

# ---------- decorator: classified_only ----------

def classified_only():
    def deco(func):
        @wraps(func)
        async def wrapper(self, interaction: discord.Interaction, *args, **kwargs):
            if int(interaction.user.id) != int(OWNER_USER_ID):
                await interaction.response.send_message("Reserved for the operator.", ephemeral=True)
                return
            if interaction.guild is not None:
                await interaction.response.send_message("This is classified. DM me to proceed.", ephemeral=True)
                return
            return await func(self, interaction, *args, **kwargs)
        return wrapper
    return deco

# ---------- Cog ----------

class MissionCog(commands.Cog):
    """Owner-only, DM-only mission storage with encryption, backups, rotation, and auto-export scheduler."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Kick off the auto-export loop if enabled
        if CFG.MISSION_AUTO_EXPORT_ENABLED and CFG.MISSION_AUTO_EXPORT_HOURS > 0:
            # Convert hours → seconds for dynamic sleep
            self._export_interval_sec = int(CFG.MISSION_AUTO_EXPORT_HOURS * 3600)
            self.auto_export_loop.start()

    def cog_unload(self):
        if self.auto_export_loop.is_running():
            self.auto_export_loop.cancel()

    # -------------- Auto Export Core --------------

    def _timestamp_name(self) -> str:
        return time.strftime("%Y%m%d-%H%M%S")

    def _export_once(self) -> str:
        """
        Save current doc, then write a timestamped copy into /data.
        Returns the path written.
        """
        _ensure_dir()
        # Ensure latest doc is saved in the current mode
        try:
            doc = _load_mission()
        except InvalidToken:
            raise RuntimeError("Auto-export skipped: decryption failed (wrong or missing passphrase).")

        _save_mission(doc)

        ts = self._timestamp_name()
        if _has_passphrase():
            src = ENCRYPTED_PATH
            ext = "enc"
        else:
            src = PLAINTEXT_PATH
            ext = "json"

        dst = os.path.join(DATA_DIR, f"mission-backup-{ts}.{ext}")
        shutil.copy2(src, dst)
        return dst

    def _prune_backups(self):
        """Keep only the newest N backups (json+enc considered separately)."""
        keep = max(1, int(CFG.MISSION_AUTO_EXPORT_KEEP))
        for ext in ("enc", "json"):
            files = sorted(glob.glob(os.path.join(DATA_DIR, f"mission-backup-*.{ext}")))
            if len(files) > keep:
                for old in files[:-keep]:
                    try:
                        os.remove(old)
                    except Exception:
                        pass

    @tasks.loop(seconds=60)  # wakes every 60s; we self-sleep to the configured interval
    async def auto_export_loop(self):
        # Sleep to the desired interval between runs
        await discord.utils.sleep_until(discord.utils.utcnow().replace(microsecond=0))
        # After bot start, wait the configured interval:
        await discord.utils.sleep_until(discord.utils.utcnow() + discord.utils.timedelta(seconds=self._export_interval_sec))
        while True:
            try:
                path = self._export_once()
                self._prune_backups()
                # Optional: DM owner on first success after boot; keep silent otherwise
                # (commented out to avoid spam)
                # if OWNER_USER_ID:
                #     user = self.bot.get_user(OWNER_USER_ID)
                #     if user:
                #         await user.send(f"Mission auto-exported → `{path}`")
            except Exception as e:
                # Log silently; avoid crashing the loop
                print(f"[mission auto-export] {e}")
            # wait the next interval
            await discord.utils.sleep_until(discord.utils.utcnow() + discord.utils.timedelta(seconds=self._export_interval_sec))

    @auto_export_loop.before_loop
    async def before_auto_export(self):
        await self.bot.wait_until_ready()

    # -------------- Keyword DM trigger --------------

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if not OWNER_USER_ID or int(message.author.id) != int(OWNER_USER_ID):
            return
        content = (message.content or "").lower()
        if "noema" in content:
            if message.guild is None:
                return
            try:
                await message.author.send(
                    "I’m here. This channel is private. Your mission notes are encrypted when you set a strong passphrase."
                )
            except Exception:
                pass

    # -------------- Commands: init / passphrase / backups / rotate --------------

    @app_commands.command(name="mission_init", description="(Owner, DM) Initialize mission storage.")
    @classified_only()
    async def mission_init(self, interaction: discord.Interaction):
        doc = _default_doc()
        _save_mission(doc)
        await interaction.response.send_message(
            f"Mission store initialized. Encrypted = {bool(_has_passphrase())}.", ephemeral=True
        )

    @app_commands.command(name="mission_setpass", description="(Owner, DM) Set or change encryption passphrase (min 8 chars).")
    @app_commands.describe(passphrase="A strong passphrase you will remember (≥ 8 characters)")
    @classified_only()
    async def mission_setpass(self, interaction: discord.Interaction, passphrase: str):
        if len(passphrase.strip()) < 8:
            await interaction.response.send_message("Passphrase must be at least 8 characters.", ephemeral=True)
            return
        try:
            _ = _load_mission()
        except InvalidToken:
            await interaction.response.send_message(
                "Decryption failed. Use `/mission_usebackup` to recover, or set the correct passphrase first.",
                ephemeral=True
            )
            return
        os.environ["MISSION_PASSPHRASE"] = passphrase
        migrated = _migrate_plaintext_to_encrypted()
        await interaction.response.send_message(
            f"Passphrase set. {'Migrated plaintext → encrypted.' if migrated else 'Ready for encrypted saves.'}",
            ephemeral=True
        )

    @app_commands.command(name="mission_genpass", description="(Owner, DM) Generate a random strong passphrase (not stored).")
    @app_commands.describe(length="Length 16-128", symbols="Include symbols for extra entropy")
    @classified_only()
    async def mission_genpass(self, interaction: discord.Interaction, length: int = 24, symbols: bool = True):
        length = max(16, min(length, 128))
        alphabet = string.ascii_letters + string.digits
        if symbols:
            alphabet += "!@#$%^&*()-_=+[]{}:,.?/|"
        while True:
            pwd = "".join(secrets.choice(alphabet) for _ in range(length))
            if (any(c.islower() for c in pwd) and any(c.isupper() for c in pwd)
                    and any(c.isdigit() for c in pwd)
                    and ((not symbols) or any(c in "!@#$%^&*()-_=+[]{}:,.?/|" for c in pwd))):
                break
        await interaction.response.send_message(
            f"Generated (not stored):\n```\n{pwd}\n```\nUse `/mission_setpass` to enable encryption with it.",
            ephemeral=True
        )

    @app_commands.command(name="mission_showpass", description="(Owner, DM) Show current passphrase (or masked).")
    @app_commands.describe(reveal="If true, reveals the passphrase openly in this DM.")
    @classified_only()
    async def mission_showpass(self, interaction: discord.Interaction, reveal: bool = False):
        val = _get_passphrase()
        if not val:
            await interaction.response.send_message("No passphrase is set.", ephemeral=True)
            return
        if reveal:
            await interaction.response.send_message(f"Passphrase:\n```\n{val}\n```", ephemeral=True)
        else:
            await interaction.response.send_message(
                f"Passphrase is set (length {len(val)}). Use `/mission_showpass reveal:true` to view.",
                ephemeral=True
            )

    @app_commands.command(name="mission_genbackup", description="(Owner, DM) Generate backup codes to recover your passphrase.")
    @app_commands.describe(count="How many (1-10)", length="Code length (12-48)")
    @classified_only()
    async def mission_genbackup(self, interaction: discord.Interaction, count: int = 5, length: int = 20):
        if not _has_passphrase():
            await interaction.response.send_message(
                "Encryption is OFF. Set a strong passphrase first with `/mission_setpass`.", ephemeral=True
            )
            return
        try:
            doc = _load_mission()
        except InvalidToken:
            await interaction.response.send_message(
                "Decryption failed. Set the correct passphrase or use `/mission_usebackup`.", ephemeral=True
            )
            return
        count = max(1, min(count, 10))
        length = max(12, min(length, 48))
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"
        codes: List[str] = []
        for _ in range(count):
            code = "".join(secrets.choice(alphabet) for _ in range(length))
            env = _make_backup_envelope(_get_passphrase(), code)
            doc.setdefault("backups", []).append(env)
            codes.append(code)
        _save_mission(doc)
        pretty = "\n".join(f"- `{c}`" for c in codes)
        await interaction.response.send_message(
            "Backup codes created (store offline):\n" + pretty +
            "\nUse `/mission_usebackup code:<one>` to recover if needed.",
            ephemeral=True
        )

    @app_commands.command(name="mission_usebackup", description="(Owner, DM) Use a backup code to recover the passphrase.")
    @app_commands.describe(code="One of your backup codes")
    @classified_only()
    async def mission_usebackup(self, interaction: discord.Interaction, code: str):
        try:
            doc = _load_mission()
        except InvalidToken:
            await interaction.response.send_message(
                "Cannot open the vault. Ensure the encrypted file is present and try again.", ephemeral=True
            )
            return
        backups: List[Dict[str, Any]] = doc.get("backups", [])
        recovered: Optional[str] = None
        idx = -1
        for i, env in enumerate(backups):
            if env.get("used"):
                continue
            val = _try_open_envelope(env, code)
            if val:
                recovered = val
                idx = i
                break
        if not recovered:
            await interaction.response.send_message("Backup code invalid or already used.", ephemeral=True)
            return
        doc["backups"][idx]["used"] = True
        _save_mission(doc)
        os.environ["MISSION_PASSPHRASE"] = recovered
        await interaction.response.send_message(
            "Passphrase recovered for this session. Consider `/mission_rotatepass` and new backups.",
            ephemeral=True
        )

    @app_commands.command(name="mission_rotatepass", description="(Owner, DM) Re-encrypt under a new passphrase.")
    @app_commands.describe(new_passphrase="New strong passphrase (≥ 8)", clear_backups="Clear old backups?")
    @classified_only()
    async def mission_rotatepass(self, interaction: discord.Interaction, new_passphrase: str, clear_backups: bool = True):
        if len(new_passphrase.strip()) < 8:
            await interaction.response.send_message("New passphrase must be ≥ 8 chars.", ephemeral=True)
            return
        try:
            doc = _load_mission()
        except InvalidToken:
            await interaction.response.send_message(
                "Decryption failed with current passphrase. Try `/mission_usebackup`.", ephemeral=True
            )
            return
        os.environ["MISSION_PASSPHRASE"] = new_passphrase
        if clear_backups:
            doc["backups"] = []
        _save_mission(doc)
        await interaction.response.send_message(
            "Vault re-encrypted with new passphrase. "
            f"{'Old backups cleared.' if clear_backups else 'Old backups still valid.'} "
            "Run `/mission_genbackup` to create new backups.",
            ephemeral=True
        )

    # -------------- CRUD + import/export --------------

    @app_commands.command(name="mission_set", description="(Owner, DM) Set a mission key/value.")
    @classified_only()
    async def mission_set(self, interaction: discord.Interaction, key: str, value: str):
        try:
            doc = _load_mission()
        except InvalidToken:
            await interaction.response.send_message("Decryption failed. Set correct passphrase.", ephemeral=True)
            return
        doc.setdefault("mission", {})[key] = value
        _save_mission(doc)
        await interaction.response.send_message(f"Saved `{key}`.", ephemeral=True)

    @app_commands.command(name="mission_get", description="(Owner, DM) Get a mission value by key.")
    @classified_only()
    async def mission_get(self, interaction: discord.Interaction, key: str):
        try:
            doc = _load_mission()
        except InvalidToken:
            await interaction.response.send_message("Decryption failed. Set correct passphrase.", ephemeral=True)
            return
        val = doc.get("mission", {}).get(key)
        if val is None:
            await interaction.response.send_message(f"`{key}` not found.", ephemeral=True)
            return
        await interaction.response.send_message(f"`{key}` = `{val}`", ephemeral=True)

    @app_commands.command(name="mission_show", description="(Owner, DM) Show all mission keys.")
    @classified_only()
    async def mission_show(self, interaction: discord.Interaction):
        try:
            doc = _load_mission()
        except InvalidToken:
            await interaction.response.send_message("Decryption failed. Set correct passphrase.", ephemeral=True)
            return
        keys = sorted(doc.get("mission", {}).keys())
        if not keys:
            await interaction.response.send_message("No mission entries yet.", ephemeral=True)
            return
        await interaction.response.send_message("Keys: " + ", ".join(f"`{k}`" for k in keys), ephemeral=True)

    @app_commands.command(name="mission_delete", description="(Owner, DM) Delete a mission key.")
    @classified_only()
    async def mission_delete(self, interaction: discord.Interaction, key: str):
        try:
            doc = _load_mission()
        except InvalidToken:
            await interaction.response.send_message("Decryption failed. Set correct passphrase.", ephemeral=True)
            return
        if key in doc.get("mission", {}):
            del doc["mission"][key]
            _save_mission(doc)
            await interaction.response.send_message(f"Removed `{key}`.", ephemeral=True)
        else:
            await interaction.response.send_message(f"`{key}` not found.", ephemeral=True)

    @app_commands.command(name="mission_export_now", description="(Owner, DM) Export immediately to /data (timestamped).")
    @classified_only()
    async def mission_export_now(self, interaction: discord.Interaction):
        try:
            path = self._export_once()
            self._prune_backups()
            await interaction.response.send_message(f"Exported → `{path}`", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Export failed: {e}", ephemeral=True)

    @app_commands.command(name="mission_autoexport", description="(Owner, DM) Configure auto-export.")
    @app_commands.describe(
        enabled="Turn on/off periodic exports",
        hours="Interval in hours (e.g., 6, 12, 24)",
        keep="How many timestamped backup files to keep"
    )
    @classified_only()
    async def mission_autoexport(self, interaction: discord.Interaction,
                                 enabled: Optional[bool] = None,
                                 hours: Optional[float] = None,
                                 keep: Optional[int] = None):
        changed = []
        if enabled is not None:
            CFG.MISSION_AUTO_EXPORT_ENABLED = bool(enabled)
            changed.append(f"enabled={CFG.MISSION_AUTO_EXPORT_ENABLED}")
        if hours is not None and hours > 0:
            CFG.MISSION_AUTO_EXPORT_HOURS = float(hours)
            self._export_interval_sec = int(CFG.MISSION_AUTO_EXPORT_HOURS * 3600)
            changed.append(f"hours={CFG.MISSION_AUTO_EXPORT_HOURS}")
        if keep is not None and keep >= 1:
            CFG.MISSION_AUTO_EXPORT_KEEP = int(keep)
            changed.append(f"keep={CFG.MISSION_AUTO_EXPORT_KEEP}")

        # manage loop state
        if CFG.MISSION_AUTO_EXPORT_ENABLED and not self.auto_export_loop.is_running():
            self.auto_export_loop.start()
        elif not CFG.MISSION_AUTO_EXPORT_ENABLED and self.auto_export_loop.is_running():
            self.auto_export_loop.cancel()

        text = "Auto-export: "
        text += "running" if (CFG.MISSION_AUTO_EXPORT_ENABLED and self.auto_export_loop.is_running()) else "stopped"
        text += f" | interval={CFG.MISSION_AUTO_EXPORT_HOURS}h, keep={CFG.MISSION_AUTO_EXPORT_KEEP}"
        if changed:
            text += " | updated: " + ", ".join(changed)

        await interaction.response.send_message(text, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(MissionCog(bot))