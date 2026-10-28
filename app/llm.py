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


def _ollama_chat(messages, tools=None, temperature=0.3, images=None, fmt=None):
    """Native Ollama API: lets us switch off Gemma 4's thinking, which is ~4x faster on CPU."""
    base = BACKENDS["local"]["base"].removesuffix("/v1")
    if images:
        messages = [dict(messages[-1], images=images)]
    body = {"model": BACKENDS["local"]["model"], "messages": messages, "stream": False,
            "think": False, "options": {"temperature": temperature}}
    if tools:
        body["tools"] = tools
    if fmt:
        body["format"] = fmt
    r = httpx.post(f"{base}/api/chat", json=body, timeout=300)
    r.raise_for_status()
    return r.json()["message"]


def chat(messages, mode="local", tools=None, temperature=0.3):
    if mode == "local":
        return _ollama_chat(messages, tools, temperature)
    b = BACKENDS[mode]
    body = {"model": b["model"], "messages": messages, "temperature": temperature}
    if tools:
        body["tools"] = tools
    for attempt in range(2):
        try:
            # The free Gemini API sometimes hangs; give up fast and let the caller fall back.
            r = httpx.post(
                f"{b['base']}/chat/completions",
                headers={"Authorization": f"Bearer {b['key']}"},
                json=body,
                timeout=45,
            )
        except httpx.TimeoutException:
            if attempt == 1:
                raise
            continue
        if r.status_code not in (429, 500, 503) or attempt == 1:
            break
        time.sleep(1)
    r.raise_for_status()
    msg = r.json()["choices"][0]["message"]
    if msg.get("content"):
        # Gemma 4 may include its reasoning; users only see the answer.
        msg["content"] = re.sub(r"<thought>.*?</thought>", "", msg["content"], flags=re.S).strip()
    return msg


def read_image_json(image_bytes, mime, prompt):
    """Run Gemma 4 vision on an image. Always local: personal documents never go to the cloud."""
    mode = "cloud" if os.environ.get("ALLOW_CLOUD_DOCUMENTS") == "1" else "local"
    if mode == "local":
        msg = _ollama_chat([{"role": "user", "content": prompt}], temperature=0,
                           images=[base64.b64encode(image_bytes).decode()], fmt="json")
        text = msg.get("content") or ""
        m = re.search(r"\{.*\}", text, re.S)
        return json.loads(m.group(0)) if m else {}, mode
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
