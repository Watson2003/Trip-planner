import type { WeatherData } from "@/types";

export default function WeatherStrip({ weather }: { weather: WeatherData[] }) {
  return (
    <section className="rounded-3xl border border-[#1a1a1a] bg-[#0a0a0a] p-6 shadow-glow backdrop-blur-xl">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold">Weather Window</h2>
          <p className="text-sm text-[#888888]">Forecast along the route</p>
        </div>
      </div>
      <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-1">
        {weather.map((item) => (
          <div key={item.city} className="rounded-2xl border border-[#1a1a1a] bg-[#111111] p-4">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h3 className="font-semibold">{item.city}</h3>
                <p className="text-sm text-[#a0a0a0]">{item.condition}</p>
              </div>
              <div className="text-right">
                <div className="text-2xl font-black">{item.temperatureC}°C</div>
                <div className="text-xs text-[#888888]">
                  H {item.highC}° / L {item.lowC}°
                </div>
              </div>
            </div>
            <div className="mt-3 text-sm text-[#a0a0a0]">
              Rain chance: <span className="font-semibold">{item.precipitationChance}%</span>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
