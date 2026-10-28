"""Sahulat web server."""
import logging
import os
import time
from pathlib import Path
from typing import Literal

import httpx
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import agent, llm

ROOT = Path(__file__).resolve().parent.parent
log = logging.getLogger("sahulat")
app = FastAPI(title="Sahulat", docs_url=None, redoc_url=None, openapi_url=None)

# "cloud" = Gemma 4 on the Gemini API with automatic fallback to our own server.
# "local" = everything on our own Gemma server. Documents are always read locally.
DEFAULT_MODE = os.environ.get("DEFAULT_MODE", "cloud" if llm.BACKENDS["cloud"]["key"] else "local")
MAX_IMAGE_BYTES = 8_000_000
PROFILE_KEYS = {"document_type", "name", "father_name", "cnic_masked", "gender",
                "date_of_birth", "address", "district", "tehsil"}

CNIC_PROMPT = """This is a photo of a Pakistani identity document (CNIC, B-Form) or a utility bill.
Read it and return ONLY a JSON object with these keys (use "" when not visible):
{"document_type": "", "name": "", "father_name": "", "cnic": "", "gender": "",
 "date_of_birth": "", "address": "", "district": "", "tehsil": ""}
Copy the text exactly as printed. Do not guess."""


class Turn(BaseModel):
    # Only user/assistant turns are accepted, so a client cannot inject system instructions.
    role: Literal["user", "assistant"]
    content: str = Field(max_length=2000)


class ChatIn(BaseModel):
    history: list[Turn] = Field(min_length=1, max_length=40)
    profile: dict | None = None


class SayIn(BaseModel):
    text: str = Field(max_length=600)


def mask(cnic: str) -> str:
    digits = "".join(c for c in cnic if c.isdigit())
    return f"{digits[:5]}-*******-{digits[-1]}" if len(digits) == 13 else ""


def clean_profile(profile):
    """Keep only known, short text fields; never pass the full CNIC to the model."""
    if not profile:
        return None
    return {k: str(v)[:120] for k, v in profile.items() if k in PROFILE_KEYS and v}


@app.post("/api/chat")
def chat(body: ChatIn):
    history = [t.model_dump() for t in body.history[-12:]]
    try:
        return agent.respond(history, mode=DEFAULT_MODE, profile=clean_profile(body.profile))
    except Exception:
        log.exception("chat failed")
        raise HTTPException(502, "Sahulat could not reach Gemma right now. Please try again in a moment.")


@app.post("/api/read-document")
async def read_document(file: UploadFile = File(...)):
    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(415, "Please upload a photo (JPG or PNG).")
    # The image is processed in memory and never written to disk.
    data = await file.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(413, "The photo is too large.")
    t = time.time()
    try:
        fields, mode = llm.read_image_json(data, file.content_type, CNIC_PROMPT)
    except Exception:
        log.exception("document read failed")
        raise HTTPException(502, "Could not read the document. Please try a clearer photo.")
    finally:
        del data
    fields = {k: str(v)[:200] for k, v in fields.items() if isinstance(v, (str, int))}
    fields["cnic_masked"] = mask(fields.get("cnic", ""))
    return {"fields": fields, "processed_on": "our own server" if mode == "local" else "cloud",
            "seconds": round(time.time() - t, 1)}


@app.post("/api/tts")
def tts(body: SayIn):
    # Urdu speech from self-hosted MMS-TTS (browsers rarely ship an Urdu voice).
    url = os.environ.get("TTS_URL", "http://localhost:8101/tts")
    try:
        r = httpx.post(url, json={"text": body.text}, timeout=60)
        r.raise_for_status()
    except Exception:
        log.exception("tts failed")
        raise HTTPException(502, "Voice is not available right now.")
    return Response(r.content, media_type="audio/wav")


@app.get("/api/services")
def services():
    return agent.KNOWLEDGE


@app.middleware("http")
async def security_headers(request, call_next):
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["Permissions-Policy"] = "camera=(self), microphone=(self), geolocation=()"
    if request.url.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store"  # personal data must not be cached
    return resp


@app.get("/")
def index():
    return FileResponse(ROOT / "static" / "index.html")


app.mount("/", StaticFiles(directory=ROOT / "static"), name="static")
