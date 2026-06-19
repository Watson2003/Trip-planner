import Link from "next/link";
import { ArrowRight, CalendarDays, MapPinned, Sparkles } from "lucide-react";

import { normalizeRecommendations, type TripResultStorage } from "@/lib/trip-result";

function normalizePlaceName(value: string) {
  return value
    .toLowerCase()
    .replace(/[\u2018\u2019`']/g, "")
    .replace(/\b(visit|explore|discover|see|lunch|dinner|breakfast|check in at|check-in at|stay at|hotel|restaurant|guest house|guesthouse)\b/g, "")
    .replace(/[^a-z0-9]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function getDayPlaces(day: NonNullable<TripResultStorage["itinerary"]>["days"][number]) {
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

function StatChip({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3 shadow-sm">
      <div className="text-[11px] uppercase tracking-[0.24em] text-slate-500">{label}</div>
      <div className="mt-1 text-sm font-semibold text-slate-950">{value}</div>
    </div>
  );
}

export default function ItineraryPreview({ trip }: { trip: TripResultStorage }) {
  const recommendations = normalizeRecommendations(trip.recommendations, trip.destination);
  const dayOne = trip.itinerary?.days?.[0];
  const dayOnePlaces = dayOne ? getDayPlaces(dayOne).slice(0, 3) : [];
  const dayCount = trip.itinerary?.total_days ?? trip.budget.trip_days ?? 0;

  return (
    <section className="overflow-hidden rounded-[2rem] border border-slate-200 bg-white shadow-xl">
      <div className="grid gap-6 p-5 lg:grid-cols-[1.1fr_0.9fr] lg:p-7">
        <div className="space-y-5">
          <div className="inline-flex items-center gap-2 rounded-full border border-blue-100 bg-blue-50 px-4 py-2 text-xs font-bold uppercase tracking-[0.24em] text-blue-700">
            <CalendarDays className="h-4 w-4" />
            Trip preview
          </div>

          <div className="space-y-3">
            <p className="text-sm uppercase tracking-[0.28em] text-slate-500">Home itinerary snapshot</p>
            <h2 className="text-2xl font-black tracking-tight text-slate-950 sm:text-3xl">Day 1 summary for {trip.destination}</h2>
            <p className="max-w-2xl text-sm leading-7 text-slate-600">
              This is a clean preview only. The full itinerary stays on the separate Day-by-Day Plan page so the home
              screen remains focused and fast.
            </p>
          </div>

          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <StatChip label="Destination" value={trip.destination} />
            <StatChip label="Days" value={`${dayCount} day${dayCount === 1 ? "" : "s"}`} />
            <StatChip label="Attractions" value={`${recommendations.attractions.length} planned`} />
            <StatChip label="Stops" value={dayOne?.time_slots?.length ? `${dayOne.time_slots.length} day 1 stops` : "Preview ready"} />
          </div>

          <div className="flex flex-wrap gap-3">
            <Link
              href="/trip-result"
              className="inline-flex items-center justify-center gap-2 rounded-2xl border border-slate-200 bg-white px-5 py-3 text-sm font-semibold text-slate-700 transition hover:border-blue-200 hover:bg-slate-50 hover:text-slate-950"
            >
              View Full Trip
              <ArrowRight className="h-4 w-4" />
            </Link>
            <Link
              href="/trip-result/itinerary"
              className="inline-flex items-center justify-center gap-2 rounded-2xl bg-[#0071e3] px-5 py-3 text-sm font-bold text-white transition hover:bg-[#0077ed]"
            >
              Open Full Itinerary
              <Sparkles className="h-4 w-4" />
            </Link>
          </div>
        </div>

        <div className="rounded-[1.75rem] border border-slate-200 bg-slate-50 p-5">
          <div className="space-y-4">
            <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <div className="text-xs uppercase tracking-[0.22em] text-slate-500">Day 1</div>
                  <h3 className="mt-1 text-lg font-bold text-slate-950">{dayOne?.day_title ?? "Itinerary preview"}</h3>
                </div>
                <div className="inline-flex items-center gap-2 rounded-full border border-blue-100 bg-blue-50 px-3 py-1.5 text-xs font-semibold text-blue-700">
                  <MapPinned className="h-3.5 w-3.5" />
                  Preview only
                </div>
              </div>
              <p className="mt-3 text-sm leading-6 text-slate-600">
                {dayOne?.summary ?? "Your trip preview will appear here once planning is complete."}
              </p>
            </div>

            <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
              <div className="text-xs uppercase tracking-[0.22em] text-slate-500">Top places</div>
              <div className="mt-3 flex flex-wrap gap-2">
                {(dayOnePlaces.length ? dayOnePlaces : recommendations.attractions.slice(0, 3).map((place) => place.name)).map(
                  (place) => (
                    <span
                      key={place}
                      className="rounded-full border border-blue-100 bg-blue-50 px-3 py-1.5 text-xs text-blue-700"
                    >
                      {place}
                    </span>
                  ),
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
