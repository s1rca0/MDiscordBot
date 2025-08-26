# ai_provider.py
import os, asyncio
from typing import List, Dict
from huggingface_hub import InferenceClient

PROVIDER  = os.getenv("PROVIDER", "hf").lower()
HF_MODEL  = os.getenv("HF_MODEL", "gpt2")
HF_TOKEN  = os.getenv("HF_API_TOKEN", "")
OPENAI_KEY = os.getenv("OPENAI_API_KEY", "")

async def ai_reply(system: str, messages: List[Dict[str, str]],
                   max_new_tokens: int = 256, temperature: float = 0.7) -> str:
    # ---- OpenAI path (optional, only if you later set PROVIDER=openai) ----
    if PROVIDER == "openai" and OPENAI_KEY:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_KEY)
        msgs = [{"role": "system", "content": system}] + messages
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=msgs,
            max_tokens=max_new_tokens,
            temperature=temperature,
        )
        return r.choices[0].message.content.strip()

    # ---- Hugging Face path (default) ----
    prompt = (
        f"System: {system}\n"
        + "\n".join(f"{m['role'].capitalize()}: {m['content']}" for m in messages)
        + "\nAssistant:"
    )

    try:
        client = InferenceClient(model=HF_MODEL, token=(HF_TOKEN or None))
        loop = asyncio.get_running_loop()

        def _call():
            try:
                return client.text_generation(
                    prompt,
                    max_new_tokens=max_new_tokens,
                    temperature=temperature,
                    do_sample=True,
                    return_full_text=False,
                )
            except StopIteration:
                # Some client builds improperly raise StopIteration
                return ""

        text = await loop.run_in_executor(None, _call)
        return (text or "").strip()

    except StopIteration:
            # Extra guard in case it bubbles up anyway
            return ""

    except Exception as e:
            return f"(HF client error) {str(e)[:200]}"