# config.py — robust env loading + DRY_RUN support
import os
from pathlib import Path
from dotenv import load_dotenv

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

__version__ = "0.25.2"