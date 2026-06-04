"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { LogOut, Moon, Route, Sun } from "lucide-react";

import { getUser, removeToken } from "@/lib/auth";

type NavbarProps = {
  theme?: "light" | "dark";
  onToggleTheme?: () => void;
};

export default function Navbar({ theme, onToggleTheme }: NavbarProps) {
  const router = useRouter();
  const user = getUser();
  const fullName = user?.full_name?.trim() || user?.username || "Traveler";
  const initial = fullName.charAt(0).toUpperCase();

  function handleLogout() {
    removeToken();
    router.replace("/login");
  }

  return (
    <header className="sticky top-0 z-50 border-b border-white/10 bg-slate-950/90 text-white backdrop-blur-xl">
      <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-3 sm:px-6 lg:px-8">
        <Link href="/" className="inline-flex items-center gap-2 text-base font-black tracking-tight text-white">
          <Route className="h-5 w-5 text-orange-400" />
          RoadMind AI
        </Link>

        {user ? (
          <div className="flex items-center gap-3 sm:gap-4">
            {onToggleTheme ? (
              <button
                type="button"
                onClick={onToggleTheme}
                className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-2 text-sm font-semibold text-slate-200 transition hover:bg-white/10"
                aria-label="Toggle theme"
              >
                {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
              </button>
            ) : null}

            <Link
              href="/my-trips"
              className="hidden rounded-full px-4 py-2 text-sm font-semibold text-slate-300 transition hover:bg-white/5 hover:text-white md:inline-flex"
            >
              My Trips
            </Link>

            <div className="flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-2">
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-orange-500/20 text-sm font-bold text-orange-300 ring-1 ring-orange-400/20">
                {initial}
              </div>
              <span className="hidden text-sm text-slate-200 sm:inline">Hello, {fullName}</span>
            </div>

            <Link
              href="/my-trips"
              className="inline-flex rounded-full px-3 py-2 text-sm font-semibold text-slate-300 transition hover:bg-white/5 hover:text-white md:hidden"
            >
              Trips
            </Link>

            <Link
              href="/logout"
              className="inline-flex items-center gap-2 rounded-full bg-orange-500 px-4 py-2 text-sm font-bold text-white transition hover:bg-orange-600"
            >
              <LogOut className="h-4 w-4" />
              Logout
            </Link>
          </div>
        ) : null}
      </div>
    </header>
  );
}
