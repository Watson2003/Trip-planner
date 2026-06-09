from __future__ import annotations

import importlib.util
from functools import lru_cache
from pathlib import Path
from typing import Any


@lru_cache(maxsize=1)
def _load_mcp_tools() -> Any:
    module_path = Path(__file__).resolve().parents[1] / "mcp" / "tools.py"
    spec = importlib.util.spec_from_file_location("road_trip_mcp_tools", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load MCP tools from {module_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def mcp_get_route(origin: str, destination: str, waypoints: list[str]) -> dict[str, Any]:
    module = _load_mcp_tools()
    return await module.get_route(origin=origin, destination=destination, waypoints=waypoints)


async def mcp_get_weather(location: str, days: int) -> dict[str, Any]:
    module = _load_mcp_tools()
    return await module.get_weather(location=location, days=days)


async def mcp_search_places(query: str, location: str, category: str) -> dict[str, Any]:
    module = _load_mcp_tools()
    return await module.search_places(query=query, location=location, category=category)


def mcp_calculate_fuel_cost(distance_km: float, fuel_efficiency_kmpl: float, fuel_price_per_litre: float) -> dict[str, float]:
    module = _load_mcp_tools()
    return module.calculate_fuel_cost(
        distance_km=distance_km,
        fuel_efficiency_kmpl=fuel_efficiency_kmpl,
        fuel_price_per_litre=fuel_price_per_litre,
    )


def mcp_generate_pdf_report(trip_data: dict[str, Any], output_path: str) -> dict[str, Any]:
    module = _load_mcp_tools()
    return module.generate_pdf_report(trip_data=trip_data, output_path=output_path)
