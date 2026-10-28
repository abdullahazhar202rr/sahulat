"""Sahulat web server."""
import time
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import agent, llm

ROOT = Path(__file__).resolve().parent.parent
app = FastAPI(title="Sahulat")

CNIC_PROMPT = """This is a photo of a Pakistani identity document (CNIC, B-Form) or a utility bill.
Read it and return ONLY a JSON object with these keys (use "" when not visible):
{"document_type": "", "name": "", "father_name": "", "cnic": "", "gender": "",
 "date_of_birth": "", "address": "", "district": "", "tehsil": ""}
Copy the text exactly as printed. Do not guess."""


class ChatIn(BaseModel):
    history: list[dict]
    mode: str = "local"
    profile: dict | None = None


def mask(cnic: str) -> str:
    digits = "".join(c for c in cnic if c.isdigit())
    return f"{digits[:5]}-*******-{digits[-1]}" if len(digits) == 13 else ""


@app.post("/api/chat")
def chat(body: ChatIn):
    if body.mode not in llm.BACKENDS:
        raise HTTPException(400, "unknown mode")
    try:
        return agent.respond(body.history[-12:], mode=body.mode, profile=body.profile)
    except Exception as e:
        raise HTTPException(502, f"Gemma is not reachable: {e}")


@app.post("/api/read-document")
async def read_document(file: UploadFile = File(...)):
    # The image is processed in memory and never written to disk.
    data = await file.read()
    if len(data) > 8_000_000:
        raise HTTPException(413, "image too large")
    t = time.time()
    try:
        fields, mode = llm.read_image_json(data, file.content_type or "image/jpeg", CNIC_PROMPT)
    except Exception as e:
        raise HTTPException(502, f"Could not read the document: {e}")
    del data
    fields["cnic_masked"] = mask(fields.get("cnic", ""))
    return {"fields": fields, "processed_on": "our own server" if mode == "local" else "cloud",
            "seconds": round(time.time() - t, 1)}


@app.get("/api/services")
def services():
    return agent.KNOWLEDGE


@app.get("/")
def index():
    return FileResponse(ROOT / "static" / "index.html")


app.mount("/", StaticFiles(directory=ROOT / "static"), name="static")
