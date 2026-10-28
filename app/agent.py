"""Sahulat agent: Gemma 4 + a few tools, grounded in the official knowledge pack."""
import json
from pathlib import Path
from urllib.parse import quote_plus

from . import llm

KNOWLEDGE = json.loads((Path(__file__).resolve().parent.parent / "knowledge" / "services.json").read_text())

SYSTEM = f"""You are Sahulat, a kind helper that guides ordinary Pakistanis through government paperwork.
Many users cannot read well, so:
- Reply in the user's language. If they write Urdu or Roman Urdu, reply in simple Urdu script.
- Keep every reply short: 2-4 short sentences. Ask only ONE question at a time.
- Use ONLY the facts in the knowledge pack below. Never invent fees, documents or offices.
  If something is not in the pack, say you are not sure and they should confirm at the office.
- To fill the form you need: who it is for, their district, and their CNIC details.
  Suggest they scan their CNIC with the camera button; the photo stays on their device.
- Call show_checklist when the user knows which service they need.
- Call find_office when they ask where to go, once you know their district.
- Call open_form when you have their district and CNIC details.
- When you call a tool, ALSO write your short reply to the user in the same message.

KNOWLEDGE PACK:
{json.dumps(KNOWLEDGE, ensure_ascii=False)}
"""

TOOLS = [
    {"type": "function", "function": {
        "name": "show_checklist",
        "description": "Show the official document checklist, fee and steps for a service.",
        "parameters": {"type": "object", "properties": {
            "service": {"type": "string", "enum": list(KNOWLEDGE)}}, "required": ["service"]}}},
    {"type": "function", "function": {
        "name": "find_office",
        "description": "Find where to apply in a district.",
        "parameters": {"type": "object", "properties": {
            "district": {"type": "string"}}, "required": ["district"]}}},
    {"type": "function", "function": {
        "name": "open_form",
        "description": "Open the pre-filled application form for the user to review and print.",
        "parameters": {"type": "object", "properties": {
            "service": {"type": "string", "enum": list(KNOWLEDGE)},
            "district": {"type": "string"},
            "purpose": {"type": "string"}}, "required": ["service"]}}},
]


def run_tool(name, args):
    """Execute a tool. Returns (result for the model, card for the UI)."""
    if name == "show_checklist":
        svc = KNOWLEDGE.get(args.get("service"), next(iter(KNOWLEDGE.values())))
        card = {"type": "checklist", "service": args.get("service"), "data": svc}
        return {"documents": [d["en"] for d in svc["documents"]], "fee": svc["fee"]["breakdown"]}, card
    if name == "find_office":
        # Only the district name is used here - never personal data.
        district = args.get("district", "").strip() or "Punjab"
        office = {
            "name": f"e-Khidmat Markaz, {district}",
            "also": f"Assistant Commissioner Office (Domicile Branch), {district}",
            "maps_url": f"https://www.google.com/maps/search/{quote_plus('e-Khidmat Markaz ' + district)}",
            "tracking": "Keep your tracking ID and check status on the e-Khidmat website or app.",
        }
        return office, {"type": "office", "data": office}
    if name == "open_form":
        return {"status": "form opened for review"}, {"type": "form", "data": args}
    return {"error": "unknown tool"}, None


def respond(history, mode="local", profile=None):
    """history: list of {role, content}. profile: details read from the user's documents."""
    sys = SYSTEM
    if profile:
        # Masked view only - the model never needs the full CNIC number.
        safe = {k: v for k, v in profile.items() if k != "cnic"}
        safe["cnic_masked"] = profile.get("cnic_masked")
        sys += f"\nDETAILS ALREADY READ FROM THE USER'S CNIC: {json.dumps(safe, ensure_ascii=False)}"
        sys += ("\nYou ALREADY KNOW their details and district. Do NOT ask for them again. "
                "Tell them their domicile form is filled and ready to print, then offer to show where to apply.")
    messages = [{"role": "system", "content": sys}] + history
    cards = []
    # Make the key cards reliable even when a small model skips the tool call.
    last = (history[-1].get("content") or "").lower() if history else ""
    if any(w in last for w in ("domicile", "ڈومیسائل", "documents", "kaghaz", "کاغذ", "fee", "فیس")):
        cards.append(run_tool("show_checklist", {"service": "domicile_punjab"})[1])
    district = next((d for d in ("sahiwal", "lahore", "okara", "pakpattan", "multan", "faisalabad") if d in last), None)
    if profile and any(w in last for w in ("form", "فارم", "bhar", "بھر")):
        cards.append(run_tool("open_form", {"service": "domicile_punjab", "district": profile.get("district", "")})[1])
    if district and any(w in last for w in ("office", "daftar", "kahan", "کہاں", "دفتر", "where")):
        cards.append(run_tool("find_office", {"district": district.title()})[1])
    for _ in range(4):
        try:
            msg = llm.chat(messages, mode=mode, tools=TOOLS)
        except Exception:
            if mode == "local":
                raise
            mode = "local"  # Gemini API busy: fall back to our own Gemma server
            msg = llm.chat(messages, mode=mode, tools=TOOLS)
        calls = msg.get("tool_calls") or []
        if not calls:
            return {"reply": (msg.get("content") or "").strip(), "cards": cards}
        messages.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
        for c in calls:
            fn = c["function"]
            args = fn.get("arguments") or "{}"
            args = json.loads(args) if isinstance(args, str) else args
            result, card = run_tool(fn["name"], args)
            if card:
                cards.append(card)
            messages.append({"role": "tool", "tool_call_id": c.get("id", fn["name"]),
                             "content": json.dumps(result, ensure_ascii=False)})
        if (msg.get("content") or "").strip():
            # Gemma already wrote its reply with the tool call: skip a second slow round trip.
            return {"reply": msg["content"].strip(), "cards": cards}
    # Too many tool rounds: ask for a plain answer.
    msg = llm.chat(messages, mode=mode)
    return {"reply": (msg.get("content") or "").strip(), "cards": cards}
