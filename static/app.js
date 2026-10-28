// Sahulat front end: chat, voice, document scan and cards.
const $ = (s) => document.querySelector(s);
const chat = $("#chat");
const state = { history: [], mode: "cloud", voice: true, profile: null };

const isUrdu = (t) => /[؀-ۿ]/.test(t);

function bubble(role, text) {
  $(".welcome")?.remove();
  const el = document.createElement("div");
  el.className = `msg ${role}`;
  el.dir = "auto";
  el.textContent = text;
  chat.appendChild(el);
  chat.scrollTop = chat.scrollHeight;
  return el;
}

function card(html) {
  const el = document.createElement("div");
  el.className = "card";
  el.innerHTML = html;
  chat.appendChild(el);
  chat.scrollTop = chat.scrollHeight;
  return el;
}

const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

// ---------- cards ----------
function renderCard(c) {
  if (c.type === "checklist") {
    const d = c.data;
    card(`
      <h3>📋 ${esc(d.title_en)} <span class="tag">Official checklist</span></h3>
      <ul>${d.documents.map((x) => `<li><input type="checkbox"><div>${esc(x.en)}<small dir="rtl" class="ur">${esc(x.ur)}</small></div></li>`).join("")}</ul>
      <div class="fee">💰 <b>Fee: Rs ${d.fee.total_pkr}</b> — ${esc(d.fee.breakdown)}. ${esc(d.fee.payment)}.</div>
      <div class="src">Source: ${d.sources.map((s) => `<a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.name)}</a>`).join(" · ")}<br>Checked on ${esc(d.checked_on)}. ${esc(d.disclaimer)}</div>`);
  } else if (c.type === "office") {
    const o = c.data;
    card(`
      <h3>📍 Where to apply <span class="tag">Only your district was searched</span></h3>
      <div><b>${esc(o.name)}</b><br><small>${esc(o.also)}</small></div>
      <div class="src">${esc(o.tracking)}</div>
      <a class="btn" href="${esc(o.maps_url)}" target="_blank" rel="noopener">Open in Google Maps</a>`);
  } else if (c.type === "form") {
    const f = { ...(state.profile || {}), ...c.data };
    sessionStorage.setItem("sahulat_form", JSON.stringify(f));
    card(`
      <h3>📝 Your application is ready <span class="tag">Filled on this device</span></h3>
      <div>Review it, correct anything, then print or save as PDF.</div>
      <a class="btn" href="form.html" target="_blank">Open filled form</a>`);
  }
}

function renderProfile(r) {
  const f = r.fields;
  const rows = [["Name", f.name], ["Father name", f.father_name], ["CNIC", f.cnic_masked || "—"], ["Date of birth", f.date_of_birth], ["Address", f.address], ["District", f.district]];
  card(`
    <h3>🪪 Details read from your document <span class="tag">🔒 Read on ${esc(r.processed_on)} in ${r.seconds}s</span></h3>
    <dl>${rows.map(([k, v]) => `<dt>${k}</dt><dd>${esc(v || "—")}</dd>`).join("")}</dl>
    <div class="src">The photo was not saved anywhere. Your full CNIC number stays only in this browser.</div>`);
}

// ---------- talking to the agent ----------
async function send(text) {
  text = text.trim();
  if (!text) return;
  bubble("user", text);
  state.history.push({ role: "user", content: text });
  $("#text").value = "";
  const wait = bubble("bot typing", "Sahulat is thinking…");
  try {
    // The full CNIC number is never sent to the model.
    const profile = state.profile ? { ...state.profile, cnic: undefined } : null;
    const r = await fetch("/api/chat", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ history: state.history, mode: state.mode, profile }),
    });
    const data = await r.json();
    wait.remove();
    if (!r.ok) throw new Error(data.detail || "error");
    (data.cards || []).forEach(renderCard);
    if (data.reply) {
      bubble("bot", data.reply);
      state.history.push({ role: "assistant", content: data.reply });
      speak(data.reply);
    }
  } catch (e) {
    wait.remove();
    bubble("bot", "⚠️ " + e.message);
  }
}

async function scan(file) {
  bubble("user", "📷 Scanned a document");
  const wait = bubble("bot typing", "Reading your document privately on our own server… (about 1 minute)");
  const fd = new FormData();
  fd.append("file", file);
  try {
    const r = await fetch("/api/read-document", { method: "POST", body: fd });
    const data = await r.json();
    wait.remove();
    if (!r.ok) throw new Error(data.detail || "error");
    state.profile = { ...(state.profile || {}), ...Object.fromEntries(Object.entries(data.fields).filter(([, v]) => v)) };
    renderProfile(data);
    send("I scanned my CNIC. Please continue.");
  } catch (e) {
    wait.remove();
    bubble("bot", "⚠️ " + e.message);
  }
}

// ---------- voice ----------
function speak(text) {
  if (!state.voice || !("speechSynthesis" in window)) return;
  speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text.replace(/[*#_`]/g, ""));
  const lang = isUrdu(text) ? "ur" : "en";
  const v = speechSynthesis.getVoices().find((x) => x.lang.toLowerCase().startsWith(lang));
  if (v) u.voice = v;
  u.lang = lang === "ur" ? "ur-PK" : "en-US";
  speechSynthesis.speak(u);
}

const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
$("#micBtn").onclick = () => {
  if (!SR) return bubble("bot", "Voice input needs Google Chrome.");
  const rec = new SR();
  rec.lang = "ur-PK";
  rec.interimResults = false;
  $("#micBtn").classList.add("live");
  rec.onresult = (e) => send(e.results[0][0].transcript);
  rec.onend = () => $("#micBtn").classList.remove("live");
  rec.start();
};

// ---------- controls ----------
$("#sendBtn").onclick = () => send($("#text").value);
$("#text").onkeydown = (e) => e.key === "Enter" && send($("#text").value);
$("#camBtn").onclick = () => $("#photo").click();
$("#photo").onchange = (e) => e.target.files[0] && scan(e.target.files[0]);
document.querySelectorAll(".chip").forEach((b) => (b.onclick = () => send(b.textContent)));
$("#voiceBtn").onclick = () => {
  state.voice = !state.voice;
  $("#voiceBtn").textContent = state.voice ? "🔊 Voice on" : "🔇 Voice off";
  if (!state.voice) speechSynthesis.cancel();
};
document.querySelectorAll(".mode button").forEach((b) => (b.onclick = () => {
  state.mode = b.dataset.mode;
  document.querySelectorAll(".mode button").forEach((x) => x.classList.toggle("on", x === b));
  const p = $("#privacy");
  
  p.textContent = state.mode === "local"
    ? "🔒 Private: everything runs on Gemma 4 on our own server. Nothing goes to Google."
    : "⚡ Chat: Gemma 4 on the Gemini API. 🔒 CNIC photos: Gemma 4 on our own server, never sent to Google.";
}));
