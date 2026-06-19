"use client";

import { useEffect, useMemo } from "react";

import L from "leaflet";
import { MapContainer, Marker, Popup, Polyline, TileLayer, useMap } from "react-leaflet";

import type { TripMapProps } from "@/components/map/TripMap";
import type { TripMarker } from "@/types";

const COLORS: Record<TripMarker["type"], string> = {
  origin: "#0071e3",
  destination: "#ffffff",
  waypoint: "#94a3b8",
};

function createMarkerIcon(type: TripMarker["type"], label: string) {
  const accent = COLORS[type];
  return L.divIcon({
    className: "trip-marker-icon",
    html: `
      <div style="
        width: 36px;
        height: 36px;
        border-radius: 9999px;
        background: ${accent};
        border: 3px solid rgba(255,255,255,0.95);
        box-shadow: 0 12px 30px rgba(15, 23, 42, 0.12);
        display: flex;
        align-items: center;
        justify-content: center;
        color: white;
        font-size: 10px;
        font-weight: 800;
        letter-spacing: 0.06em;
        text-transform: uppercase;
      ">
        ${label.slice(0, 1)}
      </div>
    `,
    iconSize: [36, 36],
    iconAnchor: [18, 36],
    popupAnchor: [0, -30],
  });
}

function FitBounds({ routeGeoJSON, markers, focusPoint }: TripMapProps) {
  const map = useMap();

  useEffect(() => {
    const timer = window.setTimeout(() => {
      map.invalidateSize(true);
    }, 50);

    if (focusPoint) {
      map.flyTo([focusPoint.lat, focusPoint.lng], focusPoint.zoom ?? 10, {
        animate: true,
        duration: 0.9,
      });
      return () => window.clearTimeout(timer);
    }

    const bounds = L.latLngBounds([]);

    const append = (lat: number, lng: number) => {
      if (Number.isFinite(lat) && Number.isFinite(lng)) {
        bounds.extend([lat, lng]);
      }
    };

    routeGeoJSON?.features?.forEach((feature) => {
      if (feature.geometry.type === "LineString") {
        feature.geometry.coordinates.forEach(([lng, lat]) => append(lat, lng));
      }
    });

    markers.forEach((marker) => append(marker.lat, marker.lng));

    if (bounds.isValid()) {
      map.fitBounds(bounds.pad(0.18), { animate: true, duration: 0.7 });
    }

    return () => window.clearTimeout(timer);
  }, [focusPoint, map, markers, routeGeoJSON]);

  return null;
}

export default function TripMapClient({ routeGeoJSON, markers, focusPoint }: TripMapProps) {
  const mapKey = useMemo(() => {
    const feature = routeGeoJSON?.features?.find((item) => item.geometry.type === "LineString") as
      | GeoJSON.Feature<GeoJSON.LineString>
      | undefined;
    const routeSignature = feature?.geometry.coordinates
      .slice(0, 2)
      .map(([lng, lat]) => `${lat},${lng}`)
      .join("|");
    const markerSignature = markers.map((marker) => `${marker.type}:${marker.label}:${marker.lat},${marker.lng}`).join("|");
    return [routeSignature || "no-route", markerSignature || "no-markers", focusPoint ? `${focusPoint.lat},${focusPoint.lng},${focusPoint.zoom ?? 0}` : "no-focus"].join("::");
  }, [focusPoint, markers, routeGeoJSON]);

  const positions = useMemo<[number, number][]>(() => {
    const feature = routeGeoJSON?.features?.find((item) => item.geometry.type === "LineString") as
      | GeoJSON.Feature<GeoJSON.LineString>
      | undefined;
    const routePositions =
      feature?.geometry.coordinates.map(([lng, lat]) => [lat, lng] as [number, number]) ?? [];
    if (routePositions.length > 1) {
      return routePositions;
    }
    if (markers.length > 1) {
      return markers.map((marker) => [marker.lat, marker.lng] as [number, number]);
    }
    return [];
  }, [markers, routeGeoJSON]);

  const center = useMemo<[number, number]>(() => {
    if (focusPoint) return [focusPoint.lat, focusPoint.lng];
    if (positions[0]) return positions[0];
    if (markers[0]) return [markers[0].lat, markers[0].lng];
    return [20.5937, 78.9629];
  }, [focusPoint, markers, positions]);

  return (
    <section className="overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-xl">
      <div className="flex items-center justify-between gap-3 border-b border-slate-200 px-5 py-4 text-slate-950">
        <div>
          <p className="text-xs uppercase tracking-[0.24em] text-slate-500">Route</p>
          <h2 className="text-lg font-semibold">Interactive Trip Map</h2>
        </div>
        <p className="text-sm text-slate-500">Drag, zoom, and inspect every stop.</p>
      </div>
      <div className="h-64 w-full sm:h-80 md:h-96 lg:h-[500px]">
        <MapContainer key={mapKey} center={center} zoom={6} scrollWheelZoom className="h-full w-full">
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          {positions.length > 1 && (
            <Polyline
              positions={positions}
              pathOptions={{
                color: "#0071e3",
                weight: 6,
                opacity: 0.95,
                lineCap: "round",
                lineJoin: "round",
              }}
            />
          )}
          {markers.map((marker) => (
            <Marker
              key={`${marker.type}-${marker.label}-${marker.lat}-${marker.lng}`}
              position={[marker.lat, marker.lng]}
              icon={createMarkerIcon(marker.type, marker.label)}
            >
              <Popup>
                <div className="space-y-1 text-slate-950">
                  <div className="text-sm font-semibold">{marker.label}</div>
                  <div className="text-xs uppercase tracking-[0.18em] text-slate-500">{marker.type}</div>
                  <div className="text-sm text-slate-600">{marker.eta ?? "ETA unavailable"}</div>
                </div>
              </Popup>
            </Marker>
          ))}
          <FitBounds routeGeoJSON={routeGeoJSON} markers={markers} focusPoint={focusPoint ?? null} />
        </MapContainer>
      </div>
    </section>
  );
}
