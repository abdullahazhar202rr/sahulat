# How Sahulat works (plain language)

## In one sentence
Sahulat is a helper that speaks Urdu. It walks a person through getting a **domicile certificate**: it tells them what papers to bring, reads their ID card, fills the form and tells them where to go.

## Who it is for
People who find government paperwork hard: people who cannot read well, older people, villagers, and anyone who pays an agent to fill a form.

## What the user does
1. **Asks** in Urdu, Roman Urdu or English, by typing or speaking ("Meri beti ka domicile banwana hai").
2. **Sees the checklist**: 6 documents, the Rs 550 fee and how to pay it, with links to the official sources.
3. **Takes a photo of their CNIC.** Sahulat reads the name, father's name, CNIC number, date of birth and address.
4. **Opens the filled form**, fixes anything wrong and prints it or saves it as a PDF.
5. **Asks where to go.** Sahulat shows the e-Khidmat Markaz for their district, with a Google Maps button.
6. **Listens.** Urdu answers are read aloud.

The panel on the right shows progress: Service, Documents and fee, Your details, Filled form, Where to go.

## The parts and what each one does

| Part | What it is | Where it runs | File |
|---|---|---|---|
| The screen | The chat page the user sees | The user's browser | `static/index.html`, `static/app.js`, `static/style.css` |
| The form | The printable domicile application | The user's browser | `static/form.html` |
| The server | Receives messages and photos and decides what to do | Your Mac (very light) | `app/main.py` |
| The agent | Gives Gemma 4 its rules and tools, and builds the cards | Your Mac | `app/agent.py` |
| The Gemma connector | Talks to Gemma 4 on the VPS or on Google's API | Your Mac | `app/llm.py` |
| The knowledge pack | The official facts: documents, fee, steps, sources | A file | `knowledge/services.json` |
| Gemma 4 (E4B) | The AI model: understands Urdu, reads photos, chooses tools | **Your VPS** (Ollama) | — |
| Urdu voice | Turns Urdu text into speech (Meta MMS-TTS) | **Your VPS** | `tts/server.py` |

## What happens when the user sends a message
1. The browser sends the conversation to the server. It never sends the full CNIC number, only a masked one (`36502-*******-3`).
2. The agent adds Gemma's rules and the knowledge pack, then asks Gemma 4.
3. **Where Gemma runs:** first Google's Gemini API. If there is no answer within 15 seconds, it switches to Gemma 4 on your VPS automatically.
4. Gemma can use three **tools**:
   - **show_checklist**: documents and fee
   - **find_office**: where to apply
   - **open_form**: the filled form

   The app also shows these cards itself when the question is clearly about them, so they always appear.
5. The reply comes back in Urdu with the cards. If it is in Urdu, the voice server reads it aloud.

## What happens when the user scans a CNIC
1. The browser makes the photo smaller (faster to read).
2. The server sends it **only to Gemma 4 on your own VPS**, never to Google.
3. Gemma returns the details. The photo is **never saved**.
4. The details appear on screen with the CNIC masked, and the form fills in automatically.

## Privacy and safety
- CNIC photos are read only on your own server and never saved.
- The AI model only sees the masked CNIC.
- The office search sends only the district name.
- The app only accepts normal chat messages, so nobody can sneak in instructions that change Gemma's rules.
- Inputs have size limits, uploads must be photos, and error messages never show internal details.
- Answers about fees and documents come only from the knowledge pack. If something is not in it (for example, passports), Sahulat says it is not sure and to confirm at the office.

## How to run it (your setup)
On the **VPS** (already running):
- Ollama with Gemma 4 E4B on port 11434
- The Urdu voice server on port 8100

On the **Mac**:
```bash
# 1. Connect to the VPS (keeps reconnecting by itself)
"/Users/abdullahazhar/Desktop/Abdullah_Azhar/my vps/sahulat-tunnel.sh" &

# 2. Start the app
cd ~/Desktop/Abdullah_Azhar/sahulat
python3 -m uvicorn app.main:app --port 8000

# 3. Open http://localhost:8000 in Chrome
```

The `.env` file (never uploaded to GitHub) holds:
- `GEMINI_API_KEY`: your Google key, for chat
- `OLLAMA_URL=http://localhost:11435/v1`: Gemma on the VPS, through the tunnel
- `LOCAL_MODEL=gemma4:e4b`

## Speed (measured)

| Action | Time |
|---|---|
| Chat reply | 7–30 seconds (the very first one after a restart takes about 55 seconds) |
| CNIC reading | About 40 seconds |
| Urdu voice | About 3 seconds |

## Limits (be honest with judges)
- One service so far: **Punjab domicile**. CNIC renewal and BISP would be added the same way, as new entries in `knowledge/services.json`.
- Rules change, so every answer shows the source and a "checked on" date.
- It runs on a CPU-only server, so the AI is a little slow. On a server with a graphics card it would be about 10 times faster.
- Voice input uses Chrome's speech recognition.

## How to add a new service
Add an entry to `knowledge/services.json` with the documents, fee, steps, form fields and sources. The agent and checklist card use it automatically.
