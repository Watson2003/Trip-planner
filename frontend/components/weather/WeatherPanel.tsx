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

function formatWeatherDate(dateString: string, dayName: string) {
  const parsed = new Date(`${dateString}T00:00:00`);
  const formatted = Number.isNaN(parsed.getTime())
    ? dateString
    : parsed.toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
      });
  return `${dayName}, ${formatted}`;
}

function splitWeatherByLocation(weatherData: DailyWeather[], origin: string, destination: string) {
  return {
    originWeather: weatherData.filter((item) => item.location === origin),
    destinationWeather: weatherData.filter((item) => item.location === destination),
  };
}

function WeatherCard({ item }: { item: DailyWeather }) {
  const alert = item.alert;

  return (
    <article className="min-w-[200px] rounded-3xl border border-slate-700/70 bg-slate-950/80 p-4 text-slate-100 shadow-lg backdrop-blur sm:min-w-0">
      <div className="mb-4 text-center">
        <div className="text-sm font-semibold text-slate-300">{formatWeatherDate(item.date, item.day_name)}</div>
        <div className="mt-3 text-5xl">{item.weather_icon}</div>
        <div className="mt-3 text-base font-medium text-slate-100">{item.condition}</div>
      </div>

      <div className="space-y-2 rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-slate-200">
        <div className="flex items-center justify-between gap-3">
          <span>🌡️ Temperature</span>
          <span className="font-semibold">
            {Math.round(item.temp_min_celsius)}°C ~ {Math.round(item.temp_max_celsius)}°C
          </span>
        </div>
        <div className="flex items-center justify-between gap-3">
          <span>🤔 Feels like</span>
          <span className="font-semibold">{Math.round(item.temp_feels_like)}°C</span>
        </div>
        <div className="flex items-center justify-between gap-3">
          <span>💧 Humidity</span>
          <span className="font-semibold">{item.humidity_percent}%</span>
        </div>
        <div className="flex items-center justify-between gap-3">
          <span>💨 Wind</span>
          <span className="font-semibold">{item.wind_speed_kmh.toFixed(1)} km/h</span>
        </div>
        <div className="flex items-center justify-between gap-3">
          <span>🌂 Rain chance</span>
          <span className="font-semibold">{item.rain_chance_percent}% chance of rain</span>
        </div>
      </div>

      {alert && (
        <div className="mt-4 rounded-2xl border border-red-500/40 bg-red-500/15 px-4 py-3 text-sm font-semibold text-red-200">
          ⚠️ {alert}
        </div>
      )}
    </article>
  );
}

function WeatherSection({ title, weather }: { title: string; weather: DailyWeather[] }) {
  return (
    <section className="w-full rounded-[2rem] border border-slate-700/60 bg-slate-900/80 p-5 shadow-xl">
      <div className="mb-4">
        <p className="text-xs uppercase tracking-[0.22em] text-slate-400">Weather Window</p>
        <h3 className="mt-1 text-base font-bold text-slate-100 sm:text-lg">{title}</h3>
      </div>

      {weather.length ? (
        <div className="flex flex-row gap-4 overflow-x-auto pb-4">
          {weather.map((item) => (
            <WeatherCard key={`${item.location}-${item.date}`} item={item} />
          ))}
        </div>
      ) : (
        <div className="w-full rounded-2xl border border-dashed border-slate-700 bg-slate-950/60 px-4 py-8 text-center text-sm text-slate-400">
          No weather data available for selected dates.
        </div>
      )}
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
      <section className="w-full rounded-[2rem] border border-blue-500/40 bg-blue-500/10 p-6 text-center text-blue-50 shadow-xl">
        <div className="flex flex-col items-center text-center">
          <div className="text-6xl">📅</div>
          <h2 className="mt-4 text-2xl font-bold">Forecast Unavailable</h2>
          <p className="mt-3 max-w-xl text-sm leading-6 text-blue-100">
            {message ?? "Forecast not available yet. Check back closer to your travel date."}
          </p>
          <p className="mt-3 text-sm text-blue-200/90">OpenWeatherMap provides forecasts up to 5 days ahead.</p>
        </div>
      </section>
    );
  }

  if (status === "past_dates") {
    return (
      <section className="w-full rounded-[2rem] border border-amber-500/40 bg-amber-500/10 p-6 text-center text-amber-50 shadow-xl">
        <div className="flex flex-col items-center text-center">
          <div className="text-6xl">⚠️</div>
          <h2 className="mt-4 text-2xl font-bold">Past Travel Dates</h2>
          <p className="mt-3 max-w-xl text-sm leading-6 text-amber-100">
            These travel dates have already passed. No forecast available.
          </p>
        </div>
      </section>
    );
  }

  const { originWeather, destinationWeather } = splitWeatherByLocation(weatherData, origin, destination);
  const hasWeather = weatherData.length > 0;

  return (
    <section className="w-full rounded-[2rem] border border-slate-700/60 bg-slate-950/90 p-5 shadow-2xl">
      <div className="mb-5 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.22em] text-slate-400">Weather</p>
          <h2 className="text-xl font-black text-slate-100 sm:text-2xl">Forecast for exact travel dates</h2>
        </div>
        <div className="text-sm text-slate-400">
          {startDate} to {endDate}
        </div>
      </div>

      {!hasWeather ? (
        <div className="w-full rounded-2xl border border-dashed border-slate-700 bg-slate-900/70 px-4 py-8 text-center text-sm text-slate-400">
          No weather data available for selected dates.
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
          <WeatherSection title={`📍 Origin Weather — ${origin}`} weather={originWeather} />
          <WeatherSection title={`📍 Destination Weather — ${destination}`} weather={destinationWeather} />
        </div>
      )}
    </section>
  );
}
