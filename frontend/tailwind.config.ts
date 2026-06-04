import type { Config } from "tailwindcss";

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
        ink: "#0f172a",
        sand: "#f8f2e8",
        sky: "#dbeafe",
        moss: "#d9f99d",
        ember: "#fde68a",
      },
      boxShadow: {
        glow: "0 20px 60px rgba(15, 23, 42, 0.18)",
      },
    },
  },
  plugins: [],
};

export default config;
