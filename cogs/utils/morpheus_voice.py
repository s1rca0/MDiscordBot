# cogs/utils/morpheus_voice.py
import random
import discord
from typing import Optional

from config import BotConfig
cfg = BotConfig()

# Color from config (supports "0x123abc" or int). Fallback to a clean blue.
_raw = getattr(cfg, "DEFAULT_EMBED_COLOR", "0x3498db")
try:
    EMBED_COLOR = int(_raw, 16) if isinstance(_raw, str) else int(_raw)
except Exception:
    EMBED_COLOR = 0x3498db

FOOTER_TEXT = "M.O.R.P.H.E.U.S."
FOOTER_ICON = None  # put a small icon URL here if you have one

LINES = {
    "ack": ["Signal received.", "On it.", "Understood."],
    "done": ["Done.", "It is set.", "The switch is flipped."],
    "error": ["The grid balked. Try again.", "That path fails a sanity check.", "Can’t route that request."],
    "deny": ["You lack the keys for that door.", "Permission insufficient.", "Not with your current clearance."],
    "hello": ["Eyes open. We’re live.", "The system’s awake.", "I see you."],
    "thinking": ["Let me trace that route…", "Consulting the console…", "Tuning the antenna…"],
    "success": ["Green lights across the board.", "Clean handshake.", "It holds."],
    "void": [
        "[signal] The Void hums tonight. Those who listen may hear the door unlatch.",
        "[signal] Silence carries far. If you listen, you’ll hear the hinges breathe.",
        "[signal] The static settles. Pathways reveal themselves to patient eyes.",
    ],
}

def speak(kind: str, fallback: str = "Acknowledged.") -> str:
    """Pick a short, moody line by type."""
    return random.choice(LINES.get(kind, [fallback]))

def mk_embed(
    title: Optional[str] = None,
    description: Optional[str] = None,
    *,
    color: Optional[int] = None,
) -> discord.Embed:
    """Standard embed shell so everything looks like the same voice."""
    emb = discord.Embed(
        title=title or None,
        description=description or None,
        color=color if color is not None else EMBED_COLOR,
    )
    try:
        if FOOTER_ICON:
            emb.set_footer(text=FOOTER_TEXT, icon_url=FOOTER_ICON)
        else:
            emb.set_footer(text=FOOTER_TEXT)
    except Exception:
        emb.set_footer(text=FOOTER_TEXT)
    return emb