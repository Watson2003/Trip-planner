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
    <div className="flex h-[72vh] min-h-[540px] items-center justify-center rounded-3xl border border-dashed border-slate-300 bg-white/70 text-slate-500">
      Loading map...
    </div>
  ),
});

export default TripMap;
