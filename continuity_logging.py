# continuity_logging.py
import os, json, time, pathlib, threading

_DEFAULT_PATH = os.getenv("CONTINUITY_LOG_PATH", "data/logs/continuity.log")
_lock = threading.Lock()

class ContinuityLogger:
    def __init__(self, bot_name: str, backend: str, memory_mode: str, guild_id: str):
        self.ctx = {
            "bot": bot_name,
            "backend": backend,
            "memory": memory_mode,
            "guild": str(guild_id or "0"),
        }
        pathlib.Path(_DEFAULT_PATH).parent.mkdir(parents=True, exist_ok=True)

    def event(self, name: str, **fields):
        rec = {
            "ts": time.time(),
            "event": name,
            **self.ctx,
            **fields,
        }
        line = json.dumps(rec, ensure_ascii=False)
        with _lock:
            with open(_DEFAULT_PATH, "a", encoding="utf-8") as f:
                f.write(line + "\n")