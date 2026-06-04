from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from agents.budget_agent import budget_agent
from agents.planner_agent import planner_agent
from agents.recommendation_agent import recommendation_agent
from agents.route_agent import route_agent
from agents.state import TripState as BaseTripState
from agents.weather_agent import weather_agent


class TripState(BaseTripState):
    # The workflow state now explicitly carries the selected vehicle and route metadata.
    vehicle: dict[str, Any]
    route: dict[str, Any]
    pass


workflow = StateGraph(TripState)

workflow.add_node("planner", planner_agent)
workflow.add_node("route", route_agent)
workflow.add_node("weather", weather_agent)
workflow.add_node("budget", budget_agent)
workflow.add_node("recommendation", recommendation_agent)

workflow.set_entry_point("planner")
workflow.add_edge("planner", "route")
workflow.add_edge("route", "weather")
workflow.add_edge("weather", "budget")
workflow.add_edge("budget", "recommendation")
workflow.add_edge("recommendation", END)

trip_planner_graph = workflow.compile()
