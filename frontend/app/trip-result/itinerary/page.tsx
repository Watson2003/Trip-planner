"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowDownToLine, ArrowLeft, MapPinned, Sparkles } from "lucide-react";
import { useRouter } from "next/navigation";

import Navbar from "@/components/auth/Navbar";
import ItineraryPlanner from "@/components/itinerary/ItineraryPlanner";
import { API_BASE_URL } from "@/lib/api";
import { getAuthHeaders } from "@/lib/auth";
import { loadStoredTripResult, normalizeDestinationKey, normalizeRecommendations, type TripResultStorage } from "@/lib/trip-result";
import type { FullItinerary } from "@/types";

function safeString(value: unknown, fallback = "") {
  return typeof value === "string" ? value : fallback;
}

function safeNumber(value: unknown, fallback = 0) {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
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

function getRouteMetrics(tripData: TripResultStorage) {
  const routeDistanceKm = tripData.distance_km > 0 ? tripData.distance_km : estimateRouteDistanceKm(tripData.route);
  const routeDurationHours =
    tripData.duration_hours > 0 ? tripData.duration_hours : estimateRouteDurationHours(routeDistanceKm);
  return { routeDistanceKm, routeDurationHours };
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

function normalizeTripData(raw: unknown): TripResultStorage | null {
  if (!raw || typeof raw !== "object") return null;

  const value = raw as Record<string, unknown>;
  const routeSource = value.route as Record<string, unknown> | undefined;
  const travelDates = (value.travel_dates as Record<string, unknown> | undefined) ?? {};
  const route = value.route && typeof value.route === "object" ? (value.route as GeoJSON.FeatureCollection) : null;
  const directDistance = safeNumber(value.distance_km ?? routeSource?.distance_km ?? value.distanceKm, 0);
  const routeDistanceKm = directDistance > 0 ? directDistance : estimateRouteDistanceKm(route);
  const directDuration = safeNumber(value.duration_hours ?? routeSource?.duration_hours ?? value.durationHours, 0);
  const routeDurationHours = directDuration > 0 ? directDuration : estimateRouteDurationHours(routeDistanceKm);

  return {
    trip_id: safeNumber(value.trip_id ?? value.tripId, 0),
    origin: safeString(value.origin),
    destination: safeString(value.destination),
    destination_key: safeString(value.destination_key),
    distance_km: routeDistanceKm,
    duration_hours: routeDurationHours,
    route: route ?? { type: "FeatureCollection", features: [] },
    weather: Array.isArray(value.weather) ? (value.weather as TripResultStorage["weather"]) : [],
    weather_status: (value.weather_status as TripResultStorage["weather_status"]) ?? "success",
    weather_message: (value.weather_message as string | null | undefined) ?? null,
    budget: value.budget as TripResultStorage["budget"],
    fuel_calculation: (value.fuel_calculation as TripResultStorage["fuel_calculation"]) ?? null,
    recommendations: normalizeRecommendations(value.recommendations, safeString(value.destination)),
    itinerary: (value.itinerary as FullItinerary | null | undefined) ?? null,
    vehicle:
      (value.vehicle as TripResultStorage["vehicle"]) ??
      ({
        vehicle_type: "car",
        vehicle_name: "Vehicle",
        fuel_type: "petrol",
        mileage_kmpl: 0,
        tank_capacity_litres: 0,
        number_of_people: 1,
      } as TripResultStorage["vehicle"]),
    startDate: safeString(value.startDate ?? travelDates.start),
    endDate: safeString(value.endDate ?? travelDates.end),
    userBudget: safeNumber(value.userBudget ?? value.total_inr, 0),
    markers: Array.isArray(value.markers) ? (value.markers as TripResultStorage["markers"]) : [],
    report_summary: safeString(value.report_summary),
  } satisfies TripResultStorage;
}

function formatDuration(hours: number) {
  const totalMinutes = Math.max(0, Math.round(hours * 60));
  const wholeHours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  if (wholeHours === 0) return `${minutes} min`;
  if (minutes === 0) return `${wholeHours} hr`;
  return `${wholeHours} hr ${minutes} min`;
}

function formatMoney(value: number) {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(value || 0);
}

function countAttractions(itinerary: FullItinerary | null) {
  if (!itinerary) return 0;
  const seen = new Set<string>();
  let count = 0;
  for (const day of itinerary.days) {
    for (const slot of day.time_slots) {
      const category = slot.type ?? slot.category;
      if (category !== "attraction" && category !== "sightseeing") continue;
      const label = `${slot.place_name || slot.title || slot.activity || ""}`.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
      if (!label || seen.has(label)) continue;
      seen.add(label);
      count += 1;
    }
  }
  return count;
}

function DayHero({
  tripData,
  itinerary,
  onDownloadPdf,
}: {
  tripData: TripResultStorage;
  itinerary: FullItinerary | null;
  onDownloadPdf: () => void;
}) {
  const attractionCount = countAttractions(itinerary);
  const dayCount = itinerary?.total_days ?? tripData.budget.trip_days ?? 0;
  const { routeDistanceKm, routeDurationHours } = getRouteMetrics(tripData);

  return (
    <section className="overflow-hidden rounded-[2.5rem] border border-slate-200 bg-white shadow-xl">
      <div className="grid gap-6 p-6 lg:grid-cols-[1.12fr_0.88fr] lg:p-8">
        <div className="space-y-5">
          <div className="inline-flex items-center gap-2 rounded-full border border-blue-100 bg-blue-50 px-4 py-2 text-xs font-bold uppercase tracking-[0.26em] text-blue-700">
            <Sparkles className="h-4 w-4 text-blue-600" />
            Day-by-Day Travel Plan
          </div>

          <div className="space-y-3">
            <p className="text-sm uppercase tracking-[0.28em] text-slate-500">Separate itinerary page</p>
            <h1 className="text-heading text-3xl font-black tracking-tight sm:text-4xl">
              {tripData.origin} → {tripData.destination}
            </h1>
            <p className="text-body max-w-2xl text-sm leading-7 sm:text-base">
              The itinerary stays on a dedicated page with a timeline-first layout, day tabs, route-aware activities,
              and a premium export experience.
            </p>
          </div>

          <div className="flex flex-wrap gap-2">
            <span className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-600 shadow-sm">
              {dayCount} day{dayCount === 1 ? "" : "s"}
            </span>
            <span className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-600 shadow-sm">
              {formatDuration(routeDurationHours)}
            </span>
            <span className="rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-xs text-emerald-700 shadow-sm">
              {attractionCount} total attractions
            </span>
            <span className="rounded-full border border-blue-100 bg-blue-50 px-3 py-1.5 text-xs text-blue-700 shadow-sm">
              {formatMoney(itinerary?.total_itinerary_cost_inr ?? tripData.budget.total)}
            </span>
          </div>

          <div className="flex flex-wrap gap-3">
            <Link
              href="/trip-result"
              className="inline-flex items-center gap-2 rounded-2xl border border-slate-200 bg-white px-5 py-3 text-sm font-semibold text-[#0B1120] shadow-sm transition hover:bg-slate-100"
            >
              <ArrowLeft className="h-4 w-4" />
              Back to Trip Overview
            </Link>
            <button
              type="button"
              onClick={onDownloadPdf}
              className="inline-flex items-center gap-2 rounded-2xl bg-[#0071e3] px-5 py-3 text-sm font-bold text-white shadow-lg transition hover:bg-[#0077ed]"
            >
              <ArrowDownToLine className="h-4 w-4" />
              Download PDF
            </button>
          </div>
        </div>

        <div className="rounded-[1.75rem] border border-slate-200 bg-slate-50 p-5 shadow-xl">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
              <div className="text-xs uppercase tracking-[0.22em] text-slate-500">Trip title</div>
              <div className="mt-2 text-lg font-bold text-slate-950">Day-by-Day Travel Plan</div>
            </div>
            <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
              <div className="text-xs uppercase tracking-[0.22em] text-slate-500">Origin → Destination</div>
              <div className="mt-2 text-lg font-bold text-slate-950">
                {tripData.origin} <span className="text-blue-600">→</span> {tripData.destination}
              </div>
            </div>
            <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
              <div className="text-xs uppercase tracking-[0.22em] text-slate-500">Total days</div>
              <div className="mt-2 text-lg font-bold text-slate-950">{dayCount}</div>
            </div>
            <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
              <div className="text-xs uppercase tracking-[0.22em] text-slate-500">Estimated cost</div>
              <div className="mt-2 text-lg font-bold text-slate-950">
                {formatMoney(itinerary?.total_itinerary_cost_inr ?? tripData.budget.total)}
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function TripItineraryContent({ tripData }: { tripData: TripResultStorage }) {
  const expectedTripDays = tripData.budget.trip_days ?? tripData.itinerary?.total_days ?? tripData.markers.length ?? 3;
  const storedItineraryMatchesDays = tripData.itinerary?.total_days === expectedTripDays;
  const { routeDistanceKm, routeDurationHours } = getRouteMetrics(tripData);

  const [itinerary, setItinerary] = useState<FullItinerary | null>(storedItineraryMatchesDays ? tripData.itinerary : null);
  const [loading, setLoading] = useState(!storedItineraryMatchesDays);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const fallbackTripDays = Math.max(1, expectedTripDays);

    setItinerary(storedItineraryMatchesDays ? tripData.itinerary : null);
    setLoading(!storedItineraryMatchesDays);
    setError(null);

    async function loadItinerary() {
      try {
        const response = await fetch(`${API_BASE_URL}/api/itinerary/generate`, {
          method: "POST",
          cache: "no-store",
          headers: {
            "Content-Type": "application/json",
            ...getAuthHeaders(),
          },
          body: JSON.stringify({
            origin: tripData.origin,
            destination: tripData.destination,
            dates: `${tripData.startDate} to ${tripData.endDate}`,
            trip_days: fallbackTripDays,
            budget: tripData.userBudget || tripData.budget.total,
            preferences: [],
            vehicle: tripData.vehicle,
            route: {
              distance_km: routeDistanceKm,
              duration_hours: routeDurationHours,
            },
            weather: tripData.weather,
            recommendations: tripData.recommendations,
          }),
        });

        const payload = (await response.json().catch(() => null)) as { itinerary?: FullItinerary; detail?: unknown } | null;
        const payloadItinerary = payload?.itinerary;

        if (!response.ok) {
          throw new Error(
            typeof payload?.detail === "string"
              ? payload.detail
              : "Itinerary generation is taking longer than expected.",
          );
        }

        if (!cancelled && payloadItinerary) {
          setItinerary(payloadItinerary);
          const stored = loadStoredTripResult();
          if (stored && normalizeDestinationKey(stored.destination) === normalizeDestinationKey(tripData.destination)) {
            window.sessionStorage.setItem(
              `tripResult:${normalizeDestinationKey(tripData.destination)}`,
              JSON.stringify({
                ...stored,
                itinerary: payloadItinerary,
                destination_key: normalizeDestinationKey(tripData.destination),
              }),
            );
            window.sessionStorage.setItem("tripResult:active", `tripResult:${normalizeDestinationKey(tripData.destination)}`);
          }
        }
      } catch (fetchError) {
        if (!cancelled) {
          const message = fetchError instanceof Error ? fetchError.message : "Itinerary generation failed.";
          setError(message);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void loadItinerary();

    return () => {
      cancelled = true;
    };
  }, [expectedTripDays, storedItineraryMatchesDays, tripData]);

  async function downloadPdf() {
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
      <DayHero tripData={tripData} itinerary={itinerary} onDownloadPdf={() => downloadPdf().catch((error) => console.error(error))} />

      {itinerary ? (
        <section className="overflow-hidden rounded-[2.25rem] border border-slate-200 bg-white shadow-xl">
          <div className="flex items-center justify-between gap-4 border-b border-slate-200 px-5 py-5 sm:px-6">
            <div>
              <p className="text-xs uppercase tracking-[0.28em] text-blue-700">Itinerary</p>
              <h2 className="text-heading mt-2 text-2xl font-black">Day-by-Day timeline</h2>
            </div>
            <div className="inline-flex items-center gap-2 rounded-full border border-blue-100 bg-blue-50 px-3 py-1.5 text-xs font-semibold text-blue-700">
              <MapPinned className="h-3.5 w-3.5" />
              View on Map available inside each activity
            </div>
          </div>
          <div className="p-3 sm:p-4">
            <ItineraryPlanner itinerary={itinerary} totalEstimatedCostInr={tripData.budget.total} />
          </div>
        </section>
      ) : loading ? (
        <div className="rounded-[2rem] border border-slate-200 bg-white p-8 text-center shadow-xl">
          <div className="mx-auto h-5 w-5 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
          <p className="mt-3 text-sm text-slate-600">Generating itinerary...</p>
        </div>
      ) : error ? (
        <div className="rounded-[2rem] border border-slate-200 bg-white p-8 text-center shadow-xl">
          <p className="text-sm text-slate-600">{error}</p>
        </div>
      ) : (
        <div className="rounded-[2rem] border border-slate-200 bg-white p-8 text-center shadow-xl">
          <p className="text-sm text-slate-600">Itinerary generation is unavailable for this trip.</p>
        </div>
      )}
    </div>
  );
}

export default function TripItineraryPage() {
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
    const stored = loadStoredTripResult();
    if (!stored) {
      setTripData(null);
      setLoaded(true);
      return;
    }

    setTripData(normalizeTripData(stored));
    setLoaded(true);
  }, []);

  return (
    <>
      <Navbar theme={theme} onToggleTheme={() => setTheme((current) => (current === "dark" ? "light" : "dark"))} />
      <main className="min-h-screen overflow-x-hidden bg-gradient-to-b from-slate-50 via-white to-slate-100 text-slate-950">
        <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
          {loaded && tripData ? (
            <TripItineraryContent tripData={tripData} />
          ) : !loaded ? (
            <section className="flex min-h-[60vh] items-center justify-center">
              <div className="max-w-md rounded-[2rem] border border-slate-200 bg-white p-8 text-center shadow-xl">
                <h1 className="text-heading text-2xl font-black">Loading itinerary...</h1>
                <p className="text-body mt-3 text-sm leading-6">We&apos;re restoring your saved trip data.</p>
              </div>
            </section>
          ) : (
            <section className="flex min-h-[60vh] items-center justify-center">
              <div className="max-w-md rounded-[2rem] border border-slate-200 bg-white p-8 text-center shadow-xl">
                <h1 className="text-heading text-2xl font-black">No trip data found.</h1>
                <p className="text-body mt-3 text-sm leading-6">Please plan a trip first.</p>
                <button
                  type="button"
                  onClick={() => router.push("/")}
                className="mt-6 inline-flex items-center justify-center rounded-2xl bg-[#0071e3] px-5 py-3 text-sm font-bold text-white shadow-lg transition hover:bg-[#0077ed]"
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
