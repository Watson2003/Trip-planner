"use client";

import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";
import {
  Globe,
  Hotel,
  MapPin,
  Navigation,
  Star,
  Target,
  UtensilsCrossed,
  X,
} from "lucide-react";

import type {
  AttractionRecommendation,
  HotelRecommendation,
  RecommendationPayload,
  RestaurantRecommendation,
} from "@/types";
import { normalizeRecommendations } from "@/lib/trip-result";

type CategoryKey = "hotels" | "restaurants" | "attractions";
type PlaceRecommendation = HotelRecommendation | RestaurantRecommendation | AttractionRecommendation;

interface RecommendationCardsProps {
  recommendations: RecommendationPayload;
  destination: string;
}

const CATEGORY_META: Record<
  CategoryKey,
  {
    label: string;
    icon: typeof Hotel;
    accent: string;
    border: string;
    bg: string;
  }
> = {
  hotels: { label: "Hotels", icon: Hotel, accent: "text-purple-700", border: "border-purple-200", bg: "bg-purple-50" },
  restaurants: { label: "Restaurants", icon: UtensilsCrossed, accent: "text-orange-700", border: "border-orange-200", bg: "bg-orange-50" },
  attractions: { label: "Attractions", icon: Target, accent: "text-emerald-700", border: "border-emerald-200", bg: "bg-emerald-50" },
};

const PlaceMiniMap = dynamic(() => import("./PlaceMiniMap"), {
  ssr: false,
  loading: () => <div className="h-[200px] w-full rounded-2xl border border-slate-200 bg-slate-50 sm:h-[250px]" />,
});

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
      <div className="flex items-center gap-0.5 text-blue-500">
        {Array.from({ length: fullStars }).map((_, index) => (
          <Star key={`full-${index}`} className="h-3.5 w-3.5 fill-current" />
        ))}
        {half ? (
          <span className="relative inline-block text-slate-300">
            <Star className="h-3.5 w-3.5 fill-current" />
            <span className="absolute inset-y-0 left-0 overflow-hidden text-blue-500" style={{ width: "50%" }}>
              <Star className="h-3.5 w-3.5 fill-current" />
            </span>
          </span>
        ) : null}
        {Array.from({ length: emptyStars }).map((_, index) => (
          <Star key={`empty-${index}`} className="h-3.5 w-3.5 text-slate-300" />
        ))}
      </div>
      <span className="font-semibold text-slate-950">
        {display} <span className="text-slate-500">({totalReviews} reviews)</span>
      </span>
    </div>
  );
}

function openNowLabel(value: boolean | null) {
  if (value === true) return { label: "Open Now", tone: "bg-emerald-50 text-emerald-700" };
  if (value === false) return { label: "Closed", tone: "bg-rose-50 text-rose-700" };
  return null;
}

function buildFallbackImageDataUrl(category: CategoryKey, title: string) {
  const label = category === "hotels" ? "Stay" : category === "restaurants" ? "Food" : "Explore";
  const safeTitle = title.replace(/[<>&]/g, "");
  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 500" role="img" aria-label="${safeTitle}">
      <defs>
        <linearGradient id="g" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stop-color="#F8FAFC"/>
          <stop offset="100%" stop-color="#E2E8F0"/>
        </linearGradient>
        <linearGradient id="accent" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stop-color="#2563EB" stop-opacity="0.9"/>
          <stop offset="100%" stop-color="#06B6D4" stop-opacity="0.25"/>
        </linearGradient>
      </defs>
      <rect width="800" height="500" fill="url(#g)"/>
      <circle cx="660" cy="95" r="120" fill="url(#accent)" opacity="0.12"/>
      <circle cx="130" cy="395" r="160" fill="#2563EB" opacity="0.06"/>
      <rect x="48" y="48" width="704" height="404" rx="28" fill="none" stroke="#CBD5E1" stroke-width="2"/>
      <text x="80" y="135" fill="#0B1120" font-family="Arial, Helvetica, sans-serif" font-size="28" font-weight="700" opacity="0.8">${label}</text>
      <text x="80" y="250" fill="#2563EB" font-family="Arial, Helvetica, sans-serif" font-size="120">${label.slice(0, 1).toUpperCase()}</text>
      <text x="80" y="330" fill="#0B1120" font-family="Arial, Helvetica, sans-serif" font-size="34" font-weight="700">${safeTitle}</text>
      <text x="80" y="375" fill="#475569" font-family="Arial, Helvetica, sans-serif" font-size="22">Free fallback image</text>
    </svg>
  `;
  return `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`;
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
  const fallbackImage = buildFallbackImageDataUrl(category, place.name || location);
  const imageSrc = place.photo_url || fallbackImage;
  const meta = CATEGORY_META[category];
  const CategoryIcon = meta.icon;

  return (
    <article className={`group overflow-hidden rounded-3xl border bg-white shadow-card transition hover:-translate-y-0.5 hover:shadow-xl ${meta.border}`}>
      <div className={`relative h-48 w-full overflow-hidden rounded-t-3xl ${meta.bg}`}>
        <img
          src={imageSrc}
          alt={place.name}
          className="h-48 w-full object-cover"
          onError={(e) => {
            const target = e.currentTarget;
            if (target.src !== fallbackImage) target.src = fallbackImage;
          }}
        />
        {badge ? (
          <span className={`absolute right-3 top-3 rounded-full px-3 py-1 text-[11px] font-bold uppercase tracking-[0.18em] ${badge.tone}`}>
            {badge.label}
          </span>
        ) : null}
      </div>

      <div className="space-y-4 p-5">
        <div className="space-y-2">
          <p className={`text-xs font-bold uppercase tracking-[0.24em] ${meta.accent} flex items-center gap-2`}>
            <CategoryIcon className="h-4 w-4" />
            {meta.label.slice(0, -1).toUpperCase()}
          </p>
          <h3 className="text-xl font-black leading-tight text-slate-950">{place.name}</h3>
        </div>

        <div className="flex flex-wrap gap-2">
          {category === "hotels" ? (
            <span className="rounded-full border border-purple-200 bg-purple-50 px-3 py-1 text-xs font-semibold text-purple-700">
              {(place as HotelRecommendation).category}
            </span>
          ) : null}
          {category === "restaurants" ? (
            <>
              <span className="rounded-full border border-orange-200 bg-orange-50 px-3 py-1 text-xs font-semibold text-orange-700">
                {(place as RestaurantRecommendation).cuisine}
              </span>
              <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-semibold text-slate-600">
                {(place as RestaurantRecommendation).price_range}
              </span>
            </>
          ) : null}
          {category === "attractions" ? (
            <>
              <span className="rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700">
                {(place as AttractionRecommendation).type}
              </span>
              <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-semibold text-slate-600">
                {(place as AttractionRecommendation).entry_fee}
              </span>
            </>
          ) : null}
        </div>

        <p className="min-h-[3rem] line-clamp-2 text-sm leading-6 text-slate-500">{place.description}</p>

        <div className="space-y-2">
          <p className="truncate text-sm text-slate-500">
            <MapPin className="mr-1 inline h-4 w-4" />
            {place.address || location}
          </p>
          <StarRating rating={place.rating} totalReviews={place.total_reviews} />
          <p className="text-sm text-slate-500">
            {category === "attractions" ? `Entry: ${(place as AttractionRecommendation).entry_fee}` : "Price available in details"}
          </p>
        </div>

        <div className="flex flex-col gap-2 sm:flex-row">
          <button
            type="button"
            onClick={() => onViewDetails(place)}
            className="inline-flex flex-1 items-center justify-center rounded-2xl bg-[#0071e3] px-4 py-3 text-sm font-bold text-white transition hover:bg-[#0077ed]"
          >
            View Details
          </button>
          <button
            type="button"
            onClick={() => onDirections(place.maps_url)}
            className="inline-flex flex-1 items-center justify-center rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm font-semibold text-slate-700 transition hover:border-slate-300 hover:bg-slate-50 hover:text-slate-950"
          >
            <Navigation className="mr-2 h-4 w-4" />
            Directions
          </button>
        </div>
      </div>
    </article>
  );
}

export default function RecommendationCards({ recommendations, destination }: RecommendationCardsProps) {
  const normalizedRecommendations = normalizeRecommendations(recommendations, destination);
  const [activeCategory, setActiveCategory] = useState<CategoryKey>("hotels");
  const [selectedPlace, setSelectedPlace] = useState<PlaceRecommendation | null>(null);
  const [modalOpen, setModalOpen] = useState(false);

  useEffect(() => {
    if (!modalOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setModalOpen(false);
    };

    document.addEventListener("keydown", onKeyDown);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = "";
    };
  }, [modalOpen]);

  const counts = useMemo(
    () => ({
      hotels: normalizedRecommendations.hotels.length,
      restaurants: normalizedRecommendations.restaurants.length,
      attractions: normalizedRecommendations.attractions.length,
    }),
    [normalizedRecommendations],
  );

  const currentPlaces = normalizedRecommendations[activeCategory] ?? [];
  const hasRecommendations = Boolean(counts.hotels || counts.restaurants || counts.attractions);

  if (!hasRecommendations) {
    return (
      <section className="rounded-[2rem] border border-slate-200 bg-white p-8 text-center shadow-card">
        <div className="mx-auto flex max-w-md flex-col items-center gap-3">
          <div className="text-4xl">🗺️</div>
          <h2 className="text-xl font-black text-slate-950">Plan a trip to see recommendations in {destination}</h2>
          <p className="text-sm leading-6 text-slate-500">
            Once your route is planned, real hotels, restaurants, and attractions for the destination will appear here.
          </p>
        </div>
      </section>
    );
  }

  const closeModal = () => {
    setModalOpen(false);
    setSelectedPlace(null);
  };

  return (
    <>
      <section className="rounded-[2rem] border border-slate-200 bg-white p-5 shadow-card">
        <div className="mb-5 space-y-2">
          <p className="text-xs font-bold uppercase tracking-[0.28em] text-slate-400">Recommendations</p>
          <h2 className="text-2xl font-black tracking-tight text-slate-950">Recommendations in {destination}</h2>
        </div>

        <div className="mt-4 flex flex-wrap gap-2 sm:gap-4">
          {(Object.keys(CATEGORY_META) as CategoryKey[]).map((category) => {
            const meta = CATEGORY_META[category];
            const active = activeCategory === category;
            const Icon = meta.icon;

            return (
              <button
                key={category}
                type="button"
                onClick={() => setActiveCategory(category)}
                className={`inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-semibold transition ${
                  active
                    ? "bg-[#0071e3] text-white"
                    : "border border-slate-200 bg-white text-slate-600 hover:border-slate-300 hover:bg-slate-50 hover:text-slate-950"
                }`}
              >
                <Icon className="h-4 w-4" />
                <span>
                  {meta.label} ({counts[category]})
                </span>
              </button>
            );
          })}
        </div>

        <div className="mt-6 grid grid-cols-1 gap-4 md:grid-cols-2">
          {currentPlaces.length === 0 ? (
            <div className="rounded-3xl border border-dashed border-slate-200 bg-slate-50 px-5 py-10 text-center text-sm text-slate-500 md:col-span-2">
              No {activeCategory} found for {destination}.
            </div>
          ) : (
            currentPlaces.map((place) => (
              <PlaceCard
                key={`${destination}-${place.place_id}`}
                place={place}
                category={activeCategory}
                location={destination}
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
          className="fixed inset-0 z-50 flex items-end justify-center overflow-y-auto bg-slate-950/20 p-0 backdrop-blur-sm sm:items-center sm:p-4"
          onClick={closeModal}
          role="presentation"
        >
          <div
            className="max-h-[90vh] w-full max-w-2xl overflow-hidden overflow-y-auto rounded-t-2xl border border-slate-200 bg-white shadow-2xl shadow-slate-300/40 sm:mx-auto sm:rounded-2xl"
            onClick={(event) => event.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-labelledby="place-detail-title"
          >
            <div className="flex items-start justify-between gap-4 border-b border-slate-200 p-5">
              <div className="space-y-2">
                <p className="text-xs font-bold uppercase tracking-[0.24em] text-slate-400">
                  {CATEGORY_META[activeCategory].label.slice(0, -1).toUpperCase()}
                </p>
                <h3 id="place-detail-title" className="text-2xl font-black text-slate-950">
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
                className="inline-flex h-10 w-10 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-600 transition hover:bg-slate-50 hover:text-slate-950"
                aria-label="Close modal"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="relative h-64 w-full overflow-hidden bg-slate-50">
              <img
                src={buildFallbackImageDataUrl(activeCategory, selectedPlace.name)}
                alt={selectedPlace.name}
                className="h-64 w-full object-cover"
              />
            </div>

            <div className="grid gap-5 p-5 md:grid-cols-2">
              <div className="space-y-4">
                <div>
                  <p className="text-xs font-bold uppercase tracking-[0.22em] text-slate-400">Place Info</p>
                  <div className="mt-3 space-y-3 text-sm text-slate-500">
                    <p className="truncate">
                      <MapPin className="mr-1 inline h-4 w-4" />
                      {selectedPlace.address || "Address not available"}
                    </p>
                    <p>
                      <Star className="mr-1 inline h-4 w-4" /> Rating: {selectedPlace.rating.toFixed(1)} (
                      {selectedPlace.total_reviews} reviews)
                    </p>
                    <p>
                      Price:{" "}
                      {"price_range" in selectedPlace
                        ? selectedPlace.price_range
                        : "entry_fee" in selectedPlace
                          ? selectedPlace.entry_fee
                          : "Not available"}
                    </p>
                    <p>Phone: {selectedPlace.phone || "Not available"}</p>
                    <p>
                      <Globe className="mr-1 inline h-4 w-4" />
                      Website:{" "}
                      {selectedPlace.website ? (
                        <a
                          href={selectedPlace.website}
                          target="_blank"
                          rel="noreferrer noopener"
                          className="text-blue-700 underline-offset-4 hover:underline"
                        >
                          Visit website
                        </a>
                      ) : (
                        "Not available"
                      )}
                    </p>
                    <p>
                      Status:{" "}
                      {selectedPlace.open_now === true ? "Open Now" : selectedPlace.open_now === false ? "Closed" : "Not available"}
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

            <div className="flex flex-col gap-3 border-t border-slate-200 p-5 sm:flex-row">
              <button
                type="button"
                onClick={() => window.open(selectedPlace.maps_url, "_blank", "noopener,noreferrer")}
                className="inline-flex flex-1 items-center justify-center rounded-2xl bg-[#0071e3] px-4 py-3 text-sm font-bold text-white transition hover:bg-[#0077ed]"
              >
                <Navigation className="mr-2 h-4 w-4" />
                Get Directions
              </button>
              {selectedPlace.website ? (
                <button
                  type="button"
                  onClick={() => window.open(selectedPlace.website || "", "_blank", "noopener,noreferrer")}
                  className="inline-flex flex-1 items-center justify-center rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm font-semibold text-slate-700 transition hover:border-slate-300 hover:bg-slate-50 hover:text-slate-950"
                >
                  <Globe className="mr-2 h-4 w-4" />
                  Visit Website
                </button>
              ) : null}
              <button
                type="button"
                onClick={closeModal}
                className="inline-flex flex-1 items-center justify-center rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm font-semibold text-slate-700 transition hover:border-slate-300 hover:bg-slate-50 hover:text-slate-950"
              >
                <X className="mr-2 h-4 w-4" />
                Close
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
