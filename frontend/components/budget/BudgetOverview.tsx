"use client";

import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from "recharts";

import type { BudgetBreakdown } from "@/types";

const COLORS = ["#ffffff", "#e0e0e0", "#a0a0a0", "#888888"];

type BudgetSlice = {
  name: string;
  value: number;
};

export default function BudgetOverview({ budget }: { budget: BudgetBreakdown }) {
  const data: BudgetSlice[] = [
    { name: "Fuel", value: budget.fuel },
    { name: "Lodging", value: budget.lodging ?? 0 },
    { name: "Food", value: budget.food },
    { name: "Activities", value: budget.activities ?? 0 },
  ];

  return (
    <section className="rounded-3xl border border-[#1a1a1a] bg-[#0a0a0a] p-6 shadow-glow backdrop-blur-xl">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold">Budget</h2>
          <p className="text-sm text-[#888888]">Estimated trip spend in INR</p>
        </div>
        <div className="text-right">
          <div className="text-xs uppercase tracking-[0.18em] text-[#888888]">Total</div>
          <div className="text-2xl font-black">₹{budget.total.toLocaleString("en-IN")}</div>
        </div>
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-[1fr_1fr]">
        <div className="h-64 rounded-3xl bg-[#111111] p-3">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie data={data} dataKey="value" nameKey="name" innerRadius={55} outerRadius={85} paddingAngle={4}>
                {data.map((entry, index) => (
                  <Cell key={entry.name} fill={COLORS[index % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </div>
        <div className="space-y-3">
          {data.map((item, index) => (
            <div key={item.name} className="rounded-2xl border border-[#1a1a1a] bg-[#111111] p-4">
              <div className="flex items-center justify-between text-sm font-medium">
                <span className="inline-flex items-center gap-2">
                  <span className="h-3 w-3 rounded-full" style={{ backgroundColor: COLORS[index] }} />
                  {item.name}
                </span>
                <span>₹{item.value.toLocaleString("en-IN")}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
