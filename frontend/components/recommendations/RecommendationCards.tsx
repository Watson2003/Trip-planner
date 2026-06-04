"use client";

import { useMemo, useState } from "react";

import type { Recommendation } from "@/types";

type TabKey = "Hotels" | "Restaurants" | "Attractions";

interface RecommendationCardsProps {
  recommendations: Recommendation[];
  onViewOnMap?: (recommendation: Recommendation) => void;
}

const TAB_ORDER: TabKey[] = ["Hotels", "Restaurants", "Attractions"];

function normalizeCategory(category: string): TabKey {
  const lowered = category.toLowerCase();
  if (lowered.includes("hotel")) return "Hotels";
  if (lowered.includes("restaurant")) return "Restaurants";
  return "Attractions";
}

function getRating(recommendation: Recommendation) {
  return Math.max(1, Math.min(5, recommendation.rating ?? (6 - (recommendation.priority || 3))));
}

function getEstimatedCost(recommendation: Recommendation) {
  if (typeof recommendation.estimatedCostInr === "number") return recommendation.estimatedCostInr;
  const category = normalizeCategory(recommendation.category);
  if (category === "Hotels") return 3200 - recommendation.priority * 250;
  if (category === "Restaurants") return 900 - recommendation.priority * 120;
  return Math.max(0, 500 - recommendation.priority * 100);
}

function formatInr(value: number) {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(Math.max(0, value));
}

function Stars({ rating }: { rating: number }) {
  return (
    <div className="flex items-center gap-1 text-amber-400">
      {Array.from({ length: 5 }).map((_, index) => (
        <span key={index} className={index < rating ? "text-amber-400" : "text-slate-300"}>
          ★
        </span>
      ))}
    </div>
  );
}

export default function RecommendationCards({ recommendations, onViewOnMap }: RecommendationCardsProps) {
  const [activeTab, setActiveTab] = useState<TabKey>("Hotels");

  const grouped = useMemo(() => {
    return recommendations.reduce<Record<TabKey, Recommendation[]>>(
      (acc, recommendation) => {
        const bucket = normalizeCategory(recommendation.category);
        acc[bucket] = [...acc[bucket], recommendation];
        return acc;
      },
      { Hotels: [], Restaurants: [], Attractions: [] },
    );
  }, [recommendations]);

  const currentItems = grouped[activeTab];

  return (
    <section className="rounded-3xl border border-white/70 bg-white/80 p-5 shadow-glow backdrop-blur-xl">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.24em] text-slate-500">Recommendations</p>
          <h2 className="text-xl font-bold text-slate-900">RAG-backed Stops</h2>
        </div>
        <div className="inline-flex rounded-2xl bg-slate-100 p-1">
          {TAB_ORDER.map((tab) => (
            <button
              key={tab}
              type="button"
              onClick={() => setActiveTab(tab)}
              className={`rounded-xl px-4 py-2 text-sm font-semibold transition ${
                activeTab === tab ? "bg-slate-950 text-white shadow" : "text-slate-600 hover:bg-white"
              }`}
            >
              {tab}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {currentItems.length === 0 ? (
          <div className="rounded-3xl border border-dashed border-slate-300 bg-slate-50 px-5 py-8 text-sm text-slate-500 md:col-span-2 xl:col-span-3">
            No recommendations available for this category yet.
          </div>
        ) : (
          currentItems.map((recommendation) => {
            const rating = getRating(recommendation);
            const estimatedCost = getEstimatedCost(recommendation);
            return (
              <article
                key={`${recommendation.category}-${recommendation.title}`}
                className="flex h-full flex-col rounded-3xl border border-slate-200 bg-slate-50 p-4 shadow-sm transition hover:-translate-y-0.5 hover:shadow-lg"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-xs uppercase tracking-[0.18em] text-slate-500">{normalizeCategory(recommendation.category)}</p>
                    <h3 className="mt-1 text-lg font-semibold text-slate-900">{recommendation.title}</h3>
                  </div>
                  <div className="rounded-full bg-white px-3 py-1 text-xs font-semibold text-slate-600 shadow-sm">
                    {formatInr(estimatedCost)}
                  </div>
                </div>

                <p className="mt-3 flex-1 text-sm leading-6 text-slate-600">{recommendation.description}</p>

                <div className="mt-4 flex items-center justify-between gap-3">
                  <Stars rating={rating} />
                  <button
                    type="button"
                    onClick={() => onViewOnMap?.(recommendation)}
                    className="rounded-full bg-slate-950 px-4 py-2 text-xs font-semibold text-white transition hover:bg-slate-800"
                  >
                    View on Map
                  </button>
                </div>
              </article>
            );
          })
        )}
      </div>
    </section>
  );
}

