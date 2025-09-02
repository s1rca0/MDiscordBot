# ai_mode.py
import json
import os
from typing import Literal

DATA_DIR = "data"
MODE_PATH = os.path.join(DATA_DIR, "ai_mode.json")

Mode = Literal["fast", "smart"]

def _ensure_dir():
    if not os.path.isdir(DATA_DIR):
        os.makedirs(DATA_DIR, exist_ok=True)

def get_mode(default: Mode = "fast") -> Mode:
    _ensure_dir()
    try:
        with open(MODE_PATH, "r", encoding="utf-8") as f:
            obj = json.load(f)
            m = str(obj.get("mode", default)).lower()
            return "smart" if m == "smart" else "fast"
    except Exception:
        return default

def set_mode(mode: Mode):
    _ensure_dir()
    with open(MODE_PATH, "w", encoding="utf-8") as f:
        json.dump({"mode": "smart" if mode == "smart" else "fast"}, f, indent=2)