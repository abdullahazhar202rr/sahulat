"""Self-hosted Urdu text-to-speech with Meta's open MMS-TTS model (facebook/mms-tts-urd)."""
import io

import numpy as np
import scipy.io.wavfile
import torch
from fastapi import FastAPI
from fastapi.responses import Response
from pydantic import BaseModel
from transformers import AutoTokenizer, VitsModel

MODEL = "facebook/mms-tts-urd-script_arabic"
tokenizer = AutoTokenizer.from_pretrained(MODEL)
model = VitsModel.from_pretrained(MODEL).eval()
app = FastAPI()


class Say(BaseModel):
    text: str


@app.post("/tts")
def tts(body: Say):
    inputs = tokenizer(body.text[:600], return_tensors="pt")
    with torch.no_grad():
        wave = model(**inputs).waveform[0].numpy()
    buf = io.BytesIO()
    scipy.io.wavfile.write(buf, model.config.sampling_rate, (wave * 32767).astype(np.int16))
    return Response(buf.getvalue(), media_type="audio/wav")
