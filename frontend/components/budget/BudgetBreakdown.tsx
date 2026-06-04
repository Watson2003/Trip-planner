"use client";

import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";

import type { BudgetBreakdown as BudgetBreakdownData } from "@/types";

interface BudgetBreakdownProps {
  budget: BudgetBreakdownData;
}

const COLORS = ["#f97316", "#2563eb", "#16a34a", "#eab308", "#8b5cf6"];

function formatInr(value: number) {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(value);
}

function formatUsd(value: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value);
}

function normalizeBudget(budget: BudgetBreakdownData) {
  const fuelInr = budget.breakdown?.fuel?.inr ?? budget.fuel;
  const tollsInr = budget.breakdown?.tolls?.inr ?? budget.tolls ?? 0;
  const hotelsInr = budget.breakdown?.hotels?.inr ?? budget.hotels ?? budget.lodging ?? 0;
  const foodInr = budget.breakdown?.food?.inr ?? budget.food;
  const miscInr = budget.breakdown?.miscellaneous?.inr ?? budget.miscellaneous ?? budget.activities ?? 0;
  const totalInr =
    budget.breakdown?.total?.inr ??
    budget.total ??
    fuelInr + tollsInr + hotelsInr + foodInr + miscInr;

  const fuelUsd = budget.breakdown?.fuel?.usd ?? budget.fuelUsd ?? fuelInr / 83;
  const tollsUsd = budget.breakdown?.tolls?.usd ?? budget.tollsUsd ?? tollsInr / 83;
  const hotelsUsd = budget.breakdown?.hotels?.usd ?? budget.hotelsUsd ?? hotelsInr / 83;
  const foodUsd = budget.breakdown?.food?.usd ?? budget.foodUsd ?? foodInr / 83;
  const miscUsd = budget.breakdown?.miscellaneous?.usd ?? budget.miscellaneousUsd ?? miscInr / 83;
  const totalUsd = budget.breakdown?.total?.usd ?? budget.totalUsd ?? totalInr / 83;

  return {
    rows: [
      { label: "Fuel", inr: fuelInr, usd: fuelUsd },
      { label: "Tolls", inr: tollsInr, usd: tollsUsd },
      { label: "Hotels", inr: hotelsInr, usd: hotelsUsd },
      { label: "Food", inr: foodInr, usd: foodUsd },
      { label: "Miscellaneous", inr: miscInr, usd: miscUsd },
      { label: "Total", inr: totalInr, usd: totalUsd },
    ],
    chart: [
      { name: "Fuel", value: fuelInr },
      { name: "Tolls", value: tollsInr },
      { name: "Hotels", value: hotelsInr },
      { name: "Food", value: foodInr },
      { name: "Misc", value: miscInr },
    ],
  };
}

export default function BudgetBreakdown({ budget }: BudgetBreakdownProps) {
  const data = normalizeBudget(budget);

  return (
    <section className="rounded-3xl border border-white/70 bg-white/80 p-5 shadow-glow backdrop-blur-xl">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-[0.24em] text-slate-500">Budget</p>
          <h2 className="text-xl font-bold text-slate-900">Itemized Breakdown</h2>
        </div>
        <div className="text-right">
          <div className="text-xs uppercase tracking-[0.18em] text-slate-500">Total</div>
          <div className="text-lg font-black text-slate-900">
            {formatInr(data.rows[data.rows.length - 1].inr)}
          </div>
          <div className="text-sm text-slate-500">{formatUsd(data.rows[data.rows.length - 1].usd)}</div>
        </div>
      </div>

      <div className="mt-5 grid gap-5 xl:grid-cols-[1.15fr_0.85fr]">
        <div className="overflow-hidden rounded-3xl border border-slate-200 bg-slate-50">
          <table className="w-full">
            <thead className="bg-slate-900 text-white">
              <tr>
                <th className="px-4 py-3 text-left text-sm font-semibold">Category</th>
                <th className="px-4 py-3 text-right text-sm font-semibold">INR</th>
                <th className="px-4 py-3 text-right text-sm font-semibold">USD</th>
              </tr>
            </thead>
            <tbody>
              {data.rows.map((row, index) => (
                <tr key={row.label} className={index === data.rows.length - 1 ? "bg-orange-50 font-bold" : "bg-white"}>
                  <td className="border-t border-slate-100 px-4 py-3 text-sm text-slate-800">{row.label}</td>
                  <td className="border-t border-slate-100 px-4 py-3 text-right text-sm text-slate-700">
                    {formatInr(row.inr)}
                  </td>
                  <td className="border-t border-slate-100 px-4 py-3 text-right text-sm text-slate-700">
                    {formatUsd(row.usd)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="rounded-3xl border border-slate-200 bg-white p-4">
          <div className="mb-3">
            <p className="text-xs uppercase tracking-[0.24em] text-slate-500">Distribution</p>
            <h3 className="text-base font-semibold text-slate-900">Budget Share</h3>
          </div>
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={data.chart} dataKey="value" nameKey="name" innerRadius={55} outerRadius={90} paddingAngle={3}>
                  {data.chart.map((entry, index) => (
                    <Cell key={entry.name} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip formatter={(value: number) => formatInr(value)} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    </section>
  );
}
