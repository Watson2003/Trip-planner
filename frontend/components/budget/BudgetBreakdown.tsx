"use client";

import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";

import type { BudgetBreakdown as BudgetBreakdownData, FuelCalculation, VehicleDetails } from "@/types";

interface BudgetBreakdownProps {
  budget: BudgetBreakdownData;
  fuelCalculation?: FuelCalculation | null;
  vehicle?: VehicleDetails | null;
  userBudget: number;
  routeDistanceKm?: number | null;
}

const INR_PER_USD = 83.5;
const FUEL_PRICE_PER_UNIT: Record<VehicleDetails["fuel_type"], number> = {
  petrol: 102.92,
  diesel: 89.62,
  electric: 8.5,
  cng: 75.5,
};

const COLORS = {
  Fuel: "#f97316",
  Hotels: "#2563eb",
  Food: "#16a34a",
  Tolls: "#8b5cf6",
  Misc: "#6b7280",
} as const;

function formatInr(value: number) {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(value);
}

function buildFallbackFuelCalculation(
  vehicle: VehicleDetails | null | undefined,
  routeDistanceKm: number | null | undefined,
  people: number,
  budgetFuelInr?: number,
) {
  const distanceKm = Math.max(0, Number(routeDistanceKm ?? 0));
  const mileage = Math.max(0, Number(vehicle?.mileage_kmpl ?? 0));
  const fuelRequired = distanceKm / mileage;
  const pricePerLitre = FUEL_PRICE_PER_UNIT[vehicle?.fuel_type ?? "petrol"];
  const totalFuelCostInr =
    distanceKm && mileage
      ? fuelRequired * pricePerLitre
      : Math.max(0, Number(budgetFuelInr ?? 0));
  const resolvedFuelRequired = mileage > 0 ? totalFuelCostInr / pricePerLitre : 0;
  const resolvedDistance = routeDistanceKm && routeDistanceKm > 0 ? routeDistanceKm : resolvedFuelRequired * mileage;

  return {
    distance_km: resolvedDistance,
    mileage_kmpl: mileage,
    fuel_required_litres: resolvedFuelRequired,
    fuel_price_per_litre: pricePerLitre,
    total_fuel_cost_inr: totalFuelCostInr,
    total_fuel_cost_usd: totalFuelCostInr / INR_PER_USD,
    refueling_stops:
      vehicle?.tank_capacity_litres && vehicle.tank_capacity_litres > 0
        ? Math.floor(resolvedFuelRequired / vehicle.tank_capacity_litres)
        : 0,
    cost_per_person_inr: totalFuelCostInr / Math.max(1, people),
    vehicle_name: vehicle?.vehicle_name ?? "Unknown Vehicle",
    vehicle_type: vehicle?.vehicle_type ?? "car",
    fuel_type: vehicle?.fuel_type ?? "petrol",
  };
}

function normalizeBudget(
  budget: BudgetBreakdownData,
  fuelCalculation?: FuelCalculation | null,
  vehicle?: VehicleDetails | null,
  routeDistanceKm?: number | null,
) {
  const fallbackFuel = buildFallbackFuelCalculation(vehicle, routeDistanceKm, vehicle?.number_of_people ?? 1);
  const resolvedFuel = fuelCalculation?.distance_km ? fuelCalculation : fallbackFuel;

  const fuelInr = resolvedFuel?.total_fuel_cost_inr ?? budget.breakdown?.fuel?.inr ?? budget.fuel ?? 0;
  const tollsInr = budget.breakdown?.tolls?.inr ?? budget.tolls ?? 0;
  const inferredHotelNights =
    budget.hotel_nights ??
    budget.hotel_daily_breakdown?.length ??
    Math.max(1, (budget.trip_days ?? 1) - 1);
  const hotelsInr =
    (budget.hotel_price_per_night && inferredHotelNights
      ? budget.hotel_price_per_night * inferredHotelNights
      : null) ??
    budget.breakdown?.hotels?.inr ??
    budget.hotels ??
    budget.lodging ??
    0;
  const foodInr = budget.breakdown?.food?.inr ?? budget.food ?? 0;
  const miscInr = budget.breakdown?.miscellaneous?.inr ?? budget.miscellaneous ?? budget.activities ?? 0;
  const totalInr = budget.breakdown?.total?.inr ?? budget.total ?? fuelInr + tollsInr + hotelsInr + foodInr + miscInr;

  return {
    rows: [
      { label: "Fuel", inr: fuelInr },
      { label: "Hotels", inr: hotelsInr },
      { label: "Food", inr: foodInr },
      { label: "Tolls", inr: tollsInr },
      { label: "Misc", inr: miscInr },
      { label: "Total", inr: totalInr },
    ],
    totalInr,
    fuelInr,
  };
}

function PieLabel({
  cx,
  cy,
  midAngle,
  innerRadius,
  outerRadius,
  percent,
  value,
}: {
  cx?: number;
  cy?: number;
  midAngle?: number;
  innerRadius?: number;
  outerRadius?: number;
  percent?: number;
  value?: number;
}) {
  if (!cx || !cy || !midAngle || !innerRadius || !outerRadius || !percent || percent < 0.05 || !value) return null;

  const RADIAN = Math.PI / 180;
  const radius = innerRadius + (outerRadius - innerRadius) * 0.65;
  const x = cx + radius * Math.cos(-midAngle * RADIAN);
  const y = cy + radius * Math.sin(-midAngle * RADIAN);

  return (
    <text
      x={x}
      y={y}
      fill="#ffffff"
      textAnchor={x > cx ? "start" : "end"}
      dominantBaseline="central"
      className="text-[11px] font-semibold"
    >
      {`${Math.round(percent * 100)}%`}
    </text>
  );
}

export default function BudgetBreakdown({
  budget,
  fuelCalculation,
  vehicle,
  userBudget,
  routeDistanceKm,
}: BudgetBreakdownProps) {
  const budgetDetails = budget as BudgetBreakdownData & {
    hotel_cost_inr?: number;
    food_cost_inr?: number;
    fuel_cost_inr?: number;
    toll_cost_inr?: number;
    misc_cost_inr?: number;
    number_of_people?: number;
    destination?: string;
  };
  const data = normalizeBudget(budget, fuelCalculation, vehicle, routeDistanceKm);
  const fuelDetails =
    fuelCalculation && fuelCalculation.distance_km > 0
      ? fuelCalculation
      : buildFallbackFuelCalculation(vehicle, routeDistanceKm, vehicle?.number_of_people ?? 1, data.fuelInr);
  const travellers = budgetDetails.number_of_people ?? vehicle?.number_of_people ?? 1;
  const hotelTotal =
    budget.hotel_price_per_night
      ? budget.hotel_price_per_night * (budget.hotel_nights || 1)
      : budgetDetails.hotel_cost_inr ?? budget.hotels ?? budget.lodging ?? data.rows[1]?.inr ?? 0;
  const hotelExplanation = budget.hotel_price_per_night
    ? `₹${budget.hotel_price_per_night.toLocaleString("en-IN")}/night × ${budget.hotel_nights || 1} night${
        (budget.hotel_nights || 1) > 1 ? "s" : ""
      } (${budget.hotel_category || "Mid"} hotel in ${budgetDetails.destination || ""})`
    : budget.hotel_explanation || "";
  const foodTotal =
    budget.food_price_per_day_per_person
      ? budget.food_price_per_day_per_person * (budgetDetails.number_of_people || 1) * (budget.food_days || 1)
      : budgetDetails.food_cost_inr ?? budget.food ?? data.rows[2]?.inr ?? 0;
  const grandTotal =
    (budgetDetails.fuel_cost_inr || fuelDetails?.total_fuel_cost_inr || 0) +
    hotelTotal +
    foodTotal +
    (budgetDetails.toll_cost_inr || budget.tolls || 0) +
    (budgetDetails.misc_cost_inr || budget.miscellaneous || 0);
  const resolvedFuelTotal = budgetDetails.fuel_cost_inr || fuelDetails?.total_fuel_cost_inr || 0;
  const resolvedTollTotal = budgetDetails.toll_cost_inr || budget.tolls || 0;
  const resolvedMiscTotal = budgetDetails.misc_cost_inr || budget.miscellaneous || 0;
  const difference = userBudget - grandTotal;
  const overBudget = difference < 0;
  const differenceAbs = Math.abs(difference);
  const budgetProgress = Math.min(100, (grandTotal / Math.max(userBudget, 1)) * 100);
  const chartData = [
    { name: "Fuel", value: resolvedFuelTotal, color: COLORS.Fuel },
    { name: "Hotels", value: hotelTotal, color: COLORS.Hotels },
    { name: "Food", value: foodTotal, color: COLORS.Food },
    { name: "Tolls", value: resolvedTollTotal, color: COLORS.Tolls },
    { name: "Misc", value: resolvedMiscTotal, color: COLORS.Misc },
  ];
  const perPersonItems = [
    {
      label: "Fuel",
      icon: "⛽",
      total: resolvedFuelTotal,
      perPerson: Math.round(
        resolvedFuelTotal /
          Math.max(travellers || 1, 1),
      ),
    },
    {
      label: "Hotel",
      icon: "🏨",
      total: hotelTotal,
      perPerson: Math.round(
        hotelTotal /
          Math.max(travellers || 1, 1),
      ),
    },
    {
      label: "Food",
      icon: "🍽️",
      total: foodTotal,
      perPerson: Math.round(
        foodTotal /
          Math.max(travellers || 1, 1),
      ),
    },
    {
      label: "Tolls",
      icon: "🛣️",
      total: resolvedTollTotal,
      perPerson: Math.round(
        resolvedTollTotal /
          Math.max(travellers || 1, 1),
      ),
    },
    {
      label: "Misc",
      icon: "🎯",
      total: resolvedMiscTotal,
      perPerson: Math.round(
        resolvedMiscTotal /
          Math.max(travellers || 1, 1),
      ),
    },
  ];

  return (
    <section className="w-full overflow-hidden rounded-[2rem] border border-gray-700 bg-gray-900 text-white shadow-2xl">
      <div className="border-b border-gray-700 px-5 pt-5 pb-3">
        <p className="text-xs uppercase tracking-[0.24em] text-gray-400">Budget</p>
        <h2 className="text-xl font-bold text-white">Your Trip Cost Breakdown</h2>
        <p className="mt-1 text-sm text-gray-400">
          {vehicle?.vehicle_name ?? "Vehicle"} · {vehicle?.vehicle_type ?? "car"} · {vehicle?.fuel_type ?? "petrol"}
        </p>
      </div>

      <div className="space-y-6 p-5">
        <div className="rounded-2xl border border-orange-500/30 bg-orange-500/10 p-4">
          <div className="mb-4 text-sm font-bold text-orange-200">Fuel Details</div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2 text-sm text-gray-200">
              <Row label="Distance" value={`${fuelDetails?.distance_km ?? 0} km`} />
              <Row label="Fuel needed" value={`${(fuelDetails?.fuel_required_litres ?? 0).toFixed(2)} litres`} />
              <Row label="Price per litre" value={formatInr(fuelDetails?.fuel_price_per_litre ?? 0)} />
              <Row label="Refueling stops" value={`${fuelDetails?.refueling_stops ?? 0}`} />
            </div>
            <div className="space-y-2 text-sm text-gray-200">
              <Row label="Vehicle" value={fuelDetails?.vehicle_name ?? vehicle?.vehicle_name ?? "-"} />
              <Row label="Mileage" value={`${fuelDetails?.mileage_kmpl ?? vehicle?.mileage_kmpl ?? 0} km/l`} />
              <Row label="Travellers" value={`${travellers}`} />
              <Row label="Per person" value={formatInr(fuelDetails?.cost_per_person_inr ?? 0)} />
            </div>
          </div>
          <div className="mt-4 rounded-2xl border border-orange-400/30 bg-gray-950/80 px-4 py-3">
            <div className="text-sm font-semibold text-gray-300">Total Fuel Cost</div>
            <div className="mt-1 text-2xl font-black text-orange-300">{formatInr(fuelDetails?.total_fuel_cost_inr ?? data.fuelInr)}</div>
          </div>
        </div>

        <div className="overflow-x-auto rounded-2xl border border-gray-700 bg-gray-950/70">
          <table className="min-w-[720px] w-full border-collapse">
            <thead>
              <tr className="bg-gray-800 text-left text-sm text-gray-300">
                <th className="px-4 py-3 font-semibold">Category</th>
                <th className="px-4 py-3 font-semibold text-right">Amount (INR)</th>
                <th className="px-4 py-3 font-semibold text-right">Amount (USD)</th>
              </tr>
            </thead>
            <tbody>
              {data.rows.map((row, index) => {
                if (row.label === "Hotels") {
                  return (
                    <tr key={row.label} className="border-b border-gray-700/50">
                      <td className="py-3 px-4">
                        <div className="flex items-center gap-2">
                          <span>🏨</span>
                          <span className="text-white">Hotels</span>
                        </div>
                        <div className="text-xs text-gray-400 mt-1">{hotelExplanation}</div>
                      </td>
                      <td className="py-3 px-4 text-right text-white">₹{hotelTotal.toLocaleString("en-IN")}</td>
                      <td className="py-3 px-4 text-right text-gray-400">${(hotelTotal / 83.5).toFixed(2)}</td>
                    </tr>
                  );
                }

                if (row.label === "Food") {
                  return (
                    <tr key={row.label} className="border-b border-gray-700/50">
                      <td className="py-3 px-4">
                        <div className="flex items-center gap-2">
                          <span>🍽️</span>
                          <span className="text-white">Food</span>
                        </div>
                        <div className="text-xs text-gray-400 mt-1">{budget.food_explanation}</div>
                      </td>
                      <td className="py-3 px-4 text-right text-white">₹{foodTotal.toLocaleString("en-IN")}</td>
                      <td className="py-3 px-4 text-right text-gray-400">${(foodTotal / 83.5).toFixed(2)}</td>
                    </tr>
                  );
                }

                if (row.label === "Total") {
                  return (
                    <tr key={row.label} className="bg-orange-500/10 font-bold">
                      <td className="py-3 px-4 text-white">Total</td>
                      <td className="py-3 px-4 text-right text-orange-400">₹{grandTotal.toLocaleString("en-IN")}</td>
                      <td className="py-3 px-4 text-right text-orange-300">${(grandTotal / 83.5).toFixed(2)}</td>
                    </tr>
                  );
                }

                return (
                  <tr
                    key={row.label}
                    className={index % 2 === 0 ? "bg-gray-900" : "bg-gray-950"}
                  >
                    <td className="border-t border-gray-800 px-4 py-3">
                      {iconForRow(row.label)} {row.label}
                    </td>
                    <td className="border-t border-gray-800 px-4 py-3 text-right">{formatInr(row.inr)}</td>
                    <td className="border-t border-gray-800 px-4 py-3 text-right text-gray-400">${(row.inr / INR_PER_USD).toFixed(2)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {travellers > 1 && (
          <div className="mt-4 rounded-xl border border-orange-500/20 bg-orange-500/10 p-4">
            <div className="mb-2 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-xl">👥</span>
                <span className="font-semibold text-white">Cost per person</span>
              </div>
              <span className="text-xl font-bold text-orange-400">
                ₹{Math.round(grandTotal / travellers).toLocaleString("en-IN")}
              </span>
            </div>

            <div className="mt-1 text-xs text-gray-400">
              <span className="text-gray-300">₹{grandTotal.toLocaleString("en-IN")}</span>
              {" "}total ÷{" "}
              <span className="text-gray-300">{travellers} travellers</span>
              {" = "}
              <span className="font-medium text-orange-400">
                ₹{Math.round(grandTotal / travellers).toLocaleString("en-IN")} per person
              </span>
            </div>

            <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3">
              {perPersonItems.map((item) => (
                <div key={item.label} className="rounded-lg bg-gray-800/60 p-2 text-center">
                  <div className="mb-1 text-xs text-gray-400">
                    {item.icon} {item.label}
                  </div>
                  <div className="text-sm font-medium text-white">
                    ₹{item.perPerson.toLocaleString("en-IN")}
                  </div>
                  <div className="mt-0.5 text-xs text-gray-500">
                    of ₹{item.total.toLocaleString("en-IN")} total
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="grid gap-4 lg:grid-cols-[1.15fr_0.85fr]">
          <div className="rounded-2xl border border-gray-700 bg-gray-950/70 p-4">
            <p className="text-xs uppercase tracking-[0.24em] text-gray-400">Budget Pie Chart</p>
            <div className="mt-3">
              <ResponsiveContainer width="100%" height={280}>
                <PieChart>
                  <Pie
                    data={chartData}
                    dataKey="value"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={95}
                    paddingAngle={3}
                    labelLine={false}
                    label={PieLabel}
                  >
                    {chartData.map((entry) => (
                      <Cell key={entry.name} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(value: number) => formatInr(value)} />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <div className="mt-4 flex flex-wrap gap-3">
              {chartData.map((entry) => (
                <div
                  key={entry.name}
                  className="inline-flex items-center gap-2 rounded-full border border-gray-700 bg-gray-900 px-3 py-1.5 text-xs text-gray-300"
                >
                  <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: entry.color }} />
                  {entry.name}
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-2xl border border-gray-700 bg-gray-950/70 p-4">
            <p className="text-xs uppercase tracking-[0.24em] text-gray-400">Budget vs Actual</p>
            <div className="mt-4 space-y-3">
              <div className="flex items-center justify-between text-sm text-gray-300">
                <span>Your budget</span>
                <span>{formatInr(userBudget)}</span>
              </div>
              <div className="flex items-center justify-between text-sm text-gray-300">
                <span>Estimated cost</span>
                <span>{formatInr(grandTotal)}</span>
              </div>
              <div className="h-3 overflow-hidden rounded-full bg-gray-800">
                <div
                  className={`h-full rounded-full transition-all ${overBudget ? "bg-rose-500" : "bg-emerald-500"}`}
                  style={{ width: `${Math.min(100, budgetProgress)}%` }}
                />
              </div>
              <div className={`text-sm font-semibold ${overBudget ? "text-rose-300" : "text-emerald-300"}`}>
                {overBudget ? `${formatInr(differenceAbs)} over budget` : `${formatInr(differenceAbs)} under budget`}
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-4 rounded-xl border border-white/10 bg-gray-950/60 px-3 py-2">
      <span className="text-gray-300">{label}</span>
      <span className="font-semibold text-white">{value}</span>
    </div>
  );
}

function iconForRow(label: string) {
  switch (label) {
    case "Fuel":
      return "⛽";
    case "Hotels":
      return "🏨";
    case "Food":
      return "🍽️";
    case "Tolls":
      return "🛣️";
    case "Misc":
      return "🎯";
    default:
      return "";
  }
}
