"use client";

import { useMemo } from "react";

import L from "leaflet";
import { MapContainer, Marker, TileLayer } from "react-leaflet";

function createMarkerIcon() {
  return L.divIcon({
    className: "place-mini-map-marker",
    html: `
      <div style="
        width: 22px;
        height: 22px;
        border-radius: 9999px;
        background: #D4AF37;
        border: 3px solid rgba(212,175,55,0.95);
        box-shadow: 0 10px 22px rgba(15, 23, 42, 0.35);
      "></div>
    `,
    iconSize: [22, 22],
    iconAnchor: [11, 11],
  });
}

export default function PlaceMiniMap({ lat, lng }: { lat: number; lng: number }) {
  const center = useMemo<[number, number]>(() => [lat, lng], [lat, lng]);

  return (
    <div className="h-[200px] w-full overflow-hidden rounded-2xl border border-[#1a1a1a] bg-[#0a0a0a] sm:h-[250px]">
      <MapContainer
        center={center}
        zoom={15}
        zoomControl
        scrollWheelZoom={false}
        dragging={false}
        doubleClickZoom={false}
        touchZoom={false}
        keyboard={false}
        className="h-full w-full"
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <Marker position={center} icon={createMarkerIcon()} />
      </MapContainer>
    </div>
  );
}
