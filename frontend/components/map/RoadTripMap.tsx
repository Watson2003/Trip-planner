"use client";

import { useEffect } from "react";
import { MapContainer, Marker, Polyline, Popup, TileLayer } from "react-leaflet";
import L from "leaflet";

import type { RouteInfo } from "@/types";

const startIcon = new L.Icon({
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41],
});

export default function RoadTripMap({ route }: { route: RouteInfo }) {
  useEffect(() => {
    delete (L.Icon.Default.prototype as any)._getIconUrl;
    L.Icon.Default.mergeOptions({
      iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
      iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
      shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
    });
  }, []);

  const center = route.polyline[0] ?? [39.5, -98.35];

  return (
    <section className="rounded-3xl border border-white/70 bg-white/80 p-4 shadow-glow backdrop-blur-xl">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold">Route Map</h2>
          <p className="text-sm text-slate-500">
            {route.origin} to {route.destination}
          </p>
        </div>
        <div className="text-right text-sm text-slate-600">
          <div className="font-semibold">{route.distanceKm} km</div>
          <div>{route.durationHours} hours</div>
        </div>
      </div>
      <div className="h-64 overflow-hidden rounded-3xl border border-slate-200 sm:h-80 md:h-96 lg:h-[500px]">
        <MapContainer center={center as [number, number]} zoom={5} scrollWheelZoom={false} className="h-full w-full">
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          <Polyline positions={route.polyline as [number, number][]} pathOptions={{ color: "#0f172a", weight: 4 }} />
          {route.polyline.length > 0 && (
            <>
              <Marker position={route.polyline[0] as [number, number]} icon={startIcon}>
                <Popup>Start: {route.origin}</Popup>
              </Marker>
              <Marker
                position={route.polyline[route.polyline.length - 1] as [number, number]}
                icon={startIcon}
              >
                <Popup>End: {route.destination}</Popup>
              </Marker>
            </>
          )}
        </MapContainer>
      </div>
    </section>
  );
}
