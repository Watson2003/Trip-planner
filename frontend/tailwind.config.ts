import type { Config } from "tailwindcss";
import lineClamp from "@tailwindcss/line-clamp";

const config: Config = {
  darkMode: "class",
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./lib/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          navy: "#0B1120",
          navySoft: "#111827",
          slate: "#334155",
          steel: "#475569",
          muted: "#94A3B8",
          border: "#E2E8F0",
          surface: "#F8FAFC",
          surfaceAlt: "#F1F5F9",
          white: "#ffffff",
        },
        accent: {
          blue: "#2563EB",
          emerald: "#10B981",
          cyan: "#06B6D4",
          purple: "#8B5CF6",
          warning: "#F59E0B",
          danger: "#EF4444",
        },
      },
      boxShadow: {
        glow: "0 20px 60px rgba(11, 17, 32, 0.12)",
        card: "0 10px 30px rgba(15, 23, 42, 0.08)",
      },
    },
  },
  plugins: [lineClamp],
};

export default config;
