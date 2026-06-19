"use client";

import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Compass, Loader2, Sparkles } from "lucide-react";
import { useRouter } from "next/navigation";

import AuthGuard from "@/components/auth/AuthGuard";
import Navbar from "@/components/auth/Navbar";
import VehicleForm from "@/components/trip/VehicleForm";
import { getAuthHeaders } from "@/lib/auth";
import { API_BASE_URL } from "@/lib/api";
import { storeTripResult, normalizeDestinationKey } from "@/lib/trip-result";
import type { TripResultStorage as StoredTripResultStorage } from "@/lib/trip-result";
import type {
  BudgetBreakdown as BudgetBreakdownType,
  FullItinerary,
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
  budgetRestaurants: boolean;
};

type TripResultStorage = {
  trip_id: number;
  origin: string;
  destination: string;
  destination_key: string;
  distance_km: number;
  duration_hours: number;
  route: GeoJSON.FeatureCollection;
  weather: PlannedTripResponse["weather"];
  weather_status: NonNullable<PlannedTripResponse["weather_status"]>;
  weather_message: string | null;
  budget: BudgetBreakdownType;
  fuel_calculation: PlannedTripResponse["fuel_calculation"];
  recommendations: PlannedTripResponse["recommendations"];
  itinerary: FullItinerary | null;
  vehicle: VehicleDetails;
  startDate: string;
  endDate: string;
  userBudget: number;
  markers: TripMarker[];
  report_summary: string;
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

function formatDateForAPI(dateStr: string): string {
  if (!dateStr) return "";

  if (/^\d{4}-\d{2}-\d{2}$/.test(dateStr)) {
    return dateStr;
  }

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

function FeaturePill({ title, text }: { title: string; text: string }) {
  return (
    <div className="rounded-2xl border border-[#1a1a1a] bg-[#0a0a0a] p-4 shadow-lg shadow-black/10">
      <div className="text-sm font-semibold text-white">{title}</div>
      <div className="mt-1 text-sm text-[#a0a0a0]">{text}</div>
    </div>
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
      <span className="text-sm font-medium text-[#a0a0a0]">{label}</span>
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        className="rounded-2xl border border-[#2a2a2a] bg-[#111111] px-4 py-3 text-white outline-none ring-0 placeholder:text-[#444444] focus:border-white"
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
      <span className="text-sm font-medium text-[#a0a0a0]">{label}</span>
      <input
        type="date"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="w-full rounded-2xl border border-[#2a2a2a] bg-[#111111] px-4 py-3 text-white outline-none focus:border-white"
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
    <label className="flex min-w-[180px] flex-1 items-center justify-between gap-3 rounded-2xl border border-[#1a1a1a] bg-[#111111] px-4 py-3">
      <span className="text-sm text-[#a0a0a0]">{label}</span>
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        className="h-4 w-4 rounded border-[#2a2a2a] bg-[#111111] text-white accent-white"
      />
    </label>
  );
}

export default function HomePage() {
  const router = useRouter();
  const [form, setForm] = useState<FormState>(DEFAULT_FORM);
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [tripDays, setTripDays] = useState<number>(1);
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
    if (tripDaysManuallyEdited) {
      return;
    }

    if (startDate && endDate) {
      try {
        const start = new Date(startDate);
        const end = new Date(endDate);
        const diffMs = end.getTime() - start.getTime();
        const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24)) + 1;
        if (diffDays >= 1) {
          setTripDays(diffDays);
        }
      } catch {
        // Keep the manually entered tripDays value if parsing fails.
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
    if (tripDays < 1) {
      setError("Please enter at least 1 day");
      return;
    }
    const todayIso = getTodayIsoDate();
    if (trimmedStartDate < todayIso) {
      setDateWarning("Start date is in the past. Weather forecast may not be available.");
    }
    if (!vehicle.vehicle_name.trim()) {
      setError("Please enter your vehicle name");
      return;
    }
    if (!Number.isFinite(vehicle.mileage_kmpl) || vehicle.mileage_kmpl <= 0) {
      setError("Please enter your vehicle mileage");
      return;
    }
    if (!Number.isFinite(vehicle.tank_capacity_litres) || vehicle.tank_capacity_litres <= 0) {
      setError("Please enter your tank capacity");
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
      console.log("=== SENDING TO API ===");
      console.log("trip_days:", tripDays);
      console.log("Full request body:", JSON.stringify(requestBody));
      console.log("Sending dates:", requestBody.dates);
      console.log("Trip days being sent:", tripDays);

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
      const tripResult = {
        trip_id: plan.trip_id,
        origin: plan.origin,
        destination: plan.destination,
        distance_km: plan.route.distance_km,
        duration_hours: plan.route.duration_hours,
        route: buildRouteGeoJSON(plan.route.polyline) ?? {
          type: "FeatureCollection",
          features: [],
        },
        weather: plan.weather,
        weather_status: plan.weather_status ?? "success",
        weather_message: plan.weather_message ?? null,
        budget: buildBudget(plan),
        fuel_calculation: plan.fuel_calculation,
        recommendations: plan.recommendations,
        itinerary: plan.itinerary ?? null,
        vehicle,
        startDate: trimmedStartDate,
        endDate: trimmedEndDate,
        userBudget: form.budget,
        markers: buildMarkers(plan),
        report_summary: plan.report_summary,
        destination_key: normalizeDestinationKey(plan.destination),
      } as StoredTripResultStorage;

      storeTripResult(tripResult);
      router.push("/trip-result");
    } catch (submitError) {
      const message = normalizeErrorMessage(submitError);
      setError(isMissingKeyMessage(message) ? `${message} Check backend/.env, restart the backend, and try again.` : message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthGuard>
      <Navbar theme={theme} onToggleTheme={() => setTheme((current) => (current === "dark" ? "light" : "dark"))} />
      <main className="min-h-screen overflow-x-hidden bg-black text-white transition-colors">
        <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
          <section className="grid gap-8 rounded-[2rem] border border-[#1a1a1a] bg-[#0a0a0a] p-5 shadow-2xl backdrop-blur-xl lg:grid-cols-[1.08fr_0.92fr] lg:p-8">
            <div className="space-y-6">
              <div className="inline-flex items-center gap-2 rounded-full border border-white/30 bg-white/10 px-4 py-2 text-sm font-semibold text-white">
                <Sparkles className="h-4 w-4" />
                AI Road Trip Planner
              </div>

              <div className="space-y-3">
                <h1 className="max-w-3xl text-4xl font-black tracking-tight text-white sm:text-5xl lg:text-6xl">
                  Plan the route, tune the budget, and keep every stop in view.
                </h1>
                <p className="max-w-2xl text-base leading-7 text-[#a0a0a0] sm:text-lg">
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
              className="sticky top-20 mx-auto w-full max-w-2xl rounded-[1.75rem] border border-[#1a1a1a] bg-[#0a0a0a] p-5 text-white shadow-2xl"
            >
              <div className="flex items-center gap-2 text-sm text-[#a0a0a0]">
                <Compass className="h-4 w-4 text-white" />
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
                      <div className="rounded-2xl border border-yellow-500/30 bg-yellow-500/10 px-4 py-3 text-sm font-medium text-yellow-200">
                        {dateWarning}
                      </div>
                    ) : null}
                  </div>
                )}

                <div className="mt-3">
                  <label className="mb-1 block text-sm text-[#888888]">Number of Days</label>
                  <div className="flex items-center gap-3 rounded-xl border border-[#2a2a2a] bg-[#111111] px-4 py-3">
                    <button
                      type="button"
                      onClick={() => {
                        setTripDaysManuallyEdited(true);
                        setTripDays((prev) => Math.max(1, prev - 1));
                      }}
                      className="flex h-8 w-8 items-center justify-center rounded-full bg-[#1a1a1a] text-lg font-bold text-white transition-colors hover:bg-[#2a2a2a]"
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
                        const val = parseInt(event.target.value, 10);
                        if (!Number.isNaN(val) && val >= 1 && val <= 30) {
                          setTripDays(val);
                        }
                      }}
                      className="w-16 border-none bg-transparent text-center text-lg font-semibold text-white outline-none"
                    />

                    <button
                      type="button"
                      onClick={() => {
                        setTripDaysManuallyEdited(true);
                        setTripDays((prev) => Math.min(30, prev + 1));
                      }}
                      className="flex h-8 w-8 items-center justify-center rounded-full bg-[#1a1a1a] text-lg font-bold text-white transition-colors hover:bg-[#2a2a2a]"
                    >
                      +
                    </button>

                    <span className="ml-1 text-sm text-[#888888]">
                      {tripDays === 1 ? "day" : "days"}
                      {tripDays > 1 && (
                        <span className="ml-2 text-[#555555]">
                          ({tripDays - 1} night{tripDays - 1 > 1 ? "s" : ""})
                        </span>
                      )}
                    </span>
                  </div>

                  <p className="mt-1 text-xs text-[#555555]">
                    Hotel cost = ₹price/night × {tripDays - 1 || 1} night{tripDays - 1 > 1 ? "s" : ""}
                  </p>
                </div>

                <div className="space-y-3 rounded-2xl border border-[#1a1a1a] bg-[#111111] p-4">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <label className="text-sm font-medium text-[#a0a0a0]">Budget</label>
                    <span className="rounded-full bg-white px-3 py-1 text-sm font-bold text-black">
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
                    className="h-2 w-full cursor-pointer appearance-none rounded-full bg-transparent accent-[#D4AF37]"
                    style={{
                      background: `linear-gradient(to right, #D4AF37 0%, #D4AF37 ${Math.max(
                        0,
                        Math.min(100, ((form.budget - 5000) / (100000 - 5000)) * 100),
                      )}%, #2a2a2a ${Math.max(0, Math.min(100, ((form.budget - 5000) / (100000 - 5000)) * 100))}%, #2a2a2a 100%)`,
                    }}
                  />
                  <div className="flex justify-between text-xs text-[#888888]">
                    <span>{"\u20b95,000"}</span>
                    <span>{"\u20b9100,000"}</span>
                  </div>
                </div>

                <div className="grid gap-2 rounded-2xl border border-[#1a1a1a] bg-[#111111] p-4 sm:grid-cols-2">
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
                  <PreferenceCheck
                    label="Budget restaurants"
                    checked={form.budgetRestaurants}
                    onChange={(checked) => setForm((current) => ({ ...current, budgetRestaurants: checked }))}
                  />
                </div>

                <div className="flex items-center gap-3 pt-1">
                  <div className="h-px flex-1 bg-white/10" />
                  <span className="text-xs font-bold uppercase tracking-[0.24em] text-white">
                    Your Vehicle
                  </span>
                  <div className="h-px flex-1 bg-white/10" />
                </div>

                <VehicleForm
                  initialValues={vehicle}
                  onChange={(nextVehicle) => setVehicle(nextVehicle)}
                  showFuelPreview={false}
                />

                {error && (
                  <div className="rounded-2xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm font-medium text-red-200">
                    {error}
                  </div>
                )}

                <button
                  type="submit"
                  disabled={loading}
                  className="inline-flex w-full items-center justify-center gap-2 rounded-2xl bg-white px-5 py-3 text-sm font-bold text-black transition hover:bg-[#e0e0e0] disabled:cursor-not-allowed disabled:opacity-70"
                >
                  {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                  {loading ? "Planning trip..." : "Plan trip"}
                </button>
              </div>
            </form>
          </section>
        </div>
      </main>
    </AuthGuard>
  );
}
