"use client";

import { useEffect, useState } from "react";
import { ArrowDownToLine } from "lucide-react";
import { useRouter } from "next/navigation";

import Navbar from "@/components/auth/Navbar";
import BudgetBreakdown from "@/components/budget/BudgetBreakdown";
import TravelChat from "@/components/chat/TravelChat";
import RecommendationCards from "@/components/recommendations/RecommendationCards";
import TripMap from "@/components/map/TripMap";
import WeatherPanel from "@/components/weather/WeatherPanel";
import { getAuthHeaders } from "@/lib/auth";
import type {
  BudgetBreakdown as BudgetBreakdownType,
  LocationRecommendation,
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
  recommendations: LocationRecommendation[];
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
    recommendations: Array.isArray(value.recommendations)
      ? (value.recommendations as LocationRecommendation[])
      : [],
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
    <div className="rounded-2xl border border-gray-700 bg-gray-950/70 p-4">
      <div className="text-[11px] uppercase tracking-[0.2em] text-slate-400">{label}</div>
      <div className="mt-2 text-lg font-semibold text-white">{value}</div>
    </div>
  );
}

function TripResultContent({ tripData }: { tripData: TripResultStorage }) {
  async function downloadReport() {
    const response = await fetch(`/api/trip/${tripData.trip_id}/pdf`, {
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
      <div className="grid gap-3 rounded-[2rem] border border-gray-700 bg-gray-900/90 p-4 shadow-2xl backdrop-blur sm:grid-cols-2 xl:grid-cols-4">
        <StatItem label="Origin" value={tripData.origin} />
        <StatItem label="Destination" value={tripData.destination} />
        <StatItem label="Distance" value={`${tripData.distance_km} km`} />
        <StatItem label="Duration" value={`${tripData.duration_hours} hrs`} />
      </div>

      <div className="grid gap-6 lg:grid-cols-[1.15fr_0.85fr]">
        <section className="rounded-[2rem] border border-gray-700 bg-gray-900 p-4 shadow-2xl">
          <div className="mb-4 flex items-center justify-between gap-3">
            <div>
              <p className="text-xs uppercase tracking-[0.24em] text-gray-400">Route</p>
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

      <BudgetBreakdown
        budget={tripData.budget}
        fuelCalculation={tripData.fuel_calculation}
        vehicle={tripData.vehicle}
        userBudget={tripData.userBudget}
        routeDistanceKm={tripData.distance_km}
      />

      <section className="rounded-[2rem] border border-gray-700 bg-gray-900 p-5 shadow-2xl">
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={() => {
              downloadReport().catch((error) => {
                console.error(error);
              });
            }}
            className="inline-flex items-center gap-2 rounded-2xl bg-orange-500 px-5 py-3 text-sm font-semibold text-white transition hover:bg-orange-600 disabled:cursor-not-allowed disabled:opacity-60"
          >
            <ArrowDownToLine className="h-4 w-4" />
            Download PDF Report
          </button>
          <div className="min-w-0 flex-1 text-sm leading-6 text-slate-300">
            {tripData.report_summary || "Your trip report will appear here after planning."}
          </div>
        </div>
      </section>

      {(tripData.recommendations?.length ?? 0) > 0 && (
        <section className="space-y-4">
          <div className="flex items-center gap-2">
            <span className="text-lg">📍</span>
            <div>
              <p className="text-xs font-bold uppercase tracking-[0.24em] text-orange-300">RECOMMENDATIONS</p>
              <h2 className="text-xl font-black text-white">Places Along Your Route</h2>
            </div>
          </div>
          <RecommendationCards recommendations={tripData.recommendations} destination={tripData.destination} />
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
    const stored = window.sessionStorage.getItem("tripResult");
    if (!stored) {
      setTripData(null);
      setLoaded(true);
      return;
    }

    try {
      setTripData(normalizeTripData(JSON.parse(stored)));
    } catch {
      setTripData(null);
    } finally {
      setLoaded(true);
    }
  }, []);

  return (
    <>
      <Navbar theme={theme} onToggleTheme={() => setTheme((current) => (current === "dark" ? "light" : "dark"))} />
      <main className="min-h-screen overflow-x-hidden bg-[radial-gradient(circle_at_top,rgba(249,115,22,0.12),transparent_35%),linear-gradient(180deg,#040816_0%,#0b1220_55%,#0f172a_100%)] text-slate-100 transition-colors">
        <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
          {loaded && tripData ? (
            <TripResultContent tripData={tripData} />
          ) : !loaded ? (
            <section className="flex min-h-[60vh] items-center justify-center">
              <div className="max-w-md rounded-[2rem] border border-white/10 bg-slate-950/80 p-8 text-center shadow-2xl">
                <h1 className="text-2xl font-black text-white">Loading trip result...</h1>
                <p className="mt-3 text-sm leading-6 text-slate-300">
                  We&apos;re restoring your saved trip data.
                </p>
              </div>
            </section>
          ) : (
            <section className="flex min-h-[60vh] items-center justify-center">
              <div className="max-w-md rounded-[2rem] border border-white/10 bg-slate-950/80 p-8 text-center shadow-2xl">
                <h1 className="text-2xl font-black text-white">No trip data found.</h1>
                <p className="mt-3 text-sm leading-6 text-slate-300">Please plan a trip first.</p>
                <button
                  type="button"
                  onClick={() => router.push("/")}
                  className="mt-6 inline-flex items-center justify-center rounded-2xl bg-orange-500 px-5 py-3 text-sm font-bold text-white transition hover:bg-orange-600"
                >
                  Plan a Trip →
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
