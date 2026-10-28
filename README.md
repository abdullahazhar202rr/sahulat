# Sahulat · سہولت

**Government paperwork, in your own language.**
Sahulat is an Urdu-speaking AI agent, built on **Google Gemma 4**, that takes an ordinary Pakistani from *"I need a domicile"* to a **filled application form, an official document checklist and the right office**, without reading a single form themselves. People can also type in English.

> Built in 24 hours for **Hacktoberfest Hack Day — Sahiwal x Zeppelin Labs** (Oct 2026).

---

## The problem

- About **4 in 10 adults in Pakistan cannot read**. Government forms are in English and the rules change often.
- People pay agents outside offices **Rs 2,000–5,000** just to fill a form, and are often sent back for a missing paper.
- Existing tools (search portals, official apps) give **links**, not guidance, and assume the user can read.

## What Sahulat does

| Step | What happens |
|---|---|
| **Speak** | *"Meri beti ka domicile banwana hai"* ("I need my daughter's domicile"), using Urdu voice input or text |
| **Guided questions** | Gemma 4 asks one simple question at a time in Urdu (district, who it is for) |
| **Official checklist** | Documents, fee breakdown and steps, **from official sources, with links and a "checked on" date** |
| **Scan CNIC** | Gemma 4 reads the card photo and pulls out name, father's name, CNIC, date of birth and address |
| **Filled form** | A pre-filled domicile application opens, ready to correct, print or save as PDF |
| **Where to go** | e-Khidmat Markaz and Assistant Commissioner office for the user's district, plus an *Open in Google Maps* button |
| **Read aloud** | Urdu replies are spoken with **Meta's open MMS-TTS Urdu model**, self-hosted (`tts/server.py`) |

## How AI is used (Gemma 4)

- **Multimodal understanding.** Gemma 4 reads CNIC photos and returns structured JSON (`/api/read-document`).
- **Urdu conversation.** Gemma 4 understands Urdu, Roman Urdu and English, and replies in simple Urdu script.
- **Agent with tool calling.** Gemma 4 decides when to call `show_checklist`, `find_office` and `open_form` (`app/agent.py`). The UI shows these as cards.
- **Grounded answers.** Fees and documents come only from a curated **knowledge pack** (`knowledge/services.json`) built from official Punjab Government sources. The model is told never to invent them, and every answer shows its source.

## Privacy by design 

Reading someone's CNIC is sensitive, so Sahulat uses the fact that **Gemma 4 is open-weight**:

- **CNIC photos are read only by Gemma 4 on our own server** (Ollama, self-hosted). They are **never sent to Google** or any third party.
- Photos are processed in memory and **never written to disk**.
- The model only ever sees a **masked CNIC** (`36502-*******-3`) during the conversation. The full number stays in the user's browser and goes only into the printable form.
- **Hybrid mode** (default): chat uses Gemma 4 on the Gemini API. If the API is slow (over 15s) or down, Sahulat answers from self-hosted Gemma 4 instead. Documents never go to the API.
- **Private mode** runs the whole conversation on self-hosted Gemma 4.
- The office search sends **only the district name**, never personal data.

## Architecture

```
Browser (HTML/JS: chat, Urdu voice, camera, form)
   │
FastAPI server (app/main.py)
   ├── Agent (app/agent.py): Gemma 4 + tools + knowledge pack
   ├── Chat ─────────► Gemma 4 via Gemini API (Fast)  or  self-hosted Ollama (Private)
   └── CNIC reading ─► Gemma 4 E4B on self-hosted Ollama only (never cloud)
```

Open-source stack: **Gemma 4** (Apache 2.0), **Ollama**, **Meta MMS-TTS Urdu** (CC-BY-NC 4.0, used for this non-commercial demo), **FastAPI**, Web Speech API. The code is MIT.

## Setup

**Requirements:** Python 3.10+, [Ollama](https://ollama.com), and Chrome (for Urdu voice input).

```bash
git clone https://github.com/abdullahazhar202rr/sahulat.git
cd sahulat
pip install -r requirements.txt

# Self-hosted Gemma 4 (on this machine or your own server)
ollama pull gemma4:e4b

# Optional: Hybrid mode chat through the Gemini API
echo "GEMINI_API_KEY=your_key" > .env

python -m uvicorn app.main:app --port 8000
# open http://localhost:8000

# Optional: self-hosted Urdu voice
pip install -r tts/requirements.txt
cd tts && uvicorn server:app --port 8101
```

**Optional settings in `.env`:**

| Variable | Default | Meaning |
|---|---|---|
| `OLLAMA_URL` | `http://localhost:11434/v1` | Your self-hosted Gemma server, for example a VPS through an SSH tunnel |
| `LOCAL_MODEL` | `gemma4:e2b` | Use `gemma4:e4b` for better document reading |
| `CLOUD_MODEL` | `gemma-4-26b-a4b-it` | Gemma 4 model on the Gemini API |
| `GEMINI_API_KEY` | — | Only needed for Hybrid mode |
| `TTS_URL` | `http://localhost:8101/tts` | Self-hosted Urdu voice server (`tts/server.py`) |

A **fake sample CNIC** for testing is in `samples/sample_cnic.png`. Never test with a real card.

## Project structure

```
app/main.py               API: chat, document reading, static files
app/agent.py              Gemma 4 agent, tools, system prompt
app/llm.py                OpenAI-compatible client for Ollama and the Gemini API
knowledge/services.json   Official rules (documents, fees, steps, sources)
static/                   Web app (chat, voice, camera) and printable form
samples/                  Fake CNIC for testing
```

## Limitations and next steps

- Version 1 covers **Punjab domicile**. Next: CNIC renewal, BISP eligibility, birth certificate, police character certificate.
- Rules change. The knowledge pack shows a *checked on* date and asks users to confirm at the office.
- WhatsApp version: most target users already use WhatsApp voice notes.

## License

[MIT](LICENSE) © 2026 Abdullah Azhar
