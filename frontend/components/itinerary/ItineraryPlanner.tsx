"use client";

import { useState } from "react";
import type { ComponentType, SVGProps } from "react";
import {
  ArrowUpRight,
  CarFront,
  Clock3,
  Fuel,
  Hotel,
  IndianRupee,
  MapPinned,
  MoonStar,
  ShoppingBag,
  Sparkles,
  UtensilsCrossed,
  Waypoints,
} from "lucide-react";

import type { DayItinerary, FullItinerary, TimeSlot } from "@/types";

interface Props {
  itinerary: FullItinerary;
  totalEstimatedCostInr?: number;
}

type SlotCategory = NonNullable<TimeSlot["type"] | TimeSlot["category"]>;

type CategoryConfig = {
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  label: string;
  accent: string;
  card: string;
  border: string;
  text: string;
  chip: string;
};

const CATEGORY_CONFIG: Record<SlotCategory, CategoryConfig> = {
  drive: {
    icon: CarFront,
    label: "Drive",
    accent: "text-blue-700",
    card: "bg-blue-50",
    border: "border-blue-200",
    text: "text-blue-700",
    chip: "bg-blue-100 text-blue-700 border-blue-200",
  },
  breakfast: {
    icon: UtensilsCrossed,
    label: "Breakfast",
    accent: "text-amber-700",
    card: "bg-amber-50",
    border: "border-amber-200",
    text: "text-amber-700",
    chip: "bg-amber-100 text-amber-700 border-amber-200",
  },
  lunch: {
    icon: UtensilsCrossed,
    label: "Lunch",
    accent: "text-yellow-700",
    card: "bg-yellow-50",
    border: "border-yellow-200",
    text: "text-yellow-700",
    chip: "bg-yellow-100 text-yellow-700 border-yellow-200",
  },
  dinner: {
    icon: UtensilsCrossed,
    label: "Dinner",
    accent: "text-rose-700",
    card: "bg-rose-50",
    border: "border-rose-200",
    text: "text-rose-700",
    chip: "bg-rose-100 text-rose-700 border-rose-200",
  },
  attraction: {
    icon: Sparkles,
    label: "Attraction",
    accent: "text-emerald-700",
    card: "bg-emerald-50",
    border: "border-emerald-200",
    text: "text-emerald-700",
    chip: "bg-emerald-100 text-emerald-700 border-emerald-200",
  },
  sightseeing: {
    icon: Sparkles,
    label: "Attraction",
    accent: "text-emerald-700",
    card: "bg-emerald-50",
    border: "border-emerald-200",
    text: "text-emerald-700",
    chip: "bg-emerald-100 text-emerald-700 border-emerald-200",
  },
  hotel: {
    icon: Hotel,
    label: "Hotel",
    accent: "text-purple-700",
    card: "bg-purple-50",
    border: "border-purple-200",
    text: "text-purple-700",
    chip: "bg-purple-100 text-purple-700 border-purple-200",
  },
  shopping: {
    icon: ShoppingBag,
    label: "Shopping",
    accent: "text-slate-700",
    card: "bg-slate-50",
    border: "border-slate-200",
    text: "text-slate-700",
    chip: "bg-slate-100 text-slate-700 border-slate-200",
  },
  rest: {
    icon: MoonStar,
    label: "Rest",
    accent: "text-slate-700",
    card: "bg-slate-50",
    border: "border-slate-200",
    text: "text-slate-700",
    chip: "bg-slate-100 text-slate-700 border-slate-200",
  },
  fuel: {
    icon: Fuel,
    label: "Fuel Stop",
    accent: "text-orange-700",
    card: "bg-orange-50",
    border: "border-orange-200",
    text: "text-orange-700",
    chip: "bg-orange-100 text-orange-700 border-orange-200",
  },
  misc: {
    icon: Waypoints,
    label: "Activity",
    accent: "text-slate-700",
    card: "bg-slate-50",
    border: "border-slate-200",
    text: "text-slate-700",
    chip: "bg-slate-100 text-slate-700 border-slate-200",
  },
};

function formatCurrency(value: number) {
  return Math.round(value).toLocaleString("en-IN");
}

function normalizePlaceLabel(value: string) {
  return value
    .toLowerCase()
    .replace(/[\u2018\u2019`']/g, "")
    .replace(/\b(visit|explore|discover|see|lunch|dinner|breakfast|check in at|check-in at|stay at|hotel|restaurant|guest house|guesthouse)\b/g, "")
    .replace(/[^a-z0-9]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function getSlotLabel(slot: TimeSlot) {
  return slot.place_name || slot.title || slot.activity || "Planned stop";
}

function getSlotCategory(slot: TimeSlot): SlotCategory {
  return (slot.type ?? slot.category ?? "misc") as SlotCategory;
}

function getMapUrl(slot: TimeSlot) {
  const latitude = slot.latitude ?? undefined;
  const longitude = slot.longitude ?? undefined;
  if (latitude == null || longitude == null) return "";
  const label = encodeURIComponent(getSlotLabel(slot));
  return `https://www.openstreetmap.org/?mlat=${latitude}&mlon=${longitude}#map=15/${latitude}/${longitude}&query=${label}`;
}

function getSlotKey(slot: TimeSlot, index: number) {
  const base = normalizePlaceLabel(getSlotLabel(slot));
  return `${slot.time}-${slot.type ?? slot.category ?? "misc"}-${base || index}`;
}

function dedupeSlots(slots: TimeSlot[]) {
  const seen = new Set<string>();
  const result: TimeSlot[] = [];
  for (const slot of slots) {
    const category = getSlotCategory(slot);
    const label = normalizePlaceLabel(getSlotLabel(slot));
    const isMeaningfulStop = Boolean(label) && category !== "drive";
    const key = isMeaningfulStop ? `${category}:${label}` : `${category}:${slot.time}:${result.length}`;
    if (isMeaningfulStop && seen.has(key)) continue;
    if (isMeaningfulStop) seen.add(key);
    result.push(slot);
  }
  return result;
}

function TimeSlotRow({
  slot,
  expanded,
  onToggle,
}: {
  slot: TimeSlot;
  expanded: boolean;
  onToggle: () => void;
}) {
  const slotType = getSlotCategory(slot);
  const config = CATEGORY_CONFIG[slotType] ?? CATEGORY_CONFIG.misc;
  const title = slot.title || slot.activity || "Planned stop";
  const placeName = slot.place_name || "";
  const reason = slot.reason || slot.description || "";
  const duration = slot.estimated_duration_minutes || slot.duration_minutes || 0;
  const cost = slot.cost_inr || slot.estimated_cost_inr || 0;
  const nearbyPlaces = slot.nearby_places || [];
  const mapUrl = getMapUrl(slot);
  const isAttraction = slotType === "attraction" || slotType === "sightseeing";
  const hasCoords = Boolean(mapUrl);

  return (
    <div className="relative flex gap-4 max-sm:gap-3">
      <div className="relative z-10 flex h-14 w-14 flex-shrink-0 flex-col items-center justify-center rounded-full border border-slate-300 bg-white text-center shadow-md">
        <config.icon className={`h-5 w-5 ${config.accent}`} />
        <span className="mt-0.5 text-[10px] leading-tight text-slate-500">{slot.time}</span>
      </div>

      <div
        className={[
          "mb-1 flex-1 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-md transition-all duration-300 hover:scale-[1.01] hover:border-blue-200 hover:shadow-xl",
        ].join(" ")}
      >
        <button type="button" onClick={onToggle} className="w-full p-4 text-left sm:p-5">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className={`rounded-full border px-2.5 py-1 text-[11px] font-semibold ${config.chip}`}>
                  {config.label}
                </span>
                {slot.best_time_to_visit ? (
                  <span className="rounded-full border border-blue-100 bg-blue-50 px-2.5 py-1 text-[11px] text-blue-700">
                    Best: {slot.best_time_to_visit}
                  </span>
                ) : null}
                {duration > 0 ? (
                  <span className="inline-flex items-center gap-1 text-xs text-slate-500">
                    <Clock3 className="h-3.5 w-3.5" />
                    {duration} min
                  </span>
                ) : null}
                {cost > 0 ? (
                  <span className="inline-flex items-center gap-1 rounded-full border border-blue-100 bg-blue-50 px-2.5 py-1 text-xs text-blue-700">
                    <IndianRupee className="h-3.5 w-3.5" />
                    {formatCurrency(cost)}
                  </span>
                ) : null}
              </div>

              <p className={`mt-2 break-words text-base font-semibold ${isAttraction ? "text-[#0B1120]" : "text-[#0B1120]"}`}>
                {title}
              </p>

              {placeName ? (
                <p className="mt-1 break-words text-sm font-medium text-blue-600">{placeName}</p>
              ) : null}

              <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-500">
                <span className="inline-flex items-center gap-1">
                  <MapPinned className="h-3.5 w-3.5" />
                  {slot.location || "Location unavailable"}
                </span>
                {slot.travel_time_minutes != null ? (
                  <span className="inline-flex items-center gap-1">
                    <Waypoints className="h-3.5 w-3.5" />
                    Travel {slot.travel_time_minutes} min
                  </span>
                ) : null}
              </div>

              <p className="mt-2 text-xs text-slate-500">
                {slot.current_location_before || slot.current_location_after
                  ? `${slot.current_location_before || "Unknown"} -> ${slot.current_location_after || "Unknown"}`
                  : "Location flow unavailable"}
              </p>
            </div>

            <div className="flex shrink-0 items-center gap-2">
              {hasCoords ? (
                <a
                  href={mapUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-[#0B1120] shadow-sm transition hover:bg-slate-100"
                  onClick={(event) => event.stopPropagation()}
                >
                  <ArrowUpRight className="h-3.5 w-3.5" />
                  View on Map
                </a>
              ) : null}
              <span className="text-xs text-slate-500">{expanded ? "Hide" : "Details"}</span>
            </div>
          </div>
        </button>

        {expanded ? (
          <div className="border-t border-slate-200 px-4 pb-4 pt-3 sm:px-5">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500">
                  {isAttraction ? "Why visit" : "Why this stop"}
                </p>
                <p className="mt-2 text-sm leading-6 text-slate-600">{reason || "A practical stop on the route."}</p>
              </div>

              <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500">Trip details</p>
                <div className="mt-2 grid gap-2 text-xs text-slate-500">
                  <div className="flex items-center justify-between gap-3">
                    <span>Duration</span>
                    <span className="text-[#0B1120]">{duration > 0 ? `${duration} min` : "Flexible"}</span>
                  </div>
                  <div className="flex items-center justify-between gap-3">
                    <span>Cost</span>
                    <span className="text-[#0B1120]">{cost > 0 ? `INR ${formatCurrency(cost)}` : "Included"}</span>
                  </div>
                  <div className="flex items-center justify-between gap-3">
                    <span>Time</span>
                    <span className="text-[#0B1120]">{slot.time || "TBA"}</span>
                  </div>
                </div>
              </div>
            </div>

            {nearbyPlaces.length > 0 ? (
              <div className="mt-3">
                <p className="mb-2 text-[11px] uppercase tracking-[0.18em] text-slate-500">Nearby places</p>
                <div className="flex flex-wrap gap-2">
                  {nearbyPlaces.map((place) => (
                    <span
                      key={`${slot.time}-${place}`}
                      className="rounded-full border border-blue-100 bg-blue-50 px-3 py-1 text-xs text-blue-700 transition hover:bg-slate-100"
                    >
                      {place}
                    </span>
                  ))}
                </div>
              </div>
            ) : null}

            <div className="mt-3 grid gap-2 text-xs sm:grid-cols-2">
              <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2">
                <span className="block text-slate-500">Before</span>
                <span className="block break-words text-[#0B1120]">{slot.current_location_before || "Unknown"}</span>
              </div>
              <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2">
                <span className="block text-slate-500">After</span>
                <span className="block break-words text-[#0B1120]">{slot.current_location_after || "Unknown"}</span>
              </div>
            </div>

            {slot.tips ? (
              <div className="mt-3 rounded-xl border border-blue-100 bg-blue-50 p-3">
                <p className="text-xs leading-6 text-blue-700">
                  <span className="font-semibold">Tip:</span> {slot.tips}
                </p>
              </div>
            ) : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}

function DayPanel({ day, itinerary }: { day: DayItinerary; itinerary: FullItinerary }) {
  const [expandedSlots, setExpandedSlots] = useState<Set<string>>(new Set());
  const uniqueSlots = dedupeSlots(day.time_slots || []);
  const attractionCount = uniqueSlots.filter((slot) => {
    const category = getSlotCategory(slot);
    return category === "attraction" || category === "sightseeing";
  }).length;
  const hasSlots = uniqueSlots.length > 0;

  const toggleSlot = (key: string) => {
    setExpandedSlots((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  };

  return (
    <div className="p-4 sm:p-6">
      <div className="mb-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <h3 className="break-words text-xl font-bold text-[#0B1120]">{day.day_title}</h3>
            <p className="mt-1 text-sm leading-6 text-slate-600">{day.summary}</p>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-right shadow-sm">
            <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500">Today</p>
            <p className="mt-1 text-sm font-semibold text-[#0B1120]">{attractionCount} places planned today</p>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap gap-3">
          {day.distance_km > 0 ? (
            <span className="rounded-full border border-blue-100 bg-blue-50 px-3 py-1.5 text-xs text-blue-700">
              Drive: {day.distance_km} km
            </span>
          ) : null}
          {day.driving_hours > 0 ? (
            <span className="rounded-full border border-blue-100 bg-blue-50 px-3 py-1.5 text-xs text-blue-700">
              Travel time: {day.driving_hours} hrs
            </span>
          ) : null}
          <span className="rounded-full border border-blue-100 bg-blue-50 px-3 py-1.5 text-xs text-blue-700">
            Est. cost: INR {formatCurrency(day.day_total_cost_inr)}
          </span>
          <span className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-600 shadow-sm">
            {uniqueSlots.length} items planned
          </span>
        </div>

        {day.highlights.length > 0 ? (
          <div className="mt-4 flex flex-wrap gap-2">
            {day.highlights.map((highlight, index) => (
              <span
                key={`${day.day_number}-highlight-${index}`}
                className="rounded-full border border-blue-100 bg-blue-50 px-3 py-1 text-xs text-blue-700 transition hover:bg-slate-100"
              >
                {highlight}
              </span>
            ))}
          </div>
        ) : null}
      </div>

      {hasSlots ? (
        <div className="relative">
          <div className="absolute bottom-0 left-[27px] top-0 w-0.5 bg-slate-200" />
          <div className="space-y-3">
            {uniqueSlots.map((slot, index) => {
              const key = getSlotKey(slot, index);
              return (
                <TimeSlotRow
                  key={key}
                  slot={slot}
                  expanded={expandedSlots.has(key)}
                  onToggle={() => toggleSlot(key)}
                />
              );
            })}
          </div>
        </div>
      ) : (
        <div className="rounded-2xl border border-dashed border-slate-200 bg-white px-5 py-8 text-center">
          <p className="text-sm font-medium text-[#0B1120]">No places planned for this day yet.</p>
          <p className="mt-2 text-sm text-slate-500">
            The itinerary will show attractions, meals, and route stops here once they are available.
          </p>
        </div>
      )}
    </div>
  );
}

export default function ItineraryPlanner({ itinerary, totalEstimatedCostInr }: Props) {
  const [activeDay, setActiveDay] = useState(0);
  const [showTips, setShowTips] = useState(false);

  const hasDays = itinerary.days.length > 0;
  const currentDay = itinerary.days[activeDay];
  const resolvedTotal =
    typeof totalEstimatedCostInr === "number" && Number.isFinite(totalEstimatedCostInr)
      ? totalEstimatedCostInr
      : itinerary.total_itinerary_cost_inr;

  return (
    <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-xl">
      <div className="border-b border-slate-200 px-5 py-5 sm:px-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="mb-1 text-xs font-medium uppercase tracking-widest text-blue-700">AI ITINERARY</p>
            <h2 className="text-heading text-2xl font-bold">Day-by-Day Travel Plan</h2>
            <p className="mt-2 text-sm text-slate-600">
              {itinerary.origin} {"->"} {itinerary.destination} Â· {itinerary.total_days} Days Â· {itinerary.start_date} to{" "}
              {itinerary.end_date}
            </p>
          </div>
          <div className="text-right">
            <p className="text-xs text-slate-500">Total Estimated Cost</p>
            <p className="text-xl font-bold text-[#0B1120]">INR {formatCurrency(resolvedTotal)}</p>
          </div>
        </div>
      </div>

      <div className="flex overflow-x-auto border-b border-slate-200 bg-slate-50">
        {itinerary.days.map((day, index) => (
          <button
            key={`${day.day_number}-${day.date}`}
            type="button"
            onClick={() => setActiveDay(index)}
            className={`flex-shrink-0 border-b-2 px-5 py-4 text-sm font-medium whitespace-nowrap transition-all ${
              activeDay === index
                ? "border-[#0071e3] bg-[#0071e3] text-white shadow-md"
                : "border-transparent bg-white text-slate-600 hover:bg-slate-100"
            }`}
          >
            <div className="mb-0.5 text-xs opacity-70">{day.date}</div>
            <div>Day {day.day_number}</div>
          </button>
        ))}
      </div>

      {hasDays && currentDay ? (
        <DayPanel day={currentDay} itinerary={itinerary} />
      ) : (
        <div className="px-6 py-10">
          <div className="rounded-2xl border border-dashed border-slate-200 bg-white p-8 text-center">
            <p className="text-lg font-semibold text-[#0B1120]">No itinerary days available.</p>
            <p className="mt-2 text-sm leading-6 text-slate-500">
              We could not find any places to show for this trip yet.
            </p>
          </div>
        </div>
      )}

      {itinerary.travel_tips.length > 0 ? (
        <div className="border-t border-slate-200 px-5 py-4 sm:px-6">
          <button
            type="button"
            onClick={() => setShowTips((current) => !current)}
            className="flex w-full items-center justify-between text-left"
          >
            <span className="flex items-center gap-2 font-medium text-blue-700">
              <Sparkles className="h-4 w-4" />
              Travel Tips ({itinerary.travel_tips.length})
            </span>
            <span className="text-sm text-slate-500">{showTips ? "Hide" : "Show"}</span>
          </button>

          {showTips ? (
            <div className="mt-3 space-y-2">
              {itinerary.travel_tips.map((tip, index) => (
                <div key={`${index}-${tip}`} className="flex items-start gap-3 rounded-xl border border-slate-200 bg-slate-50 p-3">
                  <span className="flex-shrink-0 text-sm font-bold text-blue-700">{index + 1}.</span>
                  <p className="text-sm text-slate-600">{tip}</p>
                </div>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}

      <div className="border-t border-slate-200 bg-slate-50 px-6 py-3">
        <p className="text-center text-xs text-slate-500">
          Generated by RoadMind AI Â· {itinerary.generated_at} Â· Timings are approximate
        </p>
      </div>
    </div>
  );
}
