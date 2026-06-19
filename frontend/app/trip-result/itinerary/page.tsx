"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, Loader2 } from "lucide-react";
import { useRouter } from "next/navigation";

import Navbar from "@/components/auth/Navbar";
import ItineraryPlanner from "@/components/itinerary/ItineraryPlanner";
import { API_BASE_URL } from "@/lib/api";
import { getAuthHeaders } from "@/lib/auth";
import { loadStoredTripResult, normalizeDestinationKey, type TripResultStorage, formatDuration } from "@/lib/trip-result";
import type { FullItinerary } from "@/types";

function TripItineraryContent({ tripData }: { tripData: TripResultStorage }) {
  const expectedTripDays = tripData.budget.trip_days ?? tripData.itinerary?.total_days ?? tripData.markers.length ?? 3;
  const storedItineraryMatchesDays = tripData.itinerary?.total_days === expectedTripDays;

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
              distance_km: tripData.distance_km,
              duration_hours: tripData.duration_hours,
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

  return (
    <div className="space-y-6">
      <section className="rounded-[2rem] border border-[#1a1a1a] bg-[#0a0a0a] p-5 shadow-2xl">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-[0.24em] text-[#D4AF37]">Separate Page</p>
            <h1 className="mt-2 text-3xl font-black text-white">Day-by-Day Travel Plan</h1>
            <p className="mt-2 text-sm leading-6 text-[#a0a0a0]">
              {tripData.origin} → {tripData.destination} · {formatDuration(tripData.duration_hours)}
            </p>
          </div>

          <Link
            href="/trip-result"
            className="inline-flex items-center gap-2 rounded-2xl border border-[#2a2a2a] bg-[#111111] px-4 py-3 text-sm font-semibold text-white transition hover:border-[#D4AF37] hover:text-[#D4AF37]"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to overview
          </Link>
        </div>
      </section>

      {itinerary ? (
        <ItineraryPlanner itinerary={itinerary} totalEstimatedCostInr={tripData.budget.total} />
      ) : loading ? (
        <div className="rounded-2xl border border-[#1a1a1a] bg-[#0a0a0a] p-6 text-center">
          <Loader2 className="mx-auto h-5 w-5 animate-spin text-[#D4AF37]" />
          <p className="mt-3 text-sm text-[#888888]">Generating itinerary...</p>
        </div>
      ) : error ? (
        <div className="rounded-2xl border border-[#1a1a1a] bg-[#0a0a0a] p-6 text-center">
          <p className="text-sm text-[#888888]">{error}</p>
        </div>
      ) : (
        <div className="rounded-2xl border border-[#1a1a1a] bg-[#0a0a0a] p-6 text-center">
          <p className="text-sm text-[#888888]">Itinerary generation is unavailable for this trip.</p>
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

    setTripData(stored);
    setLoaded(true);
  }, []);

  return (
    <>
      <Navbar theme={theme} onToggleTheme={() => setTheme((current) => (current === "dark" ? "light" : "dark"))} />
      <main className="min-h-screen overflow-x-hidden bg-black text-white transition-colors">
        <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
          {loaded && tripData ? (
            <TripItineraryContent tripData={tripData} />
          ) : !loaded ? (
            <section className="flex min-h-[60vh] items-center justify-center">
              <div className="max-w-md rounded-[2rem] border border-[#1a1a1a] bg-[#0a0a0a] p-8 text-center shadow-2xl">
                <h1 className="text-2xl font-black text-white">Loading itinerary...</h1>
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
      </main>
    </>
  );
}
