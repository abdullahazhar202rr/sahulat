// Sahulat front end: chat, voice, document scan, cards and progress panel.
const $ = (s) => document.querySelector(s);
const chat = $("#chat");
const state = { history: [], voice: true, profile: null, shown: new Set() };

const isUrdu = (t) => /[؀-ۿ]/.test(t);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const icon = (n) => `<span class="ms">${n}</span>`;

function scrollDown() { chat.scrollTop = chat.scrollHeight; }

function bubble(role, text) {
  $(".welcome")?.remove();
  const el = document.createElement("div");
  el.className = `msg ${role}`;
  el.dir = "auto";
  el.textContent = text;
  chat.appendChild(el);
  scrollDown();
  return el;
}

function typing(label) {
  $(".welcome")?.remove();
  const el = document.createElement("div");
  el.className = "msg bot";
  el.innerHTML = `<span class="typing"><i></i><i></i><i></i>${esc(label)}</span>`;
  chat.appendChild(el);
  scrollDown();
  return el;
}

function card(ico, title, sub, badge, body) {
  const el = document.createElement("div");
  el.className = "card";
  el.innerHTML = `<div class="card-h"><span class="ico">${icon(ico)}</span><div><b>${title}</b>${sub ? `<small>${sub}</small>` : ""}</div>${badge ? `<span class="badge">${badge}</span>` : ""}</div>${body}`;
  chat.appendChild(el);
  scrollDown();
  return el;
}

// ---------- progress panel ----------
function step(name, text, done = true) {
  const li = document.querySelector(`[data-step="${name}"]`);
  if (!li) return;
  li.classList.toggle("done", done);
  li.classList.toggle("active", !done);
  $(`#s-${name}`).textContent = text;
}

// ---------- cards ----------
function renderCard(c) {
  if (c.type !== "form" && state.shown.has(c.type)) return;  // show each card once
  state.shown.add(c.type);
  if (c.type === "checklist") {
    const d = c.data;
    step("service", d.title_en);
    step("checklist", `${d.documents.length} documents · Rs ${d.fee.total_pkr}`);
    card("checklist", d.title_en, "Documents to bring", `${icon("verified")}Official sources`, `
      <ul>${d.documents.map((x) => `<li><input type="checkbox" aria-label="${esc(x.en)}"><div>${esc(x.en)}<small dir="rtl" class="ur">${esc(x.ur)}</small></div></li>`).join("")}</ul>
      <div class="fee">${icon("payments")}<div><b>Fee: Rs ${d.fee.total_pkr}</b> · ${esc(d.fee.breakdown)}. ${esc(d.fee.payment)}.</div></div>
      <div class="src">Sources: ${d.sources.map((s) => `<a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.name)}</a>`).join(" · ")}<br>Checked on ${esc(d.checked_on)}. ${esc(d.disclaimer)}</div>`);
  } else if (c.type === "office") {
    const o = c.data;
    step("office", o.name);
    card("location_on", "Where to apply", "Only your district was searched", null, `
      <div><b>${esc(o.name)}</b><br><small>${esc(o.also)}</small></div>
      <div class="src">${esc(o.tracking)}</div>
      <a class="btn" href="${esc(o.maps_url)}" target="_blank" rel="noopener">${icon("map")}Open in Google Maps</a>`);
  } else if (c.type === "form") {
    const f = { ...(state.profile || {}), ...c.data };
    sessionStorage.setItem("sahulat_form", JSON.stringify(f));
    step("form", "Ready to print");
    card("edit_document", "Your application is ready", "Review, correct anything, then print or save as PDF", `${icon("lock")}Filled in your browser`, `
      <a class="btn" href="form.html" target="_blank">${icon("open_in_new")}Open filled form</a>`);
  }
}

function renderProfile(r) {
  const f = r.fields;
  step("details", f.name ? `${f.name} · ${f.cnic_masked || ""}` : "Read");
  const rows = [["Name", f.name], ["Father name", f.father_name], ["CNIC", f.cnic_masked], ["Date of birth", f.date_of_birth], ["Address", f.address], ["District", f.district]];
  card("badge", "Details read from your CNIC", `Read in ${r.seconds}s`, `${icon("shield_lock")}Read on ${esc(r.processed_on)}`, `
    <dl>${rows.map(([k, v]) => `<dt>${k}</dt><dd>${esc(v || "—")}</dd>`).join("")}</dl>
    <div class="src">The photo was not saved. Your full CNIC number stays only in this browser.</div>`);
}

// ---------- talking to the agent ----------
async function send(text) {
  text = text.trim();
  if (!text) return;
  bubble("user", text);
  state.history.push({ role: "user", content: text });
  $("#text").value = "";
  const wait = typing("Gemma 4 is thinking");
  try {
    // The full CNIC number is never sent to the model.
    const profile = state.profile ? { ...state.profile, cnic: undefined } : null;
    const r = await fetch("/api/chat", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ history: state.history, profile }),
    });
    const data = await r.json();
    wait.remove();
    if (!r.ok) throw new Error(data.detail || "Something went wrong");
    (data.cards || []).forEach(renderCard);
    if (data.reply) {
      bubble("bot", data.reply);
      state.history.push({ role: "assistant", content: data.reply });
      speak(data.reply);
    }
  } catch (e) {
    wait.remove();
    bubble("bot", e.message);
  }
}

// Shrink photos before upload: faster on the model, same accuracy for ID cards.
function shrink(file, max = 640) {
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => {
      const s = Math.min(1, max / Math.max(img.width, img.height));
      const c = Object.assign(document.createElement("canvas"), { width: img.width * s, height: img.height * s });
      c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
      c.toBlob((b) => resolve(b || file), "image/jpeg", 0.9);
      URL.revokeObjectURL(img.src);
    };
    img.onerror = () => resolve(file);
    img.src = URL.createObjectURL(file);
  });
}

async function scan(file) {
  bubble("user", "Scanned my CNIC");
  step("details", "Reading…", false);
  const wait = typing("Reading your CNIC privately on our own server");
  const fd = new FormData();
  fd.append("file", await shrink(file), "cnic.jpg");
  try {
    const r = await fetch("/api/read-document", { method: "POST", body: fd });
    const data = await r.json();
    wait.remove();
    if (!r.ok) throw new Error(data.detail || "Could not read the document");
    state.profile = { ...(state.profile || {}), ...Object.fromEntries(Object.entries(data.fields).filter(([, v]) => v)) };
    renderProfile(data);
    renderCard({ type: "form", data: { service: "domicile_punjab", district: state.profile.district || "" } });
    send("I scanned my CNIC. Please continue.");
  } catch (e) {
    wait.remove();
    bubble("bot", e.message);
  }
}

// ---------- voice ----------
let player;
async function speak(text) {
  if (!state.voice) return;
  text = text.replace(/[*#_`]/g, "");
  player?.pause();
  if (isUrdu(text)) {
    // Urdu voice from our self-hosted open model (Meta MMS-TTS).
    try {
      const r = await fetch("/api/tts", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }) });
      if (r.ok) { player = new Audio(URL.createObjectURL(await r.blob())); player.play(); return; }
    } catch {}
  }
  if (!("speechSynthesis" in window)) return;
  speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.lang = "en-US";
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
document.querySelectorAll(".chip").forEach((b) => (b.onclick = () => (b.dataset.action === "scan" ? $("#photo").click() : send(b.dataset.say))));
$("#voiceBtn").onclick = () => {
  state.voice = !state.voice;
  $("#voiceBtn").innerHTML = state.voice ? `${icon("volume_up")}<span class="lbl">Voice on</span>` : `${icon("volume_off")}<span class="lbl">Voice off</span>`;
  if (!state.voice) { speechSynthesis.cancel(); player?.pause(); }
};
