"use client";

import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
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
  LocationRecommendation,
  RecommendationPayload,
  RestaurantRecommendation,
} from "@/types";
import { normalizeRecommendations } from "@/lib/trip-result";

type CategoryKey = "hotels" | "restaurants" | "attractions";
type PlaceRecommendation = HotelRecommendation | RestaurantRecommendation | AttractionRecommendation;
type CategoryMeta = {
  label: string;
  icon: typeof Hotel;
  tone: string;
};

interface RecommendationCardsProps {
  recommendations: RecommendationPayload;
  destination: string;
}

const CATEGORY_META: Record<CategoryKey, CategoryMeta> = {
  hotels: { label: "Hotels", icon: Hotel, tone: "orange" },
  restaurants: { label: "Restaurants", icon: UtensilsCrossed, tone: "cyan" },
  attractions: { label: "Attractions", icon: Target, tone: "violet" },
};

const PlaceMiniMap = dynamic(() => import("./PlaceMiniMap"), {
  ssr: false,
  loading: () => <div className="h-[200px] w-full rounded-2xl border border-[#1a1a1a] bg-[#111111] sm:h-[250px]" />,
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
      <div className="flex items-center gap-0.5 text-yellow-400">
        {Array.from({ length: fullStars }).map((_, index) => (
          <Star key={`full-${index}`} className="h-3.5 w-3.5 fill-current" />
        ))}
        {half ? (
          <span className="relative inline-block text-[#555555]">
            <Star className="h-3.5 w-3.5 fill-current" />
            <span className="absolute inset-y-0 left-0 overflow-hidden text-yellow-400" style={{ width: "50%" }}>
              <Star className="h-3.5 w-3.5 fill-current" />
            </span>
          </span>
        ) : null}
        {Array.from({ length: emptyStars }).map((_, index) => (
          <Star key={`empty-${index}`} className="h-3.5 w-3.5 text-[#555555]" />
        ))}
      </div>
      <span className="font-semibold text-white">
        {display} <span className="text-[#888888]">({totalReviews} reviews)</span>
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

function buildFallbackImageDataUrl(category: CategoryKey, title: string) {
  const label = category === "hotels" ? "Stay" : category === "restaurants" ? "Food" : "Explore";
  const safeTitle = title.replace(/[<>&]/g, "");
  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 500" role="img" aria-label="${safeTitle}">
      <defs>
        <linearGradient id="g" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stop-color="#111827"/>
          <stop offset="100%" stop-color="#0f172a"/>
        </linearGradient>
        <linearGradient id="accent" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stop-color="#D4AF37" stop-opacity="0.95"/>
          <stop offset="100%" stop-color="#FFFFFF" stop-opacity="0.25"/>
        </linearGradient>
      </defs>
      <rect width="800" height="500" fill="url(#g)"/>
      <circle cx="660" cy="95" r="120" fill="url(#accent)" opacity="0.18"/>
      <circle cx="130" cy="395" r="160" fill="#D4AF37" opacity="0.08"/>
      <rect x="48" y="48" width="704" height="404" rx="28" fill="none" stroke="#D4AF37" stroke-opacity="0.22" stroke-width="2"/>
      <text x="80" y="135" fill="#F8FAFC" font-family="Arial, Helvetica, sans-serif" font-size="28" font-weight="700" opacity="0.85">${label}</text>
      <text x="80" y="250" fill="#FFFFFF" font-family="Arial, Helvetica, sans-serif" font-size="120">${label.slice(0, 1).toUpperCase()}</text>
      <text x="80" y="330" fill="#FFFFFF" font-family="Arial, Helvetica, sans-serif" font-size="34" font-weight="700">${safeTitle}</text>
      <text x="80" y="375" fill="#CBD5E1" font-family="Arial, Helvetica, sans-serif" font-size="22">Free fallback image</text>
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
  const titleTone =
    category === "hotels"
      ? "border-[#2a2a2a] bg-[#1a1a1a] text-white"
      : category === "restaurants"
        ? "border-[#2a2a2a] bg-[#1a1a1a] text-[#a0a0a0]"
        : "border-[#2a2a2a] bg-[#1a1a1a] text-[#888888]";
  const fallbackImage = buildFallbackImageDataUrl(category, place.name || location);
  const imageSrc = place.photo_url || fallbackImage;
  const CategoryIcon = CATEGORY_META[category].icon;

  return (
    <article className="group overflow-hidden rounded-3xl border border-[#1a1a1a] bg-[#0a0a0a] shadow-xl shadow-black/20 transition hover:-translate-y-0.5 hover:border-white">
      <div className="relative h-48 w-full overflow-hidden rounded-t-xl bg-gradient-to-br from-gray-800 to-gray-900">
        <img
          src={imageSrc}
          alt={place.name}
          className="h-48 w-full object-cover"
          onError={(e) => {
            const target = e.currentTarget;
            if (target.src !== fallbackImage) {
              target.src = fallbackImage;
            }
          }}
        />

        {badge ? (
          <span
            className={`absolute right-3 top-3 rounded-full px-3 py-1 text-[11px] font-bold uppercase tracking-[0.18em] ${badge.tone}`}
          >
            {badge.label}
          </span>
        ) : null}
      </div>

      <div className="space-y-4 p-5">
        <div className="space-y-2">
          <p className="text-xs font-bold uppercase tracking-[0.24em] text-[#888888] flex items-center gap-2">
            <CategoryIcon className="h-4 w-4" />
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
              <span className="rounded-full border border-[#2a2a2a] bg-[#111111] px-3 py-1 text-xs font-semibold text-[#a0a0a0]">
                {(place as RestaurantRecommendation).price_range}
              </span>
            </>
          ) : null}
          {category === "attractions" ? (
            <>
              <span className={`rounded-full border px-3 py-1 text-xs font-semibold ${titleTone}`}>
                {(place as AttractionRecommendation).type}
              </span>
              <span className="rounded-full border border-[#2a2a2a] bg-[#111111] px-3 py-1 text-xs font-semibold text-[#a0a0a0]">
                {(place as AttractionRecommendation).entry_fee}
              </span>
            </>
          ) : null}
        </div>

        <p className="min-h-[3rem] line-clamp-2 text-sm leading-6 text-[#a0a0a0]">{place.description}</p>

        <div className="space-y-2">
          <p className="truncate text-sm text-[#888888]">
            <MapPin className="mr-1 inline h-4 w-4" />
            {place.address || location}
          </p>
          <StarRating rating={place.rating} totalReviews={place.total_reviews} />
          <p className="text-sm text-[#888888]">{category === "attractions" ? `Entry: ${priceLabel(place)}` : priceLabel(place)}</p>
        </div>

        <div className="flex flex-col gap-2 sm:flex-row">
          <button
            type="button"
            onClick={() => onViewDetails(place)}
            className="inline-flex flex-1 items-center justify-center rounded-2xl bg-white px-4 py-3 text-sm font-bold text-black transition hover:bg-[#e0e0e0]"
          >
            View Details
          </button>
          <button
            type="button"
            onClick={() => onDirections(place.maps_url)}
            className="inline-flex flex-1 items-center justify-center rounded-2xl border border-[#2a2a2a] bg-transparent px-4 py-3 text-sm font-semibold text-white transition hover:bg-[#1a1a1a]"
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

  const currentPlaces = normalizedRecommendations[activeCategory] ?? [];
  const activeCounts = {
    hotels: normalizedRecommendations.hotels.length,
    restaurants: normalizedRecommendations.restaurants.length,
    attractions: normalizedRecommendations.attractions.length,
  };
  const hasRecommendations = Boolean(activeCounts.hotels || activeCounts.restaurants || activeCounts.attractions);

  const closeModal = () => {
    setModalOpen(false);
    setSelectedPlace(null);
  };

  if (!hasRecommendations) {
    return (
      <section className="rounded-[2rem] border border-[#1a1a1a] bg-[#0a0a0a] p-8 text-center shadow-2xl">
        <div className="mx-auto flex max-w-md flex-col items-center gap-3">
          <div className="text-4xl">🗺️</div>
          <h2 className="text-xl font-black text-white">Plan a trip to see recommendations in {destination}</h2>
          <p className="text-sm leading-6 text-[#a0a0a0]">
            Once your route is planned, real hotels, restaurants, and attractions for the destination will appear here.
          </p>
        </div>
      </section>
    );
  }

  return (
    <>
      <section className="rounded-[2rem] border border-[#1a1a1a] bg-[#0a0a0a] p-5 shadow-2xl shadow-black/20">
        <div className="mb-5 space-y-2">
          <p className="text-xs font-bold uppercase tracking-[0.28em] text-white">RECOMMENDATIONS</p>
          <h2 className="text-2xl font-black tracking-tight text-white">Recommendations in {destination}</h2>
        </div>

        <div className="mt-4 flex flex-wrap gap-2 sm:gap-4">
          {(Object.keys(CATEGORY_META) as CategoryKey[]).map((category) => {
            const meta = CATEGORY_META[category];
            const active = activeCategory === category;
            const count = activeCounts[category];
            const Icon = meta.icon;

            return (
              <button
                key={category}
                type="button"
                onClick={() => setActiveCategory(category)}
                className={`inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-semibold transition ${
                  active
                    ? "bg-white text-black"
                    : "border border-[#2a2a2a] bg-transparent text-[#888888] hover:border-white hover:text-white"
                }`}
              >
                <Icon className="h-4 w-4" />
                <span>
                  {meta.label} ({count})
                </span>
              </button>
            );
          })}
        </div>

        <div className="mt-6 grid grid-cols-1 gap-4 md:grid-cols-2">
          {currentPlaces.length === 0 ? (
            <div className="rounded-3xl border border-dashed border-[#2a2a2a] bg-[#111111] px-5 py-10 text-center text-sm text-[#888888] md:col-span-2">
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
          className="fixed inset-0 z-50 flex items-end justify-center overflow-y-auto bg-black/70 p-0 backdrop-blur-sm sm:items-center sm:p-4"
          onClick={closeModal}
          role="presentation"
        >
          <div
            className="max-h-[90vh] w-full max-w-2xl overflow-hidden overflow-y-auto rounded-t-2xl border border-[#1a1a1a] bg-[#0a0a0a] shadow-2xl shadow-black/40 sm:mx-auto sm:rounded-2xl"
            onClick={(event) => event.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-labelledby="place-detail-title"
          >
            <div className="flex items-start justify-between gap-4 border-b border-[#1a1a1a] p-5">
              <div className="space-y-2">
                <p className="text-xs font-bold uppercase tracking-[0.24em] text-white">
                  {CATEGORY_META[activeCategory].label.slice(0, -1).toUpperCase()}
                </p>
                <h3 id="place-detail-title" className="text-2xl font-black text-white">
                  {selectedPlace.name}
                </h3>
                {openNowLabel(selectedPlace.open_now) ? (
                  <span
                    className={`inline-flex rounded-full px-3 py-1 text-xs font-bold ${openNowLabel(selectedPlace.open_now)?.tone}`}
                  >
                    {openNowLabel(selectedPlace.open_now)?.label}
                  </span>
                ) : null}
              </div>
              <button
                type="button"
                onClick={closeModal}
                className="inline-flex h-10 w-10 items-center justify-center rounded-full border border-[#2a2a2a] bg-[#111111] text-white transition hover:bg-[#1a1a1a]"
                aria-label="Close modal"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="relative h-64 w-full overflow-hidden bg-gradient-to-br from-gray-800 to-gray-900">
              <img
                src={buildFallbackImageDataUrl(activeCategory, selectedPlace.name)}
                alt={selectedPlace.name}
                className="h-64 w-full object-cover"
              />
            </div>

            <div className="grid gap-5 p-5 md:grid-cols-2">
              <div className="space-y-4">
                <div>
                  <p className="text-xs font-bold uppercase tracking-[0.22em] text-[#888888]">Place Info</p>
                  <div className="mt-3 space-y-3 text-sm text-[#a0a0a0]">
                    <p className="truncate">
                      <MapPin className="mr-1 inline h-4 w-4" />
                      {selectedPlace.address || "Address not available"}
                    </p>
                    <p>
                      <Star className="mr-1 inline h-4 w-4" /> Rating: {selectedPlace.rating.toFixed(1)} (
                      {selectedPlace.total_reviews} reviews)
                    </p>
                    <p>Price: {priceLabel(selectedPlace)}</p>
                    <p>Phone: {selectedPlace.phone || "Not available"}</p>
                    <p>
                      <Globe className="mr-1 inline h-4 w-4" />
                      Website:{" "}
                      {selectedPlace.website ? (
                        <a
                          href={selectedPlace.website}
                          target="_blank"
                          rel="noreferrer noopener"
                          className="text-white underline-offset-4 hover:underline"
                        >
                          Visit website
                        </a>
                      ) : (
                        "Not available"
                      )}
                    </p>
                    <p>
                      Status:{" "}
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
                  <p className="text-xs font-bold uppercase tracking-[0.22em] text-[#888888]">Mini Map</p>
                  <div className="mt-3">
                    <PlaceMiniMap lat={selectedPlace.lat} lng={selectedPlace.lng} />
                  </div>
                </div>
              </div>
            </div>

            <div className="flex flex-col gap-3 border-t border-[#1a1a1a] p-5 sm:flex-row">
              <button
                type="button"
                onClick={() => window.open(selectedPlace.maps_url, "_blank", "noopener,noreferrer")}
                className="inline-flex flex-1 items-center justify-center rounded-2xl bg-white px-4 py-3 text-sm font-bold text-black transition hover:bg-[#e0e0e0]"
              >
                <Navigation className="mr-2 h-4 w-4" />
                Get Directions
              </button>
              {selectedPlace.website ? (
                <button
                  type="button"
                  onClick={() => window.open(selectedPlace.website || "", "_blank", "noopener,noreferrer")}
                  className="inline-flex flex-1 items-center justify-center rounded-2xl border border-[#2a2a2a] bg-transparent px-4 py-3 text-sm font-semibold text-white transition hover:bg-[#1a1a1a]"
                >
                  <Globe className="mr-2 h-4 w-4" />
                  Visit Website
                </button>
              ) : null}
              <button
                type="button"
                onClick={closeModal}
                className="inline-flex flex-1 items-center justify-center rounded-2xl border border-[#2a2a2a] bg-transparent px-4 py-3 text-sm font-semibold text-white transition hover:bg-[#1a1a1a]"
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
