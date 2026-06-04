"use client";

import { useEffect, useMemo, useState, type FormEvent } from "react";
import { ArrowDownToLine, Compass, Loader2, Sparkles } from "lucide-react";

import AuthGuard from "@/components/auth/AuthGuard";
import Navbar from "@/components/auth/Navbar";
import BudgetBreakdown from "@/components/budget/BudgetBreakdown";
import TravelChat from "@/components/chat/TravelChat";
import RecommendationCards from "@/components/recommendations/RecommendationCards";
import TripMap from "@/components/map/TripMap";
import WeatherPanel from "@/components/weather/WeatherPanel";
import { getAuthHeaders } from "@/lib/auth";
import type {
  DailyWeather,
  BudgetBreakdown as BudgetBreakdownType,
  PlannedTripResponse,
  Recommendation,
  TripMarker,
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
  recommendations: Recommendation[];
  focusPoint: { lat: number; lng: number; zoom?: number } | null;
};

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
        ? Math.min(polyline.length - 1, Math.round((index / Math.max(1, markerCount - 1)) * (polyline.length - 1)))
        : 0;
    const point = polyline[routeIndex] ?? polyline[0] ?? [20.5937, 78.9629];
    const eta = index === 0 ? "Start of trip" : formatEta((plan.route.duration_hours ?? 0) * (index / Math.max(1, markerCount - 1)));

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
  const total = plan.total_inr ?? fuel + tolls + hotels + food;
  const miscellaneous = Math.max(0, total - (fuel + tolls + hotels + food));
  const totalUsd = plan.total_usd ?? total / 83;

  return {
    fuel,
    tolls,
    hotels,
    food,
    miscellaneous,
    total,
    fuelUsd: fuel / 83,
    tollsUsd: tolls / 83,
    hotelsUsd: hotels / 83,
    foodUsd: food / 83,
    miscellaneousUsd: miscellaneous / 83,
    totalUsd,
    lodging: hotels,
    activities: miscellaneous,
    breakdown: {
      fuel: { inr: fuel, usd: fuel / 83 },
      tolls: { inr: tolls, usd: tolls / 83 },
      hotels: { inr: hotels, usd: hotels / 83 },
      food: { inr: food, usd: food / 83 },
      miscellaneous: { inr: miscellaneous, usd: miscellaneous / 83 },
      total: { inr: total, usd: totalUsd },
    },
  };
}

function buildRecommendations(plan: PlannedTripResponse, markers: TripMarker[]): Recommendation[] {
  const routeMidpoint = markers[Math.floor(markers.length / 2)] ?? markers[markers.length - 1];
  const destinationMarker = markers[markers.length - 1];
  const categoryToFocus: Record<string, TripMarker | undefined> = {
    Hotels: destinationMarker,
    Restaurants: destinationMarker,
    Attractions: routeMidpoint ?? destinationMarker,
  };

  const items: Recommendation[] = [];

  (Object.entries(plan.recommendations) as Array<[string, Array<Record<string, unknown>>]>).forEach(
    ([category, list]) => {
      const tabLabel = category.toLowerCase().includes("hotel")
        ? "Hotels"
        : category.toLowerCase().includes("restaurant")
          ? "Restaurants"
          : "Attractions";

      list.slice(0, 3).forEach((item, index) => {
        const title = String(item.title ?? item.name ?? `${tabLabel.slice(0, -1)} ${index + 1}`);
        const description = String(item.description ?? item.why_it_fits ?? "Recommended by the travel assistant.");
        const baseRating = tabLabel === "Hotels" ? 5 : tabLabel === "Restaurants" ? 4 : 4;
        const estimatedCost =
          tabLabel === "Hotels" ? 3200 - index * 350 : tabLabel === "Restaurants" ? 850 - index * 100 : 300 + index * 75;
        const focus = categoryToFocus[tabLabel];

        items.push({
          title,
          description,
          category: tabLabel,
          priority: index + 1,
          rating: Math.max(1, Math.min(5, baseRating - index)),
          estimatedCostInr: Math.max(0, estimatedCost),
          location: String(item.location ?? item.display_name ?? plan.destination),
          lat: typeof focus?.lat === "number" ? focus.lat : undefined,
          lng: typeof focus?.lng === "number" ? focus.lng : undefined,
        });
      });
    },
  );

  return items;
}

function LoadingSkeleton() {
  return (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="h-[72vh] min-h-[540px] rounded-3xl border border-slate-200 bg-white/70 p-6 shadow-sm">
          <div className="animate-pulse space-y-4">
            <div className="h-5 w-32 rounded bg-slate-200 dark:bg-slate-700" />
            <div className="h-[60vh] rounded-3xl bg-slate-100 dark:bg-slate-800" />
          </div>
        </div>
        <div className="space-y-6">
          <div className="rounded-3xl border border-slate-200 bg-white/70 p-5 shadow-sm">
            <div className="animate-pulse space-y-4">
              <div className="h-5 w-40 rounded bg-slate-200 dark:bg-slate-700" />
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="h-40 rounded-2xl bg-slate-100 dark:bg-slate-800" />
                <div className="h-40 rounded-2xl bg-slate-100 dark:bg-slate-800" />
              </div>
            </div>
          </div>
          <div className="rounded-3xl border border-slate-200 bg-white/70 p-5 shadow-sm">
            <div className="animate-pulse space-y-4">
              <div className="h-5 w-36 rounded bg-slate-200 dark:bg-slate-700" />
              <div className="h-72 rounded-3xl bg-slate-100 dark:bg-slate-800" />
            </div>
          </div>
        </div>
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <div className="h-48 rounded-3xl border border-slate-200 bg-white/70 p-5 shadow-sm" />
        <div className="h-48 rounded-3xl border border-slate-200 bg-white/70 p-5 shadow-sm" />
        <div className="h-48 rounded-3xl border border-slate-200 bg-white/70 p-5 shadow-sm" />
      </div>
    </div>
  );
}

export default function HomePage() {
  const [form, setForm] = useState<FormState>(DEFAULT_FORM);
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [dateError, setDateError] = useState<string | null>(null);
  const [dateWarning, setDateWarning] = useState<string | null>(null);
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
    recommendations: [],
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
      const recommendations = buildRecommendations(plan, markers);

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
        recommendations,
        focusPoint: null,
      });
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

  function focusOnRecommendation(recommendation: Recommendation) {
    if (typeof recommendation.lat === "number" && typeof recommendation.lng === "number") {
      setState((current) => ({
        ...current,
        focusPoint: {
          lat: recommendation.lat as number,
          lng: recommendation.lng as number,
          zoom: 10,
        },
      }));
      return;
    }

    const fallback = state.markers[state.markers.length - 1] ?? state.markers[0];
    if (fallback) {
      setState((current) => ({
        ...current,
        focusPoint: {
          lat: fallback.lat,
          lng: fallback.lng,
          zoom: 9,
        },
      }));
    }
  }

  const topSummary = state.trip ? (
    <div className="grid gap-3 rounded-3xl border border-white/70 bg-white/80 p-5 shadow-glow backdrop-blur-xl sm:grid-cols-2 xl:grid-cols-4 dark:border-slate-800 dark:bg-slate-900/80">
      <StatItem label="Origin" value={state.trip.origin} />
      <StatItem label="Destination" value={state.trip.destination} />
      <StatItem label="Distance" value={`${state.trip.route.distance_km} km`} />
      <StatItem label="Duration" value={`${state.trip.route.duration_hours} hrs`} />
    </div>
  ) : null;

  return (
    <AuthGuard>
      <Navbar theme={theme} onToggleTheme={() => setTheme((current) => (current === "dark" ? "light" : "dark"))} />
      <main className="min-h-screen text-slate-900 transition-colors dark:text-slate-100">
        <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
          <section className="overflow-hidden rounded-[2rem] border border-white/80 bg-white/70 shadow-glow backdrop-blur-xl dark:border-slate-800 dark:bg-slate-900/70">
            <div className="grid gap-8 px-5 py-8 lg:grid-cols-[1.1fr_0.9fr] lg:px-8">
              <div className="space-y-5">
                <div className="inline-flex items-center gap-2 rounded-full border border-orange-200 bg-orange-50 px-4 py-2 text-sm font-semibold text-orange-700 dark:border-orange-900/50 dark:bg-orange-950/40 dark:text-orange-300">
                  <Sparkles className="h-4 w-4" />
                  AI Road Trip Planner
                </div>
                <div className="space-y-3">
                  <h1 className="max-w-3xl text-4xl font-black tracking-tight sm:text-5xl dark:text-white">
                    Plan the route, tune the budget, and keep every stop in view.
                  </h1>
                  <p className="max-w-2xl text-base leading-7 text-slate-600 sm:text-lg dark:text-slate-300">
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
                className="rounded-[1.75rem] border border-slate-200 bg-slate-950 p-5 text-white shadow-2xl dark:border-slate-800"
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

                  <div className="grid gap-3 sm:grid-cols-2">
                    <DateField
                      label="Start date"
                      value={startDate}
                      onChange={(value) => {
                        setStartDate(value);
                        setDateError(null);
                      }}
                    />
                    <DateField
                      label="End date"
                      value={endDate}
                      onChange={(value) => {
                        setEndDate(value);
                        setDateError(null);
                      }}
                    />
                  </div>
                  {(dateError || dateWarning) && (
                    <div className="space-y-2">
                      {dateError ? (
                        <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm font-medium text-red-700">
                          {dateError}
                        </div>
                      ) : null}
                      {dateWarning ? (
                        <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm font-medium text-amber-700">
                          {dateWarning}
                        </div>
                      ) : null}
                    </div>
                  )}

                  <div className="space-y-3 rounded-2xl border border-white/10 bg-white/5 p-4">
                    <div className="flex items-center justify-between gap-3">
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
                      onChange={(event) =>
                        setForm((current) => ({ ...current, budget: Number(event.target.value) }))
                      }
                      className="h-2 w-full cursor-pointer appearance-none rounded-full bg-slate-800 accent-orange-500"
                    />
                    <div className="flex justify-between text-xs text-slate-400">
                      <span>{"\u20b95,000"}</span>
                      <span>{"\u20b9100,000"}</span>
                    </div>
                  </div>

                  <div className="grid gap-3 rounded-2xl border border-white/10 bg-white/5 p-4">
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

                  {state.error && (
                    <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm font-medium text-red-700">
                      {state.error}
                    </div>
                  )}

                  <button
                    type="submit"
                    disabled={state.loading}
                    className="inline-flex items-center justify-center gap-2 rounded-2xl bg-orange-500 px-5 py-3 text-sm font-bold text-white transition hover:bg-orange-600 disabled:cursor-not-allowed disabled:opacity-70"
                  >
                    {state.loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                    {state.loading ? "Planning trip..." : "Plan trip"}
                  </button>
                </div>
              </form>
            </div>
          </section>

          <div className="mt-6 space-y-6">
            {topSummary}

            {state.loading ? (
              <LoadingSkeleton />
            ) : state.trip && state.routeGeoJSON && state.budget ? (
              <div className="grid gap-6 lg:grid-cols-2">
                <div className="space-y-6">
                  <TripMap routeGeoJSON={state.routeGeoJSON} markers={state.markers} focusPoint={state.focusPoint} />
                  <RecommendationCards recommendations={state.recommendations} onViewOnMap={focusOnRecommendation} />
                </div>

                <div className="space-y-6">
                  <WeatherPanel
                    weatherData={state.weather}
                    startDate={state.trip.travel_dates.start}
                    endDate={state.trip.travel_dates.end}
                    origin={state.trip.origin}
                    destination={state.trip.destination}
                    status={state.weatherStatus}
                    message={state.weatherMessage}
                  />
                  <BudgetBreakdown budget={state.budget} />
                  <div className="flex flex-wrap items-center gap-3 rounded-3xl border border-white/70 bg-white/80 p-5 shadow-glow backdrop-blur-xl dark:border-slate-800 dark:bg-slate-900/80">
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
                      className="inline-flex items-center gap-2 rounded-2xl bg-slate-950 px-5 py-3 text-sm font-semibold text-white transition hover:bg-slate-800"
                      disabled={!canDownloadPdf}
                    >
                      <ArrowDownToLine className="h-4 w-4" />
                      Download PDF Report
                    </button>
                    <div className="text-sm text-slate-600 dark:text-slate-300">
                      {state.trip.report_summary || "Your trip report will appear here after planning."}
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              <LoadingSkeleton />
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
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="grid gap-2">
      <span className="text-sm font-medium text-slate-200">{label}</span>
      <input
        type="date"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-white outline-none focus:border-orange-400"
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
    <label className="flex items-center justify-between gap-3 rounded-2xl border border-white/10 bg-slate-900 px-4 py-3">
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
    <div className="rounded-2xl border border-white/70 bg-white/75 p-4 shadow-sm dark:border-slate-700 dark:bg-slate-900/70">
      <div className="text-sm font-semibold text-slate-900 dark:text-slate-100">{title}</div>
      <div className="mt-1 text-sm text-slate-600 dark:text-slate-300">{text}</div>
    </div>
  );
}

function StatItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-700 dark:bg-slate-950/60">
      <div className="text-xs uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">{label}</div>
      <div className="mt-2 text-lg font-semibold text-slate-900 dark:text-slate-100">{value}</div>
    </div>
  );
}
