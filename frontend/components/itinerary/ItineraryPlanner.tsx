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
};

const CATEGORY_CONFIG: Record<SlotCategory, CategoryConfig> = {
  drive: {
    icon: CarFront,
    label: "Drive",
    accent: "text-sky-300",
    card: "bg-sky-500/8",
    border: "border-sky-500/20",
    text: "text-sky-200",
  },
  breakfast: {
    icon: UtensilsCrossed,
    label: "Breakfast",
    accent: "text-amber-300",
    card: "bg-amber-500/8",
    border: "border-amber-500/20",
    text: "text-amber-200",
  },
  lunch: {
    icon: UtensilsCrossed,
    label: "Lunch",
    accent: "text-orange-300",
    card: "bg-orange-500/8",
    border: "border-orange-500/20",
    text: "text-orange-200",
  },
  dinner: {
    icon: UtensilsCrossed,
    label: "Dinner",
    accent: "text-violet-300",
    card: "bg-violet-500/8",
    border: "border-violet-500/20",
    text: "text-violet-200",
  },
  attraction: {
    icon: Sparkles,
    label: "Attraction",
    accent: "text-emerald-300",
    card: "bg-gradient-to-br from-emerald-500/12 to-transparent",
    border: "border-emerald-500/25",
    text: "text-emerald-100",
  },
  sightseeing: {
    icon: Sparkles,
    label: "Attraction",
    accent: "text-emerald-300",
    card: "bg-gradient-to-br from-emerald-500/12 to-transparent",
    border: "border-emerald-500/25",
    text: "text-emerald-100",
  },
  hotel: {
    icon: Hotel,
    label: "Hotel",
    accent: "text-[#D4AF37]",
    card: "bg-[#D4AF37]/8",
    border: "border-[#D4AF37]/20",
    text: "text-[#F2DB8A]",
  },
  shopping: {
    icon: ShoppingBag,
    label: "Shopping",
    accent: "text-pink-300",
    card: "bg-pink-500/8",
    border: "border-pink-500/20",
    text: "text-pink-200",
  },
  rest: {
    icon: MoonStar,
    label: "Rest",
    accent: "text-slate-300",
    card: "bg-slate-500/8",
    border: "border-slate-500/20",
    text: "text-slate-200",
  },
  fuel: {
    icon: Fuel,
    label: "Fuel Stop",
    accent: "text-red-300",
    card: "bg-red-500/8",
    border: "border-red-500/20",
    text: "text-red-200",
  },
  misc: {
    icon: Waypoints,
    label: "Activity",
    accent: "text-slate-300",
    card: "bg-slate-500/8",
    border: "border-slate-500/20",
    text: "text-slate-200",
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
      <div className="relative z-10 flex h-14 w-14 flex-shrink-0 flex-col items-center justify-center rounded-full border border-[#242424] bg-[#0c0c0c] text-center shadow-[0_0_0_1px_rgba(0,0,0,0.2)]">
        <config.icon className={`h-5 w-5 ${config.accent}`} />
        <span className="mt-0.5 text-[10px] leading-tight text-[#6a6a6a]">{slot.time}</span>
      </div>

      <div
        className={[
          "mb-1 flex-1 overflow-hidden rounded-2xl border bg-[#111111] transition-all hover:border-[#2c2c2c]",
          config.border,
          config.card,
          isAttraction ? "shadow-[0_0_0_1px_rgba(212,175,55,0.05)]" : "",
        ].join(" ")}
      >
        <button type="button" onClick={onToggle} className="w-full p-4 text-left sm:p-5">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${config.accent} bg-white/5`}>
                  {config.label}
                </span>
                {slot.best_time_to_visit ? (
                  <span className="rounded-full border border-[#2a2a2a] bg-[#0d0d0d] px-2.5 py-1 text-[11px] text-[#D4AF37]">
                    Best: {slot.best_time_to_visit}
                  </span>
                ) : null}
                {duration > 0 ? (
                  <span className="inline-flex items-center gap-1 text-xs text-[#bcbcbc]">
                    <Clock3 className="h-3.5 w-3.5" />
                    {duration} min
                  </span>
                ) : null}
                {cost > 0 ? (
                  <span className="inline-flex items-center gap-1 text-xs text-[#D4AF37]">
                    <IndianRupee className="h-3.5 w-3.5" />
                    {formatCurrency(cost)}
                  </span>
                ) : null}
              </div>

              <p className={`mt-2 break-words text-base font-semibold ${isAttraction ? "text-white" : "text-white/95"}`}>
                {title}
              </p>

              {placeName ? (
                <p className={`mt-1 break-words text-sm font-medium ${isAttraction ? "text-[#F2DB8A]" : "text-[#D4AF37]"}`}>
                  {placeName}
                </p>
              ) : null}

              <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-[#8c8c8c]">
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

              <p className="mt-2 text-xs text-[#686868]">
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
                  className="inline-flex items-center gap-1.5 rounded-full border border-[#2a2a2a] bg-[#0c0c0c] px-3 py-1.5 text-xs font-medium text-white transition hover:border-[#D4AF37] hover:text-[#D4AF37]"
                  onClick={(event) => event.stopPropagation()}
                >
                  <ArrowUpRight className="h-3.5 w-3.5" />
                  View on Map
                </a>
              ) : null}
              <span className="text-xs text-[#6a6a6a]">{expanded ? "Hide" : "Details"}</span>
            </div>
          </div>
        </button>

        {expanded ? (
          <div className="border-t border-white/5 px-4 pb-4 pt-3 sm:px-5">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-xl border border-white/5 bg-[#0a0a0a]/90 p-3">
                <p className="text-[11px] uppercase tracking-[0.18em] text-[#8a8a8a]">
                  {isAttraction ? "Why visit" : "Why this stop"}
                </p>
                <p className="mt-2 text-sm leading-6 text-[#c8c8c8]">{reason || "A practical stop on the route."}</p>
              </div>

              <div className="rounded-xl border border-white/5 bg-[#0a0a0a]/90 p-3">
                <p className="text-[11px] uppercase tracking-[0.18em] text-[#8a8a8a]">Trip details</p>
                <div className="mt-2 grid gap-2 text-xs text-[#a8a8a8]">
                  <div className="flex items-center justify-between gap-3">
                    <span>Duration</span>
                    <span className="text-white">{duration > 0 ? `${duration} min` : "Flexible"}</span>
                  </div>
                  <div className="flex items-center justify-between gap-3">
                    <span>Cost</span>
                    <span className="text-white">{cost > 0 ? `INR ${formatCurrency(cost)}` : "Included"}</span>
                  </div>
                  <div className="flex items-center justify-between gap-3">
                    <span>Time</span>
                    <span className="text-white">{slot.time || "TBA"}</span>
                  </div>
                </div>
              </div>
            </div>

            {nearbyPlaces.length > 0 ? (
              <div className="mt-3">
                <p className="mb-2 text-[11px] uppercase tracking-[0.18em] text-[#8a8a8a]">Nearby places</p>
                <div className="flex flex-wrap gap-2">
                  {nearbyPlaces.map((place) => (
                    <span
                      key={`${slot.time}-${place}`}
                      className="rounded-full border border-[#2a2a2a] bg-[#0c0c0c] px-3 py-1 text-xs text-[#b8b8b8]"
                    >
                      {place}
                    </span>
                  ))}
                </div>
              </div>
            ) : null}

            <div className="mt-3 grid gap-2 text-xs sm:grid-cols-2">
              <div className="rounded-xl border border-white/5 bg-[#0a0a0a]/90 px-3 py-2">
                <span className="block text-[#7c7c7c]">Before</span>
                <span className="block break-words text-white">{slot.current_location_before || "Unknown"}</span>
              </div>
              <div className="rounded-xl border border-white/5 bg-[#0a0a0a]/90 px-3 py-2">
                <span className="block text-[#7c7c7c]">After</span>
                <span className="block break-words text-white">{slot.current_location_after || "Unknown"}</span>
              </div>
            </div>

            {slot.tips ? (
              <div className="mt-3 rounded-xl border border-[#D4AF37]/20 bg-[#D4AF37]/5 p-3">
                <p className="text-xs leading-6 text-[#D4AF37]">
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
            <h3 className="break-words text-xl font-bold text-white">{day.day_title}</h3>
            <p className="mt-1 text-sm leading-6 text-[#9a9a9a]">{day.summary}</p>
          </div>
          <div className="rounded-2xl border border-[#1f1f1f] bg-[#0c0c0c] px-4 py-3 text-right">
            <p className="text-[11px] uppercase tracking-[0.18em] text-[#8a8a8a]">Today</p>
            <p className="mt-1 text-sm font-semibold text-white">{attractionCount} places planned today</p>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap gap-3">
          {day.distance_km > 0 ? (
            <span className="rounded-full border border-white/5 bg-white/5 px-3 py-1.5 text-xs text-[#b8b8b8]">
              Drive: {day.distance_km} km
            </span>
          ) : null}
          {day.driving_hours > 0 ? (
            <span className="rounded-full border border-white/5 bg-white/5 px-3 py-1.5 text-xs text-[#b8b8b8]">
              Travel time: {day.driving_hours} hrs
            </span>
          ) : null}
          <span className="rounded-full border border-[#D4AF37]/20 bg-[#D4AF37]/10 px-3 py-1.5 text-xs text-[#F2DB8A]">
            Est. cost: INR {formatCurrency(day.day_total_cost_inr)}
          </span>
          <span className="rounded-full border border-white/5 bg-white/5 px-3 py-1.5 text-xs text-[#b8b8b8]">
            {uniqueSlots.length} items planned
          </span>
        </div>

        {day.highlights.length > 0 ? (
          <div className="mt-4 flex flex-wrap gap-2">
            {day.highlights.map((highlight, index) => (
              <span
                key={`${day.day_number}-highlight-${index}`}
                className="rounded-full border border-[#D4AF37]/20 bg-[#D4AF37]/10 px-3 py-1 text-xs text-[#F2DB8A]"
              >
                {highlight}
              </span>
            ))}
          </div>
        ) : null}
      </div>

      {hasSlots ? (
        <div className="relative">
          <div className="absolute bottom-0 left-[27px] top-0 w-0.5 bg-[#1a1a1a]" />
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
        <div className="rounded-2xl border border-dashed border-[#2a2a2a] bg-[#111111] px-5 py-8 text-center">
          <p className="text-sm font-medium text-white">No places planned for this day yet.</p>
          <p className="mt-2 text-sm text-[#8a8a8a]">
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
    <div className="overflow-hidden rounded-2xl border border-[#1a1a1a] bg-[#0a0a0a]">
      <div className="border-b border-[#1a1a1a] px-5 py-5 sm:px-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="mb-1 text-xs font-medium uppercase tracking-widest text-[#D4AF37]">AI ITINERARY</p>
            <h2 className="text-2xl font-bold text-white">Day-by-Day Travel Plan</h2>
            <p className="mt-2 text-sm text-[#888888]">
              {itinerary.origin} {"->"} {itinerary.destination} · {itinerary.total_days} Days · {itinerary.start_date} to{" "}
              {itinerary.end_date}
            </p>
          </div>
          <div className="text-right">
            <p className="text-xs text-[#888888]">Total Estimated Cost</p>
            <p className="text-xl font-bold text-[#D4AF37]">INR {formatCurrency(resolvedTotal)}</p>
          </div>
        </div>
      </div>

      <div className="flex overflow-x-auto border-b border-[#1a1a1a]">
        {itinerary.days.map((day, index) => (
          <button
            key={`${day.day_number}-${day.date}`}
            type="button"
            onClick={() => setActiveDay(index)}
            className={`flex-shrink-0 border-b-2 px-5 py-4 text-sm font-medium whitespace-nowrap transition-all ${
              activeDay === index
                ? "border-[#D4AF37] bg-[#D4AF37]/5 text-[#D4AF37]"
                : "border-transparent text-[#888888] hover:text-white"
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
          <div className="rounded-2xl border border-dashed border-[#2a2a2a] bg-[#111111] p-8 text-center">
            <p className="text-lg font-semibold text-white">No itinerary days available.</p>
            <p className="mt-2 text-sm leading-6 text-[#8a8a8a]">
              We could not find any places to show for this trip yet.
            </p>
          </div>
        </div>
      )}

      {itinerary.travel_tips.length > 0 ? (
        <div className="border-t border-[#1a1a1a] px-5 py-4 sm:px-6">
          <button
            type="button"
            onClick={() => setShowTips((current) => !current)}
            className="flex w-full items-center justify-between text-left"
          >
            <span className="flex items-center gap-2 font-medium text-[#D4AF37]">
              <Sparkles className="h-4 w-4" />
              Travel Tips ({itinerary.travel_tips.length})
            </span>
            <span className="text-sm text-[#555555]">{showTips ? "Hide" : "Show"}</span>
          </button>

          {showTips ? (
            <div className="mt-3 space-y-2">
              {itinerary.travel_tips.map((tip, index) => (
                <div key={`${index}-${tip}`} className="flex items-start gap-3 rounded-xl bg-[#111111] p-3">
                  <span className="flex-shrink-0 text-sm font-bold text-[#D4AF37]">{index + 1}.</span>
                  <p className="text-sm text-[#a0a0a0]">{tip}</p>
                </div>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}

      <div className="border-t border-[#1a1a1a] bg-[#050505] px-6 py-3">
        <p className="text-center text-xs text-[#444444]">
          Generated by RoadMind AI · {itinerary.generated_at} · Timings are approximate
        </p>
      </div>
    </div>
  );
}
