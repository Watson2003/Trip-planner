"use client";

import { useEffect, useState } from "react";
import { ArrowDownToLine } from "lucide-react";
import { useRouter } from "next/navigation";

import AuthGuard from "@/components/auth/AuthGuard";
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

function StatItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-gray-700 bg-gray-950/70 p-4">
      <div className="text-[11px] uppercase tracking-[0.2em] text-slate-400">{label}</div>
      <div className="mt-2 text-lg font-semibold text-white">{value}</div>
    </div>
  );
}

function TripResultContent({ tripData }: { tripData: TripResultStorage }) {
  const router = useRouter();

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
    <>
      <div className="mb-4">
        <button
          type="button"
          onClick={() => {
            sessionStorage.removeItem("tripResult");
            router.push("/");
          }}
          className="inline-flex items-center gap-2 rounded-2xl border border-orange-400/40 px-4 py-2 text-sm font-semibold text-orange-300 transition hover:bg-orange-500/10"
        >
          ← Plan Another Trip
        </button>
      </div>

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
            <TripMap routeGeoJSON={tripData.route} markers={tripData.markers} focusPoint={null} />
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

        {tripData.recommendations.length > 0 && (
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
    </>
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
    const root = document.documentElement;
    root.classList.toggle("dark", theme === "dark");
    window.localStorage.setItem("roadmind-theme", theme);
  }, [theme]);

  useEffect(() => {
    const stored = sessionStorage.getItem("tripResult");
    if (!stored) {
      setTripData(null);
      setLoaded(true);
      return;
    }

    try {
      setTripData(JSON.parse(stored) as TripResultStorage);
    } catch {
      setTripData(null);
    } finally {
      setLoaded(true);
    }
  }, []);

  return (
    <AuthGuard>
      <Navbar theme={theme} onToggleTheme={() => setTheme((current) => (current === "dark" ? "light" : "dark"))} />
      <main className="min-h-screen overflow-x-hidden bg-[radial-gradient(circle_at_top,rgba(249,115,22,0.12),transparent_35%),linear-gradient(180deg,#040816_0%,#0b1220_55%,#0f172a_100%)] text-slate-100 transition-colors">
        <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
          {loaded && tripData ? (
            <TripResultContent tripData={tripData} />
          ) : loaded ? (
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
          ) : null}
        </div>

        {loaded && tripData ? <TravelChat tripId={String(tripData.trip_id)} /> : null}
      </main>
    </AuthGuard>
  );
}
