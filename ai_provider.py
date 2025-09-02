# ai_provider.py
import os, asyncio, time
from typing import List, Dict

# ---- Env --------------------------------------------------------------------
PROVIDER     = (os.getenv("PROVIDER", "hf") or "").strip().lower()
HF_MODEL     = (os.getenv("HF_MODEL", "gpt2") or "").strip()
HF_TOKEN     = (os.getenv("HF_API_TOKEN", "") or "").strip()
OPENAI_KEY   = (os.getenv("OPENAI_API_KEY", "") or "").strip()
GROQ_KEY     = (os.getenv("GROQ_API_KEY", "") or "").strip()
GROQ_MODEL   = (os.getenv("GROQ_MODEL", "llama-3.1-8b-instant") or "").strip()

print(f"DEBUG PROVIDER={PROVIDER} HF_MODEL={HF_MODEL!r} GROQ_MODEL={GROQ_MODEL!r}")

def build_prompt(system: str, messages: List[Dict[str, str]]) -> str:
    return (
        f"System: {system}\n"
        + "\n".join(f"{m['role'].capitalize()}: {m['content']}" for m in messages)
        + "\nAssistant:"
    )

# -----------------------------------------------------------------------------
async def ai_reply(system: str, messages: List[Dict[str, str]],
                   max_new_tokens: int = 256, temperature: float = 0.7) -> str:
    # ---------------- OpenAI path (optional) ---------------------------------
    if PROVIDER == "openai" and OPENAI_KEY:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=OPENAI_KEY)
            msgs = [{"role": "system", "content": system}] + messages
            r = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=msgs,
                max_tokens=max_new_tokens,
                temperature=temperature,
            )
            return (r.choices[0].message.content or "").strip()
        except Exception as e:
            return f"(OpenAI error) {type(e).__name__}: {str(e)[:160]}"

    # ---------------- GROQ path (recommended) --------------------------------
    if PROVIDER == "groq" and GROQ_KEY:
        try:
            # Uses Groq's OpenAI-compatible client
            from groq import Groq
            client = Groq(api_key=GROQ_KEY)
            msgs = [{"role": "system", "content": system}] + messages
            resp = await asyncio.to_thread(
                client.chat.completions.create,
                model=GROQ_MODEL,
                messages=msgs,
                max_tokens=max_new_tokens,
                temperature=temperature,
            )
            return (resp.choices[0].message.content or "").strip()
        except Exception as e:
            return f"(Groq error) {type(e).__name__}: {str(e)[:160]}"

    # ---------------- Hugging Face path (fallback) ---------------------------
    prompt = build_prompt(system, messages)

    # 1) Try hub client first
    try:
        from huggingface_hub import InferenceClient
        client = InferenceClient(token=(HF_TOKEN or None))
        loop = asyncio.get_running_loop()

        def _call_client():
            try:
                return client.text_generation(
                    prompt,
                    model=HF_MODEL,
                    max_new_tokens=max_new_tokens,
                    temperature=temperature,
                    do_sample=True,
                    return_full_text=False,
                    stream=False,
                )
            except StopIteration:
                return ""
            except Exception as e:
                return f"__HF_CLIENT_ERROR__ {type(e).__name__}: {str(e)[:160]}"

        text = await loop.run_in_executor(None, _call_client)

        if isinstance(text, str) and text.startswith("__HF_CLIENT_ERROR__"):
            raise RuntimeError(text)

        if isinstance(text, list) and text and isinstance(text[0], dict) and "generated_text" in text[0]:
            text = text[0]["generated_text"]
        elif isinstance(text, dict) and "generated_text" in text:
            text = text["generated_text"]

        if not text or not str(text).strip():
            raise RuntimeError("empty-from-client")

        return str(text).strip()

    except Exception:
        # 2) REST fallback with no-auth for public models (prevents 401 loop)
        try:
            import requests
        except Exception as e:
            return f"(HF REST import error) {type(e).__name__}: {str(e)[:160]}"

        url = f"https://api-inference.huggingface.co/models/{HF_MODEL}"
        headers = {"Content-Type": "application/json"}  # FORCE no auth to avoid 401s
        payload = {
            "inputs": prompt,
            "parameters": {
                "max_new_tokens": max_new_tokens,
                "temperature": temperature,
                "return_full_text": False,
            },
            "options": {"wait_for_model": True}
        }

        last_err = None
        for attempt in range(4):
            try:
                resp = requests.post(url, headers=headers, json=payload, timeout=90)
                code = resp.status_code
                if code in (200, 201):
                    try:
                        js = resp.json()
                    except Exception:
                        js = resp.text

                    if isinstance(js, list) and js and "generated_text" in js[0]:
                        return (js[0]["generated_text"] or "").strip()
                    if isinstance(js, dict) and "generated_text" in js:
                        return (js["generated_text"] or "").strip()
                    if isinstance(js, str):
                        s = js.strip()
                        return s if s else "…"
                    return str(js)[:500] or "…"

                if code == 503:
                    time.sleep(2 + attempt * 2)
                    continue

                return f"(HF REST {code}) {resp.text[:300]}"

            except Exception as e:
                last_err = e
                time.sleep(2 + attempt * 2)

        if last_err:
            return f"(HF REST error) {type(last_err).__name__}: {str(last_err)[:160]}"
        return "(HF REST error) No response after retries"