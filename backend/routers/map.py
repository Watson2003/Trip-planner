from __future__ import annotations

import asyncio
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query, status

from agents.fallbacks import fallback_route
from models.schemas import GeoJsonRouteResponse
from utils.config import settings

router = APIRouter(tags=["map"])
ORS_BASE_URL = "https://api.openrouteservice.org"


async def _geocode_place(client: httpx.AsyncClient, place: str, api_key: str) -> list[float]:
    response = await client.get(
        f"{ORS_BASE_URL}/geocode/search",
        params={"api_key": api_key, "text": place, "boundary.country": "IN"},
        headers={"Authorization": api_key},
    )
    response.raise_for_status()
    payload = response.json()
    features = payload.get("features", [])
    if not features:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Could not geocode location: {place}")
    lon, lat = features[0]["geometry"]["coordinates"]
    return [lon, lat]


@router.get("/map/route", response_model=GeoJsonRouteResponse)
async def get_route(origin: str = Query(...), destination: str = Query(...)) -> dict[str, Any]:
    if not settings.openrouteservice_api_key:
        route = fallback_route(origin, destination, [])
        if route is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Could not build a route for {origin} to {destination}")
        return {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {},
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[lng, lat] for lat, lng in route["polyline"]],
                    },
                }
            ],
        }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            origin_coords, destination_coords = await asyncio.gather(
                asyncio.wait_for(_geocode_place(client, origin, settings.openrouteservice_api_key), timeout=4.0),
                asyncio.wait_for(_geocode_place(client, destination, settings.openrouteservice_api_key), timeout=4.0),
            )
            response = await asyncio.wait_for(
                client.post(
                    f"{ORS_BASE_URL}/v2/directions/driving-car/geojson",
                    headers={"Authorization": settings.openrouteservice_api_key},
                    json={"coordinates": [origin_coords, destination_coords]},
                ),
                timeout=8.0,
            )
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPStatusError as exc:
        route = fallback_route(origin, destination, [])
        if route is not None:
            return {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {},
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [[lng, lat] for lat, lng in route["polyline"]],
                        },
                    }
                ],
            }
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Route provider request failed") from exc
    except httpx.HTTPError as exc:
        route = fallback_route(origin, destination, [])
        if route is not None:
            return {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {},
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [[lng, lat] for lat, lng in route["polyline"]],
                        },
                    }
                ],
            }
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Route provider unavailable") from exc

    return payload
