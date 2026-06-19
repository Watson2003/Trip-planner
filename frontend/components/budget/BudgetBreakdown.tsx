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

function firstNumber(...values: Array<number | null | undefined>) {
  for (const value of values) {
    if (typeof value === "number" && Number.isFinite(value)) {
      return value;
    }
  }
  return 0;
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
  const resolvedFuel = fuelCalculation ?? fallbackFuel;

  const fuelInr = firstNumber(resolvedFuel?.total_fuel_cost_inr, budget.breakdown?.fuel?.inr, budget.fuel);
  const tollsInr = firstNumber(budget.breakdown?.tolls?.inr, budget.tolls);
  const inferredHotelNights =
    firstNumber(budget.hotel_nights, budget.hotel_daily_breakdown?.length) ||
    Math.max(1, (budget.trip_days ?? 1) - 1);
  const hotelsInr = firstNumber(
    budget.hotel_price_per_night && inferredHotelNights ? budget.hotel_price_per_night * inferredHotelNights : undefined,
    budget.breakdown?.hotels?.inr,
    budget.hotels,
    budget.lodging,
  );
  const foodInr = firstNumber(budget.breakdown?.food?.inr, budget.food);
  const miscInr = firstNumber(budget.breakdown?.miscellaneous?.inr, budget.miscellaneous, budget.activities);
  const totalInr = firstNumber(
    budget.breakdown?.total?.inr,
    budget.total,
    fuelInr + tollsInr + hotelsInr + foodInr + miscInr,
  );

  return {
    fuelInr,
    tollsInr,
    hotelsInr,
    foodInr,
    miscInr,
    totalInr,
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

  const radian = Math.PI / 180;
  const radius = innerRadius + (outerRadius - innerRadius) * 0.65;
  const x = cx + radius * Math.cos(-midAngle * radian);
  const y = cy + radius * Math.sin(-midAngle * radian);

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
  const budgetData = budget as BudgetBreakdownData & {
    fuel_cost_inr?: number;
    fuel_cost?: number;
    fuelCost?: number;
    hotel_cost_inr?: number;
    hotel_cost?: number;
    hotelCost?: number;
    hotel?: number;
    food_cost_inr?: number;
    food_cost?: number;
    foodCost?: number;
    toll_cost_inr?: number;
    toll_cost?: number;
    tollCost?: number;
    toll?: number;
    misc_cost_inr?: number;
    misc_cost?: number;
    miscCost?: number;
    misc?: number;
    number_of_people?: number;
    numberOfPeople?: number;
    people?: number;
    hotelPricePerNight?: number;
    price_per_night?: number;
    hotelNights?: number;
    nights?: number;
    trip_nights?: number;
    foodPricePerDayPerPerson?: number;
    food_per_day?: number;
    foodDays?: number;
    days?: number;
    destination?: string;
  };

  console.log("=== BUDGET OBJECT KEYS ===", Object.keys(budgetData));
  console.log("=== BUDGET VALUES ===", budgetData);
  console.log("fuel_cost_inr:", budgetData.fuel_cost_inr);
  console.log("toll_cost_inr:", budgetData.toll_cost_inr);
  console.log("misc_cost_inr:", budgetData.misc_cost_inr);
  console.log("hotel_cost_inr:", budgetData.hotel_cost_inr);
  console.log("food_cost_inr:", budgetData.food_cost_inr);

  const normalized = normalizeBudget(budget, fuelCalculation, vehicle, routeDistanceKm);
  const fuelDetails = fuelCalculation ?? buildFallbackFuelCalculation(vehicle, routeDistanceKm, vehicle?.number_of_people ?? 1, normalized.fuelInr);

  const fuelCost = firstNumber(
    budgetData.fuel_cost_inr,
    budgetData.fuel_cost,
    budgetData.fuelCost,
    budgetData.fuel,
    fuelDetails?.total_fuel_cost_inr,
    normalized.fuelInr,
  );

  const hotelCostRaw = firstNumber(
    budgetData.hotel_cost_inr,
    budgetData.hotel_cost,
    budgetData.hotelCost,
    budgetData.hotel,
    budgetData.hotels,
    budgetData.lodging,
    normalized.hotelsInr,
  );

  const foodCostRaw = firstNumber(
    budgetData.food_cost_inr,
    budgetData.food_cost,
    budgetData.foodCost,
    budgetData.food,
    normalized.foodInr,
  );

  const tollCost = firstNumber(
    budgetData.toll_cost_inr,
    budgetData.toll_cost,
    budgetData.tollCost,
    budgetData.tolls,
    budgetData.toll,
    normalized.tollsInr,
  );

  const miscCost = firstNumber(
    budgetData.misc_cost_inr,
    budgetData.misc_cost,
    budgetData.miscCost,
    budgetData.miscellaneous,
    budgetData.activities,
    budgetData.misc,
    normalized.miscInr,
  );

  const numberOfPeople = firstNumber(budgetData.number_of_people, budgetData.numberOfPeople, budgetData.people, vehicle?.number_of_people) || 1;

  const pricePerNight = firstNumber(budgetData.hotel_price_per_night, budgetData.hotelPricePerNight, budgetData.price_per_night);

  const numberOfNights = firstNumber(budgetData.hotel_nights, budgetData.hotelNights, budgetData.nights, budgetData.trip_nights) || 1;

  const pricePerDayPerPerson = firstNumber(
    budgetData.food_price_per_day_per_person,
    budgetData.foodPricePerDayPerPerson,
    budgetData.food_per_day,
  );

  const numberOfDays = firstNumber(budgetData.food_days, budgetData.foodDays, budgetData.trip_days, budgetData.days) || 1;

  const hotelTotal = pricePerNight > 0 ? pricePerNight * numberOfNights : hotelCostRaw;
  const foodTotal = pricePerDayPerPerson > 0 ? pricePerDayPerPerson * numberOfPeople * numberOfDays : foodCostRaw;
  const grandTotal = fuelCost + hotelTotal + foodTotal + tollCost + miscCost;

  console.log("=== EXTRACTED VALUES ===");
  console.log("fuelCost:", fuelCost);
  console.log("hotelTotal:", hotelTotal);
  console.log("foodTotal:", foodTotal);
  console.log("tollCost:", tollCost);
  console.log("miscCost:", miscCost);
  console.log("numberOfPeople:", numberOfPeople);
  console.log("grandTotal:", grandTotal);

  const difference = userBudget - grandTotal;
  const overBudget = difference < 0;
  const differenceAbs = Math.abs(difference);
  const budgetProgress = Math.min(100, (grandTotal / Math.max(userBudget, 1)) * 100);

  const hotelExplanation = pricePerNight
    ? `₹${pricePerNight.toLocaleString("en-IN")}/night × ${numberOfNights} night${
        numberOfNights > 1 ? "s" : ""
      } (${budgetData.hotel_category || "Mid"} hotel in ${budgetData.destination || ""})`
    : budgetData.hotel_explanation || "";

  const perPersonItems = [
    {
      label: "Fuel",
      icon: "⛽",
      total: fuelCost,
      perPerson: Math.round(fuelCost / Math.max(numberOfPeople, 1)),
    },
    {
      label: "Hotel",
      icon: "🏨",
      total: hotelTotal,
      perPerson: Math.round(hotelTotal / Math.max(numberOfPeople, 1)),
    },
    {
      label: "Food",
      icon: "🍽️",
      total: foodTotal,
      perPerson: Math.round(foodTotal / Math.max(numberOfPeople, 1)),
    },
    {
      label: "Tolls",
      icon: "🛣️",
      total: tollCost,
      perPerson: Math.round(tollCost / Math.max(numberOfPeople, 1)),
    },
    {
      label: "Misc",
      icon: "🎯",
      total: miscCost,
      perPerson: Math.round(miscCost / Math.max(numberOfPeople, 1)),
    },
  ];

  const chartData = [
    { name: "Fuel", value: fuelCost, color: COLORS.Fuel },
    { name: "Hotels", value: hotelTotal, color: COLORS.Hotels },
    { name: "Food", value: foodTotal, color: COLORS.Food },
    { name: "Tolls", value: tollCost, color: COLORS.Tolls },
    { name: "Misc", value: miscCost, color: COLORS.Misc },
  ];

  return (
    <section className="w-full overflow-hidden rounded-[2rem] border border-[#1a1a1a] bg-[#0a0a0a] text-white shadow-2xl">
      <div className="border-b border-[#1a1a1a] px-5 pt-5 pb-3">
        <p className="text-xs uppercase tracking-[0.24em] text-[#888888]">Budget</p>
        <h2 className="text-xl font-bold text-white">Your Trip Cost Breakdown</h2>
        <p className="mt-1 text-sm text-[#888888]">
          {vehicle?.vehicle_name ?? "Vehicle"} · {vehicle?.vehicle_type ?? "car"} · {vehicle?.fuel_type ?? "petrol"}
        </p>
      </div>

      <div className="space-y-6 p-5">
        <div className="rounded-2xl border border-[#1a1a1a] bg-[#111111] p-4">
          <div className="mb-4 text-sm font-bold text-white">Fuel Details</div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2 text-sm text-[#a0a0a0]">
              <Row label="Distance" value={`${fuelDetails?.distance_km ?? 0} km`} />
              <Row label="Fuel needed" value={`${(fuelDetails?.fuel_required_litres ?? 0).toFixed(2)} litres`} />
              <Row label="Price per litre" value={formatInr(fuelDetails?.fuel_price_per_litre ?? 0)} />
            </div>
            <div className="space-y-2 text-sm text-[#a0a0a0]">
              <Row label="Vehicle" value={fuelDetails?.vehicle_name ?? vehicle?.vehicle_name ?? "-"} />
              <Row label="Mileage" value={`${fuelDetails?.mileage_kmpl ?? vehicle?.mileage_kmpl ?? 0} km/l`} />
              <Row label="Travellers" value={`${numberOfPeople}`} />
            </div>
          </div>
          <div className="mt-4 rounded-2xl border border-[#2a2a2a] bg-[#0a0a0a] px-4 py-3">
            <div className="text-sm font-semibold text-[#888888]">Total Fuel Cost</div>
            <div className="mt-1 text-2xl font-black text-white">{formatInr(fuelCost)}</div>
          </div>
        </div>

        <div className="overflow-x-auto rounded-2xl border border-[#1a1a1a] bg-[#0a0a0a]">
          <table className="min-w-[520px] w-full border-collapse">
            <thead>
              <tr className="bg-[#111111] text-left text-sm text-[#888888]">
                <th className="px-4 py-3 font-semibold">Category</th>
                <th className="px-4 py-3 font-semibold text-right">Amount (INR)</th>
              </tr>
            </thead>
            <tbody>
              <tr className="bg-[#0a0a0a]">
                <td className="border-t border-[#1a1a1a] px-4 py-3">⛽ Fuel</td>
                <td className="border-t border-[#1a1a1a] px-4 py-3 text-right">₹{Math.round(fuelCost).toLocaleString("en-IN")}</td>
              </tr>

              <tr className="border-b border-[#1a1a1a]">
                <td className="py-3 px-4">
                  <div className="flex items-center gap-2">
                    <span>🏨</span>
                    <span className="text-white">Hotels</span>
                  </div>
                  <div className="mt-1 text-xs text-[#888888]">{hotelExplanation}</div>
                </td>
                <td className="py-3 px-4 text-right text-white">₹{Math.round(hotelTotal).toLocaleString("en-IN")}</td>
              </tr>

              <tr className="border-b border-[#1a1a1a]">
                <td className="py-3 px-4">
                  <div className="flex items-center gap-2">
                    <span>🍽️</span>
                    <span className="text-white">Food</span>
                  </div>
                  <div className="mt-1 text-xs text-[#888888]">{budgetData.food_explanation}</div>
                </td>
                <td className="py-3 px-4 text-right text-white">₹{Math.round(foodTotal).toLocaleString("en-IN")}</td>
              </tr>

              <tr className="bg-[#0d0d0d]">
                <td className="border-t border-[#1a1a1a] px-4 py-3">🛣️ Tolls</td>
                <td className="border-t border-[#1a1a1a] px-4 py-3 text-right">₹{Math.round(tollCost).toLocaleString("en-IN")}</td>
              </tr>

              <tr className="bg-[#0a0a0a]">
                <td className="border-t border-[#1a1a1a] px-4 py-3">🎯 Misc</td>
                <td className="border-t border-[#1a1a1a] px-4 py-3 text-right">₹{Math.round(miscCost).toLocaleString("en-IN")}</td>
              </tr>

              <tr className="bg-white/10 font-bold">
                <td className="py-3 px-4 text-white">Total</td>
                <td className="py-3 px-4 text-right text-white">₹{Math.round(grandTotal).toLocaleString("en-IN")}</td>
              </tr>
            </tbody>
          </table>
        </div>

        {numberOfPeople > 1 && (
          <div className="mt-4 rounded-xl border border-[#1a1a1a] bg-[#111111] p-4">
            <div className="flex items-center justify-between mb-1">
              <div className="flex items-center gap-2">
                <span className="text-xl">👥</span>
                <span className="text-white font-semibold">Cost per person</span>
              </div>
              <span className="text-xl font-bold text-white">
                ₹{Math.round(grandTotal / Math.max(numberOfPeople, 1)).toLocaleString("en-IN")}
              </span>
            </div>

            <div className="mb-3 text-xs text-[#888888]">
              ₹{Math.round(grandTotal).toLocaleString("en-IN")}
              {" total ÷ "}
              {numberOfPeople}
              {" travellers = "}
              <span className="font-medium text-white">
                ₹{Math.round(grandTotal / Math.max(numberOfPeople, 1)).toLocaleString("en-IN")}
                {" per person"}
              </span>
            </div>

            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              {perPersonItems.map((item) => (
                <div key={item.label} className="rounded-lg border border-[#1a1a1a] bg-[#111111] p-3 text-center">
                  <div className="mb-1 text-xs text-[#888888]">
                    {item.icon} {item.label}
                  </div>
                  <div className="text-sm text-white font-medium">
                    ₹{item.perPerson.toLocaleString("en-IN")}
                  </div>
                  <div className="mt-1 text-xs text-[#555555]">
                    of ₹{Math.round(item.total).toLocaleString("en-IN")}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="grid gap-4 lg:grid-cols-[1.15fr_0.85fr]">
          <div className="rounded-2xl border border-[#1a1a1a] bg-[#0a0a0a] p-4">
            <p className="text-xs uppercase tracking-[0.24em] text-[#888888]">Budget Pie Chart</p>
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
                  className="inline-flex items-center gap-2 rounded-full border border-[#1a1a1a] bg-[#111111] px-3 py-1.5 text-xs text-[#a0a0a0]"
                >
                  <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: entry.color }} />
                  {entry.name}
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-2xl border border-[#1a1a1a] bg-[#0a0a0a] p-4">
            <p className="text-xs uppercase tracking-[0.24em] text-[#888888]">Budget vs Actual</p>
            <div className="mt-4 space-y-3">
              <div className="flex items-center justify-between text-sm text-[#a0a0a0]">
                <span>Your budget</span>
                <span>{formatInr(userBudget)}</span>
              </div>
              <div className="flex items-center justify-between text-sm text-[#a0a0a0]">
                <span>Estimated cost</span>
                <span>{formatInr(grandTotal)}</span>
              </div>
              <div className="h-3 overflow-hidden rounded-full bg-[#111111]">
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
    <div className="flex items-center justify-between gap-4 rounded-xl border border-[#1a1a1a] bg-[#0a0a0a]/60 px-3 py-2">
      <span className="text-[#a0a0a0]">{label}</span>
      <span className="font-semibold text-white">{value}</span>
    </div>
  );
}
