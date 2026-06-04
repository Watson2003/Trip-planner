"use client";

import type { WeatherData } from "@/types";

interface WeatherPanelProps {
  weatherData: WeatherData[];
}

function weatherEmoji(condition: string, fallback?: string) {
  const value = condition.toLowerCase();
  if (fallback) return fallback;
  if (value.includes("thunder") || value.includes("storm")) return "\u26c8\ufe0f";
  if (value.includes("rain") || value.includes("drizzle")) return "\ud83c\udf27\ufe0f";
  if (value.includes("snow")) return "\u2744\ufe0f";
  if (value.includes("cloud")) return "\u2601\ufe0f";
  if (value.includes("fog") || value.includes("mist")) return "\ud83c\udf2b\ufe0f";
  if (value.includes("wind")) return "\ud83d\udca8";
  return "\u2600\ufe0f";
}

function formatDayLabel(day?: string) {
  if (!day) return "Today";
  return day;
}

export default function WeatherPanel({ weatherData }: WeatherPanelProps) {
  const grouped = weatherData.reduce<Record<string, WeatherData[]>>((acc, item) => {
    const key = item.location ?? item.city ?? "Location";
    acc[key] = [...(acc[key] ?? []), item];
    return acc;
  }, {});

  const hasAlerts = weatherData.some((item) => Boolean(item.severeAlert));
  const locations = Object.keys(grouped).slice(0, 2);

  return (
    <section className="rounded-3xl border border-white/70 bg-white/80 p-5 shadow-glow backdrop-blur-xl">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-[0.24em] text-slate-500">Weather</p>
          <h2 className="text-xl font-bold text-slate-900">5-Day Forecast</h2>
        </div>
        <div className="rounded-full bg-slate-950 px-3 py-1 text-xs font-semibold text-white">
          Origin + Destination
        </div>
      </div>

      {hasAlerts && (
        <div className="mt-4 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          Severe weather detected on at least one day. Review the route before driving.
        </div>
      )}

      <div className="mt-5 grid gap-4 lg:grid-cols-2">
        {locations.map((location) => (
          <div key={location} className="rounded-3xl border border-slate-200 bg-slate-50 p-4">
            <div className="mb-3 flex items-center justify-between gap-2">
              <div>
                <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Location</p>
                <h3 className="text-lg font-semibold text-slate-900">{location}</h3>
              </div>
              <span className="rounded-full bg-white px-3 py-1 text-xs font-semibold text-slate-600 shadow-sm">
                5 days
              </span>
            </div>

            <div className="grid gap-3">
              {grouped[location].slice(0, 5).map((day) => {
                const alert = day.severeAlert;
                return (
                  <div
                    key={`${location}-${day.day ?? day.city ?? day.temperatureC}`}
                    className="rounded-2xl border border-white bg-white p-4 shadow-sm"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="text-sm font-semibold text-slate-900">{formatDayLabel(day.day)}</div>
                        <div className="mt-1 text-sm text-slate-500">{day.condition}</div>
                      </div>
                      <div className="text-right">
                        <div className="text-2xl">{weatherEmoji(day.condition, day.icon)}</div>
                        <div className="mt-1 text-2xl font-black text-slate-900">{Math.round(day.temperatureC)}°C</div>
                      </div>
                    </div>

                    <div className="mt-3 flex items-center justify-between text-xs text-slate-500">
                      <span>High {day.highC ?? Math.round(day.temperatureC)}°</span>
                      <span>Low {day.lowC ?? Math.round(day.temperatureC)}°</span>
                    </div>

                    {alert && (
                      <div className="mt-3 rounded-xl bg-red-50 px-3 py-2 text-xs font-semibold text-red-700">
                        {alert}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
