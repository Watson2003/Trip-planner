"use client";

import type { DailyWeather } from "@/types";

interface WeatherPanelProps {
  weatherData: DailyWeather[];
  startDate: string;
  endDate: string;
  origin: string;
  destination: string;
  status: "success" | "unavailable" | "past_dates";
  message?: string;
}

const LOCATION_ALIASES: Record<string, string> = {
  bangalore: "bengaluru",
  bengaluru: "bengaluru",
  kodaikanal: "kodaikanal",
};

function formatWeatherDate(dateString: string, dayName: string) {
  const parsed = new Date(`${dateString}T00:00:00`);
  const formatted = Number.isNaN(parsed.getTime())
    ? dateString
    : parsed.toLocaleDateString("en-US", {
        weekday: "short",
        month: "short",
        day: "numeric",
      });
  return formatted || dayName;
}

function normalizeLocation(value: string) {
  const normalized = value.trim().toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
  return LOCATION_ALIASES[normalized] ?? normalized;
}

function splitWeatherByLocation(weatherData: DailyWeather[], origin: string, destination: string) {
  const normalizedOrigin = normalizeLocation(origin);
  const normalizedDestination = normalizeLocation(destination);

  return {
    originWeather: weatherData.filter((item) => normalizeLocation(item.location) === normalizedOrigin),
    destinationWeather: weatherData.filter((item) => normalizeLocation(item.location) === normalizedDestination),
  };
}

function WeatherDayCard({ item }: { item: DailyWeather }) {
  return (
    <article className="min-w-[130px] rounded-xl border border-[#1a1a1a] bg-[#111111] p-3 text-center text-white">
      <div className="text-xs text-[#888888]">{formatWeatherDate(item.date, item.day_name)}</div>
      <div className="my-2 text-3xl">{item.weather_icon}</div>
      <div className="mb-2 text-xs text-[#a0a0a0]">{item.condition}</div>
      <div className="space-y-1 text-left text-xs text-[#a0a0a0]">
        <div className="flex items-center gap-1">🌡️ {Math.round(item.temp_min_celsius)}° ~ {Math.round(item.temp_max_celsius)}°C</div>
        <div className="flex items-center gap-1">🤔 Feels {Math.round(item.temp_feels_like)}°C</div>
        <div className="flex items-center gap-1">💧 {item.humidity_percent}%</div>
        <div className="flex items-center gap-1">💨 {item.wind_speed_kmh.toFixed(1)} km/h</div>
        <div className="flex items-center gap-1">🌂 {item.rain_chance_percent}% rain</div>
      </div>
      {item.alert ? (
        <div className="mt-2 rounded-lg bg-red-500/20 px-2 py-1 text-center text-xs text-red-400">{item.alert}</div>
      ) : null}
    </article>
  );
}

function WeatherLocationSection({ title, weather }: { title: string; weather: DailyWeather[] }) {
  return (
    <section className="overflow-hidden rounded-2xl border border-[#1a1a1a] bg-[#0a0a0a]">
      <div className="border-b border-[#1a1a1a] px-4 py-3">
        <h3 className="text-sm font-semibold text-white">{title}</h3>
      </div>
      <div className="p-4">
        {weather.length ? (
          <div className="flex flex-row gap-3 overflow-x-auto pb-2">
            {weather.map((item) => (
              <WeatherDayCard key={`${item.location}-${item.date}`} item={item} />
            ))}
          </div>
        ) : (
          <div className="rounded-xl border border-dashed border-[#2a2a2a] px-4 py-8 text-center text-sm text-[#888888]">
            No weather data available for selected dates.
          </div>
        )}
      </div>
    </section>
  );
}

export default function WeatherPanel({
  weatherData,
  startDate,
  endDate,
  origin,
  destination,
  status,
  message,
}: WeatherPanelProps) {
  if (status === "unavailable") {
    return (
      <section className="w-full rounded-2xl border border-[#1a1a1a] bg-[#0a0a0a] p-6 text-center text-white">
        <div className="text-5xl">📅</div>
        <h2 className="mt-4 text-2xl font-bold">Forecast Unavailable</h2>
        <p className="mt-3 text-sm text-[#a0a0a0]">{message ?? "Forecast not available yet. Check back closer to your travel date."}</p>
      </section>
    );
  }

  if (status === "past_dates") {
    return (
      <section className="w-full rounded-2xl border border-[#1a1a1a] bg-[#0a0a0a] p-6 text-center text-white">
        <div className="text-5xl">⚠️</div>
        <h2 className="mt-4 text-2xl font-bold">Past Travel Dates</h2>
        <p className="mt-3 text-sm text-[#a0a0a0]">These travel dates have already passed. No forecast available.</p>
      </section>
    );
  }

  const { originWeather, destinationWeather } = splitWeatherByLocation(weatherData, origin, destination);
  const hasWeather = weatherData.length > 0;

  return (
    <section className="w-full overflow-hidden rounded-2xl border border-[#1a1a1a] bg-[#0a0a0a] text-white">
      <div className="flex items-center justify-between gap-3 border-b border-[#1a1a1a] px-4 pt-4 pb-2">
        <div>
          <p className="text-xs uppercase tracking-[0.24em] text-[#888888]">Weather</p>
          <h2 className="text-lg font-bold">Forecast for exact travel dates</h2>
        </div>
        <div className="text-sm text-[#888888]">
          {startDate} to {endDate}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 p-4 md:grid-cols-2">
        {hasWeather ? (
          <>
            <WeatherLocationSection title={`📍 Origin Weather — ${origin}`} weather={originWeather} />
            <WeatherLocationSection title={`📍 Destination Weather — ${destination}`} weather={destinationWeather} />
          </>
        ) : (
          <div className="rounded-xl border border-dashed border-[#2a2a2a] px-4 py-8 text-center text-sm text-[#888888] md:col-span-2">
            No weather data available for selected dates.
          </div>
        )}
      </div>
    </section>
  );
}
