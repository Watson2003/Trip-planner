import Link from "next/link";
import type { LucideIcon } from "lucide-react";
import { ArrowRight, CalendarDays, Clock3, IndianRupee, MapPinned, Sparkles } from "lucide-react";

import { formatDuration, normalizeRecommendations, type TripResultStorage } from "@/lib/trip-result";

function formatMoney(value: number) {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(value || 0);
}

function SummaryStat({
  label,
  value,
  icon: Icon,
}: {
  label: string;
  value: string;
  icon: LucideIcon;
}) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-center gap-2 text-xs uppercase tracking-[0.22em] text-slate-500">
        <Icon className="h-4 w-4 text-blue-600" />
        {label}
      </div>
      <div className="mt-3 text-lg font-bold text-slate-950">{value}</div>
    </div>
  );
}

export default function TripSummaryCard({
  trip,
  onDownloadPdf,
}: {
  trip: TripResultStorage;
  onDownloadPdf?: () => void;
}) {
  const recommendations = normalizeRecommendations(trip.recommendations, trip.destination);
  const attractionCount = recommendations.attractions.length;
  const totalDays = trip.itinerary?.total_days ?? trip.budget.trip_days ?? 0;
  const totalCost = trip.budget.total || 0;
  const dateRange = trip.startDate && trip.endDate ? `${trip.startDate} to ${trip.endDate}` : "Dates not set";

  return (
    <section className="overflow-hidden rounded-[2rem] border border-slate-200 bg-white shadow-xl">
      <div className="grid gap-6 p-5 lg:grid-cols-[1.2fr_0.8fr] lg:p-7">
        <div className="space-y-5">
          <div className="inline-flex items-center gap-2 rounded-full border border-blue-100 bg-blue-50 px-4 py-2 text-xs font-bold uppercase tracking-[0.24em] text-blue-700">
            <Sparkles className="h-4 w-4" />
            Premium trip summary
          </div>

          <div className="space-y-3">
            <p className="text-sm uppercase tracking-[0.28em] text-slate-500">RoadMind AI Trip Overview</p>
            <h1 className="max-w-3xl text-3xl font-black tracking-tight text-slate-950 sm:text-4xl">
              {trip.origin} → {trip.destination}
            </h1>
            <p className="max-w-2xl text-sm leading-7 text-slate-600 sm:text-base">
              Your road trip is planned with route intelligence, destination-specific recommendations, weather, and
              budget insights in one polished dashboard.
            </p>
          </div>

          <div className="flex flex-wrap gap-2">
            <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs text-slate-600">
              {dateRange}
            </span>
            <span className="rounded-full border border-blue-100 bg-blue-50 px-3 py-1.5 text-xs text-blue-700">
              {trip.weather_status === "success" ? "Weather ready" : "Weather limited"}
            </span>
            <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs text-slate-600">
              {attractionCount} attractions discovered
            </span>
          </div>

          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <SummaryStat label="Distance" value={`${Math.round(trip.distance_km)} km`} icon={MapPinned} />
            <SummaryStat label="Duration" value={formatDuration(trip.duration_hours)} icon={Clock3} />
            <SummaryStat label="Days" value={`${totalDays} day${totalDays === 1 ? "" : "s"}`} icon={CalendarDays} />
            <SummaryStat label="Budget" value={formatMoney(totalCost)} icon={IndianRupee} />
          </div>

          <div className="flex flex-wrap gap-3">
            <Link
              href="/trip-result/itinerary"
              className="inline-flex items-center justify-center gap-2 rounded-2xl bg-[#0071e3] px-5 py-3 text-sm font-bold text-white transition hover:bg-[#0077ed]"
            >
              Open Day-by-Day Plan
              <ArrowRight className="h-4 w-4" />
            </Link>
            {onDownloadPdf ? (
              <button
                type="button"
                onClick={onDownloadPdf}
                className="inline-flex items-center justify-center rounded-2xl border border-slate-200 bg-white px-5 py-3 text-sm font-semibold text-slate-700 transition hover:border-blue-200 hover:bg-slate-50 hover:text-slate-950"
              >
                Download PDF
              </button>
            ) : null}
          </div>
        </div>

        <div className="rounded-[1.75rem] border border-slate-200 bg-slate-50 p-5">
          <div className="grid gap-3">
            <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
              <div className="text-xs uppercase tracking-[0.22em] text-slate-500">Top attractions</div>
              <div className="mt-3 flex flex-wrap gap-2">
                {recommendations.attractions.slice(0, 3).map((place, index) => (
                  <span
                    key={`${place.place_id ?? place.name}-${index}`}
                    className="rounded-full border border-blue-100 bg-blue-50 px-3 py-1.5 text-xs font-medium text-blue-700"
                  >
                    {place.name}
                  </span>
                ))}
                {!recommendations.attractions.length ? (
                  <span className="text-sm text-slate-500">Attraction recommendations will appear here.</span>
                ) : null}
              </div>
            </div>

            <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
              <div className="text-xs uppercase tracking-[0.22em] text-slate-500">Trip intelligence</div>
              <div className="mt-3 space-y-3 text-sm leading-6 text-slate-600">
                <p>
                  <span className="font-semibold text-slate-950">Route:</span> {trip.origin} to {trip.destination}
                </p>
                <p>
                  <span className="font-semibold text-slate-950">Cost posture:</span> Budget-aware plan with live
                  route, food, hotel, and activity allocation.
                </p>
                <p>
                  <span className="font-semibold text-slate-950">Itinerary readiness:</span>{" "}
                  {trip.itinerary?.days?.length ? `${trip.itinerary.days.length} day plan loaded` : "Itinerary will be generated on demand"}
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
