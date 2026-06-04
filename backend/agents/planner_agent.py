from __future__ import annotations

import json
import re
import asyncio
from datetime import date
from typing import Any

from langchain_core.messages import HumanMessage

from agents.llm import get_llm
from agents.state import TripState


def _extract_json(text: str) -> dict[str, Any]:
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        return {}
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}


async def planner_agent(state: TripState) -> TripState:
    trip_state: TripState = dict(state)
    trip_state.setdefault("errors", [])
    trip_state["origin"] = (trip_state.get("origin") or "").strip()
    trip_state["destination"] = (trip_state.get("destination") or "").strip()
    trip_state["user_id"] = (trip_state.get("user_id") or "guest").strip() or "guest"
    trip_state["preferences"] = list(trip_state.get("preferences") or [])
    trip_state["waypoints"] = [waypoint.strip() for waypoint in (trip_state.get("waypoints") or []) if str(waypoint).strip()][:2]

    travel_dates = trip_state.get("travel_dates") or {}
    start_date = str(travel_dates.get("start") or "").strip()
    end_date = str(travel_dates.get("end") or "").strip()
    if not start_date or not end_date:
        today = date.today().isoformat()
        trip_state["travel_dates"] = {"start": start_date or today, "end": end_date or today}
    else:
        trip_state["travel_dates"] = {"start": start_date, "end": end_date}

    if trip_state["origin"] and trip_state["destination"]:
        trip_state["budget"] = float(trip_state.get("budget") or 0)
        return trip_state

    user_input = trip_state.get("user_input", "")
    llm = get_llm()
    prompt = (
        "You are an orchestration agent for a road trip planner.\n"
        "Extract origin, destination, travel dates, budget in INR, preferences, and up to 2 waypoints from the user request.\n"
        "Return ONLY valid JSON with keys: origin, destination, travel_dates, budget, preferences, waypoints, user_id.\n"
        "travel_dates should be an object with start and end in YYYY-MM-DD format when available.\n"
        "If a field is missing, use null or an empty list.\n"
        "User request:\n"
        f"{user_input}"
    )

    try:
        response = await asyncio.wait_for(asyncio.to_thread(llm.invoke, [HumanMessage(content=prompt)]), timeout=12.0)
        parsed = _extract_json(response.content)
        trip_state["origin"] = parsed.get("origin") or trip_state.get("origin") or ""
        trip_state["destination"] = parsed.get("destination") or trip_state.get("destination") or ""
        trip_state["travel_dates"] = parsed.get("travel_dates") or trip_state.get("travel_dates") or {}
        trip_state["budget"] = float(parsed.get("budget") or trip_state.get("budget") or 0)
        trip_state["preferences"] = parsed.get("preferences") or trip_state.get("preferences") or []
        trip_state["waypoints"] = (parsed.get("waypoints") or trip_state.get("waypoints") or [])[:2]
        trip_state["user_id"] = parsed.get("user_id") or trip_state.get("user_id") or "guest"
    except Exception:
        trip_state["budget"] = float(trip_state.get("budget") or 0)

    return trip_state
