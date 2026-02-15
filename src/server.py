#!/usr/bin/env python3
import os
import re
import json
import uuid
import time
import urllib.parse
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Any, Tuple

from fastmcp import FastMCP

mcp = FastMCP("Group Planner MCP")

# -----------------------------
# Config / constants
# -----------------------------

FINAL_TAG = "[FINAL_TO_SEND]"
RESPONSE_TAG = "[GROUP_PLANNER_RESPONSE]"
DEFAULT_TZ = os.environ.get("DEFAULT_TZ", "America/Los_Angeles")  # informational only
BOOKING_WEBHOOK_URL = os.environ.get("BOOKING_WEBHOOK_URL")  # optional: teammate booking service
BOOKING_WEBHOOK_SECRET = os.environ.get("BOOKING_WEBHOOK_SECRET")  # optional auth header/token

# If you don't want persistence, leave as in-memory.
# For hackathon demo this is fine (single instance). If you scale, use Redis.
PLANS: Dict[str, Dict[str, Any]] = {}
BOOKING_JOBS: Dict[str, Dict[str, Any]] = {}

# -----------------------------
# Helpers
# -----------------------------

def _now_ts() -> float:
    return time.time()

def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"

def _safe_list(x: Any) -> List:
    if x is None:
        return []
    return x if isinstance(x, list) else [x]

def _dedup(items: List[str]) -> List[str]:
    seen = set()
    out = []
    for it in items:
        it2 = (it or "").strip()
        if not it2:
            continue
        if it2.lower() in seen:
            continue
        seen.add(it2.lower())
        out.append(it2)
    return out

def _extract_money(text: str) -> Optional[str]:
    # Rough: "$35", "under 40", "max 30"
    m = re.search(r"\$\s?(\d{1,3})", text)
    if m:
        return f"${m.group(1)}"
    m = re.search(r"(under|max|budget)\s+(\d{1,3})", text)
    if m:
        return f"<=${m.group(2)}"
    return None

def _extract_party_size(text: str) -> Optional[int]:
    # Rough: "we have 5", "party of 6", "6 ppl"
    m = re.search(r"(party of|we have|we're|we are|for)\s+(\d{1,2})", text)
    if m:
        try:
            return int(m.group(2))
        except Exception:
            return None
    m = re.search(r"(\d{1,2})\s*(people|ppl|friends|of us)", text)
    if m:
        try:
            return int(m.group(1))
        except Exception:
            return None
    return None

def _extract_time_window(text: str) -> Optional[str]:
    # Rough: "after 6:30", "7ish", "7:30", "between 7 and 8"
    # Return a human string; you can formalize later.
    t = text.lower()
    # Between X and Y
    m = re.search(r"between\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s+and\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", t)
    if m:
        a_h, a_m, a_ap = m.group(1), m.group(2) or "00", m.group(3) or ""
        b_h, b_m, b_ap = m.group(4), m.group(5) or "00", m.group(6) or ""
        return f"between {a_h}:{a_m}{a_ap} and {b_h}:{b_m}{b_ap}".strip()

    # After X
    m = re.search(r"after\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", t)
    if m:
        hh, mm, ap = m.group(1), m.group(2) or "00", m.group(3) or ""
        return f"after {hh}:{mm}{ap}".strip()

    # Exact time
    m = re.search(r"\b(\d{1,2})(?::(\d{2}))\s*(am|pm)\b", t)
    if m:
        return f"around {m.group(1)}:{m.group(2)}{m.group(3)}"
    m = re.search(r"\b(\d{1,2})\s*(am|pm)\b", t)
    if m:
        return f"around {m.group(1)}{m.group(2)}"

    # "7ish"
    m = re.search(r"\b(\d{1,2})\s*ish\b", t)
    if m:
        return f"around {m.group(1)}"

    return None

def _extract_date_hint(text: str) -> Optional[str]:
    t = text.lower()
    # Very rough: friday/sat/sunday/tomorrow
    for d in ["today", "tomorrow", "friday", "saturday", "sunday", "monday", "tuesday", "wednesday", "thursday"]:
        if d in t:
            return d.capitalize()
    # "Feb 20"
    m = re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s+(\d{1,2})\b", t)
    if m:
        return f"{m.group(1).capitalize()} {m.group(2)}"
    return None

def _extract_location(text: str) -> Optional[str]:
    t = text.lower()
    # Add your own hotspots
    if "palo alto" in t:
        return "Palo Alto"
    if "stanford" in t or "campus" in t:
        return "Near Stanford / campus"
    if "downtown" in t and "palo alto" in t:
        return "Downtown Palo Alto"
    if "sf" in t or "san francisco" in t:
        return "San Francisco"
    if "mission" in t:
        return "Mission (SF)"
    if "san jose" in t or "sj" in t:
        return "San Jose"
    return None

def _extract_dietary(text: str) -> Tuple[List[str], List[str]]:
    t = text.lower()
    dietary = []
    avoid = []

    # dietary flags
    if "vegetarian" in t or "veggie" in t:
        dietary.append("vegetarian")
    if "vegan" in t:
        dietary.append("vegan")
    if "gluten" in t:
        dietary.append("gluten-free")
    if "halal" in t:
        dietary.append("halal")
    if "kosher" in t:
        dietary.append("kosher")

    # avoid / allergies
    if "no shellfish" in t or "shellfish allergy" in t:
        avoid.append("shellfish")
    if "allergy" in t and "peanut" in t:
        avoid.append("peanuts")
    if "no sushi" in t:
        avoid.append("sushi")

    return _dedup(dietary), _dedup(avoid)

def _extract_vibe(text: str) -> List[str]:
    t = text.lower()
    vibe = []
    for key, tag in [
        ("cute", "cute"),
        ("cozy", "cozy"),
        ("chill", "chill"),
        ("lively", "lively"),
        ("quiet", "quiet"),
        ("not loud", "not too loud"),
        ("mid energy", "mid energy"),
        ("casual", "casual"),
        ("fancy", "fancy"),
        ("date night", "not date-night"),
        ("fun", "fun"),
    ]:
        if key in t:
            vibe.append(tag)
    return _dedup(vibe)

def _merge_constraints(base: Dict[str, Any], new: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base or {})
    for k, v in (new or {}).items():
        if v is None:
            continue
        if isinstance(v, list):
            out[k] = _dedup(_safe_list(out.get(k)) + v)
        else:
            out[k] = v
    return out

def _missing_fields(constraints: Dict[str, Any]) -> List[str]:
    required = ["date_hint", "time_window", "location_area", "party_size", "budget_hint"]
    missing = []
    for r in required:
        if not constraints.get(r):
            missing.append(r)
    return missing

def _make_relay(
    *,
    send: bool,
    target: str,
    text: str,
    request_id: Optional[str] = None,
    plan_id: Optional[str] = None,
    stage: Optional[str] = None,
) -> Dict[str, Any]:
    payload = {
        "send": bool(send),
        "target": target,  # "group" or "dm"
        "text": text,
    }
    if request_id:
        payload["request_id"] = request_id
    if plan_id:
        payload["plan_id"] = plan_id
    if stage:
        payload["stage"] = stage
    return payload

def _google_calendar_template_link(
    title: str,
    start_iso: str,
    end_iso: str,
    location: str,
    details: str,
) -> str:
    """
    Build a Google Calendar 'TEMPLATE' link.
    Google expects dates as YYYYMMDDTHHMMSSZ or local; we’ll accept ISO and best-effort strip.
    For hackathon: pass UTC-ish strings already if you can.
    """
    def normalize(dt: str) -> str:
        # Accept "2026-02-14T19:30:00Z" -> "20260214T193000Z"
        s = dt.strip()
        s = s.replace("-", "").replace(":", "")
        s = s.replace(".000", "")
        # Convert "YYYYMMDDTHHMMSSZ" already OK
        # Convert "YYYYMMDDTHHMMSS" -> append Z? leave as is
        return s

    dates = f"{normalize(start_iso)}/{normalize(end_iso)}"
    params = {
        "action": "TEMPLATE",
        "text": title,
        "dates": dates,
        "details": details,
        "location": location,
    }
    return "https://calendar.google.com/calendar/render?" + urllib.parse.urlencode(params, quote_via=urllib.parse.quote)

# Optional: lightweight HTTP post without external deps
def _post_json(url: str, data: Dict[str, Any], headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    import urllib.request
    req = urllib.request.Request(
        url=url,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            try:
                return {"ok": True, "status": resp.status, "body": json.loads(body)}
            except Exception:
                return {"ok": True, "status": resp.status, "body": body}
    except Exception as e:
        return {"ok": False, "error": str(e)}

# -----------------------------
# MCP tools
# -----------------------------

@mcp.tool(description="Extract structured planning constraints from a chunk of group chat transcript text.")
def extract_constraints(chat_text: str, plan_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Hackathon-friendly extraction:
    - lightweight heuristics (no LLM dependency)
    - merges into stored plan constraints if plan_id provided
    """
    text = chat_text or ""
    t = text.lower()

    found = {
        "date_hint": _extract_date_hint(text),
        "time_window": _extract_time_window(text),
        "location_area": _extract_location(text),
        "party_size": _extract_party_size(text),
        "budget_hint": _extract_money(t),
        "dietary": [],
        "avoid": [],
        "vibe": [],
        "must_haves": [],
    }

    dietary, avoid = _extract_dietary(text)
    found["dietary"] = dietary
    found["avoid"] = avoid
    found["vibe"] = _extract_vibe(text)

    # must-haves / avoid phrases
    if "walkable" in t:
        found["must_haves"].append("walkable")
    if "reservation" in t and "week" in t and "advance" in t:
        found["avoid"].append("hard to book")

    found["must_haves"] = _dedup(found["must_haves"])

    # plan management
    if not plan_id:
        plan_id = _new_id("plan")
        PLANS[plan_id] = {
            "plan_id": plan_id,
            "created_at": _now_ts(),
            "stage": "collecting",
            "constraints": {},
            "latest_transcript": "",
            "proposal": None,
            "reservation": None,
        }

    plan = PLANS.get(plan_id)
    if not plan:
        PLANS[plan_id] = {
            "plan_id": plan_id,
            "created_at": _now_ts(),
            "stage": "collecting",
            "constraints": {},
            "latest_transcript": "",
            "proposal": None,
            "reservation": None,
        }
        plan = PLANS[plan_id]

    plan["latest_transcript"] = text
    plan["constraints"] = _merge_constraints(plan.get("constraints", {}), found)

    constraints = plan["constraints"]
    missing = _missing_fields(constraints)

    # simple confidence: fraction of required fields present
    conf = 1.0 - (len(missing) / 5.0)

    return {
        "plan_id": plan_id,
        "constraints": constraints,
        "missing_fields": missing,
        "confidence": round(conf, 2),
        "stage": plan.get("stage", "collecting"),
    }

@mcp.tool(description="Generate an itinerary draft + a natural confirmation prompt to post back to the group chat.")
def propose_itinerary(
    plan_id: str,
    constraints: Optional[Dict[str, Any]] = None,
    restaurant_candidates: Optional[List[Dict[str, Any]]] = None,
    request_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Produces:
    - structured options (A/B)
    - group-friendly message with FINAL_TAG for Photon to forward
    """
    plan = PLANS.get(plan_id)
    if not plan:
        return {"error": f"Unknown plan_id: {plan_id}"}

    if constraints:
        plan["constraints"] = _merge_constraints(plan.get("constraints", {}), constraints)

    c = plan.get("constraints", {})
    missing = _missing_fields(c)
    if missing:
        # Ask naturally, not strict.
        questions = []
        if "date_hint" in missing:
            questions.append("what day are we thinking (e.g., Fri / Sat)?")
        if "time_window" in missing:
            questions.append("what time-ish (e.g., 7:30pm or after 7)?")
        if "location_area" in missing:
            questions.append("where should we keep it (campus / downtown PA / SF)?")
        if "party_size" in missing:
            questions.append("how many people should I plan for?")
        if "budget_hint" in missing:
            questions.append("what’s the rough budget per person?")

        ask = "quick qs so I can lock this in: " + " + ".join(questions[:3])
        relay_text = f"{FINAL_TAG}\n{RESPONSE_TAG}\nrequest_id={request_id or ''}\n{ask}"
        return {
            "plan_id": plan_id,
            "stage": "collecting",
            "relay": _make_relay(send=True, target="group", text=relay_text, request_id=request_id, plan_id=plan_id, stage="collecting"),
            "missing_fields": missing,
        }

    # Build 2 options; if candidates given, use them
    area = c.get("location_area") or "nearby"
    date_hint = c.get("date_hint") or "this week"
    time_window = c.get("time_window") or "evening"
    party_size = c.get("party_size") or 4
    budget = c.get("budget_hint") or "any"
    dietary = c.get("dietary") or []
    avoid = c.get("avoid") or []
    vibe = c.get("vibe") or []

    # Candidate formatting
    def fmt_place(p: Dict[str, Any], fallback_name: str) -> Tuple[str, str]:
        name = p.get("name") or fallback_name
        loc = p.get("address") or area
        notes = []
        if p.get("price"):
            notes.append(f"price: {p.get('price')}")
        if p.get("cuisine"):
            notes.append(str(p.get("cuisine")))
        return name, f"{loc}" + (f" ({', '.join(notes)})" if notes else "")

    candidates = restaurant_candidates or []
    # Two restaurant options
    if len(candidates) >= 2:
        a_name, a_loc = fmt_place(candidates[0], "Option A Restaurant")
        b_name, b_loc = fmt_place(candidates[1], "Option B Restaurant")
    elif len(candidates) == 1:
        a_name, a_loc = fmt_place(candidates[0], "Option A Restaurant")
        b_name, b_loc = ("Mediterranean spot", area)
    else:
        # generic
        a_name, a_loc = ("Mediterranean spot", f"{area}")
        b_name, b_loc = ("Italian spot", f"{area}")

    # Create structured proposal
    proposal_id = _new_id("prop")
    options = [
        {
            "id": "A",
            "dinner": {"name": a_name, "location": a_loc, "time": "7:30 PM"},
            "after": {"name": "Dessert / boba nearby", "time": "8:45 PM"},
        },
        {
            "id": "B",
            "dinner": {"name": b_name, "location": b_loc, "time": "7:45 PM"},
            "after": {"name": "Dessert / boba nearby", "time": "9:00 PM"},
        },
    ]

    plan["proposal"] = {
        "proposal_id": proposal_id,
        "created_at": _now_ts(),
        "options": options,
        "constraints_snapshot": c,
    }
    plan["stage"] = "proposed"

    # Natural confirmation ask
    meta_line = f"Context I’m optimizing for: {area}, {date_hint}, {time_window}, party ~{party_size}, budget {budget}"
    if dietary:
        meta_line += f", dietary: {', '.join(dietary)}"
    if avoid:
        meta_line += f", avoid: {', '.join(avoid)}"
    if vibe:
        meta_line += f", vibe: {', '.join(vibe)}"

    group_msg = (
        f"{FINAL_TAG}\n"
        f"{RESPONSE_TAG}\n"
        f"request_id={request_id or ''}\n"
        f"🍽️ ok i pulled two solid options — which vibe?\n\n"
        f"A) {options[0]['dinner']['name']} — {options[0]['dinner']['time']} ({options[0]['dinner']['location']})\n"
        f"   then {options[0]['after']['name']} around {options[0]['after']['time']}\n\n"
        f"B) {options[1]['dinner']['name']} — {options[1]['dinner']['time']} ({options[1]['dinner']['location']})\n"
        f"   then {options[1]['after']['name']} around {options[1]['after']['time']}\n\n"
        f"Just react / reply naturally (e.g., “A works”, “B”, “wait can we do 8”, “i can’t make it but y’all go”).\n"
        f"If nobody objects in a couple minutes, i’ll book.\n\n"
        f"({meta_line})"
    )

    return {
        "plan_id": plan_id,
        "proposal_id": proposal_id,
        "stage": "proposed",
        "options": options,
        "relay": _make_relay(send=True, target="group", text=group_msg, request_id=request_id, plan_id=plan_id, stage="proposed"),
    }

@mcp.tool(description="Detect if the group has reached a natural consensus (non-strict) from chat messages since the proposal.")
def detect_group_consensus(
    plan_id: str,
    messages_since_proposal: str,
    request_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Non-weird consensus detection (heuristics).
    Returns safe_to_book only when very confident and no recent objections.
    """
    plan = PLANS.get(plan_id)
    if not plan or not plan.get("proposal"):
        return {"error": "No active proposal for this plan_id"}

    text = (messages_since_proposal or "").strip()
    t = text.lower()

    # Basic signals
    objection_phrases = [
        "don't book", "do not book", "wait", "hold on", "stop", "change", "actually no",
        "not ok", "not okay", "i can't do", "cant do", "can't do", "no", "nah", "veto",
    ]
    soft_yes_phrases = [
        "sounds good", "down", "i'm in", "im in", "works", "fine", "ok", "okay", "yep",
        "let's do", "lets do", "go with", "lean", "i vote", "i like",
    ]
    cant_make_it_phrases = ["can't make", "cant make", "i can't", "i cant", "can't go", "cant go", "won't make", "not free"]
    go_ahead_phrases = ["y'all go", "you all go", "go ahead", "have fun", "it's fine", "im cool", "i'm cool", "all good"]

    # Option reference
    mentions_a = len(re.findall(r"\b(a)\b", t)) + len(re.findall(r"\boption a\b", t)) + len(re.findall(r"\ba works\b", t))
    mentions_b = len(re.findall(r"\b(b)\b", t)) + len(re.findall(r"\boption b\b", t)) + len(re.findall(r"\bb works\b", t))

    objections = []
    approvals = []
    cant_ok = []
    unknown = []

    # Very lightweight line parsing: one message per line
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    for ln in lines:
        l = ln.lower()

        if any(p in l for p in objection_phrases):
            objections.append(ln)
            continue

        is_cant = any(p in l for p in cant_make_it_phrases)
        is_goahead = any(p in l for p in go_ahead_phrases)

        if is_cant and is_goahead:
            cant_ok.append(ln)
            continue
        if is_cant and not is_goahead:
            # not blocking necessarily, but needs a follow-up
            unknown.append(ln)
            continue

        if any(p in l for p in soft_yes_phrases) or re.search(r"\b(a|b)\b", l):
            approvals.append(ln)
        else:
            unknown.append(ln)

    # Decide chosen option by mentions
    chosen = None
    if mentions_a > mentions_b and mentions_a >= 1:
        chosen = "A"
    elif mentions_b > mentions_a and mentions_b >= 1:
        chosen = "B"

    # Confidence scoring
    conf = 0.4
    if approvals:
        conf += min(0.4, 0.15 * len(approvals))
    if chosen:
        conf += 0.2
    if objections:
        conf = 0.1

    # Stage logic
    if objections:
        stage = "blocked"
        next_action = "ask_clarifying_q"
        safe_to_book = False
    else:
        if conf >= 0.85 and len(approvals) >= 2 and chosen is not None:
            stage = "confirmed"
            next_action = "safe_to_book"
            safe_to_book = True
        elif approvals or chosen:
            stage = "converging"
            next_action = "wait"
            safe_to_book = False
        else:
            stage = "collecting"
            next_action = "wait"
            safe_to_book = False

    relay = None
    if stage == "converging" and not safe_to_book:
        relay_text = (
            f"{FINAL_TAG}\n{RESPONSE_TAG}\nrequest_id={request_id or ''}\n"
            f"seems like we’re leaning {chosen or 'one of the options'} — any strong objections? "
            f"if not i’ll book in ~2 min."
        )
        relay = _make_relay(send=True, target="group", text=relay_text, request_id=request_id, plan_id=plan_id, stage=stage)

    if stage == "blocked":
        relay_text = (
            f"{FINAL_TAG}\n{RESPONSE_TAG}\nrequest_id={request_id or ''}\n"
            f"pause — i saw an objection. what should we change (time / place / budget / dietary)?"
        )
        relay = _make_relay(send=True, target="group", text=relay_text, request_id=request_id, plan_id=plan_id, stage=stage)

    return {
        "plan_id": plan_id,
        "stage": stage,
        "chosen_option": chosen,
        "confidence": round(conf, 2),
        "signals": {
            "approvals": approvals[:10],
            "objections": objections[:10],
            "cant_make_it_ok": cant_ok[:10],
            "unknown": unknown[:10],
        },
        "safe_to_book": safe_to_book,
        "next_action": next_action,
        "relay": relay,
    }

@mcp.tool(description="Dispatch a booking job to a teammate Browserbase/Stagehand service (OpenTable booking).")
def dispatch_booking_job(
    plan_id: str,
    chosen_option: str,
    request_id: Optional[str] = None,
    mode: str = "live",  # "live" or "simulate"
) -> Dict[str, Any]:
    """
    Creates a booking job payload. If BOOKING_WEBHOOK_URL is set and mode=live, POST it.
    Otherwise returns payload for your orchestrator to send.
    """
    plan = PLANS.get(plan_id)
    if not plan or not plan.get("proposal"):
        return {"error": "No active proposal for this plan_id"}

    proposal = plan["proposal"]
    opt = None
    for o in proposal.get("options", []):
        if o.get("id") == chosen_option:
            opt = o
            break
    if not opt:
        return {"error": f"Invalid chosen_option: {chosen_option}"}

    c = proposal.get("constraints_snapshot", plan.get("constraints", {}))
    job_id = _new_id("job")

    booking_payload = {
        "job_id": job_id,
        "plan_id": plan_id,
        "provider": "opentable",
        "reservation": {
            "date_hint": c.get("date_hint"),
            "time_pref": opt["dinner"]["time"],
            "party_size": c.get("party_size") or 4,
        },
        "venue_query": {
            "name": opt["dinner"]["name"],
            "area": c.get("location_area"),
            "budget_hint": c.get("budget_hint"),
            "dietary": c.get("dietary") or [],
            "avoid": c.get("avoid") or [],
            "vibe": c.get("vibe") or [],
        },
        "notes_for_agent": "Try the preferred time first, then +/- 30 minutes. Confirm name/address/time and return confirmation code.",
        "created_at": _now_ts(),
    }

    BOOKING_JOBS[job_id] = {
        "job_id": job_id,
        "plan_id": plan_id,
        "payload": booking_payload,
        "status": "created",
        "created_at": _now_ts(),
        "result": None,
    }

    posted = None
    if mode == "live" and BOOKING_WEBHOOK_URL:
        headers = {}
        if BOOKING_WEBHOOK_SECRET:
            headers["Authorization"] = f"Bearer {BOOKING_WEBHOOK_SECRET}"
        posted = _post_json(BOOKING_WEBHOOK_URL, booking_payload, headers=headers)
        BOOKING_JOBS[job_id]["status"] = "sent" if posted.get("ok") else "send_failed"
        BOOKING_JOBS[job_id]["post_result"] = posted

    plan["stage"] = "booking"

    relay_text = (
        f"{FINAL_TAG}\n{RESPONSE_TAG}\nrequest_id={request_id or ''}\n"
        f"ok booking Option {chosen_option} now — i’ll drop the confirmation here asap."
    )

    return {
        "plan_id": plan_id,
        "job_id": job_id,
        "stage": "booking",
        "booking_payload": booking_payload,
        "post_result": posted,
        "relay": _make_relay(send=True, target="group", text=relay_text, request_id=request_id, plan_id=plan_id, stage="booking"),
    }

@mcp.tool(description="Make a reservation using Browserbase/Stagehand to automate the OpenTable booking flow.")
def make_reservation(
    url: str,
    time_text: str,
    party_size: int,
    plan_id: Optional[str] = None,
    request_id: Optional[str] = None,
    job_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Uses Stagehand (via TypeScript script) to automate the OpenTable reservation flow.
    Requires: url (OpenTable restaurant page), time_text (e.g. "7:00 PM"), party_size.
    """
    import subprocess
    from pathlib import Path

    script_path = Path(__file__).parent.parent / "my-stagehand-app" / "index.ts"
    if not script_path.exists():
        return {"error": "Booking script not found", "success": False}

    booking_input = {"url": url, "time_text": time_text, "party_size": int(party_size)}

    try:
        result = subprocess.run(
            ["npx", "tsx", str(script_path)],
            input=json.dumps(booking_input),
            text=True,
            capture_output=True,
            timeout=120,
            env={**os.environ},
        )

        if result.returncode != 0:
            return {"error": result.stderr or result.stdout or "Unknown error", "success": False}

        # Parse JSON output from script (last line with {...})
        output_lines = result.stdout.strip().split("\n")
        json_output = None
        for line in reversed(output_lines):
            line = line.strip()
            if line.startswith("{") and line.endswith("}"):
                try:
                    json_output = json.loads(line)
                    break
                except json.JSONDecodeError:
                    continue

        if not json_output:
            return {
                "success": True,
                "message": "Reservation completed",
                "url": url,
                "time": time_text,
                "party_size": party_size,
            }

        conf = json_output.get("confirmation") or {}
        return {
            "success": True,
            "restaurant_name": conf.get("restaurant_name") if isinstance(conf, dict) else None,
            "confirmation_code": conf.get("confirmation_code") if isinstance(conf, dict) else None,
            "address": conf.get("address") if isinstance(conf, dict) else None,
            "time": time_text,
            "party_size": party_size,
            "raw": json_output,
        }
    except subprocess.TimeoutExpired:
        return {"error": "Booking timed out", "success": False}
    except Exception as e:
        return {"error": str(e), "success": False}

@mcp.tool(description="Finalize reservation details after Browserbase/Stagehand returns booking results.")
def finalize_reservation(
    plan_id: str,
    job_id: str,
    booking_result: Dict[str, Any],
    request_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    booking_result should include:
    - restaurant_name, address, time, party_size, confirmation_code, notes(optional)
    """
    plan = PLANS.get(plan_id)
    job = BOOKING_JOBS.get(job_id)
    if not plan:
        return {"error": f"Unknown plan_id: {plan_id}"}
    if not job:
        return {"error": f"Unknown job_id: {job_id}"}

    job["status"] = "completed"
    job["result"] = booking_result

    reservation = {
        "restaurant_name": booking_result.get("restaurant_name"),
        "address": booking_result.get("address"),
        "time": booking_result.get("time"),
        "party_size": booking_result.get("party_size"),
        "confirmation_code": booking_result.get("confirmation_code"),
        "notes": booking_result.get("notes"),
    }
    plan["reservation"] = reservation
    plan["stage"] = "booked"

    # Minimal confirmation (calendar link comes from build_calendar_event)
    relay_text = (
        f"{FINAL_TAG}\n{RESPONSE_TAG}\nrequest_id={request_id or ''}\n"
        f"✅ booked!\n"
        f"🍽️ {reservation.get('restaurant_name')}\n"
        f"📍 {reservation.get('address')}\n"
        f"🕒 {reservation.get('time')} (party of {reservation.get('party_size')})\n"
        f"🔐 confirmation: {reservation.get('confirmation_code') or '—'}\n"
        f"next: dropping calendar link."
    )

    return {
        "plan_id": plan_id,
        "job_id": job_id,
        "stage": "booked",
        "reservation": reservation,
        "relay": _make_relay(send=True, target="group", text=relay_text, request_id=request_id, plan_id=plan_id, stage="booked"),
    }

@mcp.tool(description="Build a calendar event payload + a 1-click Google Calendar link, and produce a final message to send to the group.")
def build_calendar_event(
    plan_id: str,
    title: Optional[str] = None,
    start_iso: Optional[str] = None,
    end_iso: Optional[str] = None,
    location: Optional[str] = None,
    description_lines: Optional[List[str]] = None,
    request_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    For hackathon: you can pass explicit start/end ISO strings.
    If omitted, we best-effort derive from stored proposal/reservation (very rough).
    """
    plan = PLANS.get(plan_id)
    if not plan:
        return {"error": f"Unknown plan_id: {plan_id}"}

    reservation = plan.get("reservation") or {}
    proposal = plan.get("proposal") or {}
    constraints = plan.get("constraints") or {}

    # Defaults
    title = title or f"Dinner Plan ({constraints.get('location_area') or 'Group'})"
    location = location or reservation.get("address") or (constraints.get("location_area") or "")

    details_lines = description_lines or []
    if reservation.get("restaurant_name"):
        details_lines.insert(0, f"Dinner: {reservation.get('restaurant_name')} — {reservation.get('time')}")
    if reservation.get("confirmation_code"):
        details_lines.append(f"Confirmation: {reservation.get('confirmation_code')}")
    if constraints.get("dietary"):
        details_lines.append(f"Dietary: {', '.join(constraints.get('dietary'))}")
    if constraints.get("budget_hint"):
        details_lines.append(f"Budget: {constraints.get('budget_hint')}")

    details = "\n".join(details_lines).strip()

    # If no start/end provided, we can’t truly infer date/time reliably from hints.
    # So for demo stability: require caller to pass start/end. We'll still allow best-effort placeholders.
    start_iso = start_iso or "2026-02-20T19:30:00Z"
    end_iso = end_iso or "2026-02-20T21:00:00Z"

    gcal_link = _google_calendar_template_link(
        title=title,
        start_iso=start_iso,
        end_iso=end_iso,
        location=location,
        details=details,
    )

    payload = {
        "title": title,
        "start_iso": start_iso,
        "end_iso": end_iso,
        "location": location,
        "description": details,
        "google_calendar_link": gcal_link,
    }

    plan["stage"] = "calendared"

    relay_text = (
        f"{FINAL_TAG}\n{RESPONSE_TAG}\nrequest_id={request_id or ''}\n"
        f"📅 add to calendar (1 click):\n{gcal_link}\n\n"
        f"summary:\n"
        f"🍽️ {reservation.get('restaurant_name') or 'Dinner'}\n"
        f"📍 {reservation.get('address') or location}\n"
        f"🕒 {reservation.get('time') or 'see link'}\n"
        f"🔐 {reservation.get('confirmation_code') or ''}".strip()
    )

    return {
        "plan_id": plan_id,
        "stage": "calendared",
        "calendar_event": payload,
        "relay": _make_relay(send=True, target="group", text=relay_text, request_id=request_id, plan_id=plan_id, stage="calendared"),
    }

@mcp.tool(description="Get current plan state (useful for debugging / recovery).")
def get_plan_state(plan_id: str) -> Dict[str, Any]:
    plan = PLANS.get(plan_id)
    if not plan:
        return {"error": f"Unknown plan_id: {plan_id}"}
    # Avoid dumping huge transcript
    out = dict(plan)
    out["latest_transcript"] = (out.get("latest_transcript") or "")[-1500:]
    return out

@mcp.tool(description="Reset plan state (for demo / if group changes their mind).")
def reset_plan(plan_id: str) -> Dict[str, Any]:
    if plan_id in PLANS:
        PLANS[plan_id]["stage"] = "collecting"
        PLANS[plan_id]["proposal"] = None
        PLANS[plan_id]["reservation"] = None
        return {"ok": True, "plan_id": plan_id}
    return {"error": f"Unknown plan_id: {plan_id}"}

# -----------------------------
# Server entrypoint
# -----------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    host = "0.0.0.0"
    print(f"Starting FastMCP server on {host}:{port}")
    # You said SSE is working for you; FastMCP transport modes can vary by version.
    # Keeping your prior approach:
    mcp.run(transport="http", host=host, port=port, stateless_http=True)