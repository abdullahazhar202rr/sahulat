"""Thin client for Gemma 4 through any OpenAI-compatible endpoint.

local  -> Ollama on this machine (or your own server), nothing leaves your control
cloud  -> Gemma 4 on the Gemini API (only used for non-personal chat)
"""
import base64
import json
import os
import re
import time
from pathlib import Path

import httpx


def _load_env():
    env = Path(__file__).resolve().parent.parent / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


_load_env()

BACKENDS = {
    "local": {
        "base": os.environ.get("OLLAMA_URL", "http://localhost:11434/v1"),
        "model": os.environ.get("LOCAL_MODEL", "gemma4:e2b"),
        "key": "ollama",
    },
    "cloud": {
        "base": "https://generativelanguage.googleapis.com/v1beta/openai",
        "model": os.environ.get("CLOUD_MODEL", "gemma-4-26b-a4b-it"),
        "key": os.environ.get("GEMINI_API_KEY", ""),
    },
}


def chat(messages, mode="local", tools=None, temperature=0.3):
    b = BACKENDS[mode]
    body = {"model": b["model"], "messages": messages, "temperature": temperature}
    if tools:
        body["tools"] = tools
    for attempt in range(3):
        r = httpx.post(
            f"{b['base']}/chat/completions",
            headers={"Authorization": f"Bearer {b['key']}"},
            json=body,
            timeout=180,
        )
        if r.status_code not in (429, 500, 503) or attempt == 2:
            break
        time.sleep(2 * (attempt + 1))  # the free API is sometimes busy
    r.raise_for_status()
    msg = r.json()["choices"][0]["message"]
    if msg.get("content"):
        # Gemma 4 may include its reasoning; users only see the answer.
        msg["content"] = re.sub(r"<thought>.*?</thought>", "", msg["content"], flags=re.S).strip()
    return msg


def read_image_json(image_bytes, mime, prompt):
    """Run Gemma 4 vision on an image. Always local: personal documents never go to the cloud."""
    mode = "cloud" if os.environ.get("ALLOW_CLOUD_DOCUMENTS") == "1" else "local"
    url = f"data:{mime};base64,{base64.b64encode(image_bytes).decode()}"
    msg = chat(
        [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": url}},
        ]}],
        mode=mode,
        temperature=0,
    )
    text = msg.get("content") or ""
    m = re.search(r"\{.*\}", text, re.S)
    return json.loads(m.group(0)) if m else {}, mode
