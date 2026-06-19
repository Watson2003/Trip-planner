"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowDownToLine, ArrowRight, CalendarDays, Sparkles } from "lucide-react";
import { useRouter } from "next/navigation";

import Navbar from "@/components/auth/Navbar";
import BudgetBreakdown from "@/components/budget/BudgetBreakdown";
import TravelChat from "@/components/chat/TravelChat";
import RecommendationCards from "@/components/recommendations/RecommendationCards";
import TripMap from "@/components/map/TripMap";
import WeatherPanel from "@/components/weather/WeatherPanel";
import { API_BASE_URL } from "@/lib/api";
import { getAuthHeaders } from "@/lib/auth";
import { loadStoredTripResult, normalizeRecommendations, normalizeDestinationKey } from "@/lib/trip-result";
import type {
  BudgetBreakdown as BudgetBreakdownType,
  FullItinerary,
  RecommendationPayload,
  TripMarker,
  VehicleDetails,
} from "@/types";

type TripResultStorage = {
  trip_id: number;
  origin: string;
  destination: string;
  distance_km: number;
  duration_hours: number;
  route: GeoJSON.FeatureCollection;
  weather: Array<{
    date: string;
    day_name: string;
    location: string;
    temp_min_celsius: number;
    temp_max_celsius: number;
    temp_feels_like: number;
    humidity_percent: number;
    condition: string;
    weather_icon: string;
    wind_speed_kmh: number;
    rain_chance_percent: number;
    alert: string | null;
  }>;
  weather_status: "success" | "unavailable" | "past_dates";
  weather_message: string | null;
  budget: BudgetBreakdownType;
  fuel_calculation: {
    distance_km: number;
    mileage_kmpl: number;
    fuel_required_litres: number;
    fuel_type: string;
    fuel_price_per_litre: number;
    total_fuel_cost_inr: number;
    total_fuel_cost_usd: number;
    refueling_stops: number;
    cost_per_person_inr: number;
    vehicle_name: string;
    vehicle_type: string;
  } | null;
  recommendations: RecommendationPayload;
  itinerary: FullItinerary | null;
  vehicle: VehicleDetails;
  startDate: string;
  endDate: string;
  userBudget: number;
  markers: TripMarker[];
  report_summary: string;
};

const DEFAULT_VEHICLE: VehicleDetails = {
  vehicle_type: "car",
  vehicle_name: "Vehicle",
  fuel_type: "petrol",
  mileage_kmpl: 0,
  tank_capacity_litres: 0,
  number_of_people: 1,
};

const DEFAULT_BUDGET: BudgetBreakdownType = {
  fuel: 0,
  tolls: 0,
  hotels: 0,
  food: 0,
  miscellaneous: 0,
  total: 0,
  fuelUsd: 0,
  tollsUsd: 0,
  hotelsUsd: 0,
  foodUsd: 0,
  miscellaneousUsd: 0,
  totalUsd: 0,
  lodging: 0,
  activities: 0,
  breakdown: {
    fuel: { inr: 0, usd: 0 },
    tolls: { inr: 0, usd: 0 },
    hotels: { inr: 0, usd: 0 },
    food: { inr: 0, usd: 0 },
    miscellaneous: { inr: 0, usd: 0 },
    total: { inr: 0, usd: 0 },
  },
};

function safeNumber(value: unknown, fallback = 0) {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function safeString(value: unknown, fallback = "") {
  return typeof value === "string" ? value : fallback;
}

function safeBudgetTotal(budget: unknown) {
  if (!budget || typeof budget !== "object") return undefined;
  const total = (budget as Record<string, unknown>).total;
  return typeof total === "number" && Number.isFinite(total) ? total : undefined;
}

function formatDuration(hours: number) {
  const totalMinutes = Math.max(0, Math.round(hours * 60));
  const wholeHours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;

  if (wholeHours === 0) return `${minutes} min`;
  if (minutes === 0) return `${wholeHours} hr`;
  return `${wholeHours} hr ${minutes} min`;
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
    distance_km: safeNumber(value.distance_km ?? routeSource?.distance_km ?? value.distanceKm, 0),
    duration_hours: safeNumber(value.duration_hours ?? routeSource?.duration_hours ?? value.durationHours, 0),
    route:
      value.route && typeof value.route === "object"
        ? (value.route as GeoJSON.FeatureCollection)
        : { type: "FeatureCollection", features: [] },
    weather: Array.isArray(value.weather) ? (value.weather as TripResultStorage["weather"]) : [],
    weather_status: (value.weather_status as TripResultStorage["weather_status"]) ?? "success",
    weather_message: (value.weather_message as string | null | undefined) ?? null,
    budget: (value.budget as BudgetBreakdownType) ?? DEFAULT_BUDGET,
    fuel_calculation: (value.fuel_calculation as TripResultStorage["fuel_calculation"]) ?? null,
    recommendations: normalizeRecommendations(value.recommendations, safeString(value.destination)),
    itinerary: (value.itinerary as FullItinerary | null | undefined) ?? null,
    vehicle: (value.vehicle as VehicleDetails) ?? DEFAULT_VEHICLE,
    startDate: safeString(value.startDate ?? travelDates.start),
    endDate: safeString(value.endDate ?? travelDates.end),
    userBudget: safeNumber(value.userBudget ?? safeBudgetTotal(value.budget) ?? value.total_inr, 0),
    markers: Array.isArray(value.markers) ? (value.markers as TripMarker[]) : [],
    report_summary: safeString(value.report_summary),
  };
}

function StatItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-[#1a1a1a] bg-[#0a0a0a] p-4">
      <div className="text-[11px] uppercase tracking-[0.2em] text-[#888888]">{label}</div>
      <div className="mt-2 text-lg font-semibold text-white">{value}</div>
    </div>
  );
}

function normalizePlaceName(value: string) {
  return value
    .toLowerCase()
    .replace(/[\u2018\u2019`']/g, "")
    .replace(/\b(visit|explore|breakfast|lunch|dinner|check in at|check-in at|hotel|restaurant|stay at)\b/g, "")
    .replace(/[^a-z0-9]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function getPlanPlaces(day: FullItinerary["days"][number]) {
  const seen = new Set<string>();
  const places: string[] = [];
  for (const slot of day.time_slots) {
    const label = slot.place_name || slot.title || slot.activity || "";
    const normalized = normalizePlaceName(label);
    if (!normalized || seen.has(normalized)) continue;
    seen.add(normalized);
    places.push(label);
  }
  return places;
}

function TripResultContent({ tripData }: { tripData: TripResultStorage }) {
  const normalizedRecommendations = normalizeRecommendations(tripData.recommendations, tripData.destination);
  const recommendationCount =
    normalizedRecommendations.hotels.length +
    normalizedRecommendations.restaurants.length +
    normalizedRecommendations.attractions.length;

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
    link.download = `trip-report-${tripData.trip_id}.pdf`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="space-y-6 py-6 md:py-10">
      <div className="grid gap-3 rounded-[2rem] border border-[#1a1a1a] bg-[#0a0a0a] p-4 shadow-2xl backdrop-blur sm:grid-cols-2 xl:grid-cols-4">
        <StatItem label="Origin" value={tripData.origin} />
        <StatItem label="Destination" value={tripData.destination} />
        <StatItem label="Distance" value={`${tripData.distance_km} km`} />
        <StatItem label="Duration" value={formatDuration(tripData.duration_hours)} />
      </div>

      <div className="grid gap-6 lg:grid-cols-[1.15fr_0.85fr]">
        <section className="rounded-[2rem] border border-[#1a1a1a] bg-[#0a0a0a] p-4 shadow-2xl">
          <div className="mb-4 flex items-center justify-between gap-3">
            <div>
              <p className="text-xs uppercase tracking-[0.24em] text-[#888888]">Route</p>
              <h2 className="text-xl font-bold text-white">Map and trip path</h2>
            </div>
          </div>
          <TripMap routeGeoJSON={tripData.route} markers={tripData.markers ?? []} focusPoint={null} />
        </section>

        <WeatherPanel
          weatherData={tripData.weather}
          startDate={tripData.startDate}
          endDate={tripData.endDate}
          origin={tripData.origin}
          destination={tripData.destination}
          status={tripData.weather_status}
          message={tripData.weather_message ?? undefined}
        />
      </div>

      <section className="rounded-[2rem] border border-[#1a1a1a] bg-[#0a0a0a] p-5 shadow-2xl">
        <div className="flex flex-col gap-5">
          <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <div>
              <p className="text-xs uppercase tracking-[0.24em] text-[#D4AF37]">Day-by-Day Plan</p>
              <h2 className="mt-2 text-2xl font-bold text-white">Tourist-focused itinerary snapshot</h2>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-[#a0a0a0]">
                The detailed schedule, grouped attractions, and travel tips live in the itinerary page. This snapshot
                shows the trip shape at a glance.
              </p>
            </div>
            <Link
              href="/trip-result/itinerary"
              className="inline-flex items-center justify-center gap-2 rounded-2xl bg-[#D4AF37] px-5 py-3 text-sm font-semibold text-black transition hover:bg-[#B8860B]"
            >
              Open itinerary page
              <ArrowRight className="h-4 w-4" />
            </Link>
          </div>

          {tripData.itinerary?.days?.length ? (
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {tripData.itinerary.days.slice(0, 3).map((day) => {
                const places = getPlanPlaces(day);
                const attractionCount = day.time_slots.filter((slot) => {
                  const type = slot.type ?? slot.category;
                  return type === "attraction" || type === "sightseeing";
                }).length;
                return (
                  <article
                    key={`${day.day_number}-${day.date}`}
                    className="rounded-3xl border border-[#1a1a1a] bg-[#111111] p-4"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="flex items-center gap-2 text-[11px] uppercase tracking-[0.22em] text-[#8a8a8a]">
                          <CalendarDays className="h-4 w-4 text-[#D4AF37]" />
                          Day {day.day_number}
                        </p>
                        <h3 className="mt-2 text-base font-semibold text-white">{day.day_title}</h3>
                      </div>
                      <span className="rounded-full border border-[#D4AF37]/20 bg-[#D4AF37]/10 px-3 py-1 text-xs text-[#F2DB8A]">
                        {attractionCount} places
                      </span>
                    </div>

                    <p className="mt-3 text-sm leading-6 text-[#a0a0a0]">{day.summary}</p>

                    <div className="mt-4 flex flex-wrap gap-2">
                      {places.slice(0, 4).map((place) => (
                        <span
                          key={`${day.day_number}-${place}`}
                          className="rounded-full border border-white/5 bg-black/30 px-3 py-1 text-xs text-[#c8c8c8]"
                        >
                          {place}
                        </span>
                      ))}
                    </div>

                    <div className="mt-4 flex items-center justify-between text-xs text-[#8a8a8a]">
                      <span className="inline-flex items-center gap-1">
                        <Sparkles className="h-3.5 w-3.5 text-[#D4AF37]" />
                        {day.time_slots.length} planned stops
                      </span>
                      <Link
                        href="/trip-result/itinerary"
                        className="inline-flex items-center gap-1 text-[#D4AF37] transition hover:text-[#F2DB8A]"
                      >
                        View full day
                        <ArrowRight className="h-3.5 w-3.5" />
                      </Link>
                    </div>
                  </article>
                );
              })}
            </div>
          ) : (
            <div className="rounded-3xl border border-dashed border-[#2a2a2a] bg-[#111111] p-5 text-sm text-[#8a8a8a]">
              No itinerary snapshot is available yet. Open the itinerary page to generate the full plan.
            </div>
          )}
        </div>
      </section>

      <BudgetBreakdown
        budget={tripData.budget}
        fuelCalculation={tripData.fuel_calculation}
        vehicle={tripData.vehicle}
        userBudget={tripData.userBudget}
        routeDistanceKm={tripData.distance_km}
      />

      <section className="rounded-[2rem] border border-[#1a1a1a] bg-[#0a0a0a] p-5 shadow-2xl">
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={() => {
              downloadReport().catch((error) => {
                console.error(error);
              });
            }}
            className="inline-flex items-center gap-2 rounded-2xl bg-[#D4AF37] px-5 py-3 text-sm font-semibold text-black transition hover:bg-[#B8860B] disabled:cursor-not-allowed disabled:opacity-60"
          >
            <ArrowDownToLine className="h-4 w-4" />
            Download PDF Report
          </button>
          <div className="min-w-0 flex-1 text-sm leading-6 text-[#a0a0a0]">
            {tripData.report_summary || "Your trip report will appear here after planning."}
          </div>
        </div>
      </section>

      {recommendationCount > 0 && (
        <section className="space-y-4">
          <div className="flex items-center gap-2">
            <span className="text-lg">🧭</span>
            <div>
              <p className="text-xs font-bold uppercase tracking-[0.24em] text-[#D4AF37]">RECOMMENDATIONS</p>
              <h2 className="text-xl font-black text-white">Places Along Your Route</h2>
            </div>
          </div>
          <RecommendationCards recommendations={normalizedRecommendations} destination={tripData.destination} />
        </section>
      )}
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
    const trip = loadStoredTripResult();
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
      <main className="min-h-screen overflow-x-hidden bg-black text-white transition-colors">
        <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
          {loaded && tripData ? (
            <TripResultContent tripData={tripData} />
          ) : !loaded ? (
            <section className="flex min-h-[60vh] items-center justify-center">
              <div className="max-w-md rounded-[2rem] border border-[#1a1a1a] bg-[#0a0a0a] p-8 text-center shadow-2xl">
                <h1 className="text-2xl font-black text-white">Loading trip result...</h1>
                <p className="mt-3 text-sm leading-6 text-[#a0a0a0]">
                  We&apos;re restoring your saved trip data.
                </p>
              </div>
            </section>
          ) : (
            <section className="flex min-h-[60vh] items-center justify-center">
              <div className="max-w-md rounded-[2rem] border border-[#1a1a1a] bg-[#0a0a0a] p-8 text-center shadow-2xl">
                <h1 className="text-2xl font-black text-white">No trip data found.</h1>
                <p className="mt-3 text-sm leading-6 text-[#a0a0a0]">Please plan a trip first.</p>
                <button
                  type="button"
                  onClick={() => router.push("/")}
                  className="mt-6 inline-flex items-center justify-center rounded-2xl bg-[#D4AF37] px-5 py-3 text-sm font-bold text-black transition hover:bg-[#B8860B]"
                >
                  Plan a Trip
                </button>
              </div>
            </section>
          )}
        </div>

        {loaded && tripData ? <TravelChat tripId={String(tripData.trip_id)} /> : null}
      </main>
    </>
  );
}
