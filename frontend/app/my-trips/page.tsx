"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  ArrowRight,
  CalendarDays,
  ChevronDown,
  ChevronUp,
  FileDown,
  IndianRupee,
  Loader2,
  Route,
} from "lucide-react";

import AuthGuard from "@/components/auth/AuthGuard";
import Navbar from "@/components/auth/Navbar";
import { normalizeRecommendations } from "@/lib/trip-result";
import { API_BASE_URL } from "@/lib/api";
import { getAuthHeaders } from "@/lib/auth";
import type { RecommendationPayload } from "@/types";

type TripSummary = {
  id: number;
  origin: string;
  destination: string;
  dates?: {
    start: string;
    end: string;
  } | null;
  budget?: number | null;
  created_at: string;
};

type TripDetailResponse = {
  recommendations?: RecommendationPayload;
};

function formatDate(value?: string | null) {
  if (!value) return "Not set";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function LoadingCard() {
  return (
    <div className="rounded-[1.75rem] border border-[#1a1a1a] bg-[#0a0a0a] p-5 shadow-2xl shadow-black/30 backdrop-blur-xl">
      <div className="animate-pulse space-y-4">
        <div className="flex items-center justify-between">
          <div className="h-5 w-36 rounded bg-white/10" />
          <Loader2 className="h-5 w-5 animate-spin text-white" />
        </div>
        <div className="h-8 w-3/4 rounded bg-white/10" />
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="h-12 rounded-2xl bg-white/10" />
          <div className="h-12 rounded-2xl bg-white/10" />
        </div>
        <div className="h-10 rounded-2xl bg-white/10" />
      </div>
    </div>
  );
}

function RecommendationPreview({
  recommendations,
  loading,
  error,
}: {
  recommendations: RecommendationPayload;
  loading: boolean;
  error: string;
}) {
  const normalized = normalizeRecommendations(recommendations);

  if (loading) {
    return (
      <div className="grid gap-3 md:grid-cols-2">
        <div className="h-32 rounded-2xl bg-white/10 animate-pulse" />
        <div className="h-32 rounded-2xl bg-white/10 animate-pulse" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-2xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-200">
        {error}
      </div>
    );
  }

  if (!normalized.hotels.length && !normalized.restaurants.length && !normalized.attractions.length) {
    return (
      <div className="rounded-2xl border border-[#1a1a1a] bg-[#111111] px-4 py-3 text-sm text-[#888888]">
        No recommendation details available for this trip yet.
      </div>
    );
  }

  return (
    <div className="grid gap-3 md:grid-cols-2">
      <div className="rounded-2xl border border-[#1a1a1a] bg-[#111111] p-4">
        <div className="text-sm font-bold text-white">{normalized.destination || "Destination recommendations"}</div>
        <div className="mt-3 space-y-3 text-sm text-[#a0a0a0]">
          <div>
            <div className="text-[11px] uppercase tracking-[0.18em] text-white">Hotel</div>
            <div className="mt-1 font-semibold text-white">{normalized.hotels[0]?.name ?? "No hotel suggestion"}</div>
          </div>
          <div>
            <div className="text-[11px] uppercase tracking-[0.18em] text-[#a0a0a0]">Restaurant</div>
            <div className="mt-1 font-semibold text-white">
              {normalized.restaurants[0]?.name ?? "No restaurant suggestion"}
            </div>
          </div>
          <div>
            <div className="text-[11px] uppercase tracking-[0.18em] text-[#a0a0a0]">Attraction</div>
            <div className="mt-1 font-semibold text-white">
              {normalized.attractions[0]?.name ?? "No attraction suggestion"}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function MyTripsPage() {
  const [trips, setTrips] = useState<TripSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [expandedTrips, setExpandedTrips] = useState<number[]>([]);
  const [recommendationsByTripId, setRecommendationsByTripId] = useState<Record<number, RecommendationPayload>>({});
  const [loadingRecommendations, setLoadingRecommendations] = useState<Record<number, boolean>>({});
  const [recommendationErrors, setRecommendationErrors] = useState<Record<number, string>>({});

  useEffect(() => {
    let cancelled = false;

    async function loadTrips() {
      setLoading(true);
      setError("");

      try {
        const response = await fetch(`${API_BASE_URL}/api/trip/my-trips`, {
          headers: {
            ...getAuthHeaders(),
          },
        });

        if (!response.ok) {
          const payload = await response.json().catch(() => null);
          throw new Error(typeof payload?.detail === "string" ? payload.detail : "Unable to load your trips.");
        }

        const data = (await response.json()) as TripSummary[];
        if (!cancelled) setTrips(data);
      } catch (fetchError) {
        if (!cancelled) {
          setError(fetchError instanceof Error ? fetchError.message : "Unable to load your trips.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    loadTrips();

    return () => {
      cancelled = true;
    };
  }, []);

  async function loadRecommendations(tripId: number) {
    if (recommendationsByTripId[tripId] || loadingRecommendations[tripId]) return;

    setLoadingRecommendations((current) => ({ ...current, [tripId]: true }));
    setRecommendationErrors((current) => ({ ...current, [tripId]: "" }));

    try {
      const response = await fetch(`${API_BASE_URL}/api/trip/${tripId}`, {
        headers: {
          ...getAuthHeaders(),
        },
      });

      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(typeof payload?.detail === "string" ? payload.detail : "Unable to load recommendations.");
      }

      const detail = (await response.json()) as TripDetailResponse;
      setRecommendationsByTripId((current) => ({
        ...current,
        [tripId]: detail.recommendations ?? [],
      }));
    } catch (fetchError) {
      setRecommendationErrors((current) => ({
        ...current,
        [tripId]: fetchError instanceof Error ? fetchError.message : "Unable to load recommendations.",
      }));
    } finally {
      setLoadingRecommendations((current) => ({ ...current, [tripId]: false }));
    }
  }

  function toggleRecommendations(tripId: number) {
    setExpandedTrips((current) =>
      current.includes(tripId) ? current.filter((id) => id !== tripId) : [...current, tripId],
    );
    void loadRecommendations(tripId);
  }

  async function downloadPdf(tripId: number) {
    const response = await fetch(`${API_BASE_URL}/api/trip/${tripId}/pdf`, {
      headers: {
        ...getAuthHeaders(),
      },
    });

    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      throw new Error(typeof payload?.detail === "string" ? payload.detail : "Unable to download PDF");
    }

    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `trip-report-${tripId}.pdf`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  return (
    <AuthGuard>
      <div className="min-h-screen bg-black text-white">
        <Navbar />

        <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
          <section className="mb-8 overflow-hidden rounded-[2rem] border border-[#1a1a1a] bg-[#0a0a0a] p-6 shadow-2xl shadow-black/30 sm:p-8">
            <div className="max-w-3xl space-y-4">
              <div className="inline-flex items-center gap-2 rounded-full border border-[#D4AF37]/30 bg-[#D4AF37]/10 px-4 py-2 text-sm font-semibold text-[#D4AF37]">
                <Route className="h-4 w-4" />
                My Trips
              </div>
              <h1 className="text-3xl font-black tracking-tight sm:text-4xl">Your saved road trip plans</h1>
              <p className="max-w-2xl text-sm leading-6 text-[#a0a0a0] sm:text-base">
                Browse every trip you&apos;ve planned, review when each one was created, and download the PDF
                whenever you need the report again.
              </p>
            </div>
          </section>

          {loading ? (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
              <LoadingCard />
              <LoadingCard />
            </div>
          ) : error ? (
            <div className="rounded-[1.75rem] border border-red-500/20 bg-red-500/10 px-5 py-4 text-sm text-red-200">
              {error}
            </div>
          ) : trips.length === 0 ? (
            <section className="flex min-h-[40vh] w-full flex-col items-center justify-center rounded-[2rem] border border-[#1a1a1a] bg-[#0a0a0a] px-6 py-20 text-center">
              <div className="mb-5 flex h-20 w-20 items-center justify-center rounded-full bg-[#D4AF37]/10 text-[#D4AF37] ring-1 ring-[#D4AF37]/30">
                <Route className="h-10 w-10" />
              </div>
              <h2 className="text-2xl font-black tracking-tight">No trips yet</h2>
              <p className="mt-3 max-w-md text-sm leading-6 text-[#888888]">
                Plan your first route and it will appear here with the download link and trip details.
              </p>
              <Link
                href="/"
                className="mt-6 inline-flex items-center gap-2 rounded-2xl bg-[#D4AF37] px-5 py-3 text-sm font-bold text-black transition hover:bg-[#B8860B]"
              >
                Plan Your First Trip
              </Link>
            </section>
          ) : (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {trips.map((trip) => (
                <article
                  key={trip.id}
                  className="w-full overflow-hidden rounded-[1.75rem] border border-[#1a1a1a] bg-[#0a0a0a] p-5 shadow-2xl shadow-black/20 backdrop-blur-xl"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <div className="text-xs uppercase tracking-[0.24em] text-[#888888]">Trip #{trip.id}</div>
                      <h2 className="mt-2 flex flex-wrap items-center gap-2 text-2xl font-black tracking-tight">
                        <span>{trip.origin}</span>
                        <ArrowRight className="h-5 w-5 text-white" />
                        <span>{trip.destination}</span>
                      </h2>
                    </div>

                    <div className="rounded-full border border-[#D4AF37]/20 bg-[#D4AF37]/10 px-3 py-2 text-xs font-semibold text-[#D4AF37]">
                      Saved
                    </div>
                  </div>

                  <div className="mt-5 grid gap-3 sm:grid-cols-2">
                    <div className="rounded-2xl border border-[#1a1a1a] bg-[#111111] p-4">
                      <div className="flex items-center gap-2 text-xs uppercase tracking-[0.2em] text-[#D4AF37]">
                        <CalendarDays className="h-3.5 w-3.5" />
                        Travel Dates
                      </div>
                      <div className="mt-2 text-sm font-semibold text-white">
                        {formatDate(trip.dates?.start)} - {formatDate(trip.dates?.end)}
                      </div>
                    </div>

                    <div className="rounded-2xl border border-[#1a1a1a] bg-[#111111] p-4">
                      <div className="flex items-center gap-2 text-xs uppercase tracking-[0.2em] text-[#D4AF37]">
                        <IndianRupee className="h-3.5 w-3.5" />
                        Total Budget
                      </div>
                      <div className="mt-2 text-sm font-semibold text-white">
                        {"\u20b9"}
                        {Math.round(trip.budget ?? 0).toLocaleString("en-IN")}
                      </div>
                    </div>
                  </div>

                  <div className="mt-4 rounded-2xl border border-[#1a1a1a] bg-[#111111] p-4">
                    <div className="text-xs uppercase tracking-[0.2em] text-[#D4AF37]">Created</div>
                    <div className="mt-2 text-sm font-semibold text-white">{formatDate(trip.created_at)}</div>
                  </div>

                  <div className="mt-5 flex flex-col gap-2 sm:flex-row">
                    <button
                      type="button"
                      onClick={() => {
                        downloadPdf(trip.id).catch((downloadError) => {
                          setError(downloadError instanceof Error ? downloadError.message : "Unable to download PDF");
                        });
                      }}
                      className="inline-flex w-full flex-1 items-center justify-center gap-2 rounded-2xl bg-[#D4AF37] px-5 py-3 text-sm font-bold text-black transition hover:bg-[#B8860B]"
                    >
                      <FileDown className="h-4 w-4" />
                      Download PDF
                    </button>

                    <button
                      type="button"
                      onClick={() => toggleRecommendations(trip.id)}
                      className="inline-flex w-full flex-1 items-center justify-center gap-2 rounded-2xl border border-[#D4AF37]/30 bg-transparent px-5 py-3 text-sm font-semibold text-[#D4AF37] transition hover:bg-[#D4AF37]/10"
                    >
                      View Recommendations
                      {expandedTrips.includes(trip.id) ? (
                        <ChevronUp className="h-4 w-4" />
                      ) : (
                        <ChevronDown className="h-4 w-4" />
                      )}
                    </button>
                  </div>

                  {expandedTrips.includes(trip.id) ? (
                    <div className="mt-4 space-y-4 rounded-3xl border border-[#1a1a1a] bg-[#111111] p-4">
                      <RecommendationPreview
                        recommendations={recommendationsByTripId[trip.id] ?? []}
                        loading={Boolean(loadingRecommendations[trip.id])}
                        error={recommendationErrors[trip.id] ?? ""}
                      />
                      <button
                        type="button"
                        className="inline-flex w-full items-center justify-center rounded-2xl bg-[#D4AF37] px-5 py-3 text-sm font-bold text-black transition hover:bg-[#B8860B]"
                      >
                        See Full Trip
                      </button>
                    </div>
                  ) : null}
                </article>
              ))}
            </div>
          )}
        </main>
      </div>
    </AuthGuard>
  );
}
