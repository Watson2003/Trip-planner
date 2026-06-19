"use client";

import { useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from "react";
import Link from "next/link";
import {
  ArrowRight,
  CloudSun,
  Compass,
  FileDown,
  Globe2,
  Hotel,
  Loader2,
  MapPinned,
  MessageSquareMore,
  ShieldCheck,
  Sparkles,
  Star,
  TrendingUp,
  Wallet,
} from "lucide-react";

import Navbar from "@/components/auth/Navbar";
import VehicleForm from "@/components/trip/VehicleForm";
import ItineraryPreview from "@/components/trip/ItineraryPreview";
import TripSummaryCard from "@/components/trip/TripSummaryCard";
import { API_BASE_URL } from "@/lib/api";
import { getAuthHeaders } from "@/lib/auth";
import {
  loadStoredTripResult,
  normalizeDestinationKey,
  normalizeRecommendations,
  storeTripResult,
  type TripResultStorage,
} from "@/lib/trip-result";
import type { BudgetBreakdown as BudgetBreakdownType, PlannedTripResponse, TripMarker, VehicleDetails } from "@/types";

type FormState = {
  origin: string;
  destination: string;
  budget: number;
  scenicRoute: boolean;
  budgetHotels: boolean;
  vegetarianFood: boolean;
  budgetRestaurants: boolean;
};

const INR_PER_USD = 83.5;

const DEFAULT_FORM: FormState = {
  origin: "",
  destination: "",
  budget: 25000,
  scenicRoute: true,
  budgetHotels: false,
  vegetarianFood: false,
  budgetRestaurants: false,
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
  if (detail && typeof detail === "object") return JSON.stringify(detail);
  return "Trip planning failed";
}

function getTodayIsoDate() {
  const now = new Date();
  const localDate = new Date(now.getTime() - now.getTimezoneOffset() * 60000);
  return localDate.toISOString().slice(0, 10);
}

function isMissingKeyMessage(message: string) {
  const lowered = message.toLowerCase();
  return lowered.includes("api key") || lowered.includes("is not set in the environment") || (lowered.includes("missing") && lowered.includes("key"));
}

function isValidIsoDate(value: string) {
  return /^\d{4}-\d{2}-\d{2}$/.test(value);
}

function formatDateForAPI(dateStr: string) {
  if (!dateStr) return "";
  if (/^\d{4}-\d{2}-\d{2}$/.test(dateStr)) return dateStr;
  if (/^\d{2}-\d{2}-\d{4}$/.test(dateStr)) {
    const [dd, mm, yyyy] = dateStr.split("-");
    return `${yyyy}-${mm}-${dd}`;
  }
  return dateStr;
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

function estimateRouteDistanceKm(polyline: Array<[number, number]> | undefined | null) {
  if (!polyline?.length) return 0;
  let total = 0;
  for (let index = 1; index < polyline.length; index += 1) {
    const previous = polyline[index - 1];
    const current = polyline[index];
    if (!previous || !current) continue;
    total += haversineDistanceKm(previous[0], previous[1], current[0], current[1]);
  }
  return Math.round(total * 100) / 100;
}

function estimateRouteDurationHours(distanceKm: number) {
  if (!Number.isFinite(distanceKm) || distanceKm <= 0) return 0;
  const averageSpeedKmh = 45;
  return Math.round((distanceKm / averageSpeedKmh) * 100) / 100;
}

function buildMarkers(plan: PlannedTripResponse): TripMarker[] {
  const route = plan.route as PlannedTripResponse["route"] & {
    origin_coords?: [number, number] | null;
    destination_coords?: [number, number] | null;
  };
  const polyline = route.polyline ?? [];
  const stops = [plan.origin, ...(plan.waypoints ?? []), plan.destination].filter(Boolean);
  const markerCount = stops.length || 2;

  return stops.map((label, index) => {
    const type: TripMarker["type"] = index === 0 ? "origin" : index === markerCount - 1 ? "destination" : "waypoint";
    const routeIndex =
      polyline.length > 1
        ? Math.min(polyline.length - 1, Math.round((index / Math.max(1, markerCount - 1)) * (polyline.length - 1)))
        : 0;
    const sampledPoint = polyline[routeIndex] ?? polyline[0] ?? [20.5937, 78.9629];
    const originPoint = normalizeRoutePoint(route.origin_coords) ?? sampledPoint;
    const destinationPoint = normalizeRoutePoint(route.destination_coords) ?? sampledPoint;
    const point = index === 0 ? originPoint : index === markerCount - 1 ? destinationPoint : sampledPoint;
    const eta =
      index === 0 ? "Start of trip" : formatEta((plan.route.duration_hours ?? 0) * (index / Math.max(1, markerCount - 1)));

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
    hotel_price_per_night: plan.hotel_price_per_night ?? undefined,
    hotel_category: plan.hotel_category ?? undefined,
    hotel_nights: plan.hotel_nights ?? undefined,
    hotel_daily_breakdown: plan.hotel_daily_breakdown ?? undefined,
    hotel_explanation: plan.hotel_explanation ?? undefined,
    food_price_per_day_per_person: plan.food_price_per_day_per_person ?? undefined,
    food_type: plan.food_type ?? undefined,
    food_days: plan.food_days ?? undefined,
    food_is_vegetarian: plan.food_is_vegetarian ?? undefined,
    food_daily_breakdown: plan.food_daily_breakdown ?? undefined,
    food_explanation: plan.food_explanation ?? undefined,
    trip_days: plan.trip_days ?? undefined,
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

function SectionCard({
  eyebrow,
  title,
  description,
  action,
  children,
}: {
  eyebrow: string;
  title: string;
  description: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="roadmind-panel overflow-hidden rounded-[2.25rem] border border-slate-200 bg-white">
      <div className="flex flex-col gap-3 border-b border-slate-200 px-5 py-5 sm:flex-row sm:items-end sm:justify-between sm:px-6">
        <div className="space-y-2">
          <p className="text-caption text-xs uppercase tracking-[0.28em]">{eyebrow}</p>
          <h2 className="text-heading text-2xl font-black tracking-tight">{title}</h2>
          <p className="text-body max-w-2xl text-sm leading-6">{description}</p>
        </div>
        {action ? <div>{action}</div> : null}
      </div>
      <div className="p-5 sm:p-6">{children}</div>
    </section>
  );
}

const POPULAR_DESTINATIONS = [
  { name: "Ooty", tone: "from-blue-50 to-white", icon: "🏞️" },
  { name: "Goa", tone: "from-cyan-50 to-white", icon: "🏖️" },
  { name: "Munnar", tone: "from-emerald-50 to-white", icon: "🌿" },
  { name: "Kodaikanal", tone: "from-violet-50 to-white", icon: "⛰️" },
  { name: "Pondicherry", tone: "from-amber-50 to-white", icon: "🌊" },
];

const WHY_ROADMIND = [
  { title: "AI Route Intelligence", description: "Smarter paths with destination-aware planning.", icon: MapPinned, accent: "text-blue-600", bg: "bg-blue-50" },
  { title: "Weather Insights", description: "Forecast-aware trips with safer travel timing.", icon: CloudSun, accent: "text-cyan-600", bg: "bg-cyan-50" },
  { title: "Budget Planning", description: "Clear costs with fuel, hotel, food, and tolls.", icon: Wallet, accent: "text-emerald-600", bg: "bg-emerald-50" },
  { title: "Smart Hotels", description: "Destination-fit stays with practical recommendations.", icon: Hotel, accent: "text-purple-600", bg: "bg-purple-50" },
  { title: "PDF Export", description: "Save and share a polished trip plan instantly.", icon: FileDown, accent: "text-blue-600", bg: "bg-blue-50" },
  { title: "AI Chat Assistant", description: "Ask follow-up questions inside the trip workspace.", icon: MessageSquareMore, accent: "text-rose-600", bg: "bg-rose-50" },
];

const DASHBOARD_STATS = [
  { value: "1000+", label: "Trips Planned", icon: TrendingUp },
  { value: "50+", label: "Destinations", icon: Globe2 },
  { value: "AI Powered", label: "Always On", icon: Sparkles },
  { value: "Real-time", label: "Recommendations", icon: ShieldCheck },
];

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
      <span className="text-sm font-medium text-slate-700">{label}</span>
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        className="roadmind-input px-4 py-3 text-[15px]"
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
      <span className="text-sm font-medium text-slate-700">{label}</span>
      <input
        type="date"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="roadmind-input px-4 py-3 text-[15px]"
      />
    </label>
  );
}

function ToggleChip({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label
      className={[
        "flex items-center justify-between gap-3 rounded-2xl border px-4 py-3 transition duration-300",
        checked
          ? "border-blue-200 bg-blue-50 text-blue-700 shadow-sm"
          : "border-slate-200 bg-white text-slate-700 shadow-sm hover:border-blue-400 hover:shadow-md",
      ].join(" ")}
    >
      <span className="text-sm font-medium">{label}</span>
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        className="h-4 w-4 rounded border-slate-300 bg-transparent text-blue-600 accent-blue-600"
      />
    </label>
  );
}

function FloatingStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="text-[11px] uppercase tracking-[0.24em] text-slate-400">{label}</div>
      <div className="mt-2 text-lg font-bold text-slate-950">{value}</div>
    </div>
  );
}

export default function HomePage() {
  const [form, setForm] = useState<FormState>(DEFAULT_FORM);
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [tripDays, setTripDays] = useState(1);
  const [tripDaysManuallyEdited, setTripDaysManuallyEdited] = useState(false);
  const [dateError, setDateError] = useState<string | null>(null);
  const [dateWarning, setDateWarning] = useState<string | null>(null);
  const [vehicle, setVehicle] = useState<VehicleDetails>({
    vehicle_type: "car",
    vehicle_name: "",
    fuel_type: "petrol",
    mileage_kmpl: 15,
    tank_capacity_litres: 40,
    number_of_people: 1,
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [theme, setTheme] = useState<"light" | "dark">("light");
  const [tripResult, setTripResult] = useState<TripResultStorage | null>(null);
  const formRef = useRef<HTMLDivElement | null>(null);
  const previewRef = useRef<HTMLDivElement | null>(null);

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
    if (stored) {
      setTripResult(stored);
    }
  }, []);

  useEffect(() => {
    if (tripDaysManuallyEdited) return;
    if (startDate && endDate) {
      try {
        const start = new Date(startDate);
        const end = new Date(endDate);
        const diffMs = end.getTime() - start.getTime();
        const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24)) + 1;
        if (diffDays >= 1) setTripDays(diffDays);
      } catch {
        // Leave manual input intact.
      }
    }
  }, [startDate, endDate, tripDaysManuallyEdited]);

  const selectedPreferences = useMemo(() => {
    const preferences: string[] = [];
    if (form.scenicRoute) preferences.push("scenic");
    if (form.budgetHotels) preferences.push("budget hotels");
    if (form.vegetarianFood) preferences.push("vegetarian food");
    if (form.budgetRestaurants) preferences.push("budget restaurants");
    return preferences;
  }, [form.budgetHotels, form.budgetRestaurants, form.scenicRoute, form.vegetarianFood]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setDateError(null);
    setDateWarning(null);

    const trimmedOrigin = form.origin.trim();
    const trimmedDestination = form.destination.trim();
    if (trimmedOrigin.toLowerCase() === trimmedDestination.toLowerCase()) {
      setError("Origin and destination must be different.");
      return;
    }

    const trimmedStartDate = startDate.trim();
    const trimmedEndDate = endDate.trim();

    if (!trimmedStartDate) {
      setDateError("Please select a start date.");
      return;
    }
    if (!trimmedEndDate) {
      setDateError("Please select an end date.");
      return;
    }
    if (!isValidIsoDate(trimmedStartDate) || !isValidIsoDate(trimmedEndDate) || trimmedEndDate < trimmedStartDate) {
      setDateError("End date must be after start date.");
      return;
    }
    if (tripDays < 1) {
      setError("Please enter at least 1 day.");
      return;
    }

    const todayIso = getTodayIsoDate();
    if (trimmedStartDate < todayIso) {
      setDateWarning("Start date is in the past. Weather forecast may be limited.");
    }
    if (!vehicle.vehicle_name.trim()) {
      setError("Please enter your vehicle name.");
      return;
    }
    if (!Number.isFinite(vehicle.mileage_kmpl) || vehicle.mileage_kmpl <= 0) {
      setError("Please enter your vehicle mileage.");
      return;
    }
    if (!Number.isFinite(vehicle.tank_capacity_litres) || vehicle.tank_capacity_litres <= 0) {
      setError("Please enter your tank capacity.");
      return;
    }

    setLoading(true);
    try {
      const requestBody = {
        origin: form.origin,
        destination: form.destination,
        dates: `${formatDateForAPI(trimmedStartDate)} to ${formatDateForAPI(trimmedEndDate)}`,
        trip_days: tripDays,
        budget: form.budget,
        preferences: selectedPreferences,
        vehicle,
      };

      const planResponse = await fetch(`${API_BASE_URL}/api/trip/plan`, {
        method: "POST",
        cache: "no-store",
        headers: {
          "Content-Type": "application/json",
          ...getAuthHeaders(),
        },
        body: JSON.stringify(requestBody),
      });

      if (!planResponse.ok) {
        const payload = await planResponse.json().catch(() => null);
        throw new Error(formatApiDetail(payload?.detail));
      }

      const plan = (await planResponse.json()) as PlannedTripResponse;
      const routeDistanceKm = Math.max(plan.route.distance_km ?? 0, estimateRouteDistanceKm(plan.route.polyline));
      const routeDurationHours = Math.max(plan.route.duration_hours ?? 0, estimateRouteDurationHours(routeDistanceKm));
      const trip = {
        trip_id: plan.trip_id,
        origin: plan.origin,
        destination: plan.destination,
        distance_km: routeDistanceKm,
        duration_hours: routeDurationHours,
        route: buildRouteGeoJSON(plan.route.polyline) ?? { type: "FeatureCollection", features: [] },
        weather: plan.weather,
        weather_status: plan.weather_status ?? "success",
        weather_message: plan.weather_message ?? null,
        budget: buildBudget(plan),
        fuel_calculation: plan.fuel_calculation ?? null,
        recommendations: normalizeRecommendations(plan.recommendations, plan.destination),
        itinerary: plan.itinerary ?? null,
        vehicle,
        startDate: trimmedStartDate,
        endDate: trimmedEndDate,
        userBudget: form.budget,
        markers: buildMarkers(plan),
        report_summary: plan.report_summary,
        destination_key: normalizeDestinationKey(plan.destination),
      } satisfies TripResultStorage;

      storeTripResult(trip);
      setTripResult(trip);
      previewRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (submitError) {
      const message = normalizeErrorMessage(submitError);
      setError(isMissingKeyMessage(message) ? `${message} Check backend/.env, restart the backend, and try again.` : message);
    } finally {
      setLoading(false);
    }
  }

  const topFeatureCards = [
    { label: "Route insight", value: "Smart driving paths" },
    { label: "Destination quality", value: "Curated attractions" },
    { label: "Planning clarity", value: "Budget and weather ready" },
  ];

  return (
    <>
      <Navbar theme={theme} onToggleTheme={() => setTheme((current) => (current === "dark" ? "light" : "dark"))} />
      <main className="min-h-screen overflow-x-hidden text-slate-950">
        <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
          <section className="grid gap-6 lg:grid-cols-[1.06fr_0.94fr]">
            <div className="roadmind-panel overflow-hidden rounded-[2.5rem] border border-slate-200 bg-white p-6 shadow-xl sm:p-8">
              <div className="inline-flex items-center gap-2 rounded-full border border-blue-100 bg-blue-50 px-4 py-2 text-xs font-bold uppercase tracking-[0.26em] text-blue-700">
                <Sparkles className="h-4 w-4 text-blue-600" />
                AI-powered road trip planner
              </div>

              <div className="mt-6 space-y-4">
                <h1 className="text-heading max-w-3xl text-4xl font-black tracking-tight sm:text-5xl lg:text-6xl">
                  RoadMind AI
                </h1>
                <p className="text-lg font-medium text-blue-700 sm:text-xl">AI-powered road trip planner</p>
                <p className="text-body max-w-2xl text-sm leading-7 sm:text-base">
                  Build premium road trips with destination-specific attractions, realistic routes, weather, budget
                  intelligence, and a polished itinerary preview. Everything stays in one beautiful travel workspace.
                </p>
              </div>

              <div className="mt-8 grid gap-3 sm:grid-cols-3">
                {topFeatureCards.map((item) => (
                  <FloatingStat key={item.label} label={item.label} value={item.value} />
                ))}
              </div>

              <div className="mt-8 flex flex-wrap gap-3">
                <button
                  type="button"
                  onClick={() => formRef.current?.scrollIntoView({ behavior: "smooth", block: "start" })}
                  className="roadmind-primary-button inline-flex items-center justify-center gap-2 rounded-2xl px-5 py-3 text-sm font-bold"
                >
                  Plan My Trip
                  <ArrowRight className="h-4 w-4" />
                </button>
                <Link
                  href="/trip-result"
                  className="inline-flex items-center justify-center gap-2 rounded-2xl border border-slate-200 bg-white px-5 py-3 text-sm font-semibold text-slate-700 shadow-sm transition duration-300 hover:border-blue-400 hover:bg-slate-50 hover:text-slate-950 hover:shadow-md"
                >
                  View Last Trip
                </Link>
              </div>

              <div className="mt-8 grid gap-3 sm:grid-cols-2">
                <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
                  <p className="text-caption text-xs uppercase tracking-[0.24em]">Why it feels premium</p>
                  <p className="text-body mt-2 text-sm leading-6">
                    Elegant route planning, curated places, and day-by-day itinerary intelligence without clutter.
                  </p>
                </div>
                <div className="rounded-3xl border border-slate-200 bg-slate-50 p-5 shadow-sm">
                  <p className="text-caption text-xs uppercase tracking-[0.24em]">Built for travel</p>
                  <p className="text-body mt-2 text-sm leading-6">
                    Map, weather, budget, PDF export, and AI chat all stay connected to the same saved trip result.
                  </p>
                </div>
              </div>

              <div className="mt-8 space-y-5">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-caption text-xs uppercase tracking-[0.26em]">Travel Intelligence</p>
                    <h2 className="text-heading mt-1 text-2xl font-black tracking-tight">Explore smarter trip planning</h2>
                  </div>
                  <div className="hidden rounded-full border border-blue-100 bg-blue-50 px-3 py-1 text-xs font-semibold text-blue-700 sm:inline-flex">
                    Premium dashboard
                  </div>
                </div>

                <div className="grid gap-4 xl:grid-cols-2">
                  <div className="roadmind-glass rounded-[1.75rem] p-5 shadow-sm transition duration-300 hover:-translate-y-0.5 hover:shadow-xl">
                    <div className="mb-4 flex items-center justify-between gap-3">
                      <div>
                        <p className="text-caption text-xs uppercase tracking-[0.24em]">Popular Destinations</p>
                        <h3 className="text-heading mt-1 text-lg font-bold">Where travelers are going</h3>
                      </div>
                      <MapPinned className="h-5 w-5 text-blue-600" />
                    </div>
                    <div className="grid gap-3 sm:grid-cols-2">
                      {POPULAR_DESTINATIONS.map((item) => (
                        <button
                          key={item.name}
                          type="button"
                          className={`group rounded-2xl border border-slate-200 bg-gradient-to-br ${item.tone} p-4 text-left shadow-sm transition duration-300 hover:-translate-y-0.5 hover:border-blue-400 hover:shadow-md`}
                        >
                          <div className="flex items-center gap-3">
                            <span className="flex h-10 w-10 items-center justify-center rounded-2xl bg-white text-lg shadow-sm transition group-hover:scale-105">
                              {item.icon}
                            </span>
                            <div>
                              <div className="text-heading text-sm font-bold">{item.name}</div>
                              <div className="text-caption text-xs">Curated travel quality</div>
                            </div>
                          </div>
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="roadmind-glass rounded-[1.75rem] p-5 shadow-sm transition duration-300 hover:-translate-y-0.5 hover:shadow-xl">
                    <div className="mb-4 flex items-center justify-between gap-3">
                      <div>
                        <p className="text-caption text-xs uppercase tracking-[0.24em]">Why RoadMind AI</p>
                        <h3 className="text-heading mt-1 text-lg font-bold">Intelligence built for road trips</h3>
                      </div>
                      <Sparkles className="h-5 w-5 text-blue-600" />
                    </div>
                    <div className="grid gap-3 sm:grid-cols-2">
                      {WHY_ROADMIND.map((item) => {
                        const Icon = item.icon;
                        return (
                          <div
                            key={item.title}
                            className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm transition duration-300 hover:-translate-y-0.5 hover:border-blue-400 hover:shadow-md"
                          >
                            <div className={`mb-3 flex h-10 w-10 items-center justify-center rounded-2xl ${item.bg} ${item.accent}`}>
                              <Icon className="h-5 w-5" />
                            </div>
                            <div className="text-heading text-sm font-bold">{item.title}</div>
                            <p className="text-body mt-2 text-sm leading-6">{item.description}</p>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </div>

                <div className="roadmind-glass rounded-[1.75rem] p-5 shadow-sm transition duration-300 hover:shadow-xl">
                  <div className="mb-4 flex items-center justify-between gap-3">
                    <div>
                      <p className="text-caption text-xs uppercase tracking-[0.24em]">Stats</p>
                      <h3 className="text-heading mt-1 text-lg font-bold">RoadMind AI in numbers</h3>
                    </div>
                    <TrendingUp className="h-5 w-5 text-emerald-600" />
                  </div>
                  <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                    {DASHBOARD_STATS.map((item) => {
                      const Icon = item.icon;
                      return (
                        <div
                          key={item.label}
                          className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm transition duration-300 hover:-translate-y-0.5 hover:border-blue-400 hover:shadow-md"
                        >
                          <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-2xl bg-slate-50 text-blue-600">
                            <Icon className="h-5 w-5" />
                          </div>
                          <div className="text-heading text-2xl font-black tracking-tight">{item.value}</div>
                          <div className="text-caption mt-1 text-sm">{item.label}</div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
            </div>

            <div ref={formRef} className="roadmind-form-card rounded-[2.5rem] p-5 sm:p-6">
              <div className="mb-5 flex items-center gap-3">
                <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-blue-50 text-blue-600">
                  <Compass className="h-5 w-5" />
                </div>
                <div>
                  <p className="text-caption text-xs uppercase tracking-[0.24em]">Trip planner</p>
                  <h2 className="text-heading text-xl font-bold">Start your road trip</h2>
                </div>
              </div>

              <form onSubmit={handleSubmit} className="space-y-4">
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

                {dateError || dateWarning ? (
                  <div className="space-y-2">
                    {dateError ? (
                      <div className="rounded-2xl border border-rose-400/20 bg-rose-400/10 px-4 py-3 text-sm text-rose-100">
                        {dateError}
                      </div>
                    ) : null}
                    {dateWarning ? (
                      <div className="rounded-2xl border border-blue-100 bg-blue-50 px-4 py-3 text-sm text-blue-700">
                        {dateWarning}
                      </div>
                    ) : null}
                  </div>
                ) : null}

                <div>
                  <label className="mb-2 block text-sm font-medium text-slate-700">Number of Days</label>
                  <div className="roadmind-counter flex items-center gap-3 rounded-2xl px-4 py-3">
                    <button
                      type="button"
                      onClick={() => {
                        setTripDaysManuallyEdited(true);
                        setTripDays((prev) => Math.max(1, prev - 1));
                      }}
                      className="roadmind-counter-button h-9 w-9 text-lg font-bold"
                    >
                      -
                    </button>

                    <input
                      type="number"
                      min={1}
                      max={30}
                      value={tripDays}
                      onChange={(event) => {
                        setTripDaysManuallyEdited(true);
                        const value = Number.parseInt(event.target.value, 10);
                        if (!Number.isNaN(value) && value >= 1 && value <= 30) setTripDays(value);
                      }}
                      className="w-16 border-none bg-transparent text-center text-lg font-semibold text-slate-950 outline-none"
                    />

                    <button
                      type="button"
                      onClick={() => {
                        setTripDaysManuallyEdited(true);
                        setTripDays((prev) => Math.min(30, prev + 1));
                      }}
                      className="roadmind-counter-button h-9 w-9 text-lg font-bold"
                    >
                      +
                    </button>

                    <span className="ml-1 text-sm text-slate-700">
                      {tripDays} day{tripDays === 1 ? "" : "s"}
                    </span>
                  </div>
                </div>

                <div className="space-y-3 rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
                  <div className="flex items-center justify-between gap-3">
                    <label className="text-sm font-medium text-slate-700">Budget</label>
                  <span className="rounded-full bg-blue-50 px-3 py-1 text-sm font-bold text-blue-700">
                      ₹{form.budget.toLocaleString("en-IN")}
                    </span>
                  </div>
                  <input
                    type="range"
                    min={5000}
                    max={100000}
                    step={500}
                    value={form.budget}
                    onChange={(event) => setForm((current) => ({ ...current, budget: Number(event.target.value) }))}
                    className="h-2 w-full cursor-pointer appearance-none rounded-full bg-transparent accent-blue-500"
                    style={{
                      background: `linear-gradient(to right, #2563EB 0%, #2563EB ${Math.max(
                        0,
                        Math.min(100, ((form.budget - 5000) / (100000 - 5000)) * 100),
                      )}%, rgba(255,255,255,0.12) ${Math.max(
                        0,
                        Math.min(100, ((form.budget - 5000) / (100000 - 5000)) * 100),
                      )}%, rgba(255,255,255,0.12) 100%)`,
                    }}
                  />
                  <div className="flex justify-between text-xs text-slate-500">
                    <span>₹5,000</span>
                    <span>₹1,00,000</span>
                  </div>
                </div>

                <div className="grid gap-3 sm:grid-cols-2">
                  <ToggleChip
                    label="Scenic route"
                    checked={form.scenicRoute}
                    onChange={(checked) => setForm((current) => ({ ...current, scenicRoute: checked }))}
                  />
                  <ToggleChip
                    label="Budget hotels"
                    checked={form.budgetHotels}
                    onChange={(checked) => setForm((current) => ({ ...current, budgetHotels: checked }))}
                  />
                  <ToggleChip
                    label="Vegetarian food"
                    checked={form.vegetarianFood}
                    onChange={(checked) => setForm((current) => ({ ...current, vegetarianFood: checked }))}
                  />
                  <ToggleChip
                    label="Budget restaurants"
                    checked={form.budgetRestaurants}
                    onChange={(checked) => setForm((current) => ({ ...current, budgetRestaurants: checked }))}
                  />
                </div>

                <div className="pt-1">
                  <div className="mb-3 flex items-center gap-3">
                    <div className="h-px flex-1 bg-white/8" />
                    <span className="text-xs font-bold uppercase tracking-[0.24em] text-slate-400">Your vehicle</span>
                    <div className="h-px flex-1 bg-white/8" />
                  </div>
                  <VehicleForm
                    initialValues={vehicle}
                    onChange={(nextVehicle) => setVehicle(nextVehicle)}
                    showFuelPreview={false}
                  />
                </div>

                {error ? (
                  <div className="rounded-2xl border border-rose-400/20 bg-rose-400/10 px-4 py-3 text-sm text-rose-100">
                    {error}
                  </div>
                ) : null}

                <button
                  type="submit"
                  disabled={loading}
                  className="roadmind-primary-button inline-flex w-full items-center justify-center gap-2 rounded-2xl px-5 py-3.5 text-sm font-bold disabled:cursor-not-allowed disabled:opacity-70"
                >
                  {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                  {loading ? "Planning trip..." : "Plan trip"}
                </button>
              </form>
            </div>
          </section>

          <div className="mt-6" ref={previewRef}>
            {tripResult ? (
              <div className="space-y-6">
                <TripSummaryCard trip={tripResult} />
                <ItineraryPreview trip={tripResult} />
              </div>
            ) : (
              <SectionCard
                eyebrow="After planning"
                title="Your trip preview will appear here"
                description="Once the route is generated, this home screen will show a clean snapshot with destination, budget, top attractions, and a Day 1 summary."
              >
                <div className="grid gap-3 sm:grid-cols-3">
                  <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">
                    <MapPinned className="mb-3 h-5 w-5 text-blue-600" />
                    Destination and route summary
                  </div>
                  <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">
                    <Star className="mb-3 h-5 w-5 text-emerald-600" />
                    Top 3 attractions
                  </div>
                  <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">
                    <Sparkles className="mb-3 h-5 w-5 text-purple-600" />
                    Day 1 itinerary preview
                  </div>
                </div>
              </SectionCard>
            )}
          </div>
        </div>
      </main>
    </>
  );
}
