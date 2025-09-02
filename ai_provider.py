# ai_provider.py
from __future__ import annotations
import os
from typing import List, Dict, Any

from config import BotConfig
from ai_mode import get_mode

cfg = BotConfig()

# Lazy clients (loaded only if used)
_groq_client = None
_openai_client = None

def _groq():
    global _groq_client
    if _groq_client is None:
        from groq import Groq
        _groq_client = Groq(api_key=os.getenv("GROQ_API_KEY", "").strip() or None)
    return _groq_client

def _openai():
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI
        _openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY", "").strip() or None)
    return _openai_client

def current_model_name() -> str:
    """
    Decide the LLM name based on provider + runtime mode.
    - For Groq: choose fast/smart from env secrets.
    - For others: keep existing single-model env (compat).
    """
    if cfg.PROVIDER == "groq":
        mode = get_mode(cfg.AI_MODE_DEFAULT)
        if mode == "smart":
            return cfg.GROQ_MODEL_SMART or cfg.GROQ_MODEL or "llama-3.1-70b-versatile"
        return cfg.GROQ_MODEL_FAST or cfg.GROQ_MODEL or "llama-3.1-8b-instant"

    if cfg.PROVIDER == "openai":
        return cfg.OPENAI_MODEL or "gpt-4o-mini"

    if cfg.PROVIDER == "hf":
        return cfg.HF_MODEL or "gpt2"

    # default fallback
    return cfg.GROQ_MODEL_FAST or cfg.GROQ_MODEL or "llama-3.1-8b-instant"


def chat_completion(
    messages: List[Dict[str, str]],
    temperature: float | None = None,
    max_tokens: int | None = None
) -> str:
    """
    Minimal chat wrapper used by the bot's /ask (and others).
    """
    model = current_model_name()
    temp = cfg.AI_TEMPERATURE if temperature is None else temperature
    mxt  = cfg.AI_MAX_NEW_TOKENS if max_tokens is None else max_tokens

    if cfg.PROVIDER == "groq":
        client = _groq()
        if client is None:
            return "GROQ_API_KEY is missing."
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=float(temp),
            max_tokens=int(mxt),
        )
        return resp.choices[0].message.content or ""

    if cfg.PROVIDER == "openai":
        client = _openai()
        if client is None:
            return "OPENAI_API_KEY is missing."
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=float(temp),
            max_tokens=int(mxt),
        )
        # openai client may return as dict-like
        return resp.choices[0].message["content"] or ""

    # Hugging Face (very minimal, text-generation style)
    if cfg.PROVIDER == "hf":
        import requests
        api = os.getenv("HF_API_URL", "").strip()
        token = os.getenv("HF_API_KEY", "").strip()
        if not api or not token:
            return "HF_API_URL or HF_API_KEY is missing."
        prompt = "\n".join(f"{m['role']}: {m['content']}" for m in messages)
        headers = {"Authorization": f"Bearer {token}"}
        payload = {"inputs": prompt, "parameters": {"temperature": float(temp), "max_new_tokens": int(mxt)}}
        r = requests.post(api, headers=headers, json=payload, timeout=120)
        r.raise_for_status()
        data = r.json()
        # Try common HF output shapes:
        if isinstance(data, list) and data and "generated_text" in data[0]:
            out = data[0]["generated_text"]
            return out.split("assistant:", 1)[-1].strip() if "assistant:" in out else out
        if isinstance(data, dict) and "generated_text" in data:
            return str(data["generated_text"])
        return str(data)

    return "Provider not configured."


# ---------- NEW: simple public entrypoint expected by the bot ----------
def ai_reply(
    prompt: str,
    system: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> str:
    """
    Public entry used elsewhere in the bot: turns a plain prompt into a chat completion.
    Keeps the runtime mode selection logic inside current_model_name().
    """
    messages: List[Dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    return chat_completion(messages, temperature=temperature, max_tokens=max_tokens)


__all__ = ["chat_completion", "ai_reply", "current_model_name"]