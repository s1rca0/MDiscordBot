# config.py — robust env loading + DRY_RUN support
import os
from pathlib import Path
from dotenv import load_dotenv
from typing import Dict, Optional

load_dotenv()

# Load .env explicitly from repo root; fall back to process env
ROOT = Path(__file__).resolve().parent
ENV_PATH = ROOT / ".env"
if ENV_PATH.exists():
    load_dotenv(ENV_PATH, override=False)
    print(f"[config] Loaded .env from {ENV_PATH}")
else:
    load_dotenv(override=False)
    print("[config] .env not found next to config.py; relying on process env only")

# Core secrets
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "").strip()

# DRY_RUN: allow local imports/runs without a token
DRY_RUN = False
if not DISCORD_TOKEN:
    DRY_RUN = True
    print("[config] No DISCORD_TOKEN found; DRY_RUN=True (no Discord login).")

# Owners (comma-separated Discord user IDs)
raw_owner_ids = os.getenv("OWNER_IDS", "")
OWNERS = {int(x) for x in raw_owner_ids.replace(" ", "").split(",") if x}

# Optional providers; safe to leave empty
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
GROQ_API_KEY   = os.getenv("GROQ_API_KEY", "").strip()

# Data directory for small state
DATA_DIR = os.getenv("DATA_DIR", "./data").rstrip("/")
STATE_FILE = os.path.join(DATA_DIR, "state.json")

# Branding default if a guild hasn't set its nickname
DEFAULT_BRAND_NICK = os.getenv("DEFAULT_BRAND_NICK", "Morpheus")


# Optional: per-guild command sync for instant updates during dev
DEV_GUILD_IDS = {int(x) for x in os.getenv("DEV_GUILD_IDS", "").replace(" ", "").split(",") if x}

# ── Debate Dojo / Onboarding toggles & IDs ─────────────────────────────────────
# Core role IDs (set in your server; leave 0 if not used yet)
MAINFRAME_ROLE_ID       = int(os.getenv("MAINFRAME_ROLE_ID", "0"))    # default/basic role on join
THE_CONSTRUCT_ROLE_ID   = int(os.getenv("THE_CONSTRUCT_ROLE_ID", "0")) # granted on Red Pill

# Role IDs mapping for align_cog and quiz system (empty dict by default)
ROLE_IDS: Dict[str, int] = {}  # mapping of role names to IDs for align_cog and quiz system

# Review channel ID for quiz system feedback and discussion
REVIEW_CHANNEL_ID = int(os.getenv("REVIEW_CHANNEL_ID", "0"))  # channel ID for quiz review

# Default color for embeds in align_cog and quiz system (decimal)
COLOR = int(os.getenv("COLOR", str(int("0x00FF88", 16))))  # embed color accent

# Where to send step‑2 role menu (Option B flow). If 0, bot will DM instead.
ROLE_CONSOLE_CHAN_ID    = int(os.getenv("ROLE_CONSOLE_CHAN_ID", "0"))

# Optional ops log for audit breadcrumbs (joins, role grants, purges)
OPS_LOG_CHAN_ID         = int(os.getenv("OPS_LOG_CHAN_ID", "0"))

# UI polish: small animated boot line before the main embed (typing indicator)
ANIMATED_BOOT_ENABLED   = os.getenv("ANIMATED_BOOT_ENABLED", "true").lower() in {"1","true","yes","on"}
BOOT_DELETE_SECS        = int(os.getenv("BOOT_DELETE_SECS", "8"))      # ephemeral boot line lifetime

# Purger cadence (minutes). 0 disables scheduled purges; slash command still works.
VOID_PURGE_EVERY_MIN    = int(os.getenv("VOID_PURGE_EVERY_MIN", "1440"))

# Custom emoji IDs for the pills (server-specific). If left 0, fallback to unicode 🔴 🔵.
RED_PILL_EMOJI_ID       = int(os.getenv("RED_PILL_EMOJI_ID", "0"))
BLUE_PILL_EMOJI_ID      = int(os.getenv("BLUE_PILL_EMOJI_ID", "0"))

# Branding / color accents for embeds (decimal 0–16777215). Example: 0x10A37F → 1099199
BRAND_PRIMARY_COLOR     = int(os.getenv("BRAND_PRIMARY_COLOR", str(int("0x10A37F", 16))))
BRAND_ACCENT_COLOR      = int(os.getenv("BRAND_ACCENT_COLOR", str(int("0x2D2A32", 16))))

__version__ = "0.26.0"