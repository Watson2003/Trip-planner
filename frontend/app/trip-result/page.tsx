"use client";

import { useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import { ArrowDownToLine, ArrowRight, Sparkles } from "lucide-react";
import { useRouter } from "next/navigation";

import Navbar from "@/components/auth/Navbar";
import BudgetBreakdown from "@/components/budget/BudgetBreakdown";
import TravelChat from "@/components/chat/TravelChat";
import RecommendationCards from "@/components/recommendations/RecommendationCards";
import TripMap from "@/components/map/TripMap";
import WeatherPanel from "@/components/weather/WeatherPanel";
import TripSummaryCard from "@/components/trip/TripSummaryCard";
import { API_BASE_URL } from "@/lib/api";
import { getAuthHeaders } from "@/lib/auth";
import { loadStoredTripResult, normalizeDestinationKey, normalizeRecommendations, type TripResultStorage } from "@/lib/trip-result";
import type { FullItinerary, TripMarker, VehicleDetails } from "@/types";

function formatDuration(hours: number) {
  const totalMinutes = Math.max(0, Math.round(hours * 60));
  const wholeHours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  if (wholeHours === 0) return `${minutes} min`;
  if (minutes === 0) return `${wholeHours} hr`;
  return `${wholeHours} hr ${minutes} min`;
}

function safeString(value: unknown, fallback = "") {
  return typeof value === "string" ? value : fallback;
}

function safeNumber(value: unknown, fallback = 0) {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function sanitizeFilenamePart(value: string) {
  return value
    .trim()
    .replace(/[\u2018\u2019`'"]/g, "")
    .replace(/[^a-z0-9]+/gi, "_")
    .replace(/^_+|_+$/g, "");
}

function getPdfFilename(response: Response, fallbackName: string) {
  const contentDisposition = response.headers.get("content-disposition") ?? response.headers.get("Content-Disposition") ?? "";
  const match = contentDisposition.match(/filename\*=(?:UTF-8''|)([^;]+)|filename="?([^";]+)"?/i);
  const rawFilename = match?.[1] || match?.[2];
  const decoded = rawFilename ? decodeURIComponent(rawFilename.trim().replace(/^"|"$/g, "")) : "";
  return decoded || fallbackName;
}

function normalizeRoutePoint(point: unknown): [number, number] | null {
  if (!Array.isArray(point) || point.length < 2) return null;
  const [lat, lng] = point;
  if (typeof lat !== "number" || typeof lng !== "number") return null;
  if (!Number.isFinite(lat) || !Number.isFinite(lng)) return null;
  return [lat, lng];
}

function haversineDistanceKm(lat1: number, lon1: number, lat2: number, lon2: number) {
  const toRad = (value: number) => (value * Math.PI) / 180;
  const earthRadiusKm = 6371;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
  return 2 * earthRadiusKm * Math.asin(Math.sqrt(a));
}

function estimateRouteDistanceKm(routeGeoJSON: GeoJSON.FeatureCollection | null) {
  if (!routeGeoJSON) return 0;
  let total = 0;
  for (const feature of routeGeoJSON.features ?? []) {
    if (feature.geometry.type !== "LineString") continue;
    const coordinates = feature.geometry.coordinates;
    for (let index = 1; index < coordinates.length; index += 1) {
      const previous = coordinates[index - 1];
      const current = coordinates[index];
      if (!Array.isArray(previous) || !Array.isArray(current)) continue;
      const [prevLon, prevLat] = previous;
      const [currLon, currLat] = current;
      if (
        typeof prevLat !== "number" ||
        typeof prevLon !== "number" ||
        typeof currLat !== "number" ||
        typeof currLon !== "number" ||
        !Number.isFinite(prevLat) ||
        !Number.isFinite(prevLon) ||
        !Number.isFinite(currLat) ||
        !Number.isFinite(currLon)
      ) {
        continue;
      }
      total += haversineDistanceKm(prevLat, prevLon, currLat, currLon);
    }
  }
  return Math.round(total * 100) / 100;
}

function estimateRouteDurationHours(distanceKm: number) {
  if (!Number.isFinite(distanceKm) || distanceKm <= 0) return 0;
  const averageSpeedKmh = 45;
  return Math.round((distanceKm / averageSpeedKmh) * 100) / 100;
}

function buildMarkersFromRoute(
  routeGeoJSON: GeoJSON.FeatureCollection | null,
  origin: string,
  destination: string,
  existingMarkers: TripMarker[],
) {
  const feature = routeGeoJSON?.features?.find((item) => item.geometry.type === "LineString") as
    | GeoJSON.Feature<GeoJSON.LineString>
    | undefined;
  const routePoints =
    feature?.geometry.coordinates.map(([lng, lat]) => [lat, lng] as [number, number]) ?? [];
  if (!routePoints.length) {
    return existingMarkers;
  }

  const originPoint = routePoints[0];
  const destinationPoint = routePoints[routePoints.length - 1];
  const nextMarkers = [...existingMarkers];

  const originMarker = { lat: originPoint[0], lng: originPoint[1], label: origin, type: "origin" as const };
  const destinationMarker = {
    lat: destinationPoint[0],
    lng: destinationPoint[1],
    label: destination,
    type: "destination" as const,
  };

  const originIndex = nextMarkers.findIndex((marker) => marker.type === "origin");
  if (originIndex >= 0) nextMarkers[originIndex] = originMarker;
  else nextMarkers.unshift(originMarker);

  const destinationIndex = nextMarkers.findIndex((marker) => marker.type === "destination");
  if (destinationIndex >= 0) nextMarkers[destinationIndex] = destinationMarker;
  else nextMarkers.push(destinationMarker);

  return nextMarkers;
}

function normalizeTripData(raw: unknown): TripResultStorage | null {
  if (!raw || typeof raw !== "object") return null;

  const value = raw as Record<string, unknown>;
  const routeSource = value.route as Record<string, unknown> | undefined;
  const travelDates = (value.travel_dates as Record<string, unknown> | undefined) ?? {};

  return {
    trip_id: safeNumber(value.trip_id ?? value.tripId, 0),
    origin: safeString(value.origin),
    destination: safeString(value.destination),
    destination_key: safeString(value.destination_key),
    distance_km: safeNumber(value.distance_km ?? routeSource?.distance_km ?? value.distanceKm, 0),
    duration_hours: safeNumber(value.duration_hours ?? routeSource?.duration_hours ?? value.durationHours, 0),
    route:
      value.route && typeof value.route === "object"
        ? (value.route as GeoJSON.FeatureCollection)
        : { type: "FeatureCollection", features: [] },
    weather: Array.isArray(value.weather) ? (value.weather as TripResultStorage["weather"]) : [],
    weather_status: (value.weather_status as TripResultStorage["weather_status"]) ?? "success",
    weather_message: (value.weather_message as string | null | undefined) ?? null,
    budget: (value.budget as TripResultStorage["budget"]) ?? (value.budget as never),
    fuel_calculation: (value.fuel_calculation as TripResultStorage["fuel_calculation"]) ?? null,
    recommendations: normalizeRecommendations(value.recommendations, safeString(value.destination)),
    itinerary: (value.itinerary as FullItinerary | null | undefined) ?? null,
    vehicle: (value.vehicle as VehicleDetails) ?? {
      vehicle_type: "car",
      vehicle_name: "Vehicle",
      fuel_type: "petrol",
      mileage_kmpl: 0,
      tank_capacity_litres: 0,
      number_of_people: 1,
    },
    startDate: safeString(value.startDate ?? travelDates.start),
    endDate: safeString(value.endDate ?? travelDates.end),
    userBudget: safeNumber(value.userBudget ?? value.total_inr, 0),
    markers: Array.isArray(value.markers) ? (value.markers as TripMarker[]) : [],
    report_summary: safeString(value.report_summary),
  } satisfies TripResultStorage;
}

function SectionCard({
  eyebrow,
  title,
  description,
  children,
}: {
  eyebrow: string;
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <section className="overflow-hidden rounded-[2.25rem] border border-slate-200 bg-white shadow-xl">
      <div className="border-b border-slate-200 px-5 py-5 sm:px-6">
        <p className="text-xs uppercase tracking-[0.28em] text-blue-700">{eyebrow}</p>
        <h2 className="mt-2 text-2xl font-black tracking-tight text-slate-950">{title}</h2>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">{description}</p>
      </div>
      <div className="p-5 sm:p-6">{children}</div>
    </section>
  );
}

function InfoPill({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 shadow-sm">
      <div className="text-[11px] uppercase tracking-[0.24em] text-slate-500">{label}</div>
      <div className="mt-1 text-sm font-semibold text-slate-950">{value}</div>
    </div>
  );
}

function extractRecommendationCount(tripData: TripResultStorage) {
  const recommendations = normalizeRecommendations(tripData.recommendations, tripData.destination);
  return recommendations.hotels.length + recommendations.restaurants.length + recommendations.attractions.length;
}

function TripResultContent({ tripData }: { tripData: TripResultStorage }) {
  const normalizedRecommendations = normalizeRecommendations(tripData.recommendations, tripData.destination);
  const recommendationCount = extractRecommendationCount(tripData);
  const [mapRoute, setMapRoute] = useState<GeoJSON.FeatureCollection | null>(tripData.route ?? null);
  const [mapMarkers, setMapMarkers] = useState<TripMarker[]>(tripData.markers ?? []);
  const [weatherData, setWeatherData] = useState(tripData.weather ?? []);
  const [weatherStatus, setWeatherStatus] = useState(tripData.weather_status ?? "success");
  const [weatherMessage, setWeatherMessage] = useState(tripData.weather_message ?? null);
  const routeDistanceKm = Math.max(tripData.distance_km ?? 0, estimateRouteDistanceKm(mapRoute ?? tripData.route ?? null));
  const routeDurationHours = Math.max(tripData.duration_hours ?? 0, estimateRouteDurationHours(routeDistanceKm));
  const tripForDisplay = {
    ...tripData,
    distance_km: routeDistanceKm,
    duration_hours: routeDurationHours,
  };

  useEffect(() => {
    let cancelled = false;

    async function refreshRoute() {
      try {
        const response = await fetch(
          `${API_BASE_URL}/api/map/route?origin=${encodeURIComponent(tripData.origin)}&destination=${encodeURIComponent(tripData.destination)}`,
          { cache: "no-store" },
        );
        if (!response.ok) return;
        const payload = (await response.json()) as GeoJSON.FeatureCollection;
        if (cancelled) return;
        setMapRoute(payload);
        setMapMarkers(buildMarkersFromRoute(payload, tripData.origin, tripData.destination, tripData.markers ?? []));
      } catch {
        if (cancelled) return;
        setMapRoute(tripData.route ?? null);
        setMapMarkers(tripData.markers ?? []);
      }
    }

    refreshRoute();

    return () => {
      cancelled = true;
    };
  }, [tripData]);

  useEffect(() => {
    let cancelled = false;

    async function refreshWeather() {
      const originUrl = `${API_BASE_URL}/api/weather/${encodeURIComponent(tripData.origin)}?start_date=${encodeURIComponent(tripData.startDate)}&end_date=${encodeURIComponent(tripData.endDate)}`;
      const destinationUrl = `${API_BASE_URL}/api/weather/${encodeURIComponent(tripData.destination)}?start_date=${encodeURIComponent(tripData.startDate)}&end_date=${encodeURIComponent(tripData.endDate)}`;

      try {
        const [originResponse, destinationResponse] = await Promise.all([
          fetch(originUrl, { cache: "no-store" }),
          fetch(destinationUrl, { cache: "no-store" }),
        ]);

        if (cancelled) return;

        const originPayload = originResponse.ok ? await originResponse.json() : null;
        const destinationPayload = destinationResponse.ok ? await destinationResponse.json() : null;
        const originWeather = Array.isArray(originPayload?.weather) ? originPayload.weather : [];
        const destinationWeather = Array.isArray(destinationPayload?.weather) ? destinationPayload.weather : [];
        const combinedWeather = [...originWeather, ...destinationWeather];

        if (combinedWeather.length) {
          setWeatherData(combinedWeather);
          setWeatherStatus("success");
          setWeatherMessage("");
          return;
        }

        setWeatherData(tripData.weather ?? []);
        setWeatherStatus(tripData.weather_status ?? "success");
        setWeatherMessage(tripData.weather_message ?? null);
      } catch (error) {
        if (cancelled) return;
        console.error("Weather refresh failed", error);
        setWeatherData(tripData.weather ?? []);
        setWeatherStatus(tripData.weather_status ?? "success");
        setWeatherMessage(tripData.weather_message ?? null);
      }
    }

    refreshWeather();

    return () => {
      cancelled = true;
    };
  }, [tripData.destination, tripData.endDate, tripData.origin, tripData.startDate, tripData.weather, tripData.weather_message, tripData.weather_status]);

  async function downloadReport() {
    const response = await fetch(`${API_BASE_URL}/api/trip/${tripData.trip_id}/pdf`, {
      headers: {
        ...getAuthHeaders(),
      },
    });

    if (!response.ok) {
      throw new Error("Unable to download the PDF report.");
    }

    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = getPdfFilename(
      response,
      `RoadMind_${sanitizeFilenamePart(tripData.origin)}_${sanitizeFilenamePart(tripData.destination)}.pdf`,
    );
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  return (
    <div className="space-y-6 py-6 md:py-8">
      <TripSummaryCard trip={tripForDisplay} onDownloadPdf={() => downloadReport().catch((error) => console.error(error))} />

      <section className="grid gap-6 lg:grid-cols-[1.15fr_0.85fr]">
        <SectionCard
          eyebrow="Route"
          title="Interactive trip map"
          description="Inspect the driving route, origin, destination, and waypoint markers before diving into the detailed itinerary."
        >
          <TripMap routeGeoJSON={mapRoute ?? tripData.route} markers={mapMarkers} focusPoint={null} />
        </SectionCard>

        <WeatherPanel
          weatherData={weatherData}
          startDate={tripData.startDate}
          endDate={tripData.endDate}
          origin={tripData.origin}
          destination={tripData.destination}
          status={weatherStatus}
          message={weatherMessage ?? undefined}
        />
      </section>

      <SectionCard
        eyebrow="Budget"
        title="Budget breakdown"
        description="A polished breakdown of fuel, hotels, food, tolls, and miscellaneous trip costs."
      >
          <BudgetBreakdown
            budget={tripData.budget}
            fuelCalculation={tripData.fuel_calculation}
            vehicle={tripData.vehicle}
            userBudget={tripData.userBudget}
            routeDistanceKm={routeDistanceKm}
          />
      </SectionCard>

      <SectionCard
        eyebrow="Recommendations"
        title="Hotels, restaurants, and attractions"
        description="Destination-specific recommendations are grouped into elegant, high-quality cards for quick planning."
        children={
          recommendationCount > 0 ? (
            <RecommendationCards recommendations={normalizedRecommendations} destination={tripData.destination} />
          ) : (
            <div className="rounded-3xl border border-dashed border-slate-200 bg-slate-50 p-8 text-center text-sm text-slate-500">
              No recommendations available yet.
            </div>
          )
        }
      />

      <SectionCard
        eyebrow="Overview"
        title="Trip actions"
        description="Save the report, open the full itinerary, or return to the travel overview whenever you need it."
      >
        <div className="grid gap-3 md:grid-cols-[1.1fr_0.9fr]">
          <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={() => {
                  downloadReport().catch((error) => {
                    console.error(error);
                  });
                }}
                className="inline-flex items-center gap-2 rounded-2xl bg-[#0071e3] px-5 py-3 text-sm font-bold text-white transition hover:bg-[#0077ed]"
              >
                <ArrowDownToLine className="h-4 w-4" />
                Download PDF
              </button>
              <Link
                href="/trip-result/itinerary"
                className="inline-flex items-center gap-2 rounded-2xl border border-slate-200 bg-white px-5 py-3 text-sm font-semibold text-slate-700 transition hover:border-blue-200 hover:bg-slate-50 hover:text-slate-950"
              >
                Open Day-by-Day Plan
                <ArrowRight className="h-4 w-4" />
              </Link>
            </div>

            <div className="mt-4 text-sm leading-7 text-slate-600">
              {tripData.report_summary || "Your trip report summary will appear here after planning."}
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <InfoPill label="Origin" value={tripData.origin} />
            <InfoPill label="Destination" value={tripData.destination} />
            <InfoPill label="Distance" value={`${Math.round(routeDistanceKm)} km`} />
            <InfoPill label="Duration" value={formatDuration(routeDurationHours)} />
          </div>
        </div>
      </SectionCard>

      <SectionCard
        eyebrow="Chat"
        title="Travel assistant"
        description="Ask RoadMind AI about route choices, itinerary timing, hotels, and destination ideas."
      >
        <div id="chat-panel">
          <TravelChat tripId={String(tripData.trip_id)} />
        </div>
      </SectionCard>
    </div>
  );
}

export default function TripResultPage() {
  const router = useRouter();
  const [theme, setTheme] = useState<"light" | "dark">("light");
  const [loaded, setLoaded] = useState(false);
  const [tripData, setTripData] = useState<TripResultStorage | null>(null);

  useEffect(() => {
    const savedTheme = window.localStorage.getItem("roadmind-theme") as "light" | "dark" | null;
    const preferredTheme =
      savedTheme ?? (window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    setTheme(preferredTheme);
  }, []);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    window.localStorage.setItem("roadmind-theme", theme);
  }, [theme]);

  useEffect(() => {
    const trip = loadStoredTripResult() ?? null;
    if (!trip) {
      setTripData(null);
      setLoaded(true);
      return;
    }

    const resolvedDestinationKey = normalizeDestinationKey(trip.destination);
    if (trip.destination_key && trip.destination_key !== resolvedDestinationKey) {
      window.sessionStorage.removeItem("tripResult:active");
      setTripData(null);
      setLoaded(true);
      return;
    }

    setTripData(trip);
    setLoaded(true);
  }, []);

  return (
    <>
      <Navbar theme={theme} onToggleTheme={() => setTheme((current) => (current === "dark" ? "light" : "dark"))} />
      <main className="min-h-screen overflow-x-hidden bg-gradient-to-b from-slate-50 via-white to-slate-100 text-slate-950">
        <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
          {loaded && tripData ? (
            <TripResultContent tripData={tripData} />
          ) : !loaded ? (
            <section className="flex min-h-[60vh] items-center justify-center">
              <div className="max-w-md rounded-[2rem] border border-slate-200 bg-white p-8 text-center shadow-xl">
                <h1 className="text-2xl font-black text-slate-950">Loading trip result...</h1>
                <p className="mt-3 text-sm leading-6 text-slate-600">We&apos;re restoring your saved trip data.</p>
              </div>
            </section>
          ) : (
            <section className="flex min-h-[60vh] items-center justify-center">
              <div className="max-w-md rounded-[2rem] border border-slate-200 bg-white p-8 text-center shadow-xl">
                <h1 className="text-2xl font-black text-slate-950">No trip data found.</h1>
                <p className="mt-3 text-sm leading-6 text-slate-600">Please plan a trip first.</p>
                <button
                  type="button"
                  onClick={() => router.push("/")}
                  className="mt-6 inline-flex items-center justify-center rounded-2xl bg-[#0071e3] px-5 py-3 text-sm font-bold text-white transition hover:bg-[#0077ed]"
                >
                  Plan a Trip
                </button>
              </div>
            </section>
          )}
        </div>
      </main>
    </>
  );
}
