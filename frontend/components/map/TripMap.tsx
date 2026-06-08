import dynamic from "next/dynamic";

import type { TripMarker } from "@/types";

type RouteGeoJSON = GeoJSON.FeatureCollection;

export interface TripMapProps {
  routeGeoJSON: RouteGeoJSON | null;
  markers: TripMarker[];
  focusPoint?: {
    lat: number;
    lng: number;
    zoom?: number;
  } | null;
}

const TripMap = dynamic<TripMapProps>(() => import("./TripMapClient"), {
  ssr: false,
  loading: () => (
    <div className="flex h-64 items-center justify-center rounded-3xl border border-dashed border-[#2a2a2a] bg-[#111111] text-[#888888] sm:h-80 md:h-96 lg:h-[500px]">
      Loading map...
    </div>
  ),
});

export default TripMap;
