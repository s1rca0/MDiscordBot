# memory_bridge.py
"""
Helper module for mission memory persistence.
Used by memory_bridge_cog.py to export/import important state.
"""

import os, json, time
from typing import Any, Dict

DATA_DIR = "data"
MEM_PATH = os.path.join(DATA_DIR, "mission_memory.json")

def _ensure_dir():
    if not os.path.isdir(DATA_DIR):
        os.makedirs(DATA_DIR, exist_ok=True)

def load_memory() -> Dict[str, Any]:
    """Load mission memory JSON if exists, else empty dict."""
    _ensure_dir()
    if not os.path.isfile(MEM_PATH):
        return {"created": time.time(), "entries": []}
    try:
        with open(MEM_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"created": time.time(), "entries": []}

def save_memory(payload: Dict[str, Any]):
    """Save mission memory JSON safely."""
    _ensure_dir()
    with open(MEM_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

def append_entry(note: str, meta: Dict[str, Any] = None):
    """Append a text entry with timestamp and optional metadata."""
    db = load_memory()
    entry = {
        "ts": time.time(),
        "note": note,
        "meta": meta or {}
    }
    db.setdefault("entries", []).append(entry)
    save_memory(db)
    return entry

def last_entries(n: int = 5):
    """Get last n entries for quick preview."""
    db = load_memory()
    return db.get("entries", [])[-n:]