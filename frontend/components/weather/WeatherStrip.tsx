import type { WeatherData } from "@/types";

export default function WeatherStrip({ weather }: { weather: WeatherData[] }) {
  return (
    <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-card backdrop-blur-xl">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-slate-950">Weather Window</h2>
          <p className="text-sm text-slate-500">Forecast along the route</p>
        </div>
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-1">
        {weather.map((item) => (
          <div key={item.city} className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h3 className="font-semibold text-slate-950">{item.city}</h3>
                <p className="text-sm text-slate-500">{item.condition}</p>
              </div>
              <div className="text-right">
                <div className="text-2xl font-black text-slate-950">{item.temperatureC}°C</div>
                <div className="text-xs text-slate-400">
                  H {item.highC}° / L {item.lowC}°
                </div>
              </div>
            </div>
            <div className="mt-3 text-sm text-slate-500">
              Rain chance: <span className="font-semibold text-cyan-700">{item.precipitationChance}%</span>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
