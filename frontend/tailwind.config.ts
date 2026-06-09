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
          black: "#000000",
          nearBlack: "#0a0a0a",
          dark: "#111111",
          darkGray: "#1a1a1a",
          gray: "#2a2a2a",
          midGray: "#555555",
          lightGray: "#888888",
          silver: "#a0a0a0",
          light: "#e0e0e0",
          white: "#ffffff",
        },
        gold: {
          DEFAULT: "#D4AF37",
          bright: "#FFD700",
          light: "#F5E6A3",
          dark: "#B8860B",
          muted: "#C9A84C",
        },
      },
      boxShadow: {
        glow: "0 20px 60px rgba(15, 23, 42, 0.18)",
      },
    },
  },
  plugins: [lineClamp],
};

export default config;
