"use client";

import { useEffect, useMemo, useState, type FormEvent } from "react";
import { ArrowDownToLine, Compass, Loader2, Sparkles } from "lucide-react";

import AuthGuard from "@/components/auth/AuthGuard";
import Navbar from "@/components/auth/Navbar";
import BudgetBreakdown from "@/components/budget/BudgetBreakdown";
import TravelChat from "@/components/chat/TravelChat";
import RecommendationCards from "@/components/recommendations/RecommendationCards";
import VehicleForm from "@/components/trip/VehicleForm";
import TripMap from "@/components/map/TripMap";
import WeatherPanel from "@/components/weather/WeatherPanel";
import { getAuthHeaders } from "@/lib/auth";
import type {
  DailyWeather,
  BudgetBreakdown as BudgetBreakdownType,
  LocationRecommendation,
  PlannedTripResponse,
  TripMarker,
  VehicleDetails,
} from "@/types";

type FormState = {
  origin: string;
  destination: string;
  budget: number;
  scenicRoute: boolean;
  budgetHotels: boolean;
  vegetarianFood: boolean;
};

type UiState = {
  loading: boolean;
  error: string | null;
  trip: PlannedTripResponse | null;
  routeGeoJSON: GeoJSON.FeatureCollection | null;
  markers: TripMarker[];
  weather: DailyWeather[];
  weatherStatus: "success" | "unavailable" | "past_dates";
  weatherMessage?: string;
  budget: BudgetBreakdownType | null;
  focusPoint: { lat: number; lng: number; zoom?: number } | null;
};

const INR_PER_USD = 83.5;

const DEFAULT_FORM: FormState = {
  origin: "",
  destination: "",
  budget: 25000,
  scenicRoute: true,
  budgetHotels: false,
  vegetarianFood: false,
};

function formatEta(hours: number) {
  const safeHours = Math.max(0, hours);
  const wholeHours = Math.floor(safeHours);
  const minutes = Math.round((safeHours - wholeHours) * 60);
  if (wholeHours === 0) return `ETA ~ ${minutes} min`;
  if (minutes === 0) return `ETA ~ ${wholeHours} hr`;
  return `ETA ~ ${wholeHours} hr ${minutes} min`;
}

function normalizeErrorMessage(error: unknown) {
  if (error instanceof Error) return error.message;
  return "Something went wrong";
}

function formatApiDetail(detail: unknown) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item === "string") return item;
        if (item && typeof item === "object" && "msg" in item) return String((item as { msg?: unknown }).msg);
        return JSON.stringify(item);
      })
      .join("; ");
  }
  if (detail && typeof detail === "object") {
    return JSON.stringify(detail);
  }
  return "Trip planning failed";
}

function getTodayIsoDate() {
  const now = new Date();
  const localDate = new Date(now.getTime() - now.getTimezoneOffset() * 60000);
  return localDate.toISOString().slice(0, 10);
}

function isMissingKeyMessage(message: string) {
  const lowered = message.toLowerCase();
  return (
    lowered.includes("api key") ||
    lowered.includes("is not set in the environment") ||
    (lowered.includes("missing") && lowered.includes("key"))
  );
}

function isValidIsoDate(value: string) {
  return /^\d{4}-\d{2}-\d{2}$/.test(value);
}

function buildRouteGeoJSON(polyline: Array<[number, number]> | undefined | null) {
  if (!polyline?.length) return null;
  return {
    type: "FeatureCollection" as const,
    features: [
      {
        type: "Feature" as const,
        properties: {},
        geometry: {
          type: "LineString" as const,
          coordinates: polyline.map(([lat, lng]) => [lng, lat]),
        },
      },
    ],
  } satisfies GeoJSON.FeatureCollection;
}

function buildMarkers(plan: PlannedTripResponse): TripMarker[] {
  const polyline = plan.route.polyline ?? [];
  const stops = [plan.origin, ...(plan.waypoints ?? []), plan.destination].filter(Boolean);
  const markerCount = stops.length || 2;

  return stops.map((label, index) => {
    const type: TripMarker["type"] =
      index === 0 ? "origin" : index === markerCount - 1 ? "destination" : "waypoint";
    const routeIndex =
      polyline.length > 1
        ? Math.min(
            polyline.length - 1,
            Math.round((index / Math.max(1, markerCount - 1)) * (polyline.length - 1)),
          )
        : 0;
    const point = polyline[routeIndex] ?? polyline[0] ?? [20.5937, 78.9629];
    const eta =
      index === 0
        ? "Start of trip"
        : formatEta((plan.route.duration_hours ?? 0) * (index / Math.max(1, markerCount - 1)));

    return {
      lat: point[0],
      lng: point[1],
      label,
      type,
      eta,
    };
  });
}

function buildBudget(plan: PlannedTripResponse): BudgetBreakdownType {
  const fuel = plan.fuel_cost_inr ?? 0;
  const tolls = plan.toll_cost_inr ?? 0;
  const hotels = plan.hotel_cost_inr ?? 0;
  const food = plan.food_cost_inr ?? 0;
  const miscellaneous =
    plan.misc_cost_inr ?? Math.max(0, (plan.total_inr ?? fuel + tolls + hotels + food) - (fuel + tolls + hotels + food));
  const total = plan.total_inr ?? fuel + tolls + hotels + food + miscellaneous;
  const totalUsd = plan.total_usd ?? total / INR_PER_USD;

  return {
    fuel,
    tolls,
    hotels,
    food,
    miscellaneous,
    total,
    fuelUsd: fuel / INR_PER_USD,
    tollsUsd: tolls / INR_PER_USD,
    hotelsUsd: hotels / INR_PER_USD,
    foodUsd: food / INR_PER_USD,
    miscellaneousUsd: miscellaneous / INR_PER_USD,
    totalUsd,
    lodging: hotels,
    activities: miscellaneous,
    breakdown: {
      fuel: { inr: fuel, usd: fuel / INR_PER_USD },
      tolls: { inr: tolls, usd: tolls / INR_PER_USD },
      hotels: { inr: hotels, usd: hotels / INR_PER_USD },
      food: { inr: food, usd: food / INR_PER_USD },
      miscellaneous: { inr: miscellaneous, usd: miscellaneous / INR_PER_USD },
      total: { inr: total, usd: totalUsd },
    },
  };
}

function LoadingSkeleton() {
  return (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="h-[72vh] min-h-[540px] rounded-[2rem] border border-gray-700 bg-gray-900 p-6 shadow-2xl">
          <div className="animate-pulse space-y-4">
            <div className="h-5 w-32 rounded bg-gray-700" />
            <div className="h-[60vh] rounded-3xl bg-gray-800" />
          </div>
        </div>
        <div className="space-y-6">
          <div className="rounded-[2rem] border border-gray-700 bg-gray-900 p-5 shadow-2xl">
            <div className="animate-pulse space-y-4">
              <div className="h-5 w-40 rounded bg-gray-700" />
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="h-40 rounded-2xl bg-gray-800" />
                <div className="h-40 rounded-2xl bg-gray-800" />
              </div>
            </div>
          </div>
          <div className="rounded-[2rem] border border-gray-700 bg-gray-900 p-5 shadow-2xl">
            <div className="animate-pulse space-y-4">
              <div className="h-5 w-36 rounded bg-gray-700" />
              <div className="h-72 rounded-3xl bg-gray-800" />
            </div>
          </div>
        </div>
      </div>
      <div className="rounded-[2rem] border border-gray-700 bg-gray-900 p-5 shadow-2xl">
        <div className="animate-pulse space-y-4">
          <div className="h-5 w-40 rounded bg-gray-700" />
          <div className="h-8 w-72 rounded bg-gray-700" />
          <div className="grid gap-4 md:grid-cols-2">
            <div className="h-72 rounded-3xl bg-gray-800" />
            <div className="h-72 rounded-3xl bg-gray-800" />
          </div>
        </div>
      </div>
    </div>
  );
}

export default function HomePage() {
  const [form, setForm] = useState<FormState>(DEFAULT_FORM);
  const [origin, setOrigin] = useState("");
  const [destination, setDestination] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [dateError, setDateError] = useState<string | null>(null);
  const [dateWarning, setDateWarning] = useState<string | null>(null);
  const [recommendations, setRecommendations] = useState<LocationRecommendation[]>([]);
  const [vehicle, setVehicle] = useState<VehicleDetails>({
    vehicle_type: "car",
    vehicle_name: "",
    fuel_type: "petrol",
    mileage_kmpl: 15,
    tank_capacity_litres: 40,
    number_of_people: 1,
  });
  const [fuelCalc, setFuelCalc] = useState<NonNullable<PlannedTripResponse["fuel_calculation"]> | null>(null);
  const [theme, setTheme] = useState<"light" | "dark">("light");
  const [state, setState] = useState<UiState>({
    loading: false,
    error: null,
    trip: null,
    routeGeoJSON: null,
    markers: [],
    weather: [],
    weatherStatus: "success",
    weatherMessage: undefined,
    budget: null,
    focusPoint: null,
  });

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

  const canDownloadPdf = Boolean(state.trip?.trip_id);

  const selectedPreferences = useMemo(() => {
    const preferences: string[] = [];
    if (form.scenicRoute) preferences.push("scenic");
    if (form.budgetHotels) preferences.push("budget hotels");
    if (form.vegetarianFood) preferences.push("vegetarian food");
    return preferences;
  }, [form.budgetHotels, form.scenicRoute, form.vegetarianFood]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmedOrigin = form.origin.trim();
    const trimmedDestination = form.destination.trim();
    setOrigin(trimmedOrigin);
    setDestination(trimmedDestination);
    setRecommendations([]);
    setFuelCalc(null);

    if (form.origin.trim().toLowerCase() === form.destination.trim().toLowerCase()) {
      setState((current) => ({
        ...current,
        error: "Origin and destination must be different.",
      }));
      return;
    }

    const trimmedStartDate = startDate.trim();
    const trimmedEndDate = endDate.trim();
    setDateError(null);
    setDateWarning(null);

    if (!trimmedStartDate) {
      setDateError("Please select start date");
      return;
    }
    if (!trimmedEndDate) {
      setDateError("Please select end date");
      return;
    }
    if (!isValidIsoDate(trimmedStartDate) || !isValidIsoDate(trimmedEndDate) || trimmedEndDate < trimmedStartDate) {
      setDateError("End date must be after start date");
      return;
    }
    const todayIso = getTodayIsoDate();
    if (trimmedStartDate < todayIso) {
      setDateWarning("Start date is in the past. Weather forecast may not be available.");
    }
    if (!vehicle.vehicle_name.trim()) {
      setState((current) => ({
        ...current,
        loading: false,
        error: "Please enter your vehicle name",
      }));
      return;
    }
    if (!Number.isFinite(vehicle.mileage_kmpl) || vehicle.mileage_kmpl <= 0) {
      setState((current) => ({
        ...current,
        loading: false,
        error: "Please enter your vehicle mileage",
      }));
      return;
    }
    if (!Number.isFinite(vehicle.tank_capacity_litres) || vehicle.tank_capacity_litres <= 0) {
      setState((current) => ({
        ...current,
        loading: false,
        error: "Please enter your tank capacity",
      }));
      return;
    }

    setState((current) => ({ ...current, loading: true, error: null, focusPoint: null }));

    try {
      const planResponse = await fetch("/api/trip/plan", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...getAuthHeaders(),
        },
        body: JSON.stringify({
          origin: form.origin,
          destination: form.destination,
          dates: `${trimmedStartDate} to ${trimmedEndDate}`,
          budget: form.budget,
          preferences: selectedPreferences,
          vehicle,
        }),
      });

      if (!planResponse.ok) {
        const payload = await planResponse.json().catch(() => null);
        throw new Error(formatApiDetail(payload?.detail));
      }

      const plan = (await planResponse.json()) as PlannedTripResponse;

      const routeGeoJSON = buildRouteGeoJSON(plan.route.polyline);
      const markers = buildMarkers(plan);
      const budget = buildBudget(plan);

      setState({
        loading: false,
        error: null,
        trip: plan,
        routeGeoJSON,
        markers,
        weather: plan.weather,
        weatherStatus: plan.weather_status || "success",
        weatherMessage: plan.weather_message || "",
        budget,
        focusPoint: null,
      });
      setRecommendations(plan.recommendations || []);
      setFuelCalc(plan.fuel_calculation ?? null);
    } catch (error) {
      const message = normalizeErrorMessage(error);
      setState((current) => ({
        ...current,
        loading: false,
        error: isMissingKeyMessage(message)
          ? `${message} Check backend/.env, restart the backend, and try again.`
          : message,
      }));
    }
  }

  async function downloadReport() {
    if (!state.trip?.trip_id) return;
    const response = await fetch(`/api/trip/${state.trip.trip_id}/pdf`, {
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
    link.download = `trip-report-${state.trip.trip_id}.pdf`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  const topSummary = state.trip ? (
    <div className="grid gap-3 rounded-[2rem] border border-gray-700 bg-gray-900/90 p-4 shadow-2xl backdrop-blur sm:grid-cols-2 xl:grid-cols-4">
      <StatItem label="Origin" value={state.trip.origin} />
      <StatItem label="Destination" value={state.trip.destination} />
      <StatItem label="Distance" value={`${state.trip.route.distance_km} km`} />
      <StatItem label="Duration" value={`${state.trip.route.duration_hours} hrs`} />
    </div>
  ) : null;

  return (
    <AuthGuard>
      <Navbar theme={theme} onToggleTheme={() => setTheme((current) => (current === "dark" ? "light" : "dark"))} />
      <main className="min-h-screen overflow-x-hidden bg-[radial-gradient(circle_at_top,rgba(249,115,22,0.12),transparent_35%),linear-gradient(180deg,#040816_0%,#0b1220_55%,#0f172a_100%)] text-slate-100 transition-colors">
        <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
          <section className="grid gap-8 rounded-[2rem] border border-white/10 bg-slate-950/70 p-5 shadow-2xl backdrop-blur-xl lg:grid-cols-[1.08fr_0.92fr] lg:p-8">
            <div className="space-y-6">
              <div className="inline-flex items-center gap-2 rounded-full border border-orange-500/20 bg-orange-500/10 px-4 py-2 text-sm font-semibold text-orange-200">
                <Sparkles className="h-4 w-4" />
                AI Road Trip Planner
              </div>

              <div className="space-y-3">
                <h1 className="max-w-3xl text-4xl font-black tracking-tight text-white sm:text-5xl lg:text-6xl">
                  Plan the route, tune the budget, and keep every stop in view.
                </h1>
                <p className="max-w-2xl text-base leading-7 text-slate-300 sm:text-lg">
                  Enter your trip details, generate an AI-planned road trip, and review the route map, weather
                  outlook, recommendations, and detailed budget breakdown in one responsive dashboard.
                </p>
              </div>

              <div className="grid gap-3 sm:grid-cols-3">
                <FeaturePill title="Scenic" text="Coastal and hill routes" />
                <FeaturePill title="Budget" text="Stay within spending limits" />
                <FeaturePill title="Weather" text="Spot risky conditions early" />
              </div>
            </div>

            <form
              onSubmit={handleSubmit}
              className="sticky top-20 mx-auto w-full max-w-2xl rounded-[1.75rem] border border-gray-700 bg-gray-950 p-5 text-white shadow-2xl"
            >
              <div className="flex items-center gap-2 text-sm text-slate-300">
                <Compass className="h-4 w-4 text-orange-400" />
                Trip details
              </div>

              <div className="mt-4 grid gap-4">
                <TextField
                  label="Origin"
                  value={form.origin}
                  onChange={(value) => setForm((current) => ({ ...current, origin: value }))}
                  placeholder="e.g. Mumbai"
                />
                <TextField
                  label="Destination"
                  value={form.destination}
                  onChange={(value) => setForm((current) => ({ ...current, destination: value }))}
                  placeholder="e.g. Goa"
                />

                <div className="flex flex-col gap-3 md:flex-row">
                  <DateField
                    label="Start date"
                    value={startDate}
                    onChange={(value) => {
                      setStartDate(value);
                      setDateError(null);
                    }}
                    className="w-full flex-1"
                  />
                  <DateField
                    label="End date"
                    value={endDate}
                    onChange={(value) => {
                      setEndDate(value);
                      setDateError(null);
                    }}
                    className="w-full flex-1"
                  />
                </div>

                {(dateError || dateWarning) && (
                  <div className="space-y-2">
                    {dateError ? (
                      <div className="rounded-2xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm font-medium text-red-200">
                        {dateError}
                      </div>
                    ) : null}
                    {dateWarning ? (
                      <div className="rounded-2xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm font-medium text-amber-200">
                        {dateWarning}
                      </div>
                    ) : null}
                  </div>
                )}

                <div className="space-y-3 rounded-2xl border border-white/10 bg-white/5 p-4">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <label className="text-sm font-medium text-slate-200">Budget</label>
                    <span className="rounded-full bg-white px-3 py-1 text-sm font-bold text-slate-900">
                      {"\u20b9"}
                      {form.budget.toLocaleString("en-IN")}
                    </span>
                  </div>
                  <input
                    type="range"
                    min={5000}
                    max={100000}
                    step={500}
                    value={form.budget}
                    onChange={(event) => setForm((current) => ({ ...current, budget: Number(event.target.value) }))}
                    className="h-2 w-full cursor-pointer appearance-none rounded-full bg-slate-800 accent-orange-500"
                  />
                  <div className="flex justify-between text-xs text-slate-400">
                    <span>{"\u20b95,000"}</span>
                    <span>{"\u20b9100,000"}</span>
                  </div>
                </div>

                <div className="flex flex-wrap gap-2 rounded-2xl border border-white/10 bg-white/5 p-4">
                  <PreferenceCheck
                    label="Scenic route"
                    checked={form.scenicRoute}
                    onChange={(checked) => setForm((current) => ({ ...current, scenicRoute: checked }))}
                  />
                  <PreferenceCheck
                    label="Budget hotels"
                    checked={form.budgetHotels}
                    onChange={(checked) => setForm((current) => ({ ...current, budgetHotels: checked }))}
                  />
                  <PreferenceCheck
                    label="Vegetarian food"
                    checked={form.vegetarianFood}
                    onChange={(checked) => setForm((current) => ({ ...current, vegetarianFood: checked }))}
                  />
                </div>

                <div className="flex items-center gap-3 pt-1">
                  <div className="h-px flex-1 bg-white/10" />
                  <span className="text-xs font-bold uppercase tracking-[0.24em] text-orange-300">
                    Your Vehicle
                  </span>
                  <div className="h-px flex-1 bg-white/10" />
                </div>

                <VehicleForm
                  initialValues={vehicle}
                  routeDistanceKm={state.trip?.route.distance_km ?? null}
                  onChange={(nextVehicle) => setVehicle(nextVehicle)}
                />

                {state.error && (
                  <div className="rounded-2xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm font-medium text-red-200">
                    {state.error}
                  </div>
                )}

                <button
                  type="submit"
                  disabled={state.loading}
                  className="inline-flex w-full items-center justify-center gap-2 rounded-2xl bg-orange-500 px-5 py-3 text-sm font-bold text-white transition hover:bg-orange-600 disabled:cursor-not-allowed disabled:opacity-70"
                >
                  {state.loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                  {state.loading ? "Planning trip..." : "Plan trip"}
                </button>
              </div>
            </form>
          </section>

          <div className="space-y-6 py-6 md:py-10">
            {topSummary}

            {state.loading ? (
              <LoadingSkeleton />
            ) : state.trip && state.routeGeoJSON && state.budget ? (
              <div className="space-y-6">
                <div className="grid gap-6 lg:grid-cols-[1.15fr_0.85fr]">
                  <section className="rounded-[2rem] border border-gray-700 bg-gray-900 p-4 shadow-2xl">
                    <div className="mb-4 flex items-center justify-between gap-3">
                      <div>
                        <p className="text-xs uppercase tracking-[0.24em] text-gray-400">Route</p>
                        <h2 className="text-xl font-bold text-white">Map and trip path</h2>
                      </div>
                    </div>
                    <TripMap routeGeoJSON={state.routeGeoJSON} markers={state.markers} focusPoint={state.focusPoint} />
                  </section>

                  <WeatherPanel
                    weatherData={state.weather}
                    startDate={state.trip.travel_dates.start}
                    endDate={state.trip.travel_dates.end}
                    origin={state.trip.origin}
                    destination={state.trip.destination}
                    status={state.weatherStatus}
                    message={state.weatherMessage}
                  />
                </div>

                <BudgetBreakdown
                  budget={state.budget}
                  fuelCalculation={state.trip?.fuel_calculation ?? fuelCalc}
                  vehicle={state.trip?.vehicle ?? vehicle}
                  userBudget={form.budget}
                  routeDistanceKm={state.trip?.route.distance_km ?? null}
                />

                <section className="rounded-[2rem] border border-gray-700 bg-gray-900 p-5 shadow-2xl">
                  <div className="flex flex-wrap items-center gap-3">
                    <button
                      type="button"
                      onClick={() => {
                        downloadReport().catch((error) => {
                          setState((current) => ({
                            ...current,
                            error: error instanceof Error ? error.message : "Could not download PDF",
                          }));
                        });
                      }}
                      className="inline-flex items-center gap-2 rounded-2xl bg-orange-500 px-5 py-3 text-sm font-semibold text-white transition hover:bg-orange-600 disabled:cursor-not-allowed disabled:opacity-60"
                      disabled={!canDownloadPdf}
                    >
                      <ArrowDownToLine className="h-4 w-4" />
                      Download PDF Report
                    </button>
                    <div className="min-w-0 flex-1 text-sm leading-6 text-slate-300">
                      {state.trip.report_summary || "Your trip report will appear here after planning."}
                    </div>
                  </div>
                </section>

                {recommendations.length > 0 && (
                  <section className="space-y-4">
                    <div className="flex items-center gap-2">
                      <span className="text-lg">📍</span>
                      <div>
                        <p className="text-xs font-bold uppercase tracking-[0.24em] text-orange-300">
                          RECOMMENDATIONS
                        </p>
                        <h2 className="text-xl font-black text-white">Places Along Your Route</h2>
                      </div>
                    </div>
                    <RecommendationCards recommendations={recommendations} destination={destination} />
                  </section>
                )}
              </div>
            ) : (
              <section className="rounded-[2rem] border border-gray-700 bg-gray-900 p-6 text-center shadow-2xl">
                <div className="mx-auto max-w-2xl space-y-3">
                  <p className="text-xs uppercase tracking-[0.24em] text-gray-400">Dashboard</p>
                  <h2 className="text-2xl font-bold text-white">Your trip results will appear here</h2>
                  <p className="text-sm leading-6 text-slate-300">
                    Plan a route to see the map, weather forecast, fuel breakdown, budget comparison, and route
                    recommendations in the aligned dashboard below.
                  </p>
                </div>
              </section>
            )}
          </div>
        </div>

        <TravelChat tripId={String(state.trip?.trip_id ?? "")} />
      </main>
    </AuthGuard>
  );
}

function TextField({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}) {
  return (
    <label className="grid gap-2">
      <span className="text-sm font-medium text-slate-200">{label}</span>
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-white outline-none ring-0 placeholder:text-slate-500 focus:border-orange-400"
      />
    </label>
  );
}

function DateField({
  label,
  value,
  onChange,
  className = "",
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  className?: string;
}) {
  return (
    <label className={`grid gap-2 ${className}`}>
      <span className="text-sm font-medium text-slate-200">{label}</span>
      <input
        type="date"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-white outline-none focus:border-orange-400"
      />
    </label>
  );
}

function PreferenceCheck({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label className="flex min-w-[180px] flex-1 items-center justify-between gap-3 rounded-2xl border border-white/10 bg-slate-900 px-4 py-3">
      <span className="text-sm text-slate-200">{label}</span>
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        className="h-4 w-4 rounded border-slate-500 bg-slate-800 text-orange-500 accent-orange-500"
      />
    </label>
  );
}

function FeaturePill({ title, text }: { title: string; text: string }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-4 shadow-lg shadow-black/10">
      <div className="text-sm font-semibold text-white">{title}</div>
      <div className="mt-1 text-sm text-slate-300">{text}</div>
    </div>
  );
}

function StatItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-gray-700 bg-gray-950/70 p-4">
      <div className="text-[11px] uppercase tracking-[0.2em] text-slate-400">{label}</div>
      <div className="mt-2 text-lg font-semibold text-white">{value}</div>
    </div>
  );
}
