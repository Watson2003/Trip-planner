"use client";

import { useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";

import type {
  AttractionRecommendation,
  HotelRecommendation,
  LocationRecommendation,
  PlaceBase,
  RestaurantRecommendation,
} from "@/types";

type CategoryKey = "hotels" | "restaurants" | "attractions";
type PlaceRecommendation = HotelRecommendation | RestaurantRecommendation | AttractionRecommendation;

interface RecommendationCardsProps {
  recommendations: LocationRecommendation[];
  origin: string;
  destination: string;
}

const CATEGORY_META: Record<CategoryKey, { label: string; icon: string; tone: string }> = {
  hotels: { label: "Hotels", icon: "🏨", tone: "orange" },
  restaurants: { label: "Restaurants", icon: "🍽️", tone: "cyan" },
  attractions: { label: "Attractions", icon: "🎯", tone: "violet" },
};

const PlaceMiniMap = dynamic(() => import("./PlaceMiniMap"), {
  ssr: false,
  loading: () => <div className="h-[200px] w-full rounded-2xl border border-white/10 bg-slate-800/70 sm:h-[250px]" />,
});

function areSameLocation(a: string, b: string) {
  return a.trim().toLowerCase() === b.trim().toLowerCase();
}

function buildStarDisplay(rating: number) {
  const clamped = Math.max(0, Math.min(5, rating));
  const fullStars = Math.floor(clamped);
  const half = clamped - fullStars >= 0.5;
  const emptyStars = 5 - fullStars - (half ? 1 : 0);
  return { fullStars, half, emptyStars, display: clamped.toFixed(1) };
}

function StarRating({ rating, totalReviews }: { rating: number; totalReviews: number }) {
  const { fullStars, half, emptyStars, display } = buildStarDisplay(rating);

  return (
    <div className="flex flex-wrap items-center gap-2 text-sm">
      <div className="flex items-center gap-0.5 text-amber-400">
        {Array.from({ length: fullStars }).map((_, index) => (
          <span key={`full-${index}`}>★</span>
        ))}
        {half ? (
          <span className="relative inline-block text-slate-500">
            <span>★</span>
            <span className="absolute inset-y-0 left-0 overflow-hidden text-amber-400" style={{ width: "50%" }}>
              ★
            </span>
          </span>
        ) : null}
        {Array.from({ length: emptyStars }).map((_, index) => (
          <span key={`empty-${index}`} className="text-slate-500">
            ☆
          </span>
        ))}
      </div>
      <span className="font-semibold text-slate-200">
        {display} <span className="text-slate-400">({totalReviews} reviews)</span>
      </span>
    </div>
  );
}

function priceLabel(place: PlaceRecommendation) {
  if ("price_range" in place) return place.price_range;
  return "Price unavailable";
}

function openNowLabel(value: boolean | null) {
  if (value === true) return { label: "Open Now", tone: "bg-emerald-500/90 text-white" };
  if (value === false) return { label: "Closed", tone: "bg-rose-500/90 text-white" };
  return null;
}

function placeInitial(place: PlaceBase) {
  return (place.name?.trim()?.[0] || "P").toUpperCase();
}

function PlaceCard({
  place,
  category,
  location,
  onViewDetails,
  onDirections,
}: {
  place: PlaceRecommendation;
  category: CategoryKey;
  location: string;
  onViewDetails: (place: PlaceRecommendation) => void;
  onDirections: (url: string) => void;
}) {
  const badge = openNowLabel(place.open_now);
  const titleTone =
    category === "hotels"
      ? "border-orange-500/30 bg-orange-500/10 text-orange-200"
      : category === "restaurants"
        ? "border-cyan-500/30 bg-cyan-500/10 text-cyan-200"
        : "border-violet-500/30 bg-violet-500/10 text-violet-200";

  return (
    <article className="group overflow-hidden rounded-3xl border border-white/10 bg-slate-900/90 shadow-xl shadow-black/20 transition hover:-translate-y-0.5 hover:border-orange-400/30">
      <div className="relative">
        {place.photo_url ? (
          <img
            src={place.photo_url}
            alt={place.name}
            className="h-40 w-full object-cover sm:h-48"
            loading="lazy"
          />
        ) : (
          <div className="flex h-40 w-full items-center justify-center bg-gradient-to-br from-slate-700 via-slate-800 to-slate-950 sm:h-48">
            <span className="text-5xl font-black text-white/80">{placeInitial(place)}</span>
          </div>
        )}

        {badge ? (
          <span className={`absolute right-3 top-3 rounded-full px-3 py-1 text-[11px] font-bold uppercase tracking-[0.18em] ${badge.tone}`}>
            {badge.label}
          </span>
        ) : null}
      </div>

      <div className="space-y-4 p-5">
        <div className="space-y-2">
          <p className="text-xs font-bold uppercase tracking-[0.24em] text-slate-500 dark:text-slate-400">
            {CATEGORY_META[category].label.slice(0, -1).toUpperCase()}
          </p>
          <h3 className="text-xl font-black leading-tight text-white">{place.name}</h3>
        </div>

        <div className="flex flex-wrap gap-2">
          {category === "hotels" ? (
            <span className={`rounded-full border px-3 py-1 text-xs font-semibold ${titleTone}`}>
              {(place as HotelRecommendation).category}
            </span>
          ) : null}
          {category === "restaurants" ? (
            <>
              <span className={`rounded-full border px-3 py-1 text-xs font-semibold ${titleTone}`}>
                {(place as RestaurantRecommendation).cuisine}
              </span>
              <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs font-semibold text-slate-200">
                {(place as RestaurantRecommendation).price_range}
              </span>
            </>
          ) : null}
          {category === "attractions" ? (
            <>
              <span className={`rounded-full border px-3 py-1 text-xs font-semibold ${titleTone}`}>
                {(place as AttractionRecommendation).type}
              </span>
              <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs font-semibold text-slate-200">
                {(place as AttractionRecommendation).entry_fee}
              </span>
            </>
          ) : null}
        </div>

        <p className="line-clamp-2 min-h-[3rem] text-sm leading-6 text-slate-300">{place.description}</p>

        <div className="space-y-2">
          <p className="truncate text-sm text-slate-400">
            <span className="mr-1">📍</span>
            {place.address || location}
          </p>
          <StarRating rating={place.rating} totalReviews={place.total_reviews} />
          <p className="text-sm text-slate-400">
            {category === "attractions" ? `Entry: ${priceLabel(place)}` : priceLabel(place)}
          </p>
        </div>

        <div className="flex flex-col gap-2 sm:flex-row">
          <button
            type="button"
            onClick={() => onViewDetails(place)}
            className="inline-flex flex-1 items-center justify-center rounded-2xl bg-orange-500 px-4 py-3 text-sm font-bold text-white transition hover:bg-orange-600"
          >
            View Details
          </button>
          <button
            type="button"
            onClick={() => onDirections(place.maps_url)}
            className="inline-flex flex-1 items-center justify-center rounded-2xl border border-white/15 bg-white/5 px-4 py-3 text-sm font-semibold text-slate-100 transition hover:bg-white/10"
          >
            📍 Directions
          </button>
        </div>
      </div>
    </article>
  );
}

export default function RecommendationCards({ recommendations, origin, destination }: RecommendationCardsProps) {
  const visibleRecommendations = useMemo(() => {
    const routeMatches = recommendations.filter((item) =>
      [origin, destination].some((target) => areSameLocation(item.location, target)),
    );
    return routeMatches.length > 0 ? routeMatches : recommendations;
  }, [destination, origin, recommendations]);

  const visibleLocations = useMemo(
    () => Array.from(new Set(visibleRecommendations.map((item) => item.location))).filter(Boolean),
    [visibleRecommendations],
  );

  const [activeLocation, setActiveLocation] = useState<string>(visibleLocations[0] ?? origin ?? destination);
  const [activeCategory, setActiveCategory] = useState<CategoryKey>("hotels");
  const [selectedPlace, setSelectedPlace] = useState<PlaceRecommendation | null>(null);
  const [modalOpen, setModalOpen] = useState(false);

  useEffect(() => {
    if (!visibleLocations.length) {
      setActiveLocation("");
      return;
    }
    if (!visibleLocations.includes(activeLocation)) {
      setActiveLocation(visibleLocations[0]);
    }
  }, [activeLocation, visibleLocations]);

  useEffect(() => {
    if (!modalOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setModalOpen(false);
      }
    };
    document.addEventListener("keydown", onKeyDown);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = "";
    };
  }, [modalOpen]);

  const activeLocationData = visibleRecommendations.find((item) => item.location === activeLocation) ?? visibleRecommendations[0];
  const currentPlaces = useMemo(() => {
    if (!activeLocationData) return [];
    return activeLocationData[activeCategory];
  }, [activeCategory, activeLocationData]);

  const activeCounts = {
    hotels: activeLocationData?.hotels?.length ?? 0,
    restaurants: activeLocationData?.restaurants?.length ?? 0,
    attractions: activeLocationData?.attractions?.length ?? 0,
  };

  const closeModal = () => {
    setModalOpen(false);
    setSelectedPlace(null);
  };

  if (!recommendations.length) {
    return (
      <section className="rounded-[2rem] border border-white/10 bg-slate-950/90 p-8 text-center shadow-2xl">
        <div className="mx-auto flex max-w-md flex-col items-center gap-3">
          <div className="text-4xl">🗺️</div>
          <h2 className="text-xl font-black text-white">Plan a trip to see recommendations for your route</h2>
          <p className="text-sm leading-6 text-slate-400">
            Once your route is planned, real hotels, restaurants, and attractions will appear here.
          </p>
        </div>
      </section>
    );
  }

  return (
    <>
      <section className="rounded-[2rem] border border-white/10 bg-slate-950/90 p-5 shadow-2xl shadow-black/20">
        <div className="mb-5 space-y-2">
          <p className="text-xs font-bold uppercase tracking-[0.28em] text-orange-300">RECOMMENDATIONS</p>
          <h2 className="text-2xl font-black tracking-tight text-white">Stops Along Your Route</h2>
        </div>

        <div className="flex flex-wrap gap-2">
          {visibleLocations.map((location) => {
            const active = activeLocation === location;
            return (
              <button
                key={location}
                type="button"
                onClick={() => setActiveLocation(location)}
                className={`rounded-full px-4 py-2 text-sm font-semibold transition ${
                  active
                    ? "bg-orange-500 text-white shadow-lg shadow-orange-500/20"
                    : "border border-white/15 bg-transparent text-slate-300 hover:bg-white/5"
                }`}
              >
                {location}
              </button>
            );
          })}
        </div>

        <div className="mt-4 flex flex-wrap gap-2 sm:gap-4">
          {(Object.keys(CATEGORY_META) as CategoryKey[]).map((category) => {
            const meta = CATEGORY_META[category];
            const active = activeCategory === category;
            const count = activeCounts[category];
            return (
              <button
                key={category}
                type="button"
                onClick={() => setActiveCategory(category)}
                className={`inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-semibold transition ${
                  active ? "bg-slate-100 text-slate-950" : "bg-slate-800 text-slate-300 hover:bg-slate-700"
                }`}
              >
                <span>{meta.icon}</span>
                <span>
                  {meta.label} ({count})
                </span>
              </button>
            );
          })}
        </div>

        <div className="mt-6 grid grid-cols-1 gap-4 md:grid-cols-2">
          {currentPlaces.length === 0 ? (
            <div className="rounded-3xl border border-dashed border-white/10 bg-white/5 px-5 py-10 text-center text-sm text-slate-400 md:col-span-2">
              No {activeCategory} found for {activeLocation}.
            </div>
          ) : (
            currentPlaces.map((place) => (
              <PlaceCard
                key={`${activeLocation}-${place.place_id}`}
                place={place}
                category={activeCategory}
                location={activeLocation}
                onViewDetails={(selected) => {
                  setSelectedPlace(selected);
                  setModalOpen(true);
                }}
                onDirections={(url) => window.open(url, "_blank", "noopener,noreferrer")}
              />
            ))
          )}
        </div>
      </section>

      {modalOpen && selectedPlace ? (
        <div
          className="fixed inset-0 z-50 flex items-end justify-center overflow-y-auto bg-black/70 p-0 backdrop-blur-sm sm:items-center sm:p-4"
          onClick={closeModal}
          role="presentation"
        >
          <div
            className="w-full max-w-2xl overflow-hidden rounded-t-2xl bg-gray-900 shadow-2xl shadow-black/40 max-h-[90vh] overflow-y-auto sm:mx-auto sm:rounded-2xl"
            onClick={(event) => event.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-labelledby="place-detail-title"
          >
            <div className="flex items-start justify-between gap-4 border-b border-white/10 p-5">
              <div className="space-y-2">
                <p className="text-xs font-bold uppercase tracking-[0.24em] text-orange-300">
                  {CATEGORY_META[activeCategory].label.slice(0, -1).toUpperCase()}
                </p>
                <h3 id="place-detail-title" className="text-2xl font-black text-white">
                  {selectedPlace.name}
                </h3>
                {openNowLabel(selectedPlace.open_now) ? (
                  <span className={`inline-flex rounded-full px-3 py-1 text-xs font-bold ${openNowLabel(selectedPlace.open_now)?.tone}`}>
                    {openNowLabel(selectedPlace.open_now)?.label}
                  </span>
                ) : null}
              </div>
              <button
                type="button"
                onClick={closeModal}
                className="inline-flex h-10 w-10 items-center justify-center rounded-full border border-white/10 bg-white/5 text-white transition hover:bg-white/10"
                aria-label="Close modal"
              >
                ✕
              </button>
            </div>

            {selectedPlace.photo_url ? (
              <img
                src={selectedPlace.photo_url}
                alt={selectedPlace.name}
                className="h-[300px] w-full object-cover"
                loading="lazy"
              />
            ) : (
              <div className="flex h-[300px] w-full items-center justify-center bg-gradient-to-br from-slate-700 via-slate-800 to-slate-950">
                <span className="text-7xl font-black text-white/80">{placeInitial(selectedPlace)}</span>
              </div>
            )}

            <div className="grid gap-5 p-5 md:grid-cols-2">
              <div className="space-y-4">
                <div>
                  <p className="text-xs font-bold uppercase tracking-[0.22em] text-slate-400">Place Info</p>
                  <div className="mt-3 space-y-3 text-sm text-slate-200">
                    <p className="truncate">📍 {selectedPlace.address || "Address not available"}</p>
                    <p>
                      ⭐ Rating: {selectedPlace.rating.toFixed(1)} ({selectedPlace.total_reviews} reviews)
                    </p>
                    <p>💰 Price: {priceLabel(selectedPlace)}</p>
                    <p>📞 Phone: {selectedPlace.phone || "Not available"}</p>
                    <p>
                      🌐 Website:{" "}
                      {selectedPlace.website ? (
                        <a
                          href={selectedPlace.website}
                          target="_blank"
                          rel="noreferrer noopener"
                          className="text-orange-300 underline-offset-4 hover:underline"
                        >
                          Visit website
                        </a>
                      ) : (
                        "Not available"
                      )}
                    </p>
                    <p>
                      🕐 Status:{" "}
                      {selectedPlace.open_now === true
                        ? "Open Now"
                        : selectedPlace.open_now === false
                          ? "Closed"
                          : "Not available"}
                    </p>
                  </div>
                </div>
              </div>

              <div className="space-y-4">
                <div>
                  <p className="text-xs font-bold uppercase tracking-[0.22em] text-slate-400">Mini Map</p>
                  <div className="mt-3">
                    <PlaceMiniMap lat={selectedPlace.lat} lng={selectedPlace.lng} />
                  </div>
                </div>
              </div>
            </div>

            <div className="flex flex-col gap-3 border-t border-white/10 p-5 sm:flex-row">
              <button
                type="button"
                onClick={() => window.open(selectedPlace.maps_url, "_blank", "noopener,noreferrer")}
                className="inline-flex flex-1 items-center justify-center rounded-2xl bg-orange-500 px-4 py-3 text-sm font-bold text-white transition hover:bg-orange-600"
              >
                📍 Get Directions
              </button>
              {selectedPlace.website ? (
                <button
                  type="button"
                  onClick={() => window.open(selectedPlace.website || "", "_blank", "noopener,noreferrer")}
                  className="inline-flex flex-1 items-center justify-center rounded-2xl border border-white/15 bg-white/5 px-4 py-3 text-sm font-semibold text-slate-100 transition hover:bg-white/10"
                >
                  🌐 Visit Website
                </button>
              ) : null}
              <button
                type="button"
                onClick={closeModal}
                className="inline-flex flex-1 items-center justify-center rounded-2xl border border-white/15 bg-white/5 px-4 py-3 text-sm font-semibold text-slate-100 transition hover:bg-white/10"
              >
                ✕ Close
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
