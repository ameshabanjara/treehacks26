#!/usr/bin/env python3
import os
from typing import List, Dict, Optional
from fastmcp import FastMCP

mcp = FastMCP("Group Planner MCP")

@mcp.tool(description="Extract structured planning constraints from a chunk of group chat text.")
def extract_constraints(chat_text: str) -> Dict:
    # Keep it simple for hackathon: lightweight heuristics
    text = chat_text.lower()
    constraints = {
        "date": None,
        "time_window": None,
        "location_area": None,
        "party_size": None,
        "vibe": [],
        "budget": None,
        "dietary": [],
        "must_haves": [],
        "avoid": [],
    }

    # ultra-minimal examples (you can improve later)
    if "palo alto" in text: constraints["location_area"] = "Palo Alto"
    if "sf" in text or "san francisco" in text: constraints["location_area"] = "San Francisco"
    if "cheap" in text or "budget" in text: constraints["budget"] = "budget-friendly"
    if "vegan" in text: constraints["dietary"].append("vegan")
    if "gluten" in text: constraints["dietary"].append("gluten-free")

    return constraints

@mcp.tool(description="Generate an itinerary draft + a short poll question to confirm with the group.")
def propose_itinerary(constraints: Dict, options: Optional[List[Dict]] = None) -> Dict:
    # options could be restaurant candidates your teammate finds; keep optional
    area = constraints.get("location_area") or "near you"
    budget = constraints.get("budget") or "any"
    dietary = constraints.get("dietary") or []

    itinerary = [
        {"time": "6:30 PM", "item": f"Dinner reservation in {area}", "notes": f"budget: {budget}, dietary: {dietary}"},
        {"time": "8:00 PM", "item": "Dessert / boba nearby", "notes": "short walk, chill"},
        {"time": "8:45 PM", "item": "Optional: activity (walk / arcade / photo spot)", "notes": "flex depending on energy"},
    ]

    poll = "Reply 'confirm' if this looks good, or tell me what to change (time/place/vibe)."

    return {"itinerary": itinerary, "poll": poll}

@mcp.tool(description="Check if the plan is unanimously confirmed based on a list of participant confirmations.")
def is_unanimous_confirm(participants: List[str], confirms: List[str]) -> Dict:
    # confirms is list of names who have confirmed
    missing = [p for p in participants if p not in set(confirms)]
    return {"unanimous": len(missing) == 0, "missing": missing}

@mcp.tool(description="Create a calendar event payload once the plan is confirmed.")
def build_calendar_event(
    title: str,
    start_iso: str,
    end_iso: str,
    location: str,
    attendees_emails: List[str],
    description_lines: List[str],
) -> Dict:
    return {
        "title": title,
        "start_iso": start_iso,
        "end_iso": end_iso,
        "location": location,
        "attendees": attendees_emails,
        "description": "\n".join(description_lines),
    }

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    host = "0.0.0.0"
    print(f"Starting FastMCP server on {host}:{port}")
    mcp.run(transport="http", host=host, port=port, stateless_http=True)
