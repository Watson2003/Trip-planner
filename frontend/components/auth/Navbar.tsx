"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ChevronDown, LogOut, Menu, Moon, Route, Sun, X } from "lucide-react";

import { getUser, removeToken } from "@/lib/auth";

type NavbarProps = {
  theme?: "light" | "dark";
  onToggleTheme?: () => void;
};

export default function Navbar({ theme, onToggleTheme }: NavbarProps) {
  const router = useRouter();
  const user = getUser();
  const dropdownRef = useRef<HTMLDivElement | null>(null);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const fullName = user?.full_name?.trim() || user?.username || "Traveler";
  const initial = fullName.charAt(0).toUpperCase();

  function handleLogout() {
    removeToken();
    router.replace("/login");
  }

  useEffect(() => {
    if (!mobileMenuOpen) return;
    const handleOutsideClick = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setMobileMenuOpen(false);
      }
    };

    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMobileMenuOpen(false);
    };

    document.addEventListener("mousedown", handleOutsideClick);
    document.addEventListener("keydown", handleEscape);
    return () => {
      document.removeEventListener("mousedown", handleOutsideClick);
      document.removeEventListener("keydown", handleEscape);
    };
  }, [mobileMenuOpen]);

  useEffect(() => {
    if (!mobileMenuOpen) return;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = "";
    };
  }, [mobileMenuOpen]);

  return (
    <header className="sticky top-0 z-50 border-b border-white/10 bg-slate-950/95 text-white backdrop-blur-xl">
      <div className="mx-auto flex w-full max-w-7xl items-center justify-between gap-3 px-4 py-3 sm:px-6 lg:px-8">
        <Link href="/" className="inline-flex min-w-0 items-center gap-2 text-base font-black tracking-tight text-white">
          <Route className="h-5 w-5 shrink-0 text-orange-400" />
          <span className="truncate">RoadMind AI</span>
        </Link>

        {user ? (
          <>
            <div className="hidden items-center gap-3 sm:flex">
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
                className="rounded-full px-4 py-2 text-sm font-semibold text-slate-300 transition hover:bg-white/5 hover:text-white"
              >
                My Trips
              </Link>

              <div className="flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-2">
                <div className="flex h-8 w-8 items-center justify-center rounded-full bg-orange-500/20 text-sm font-bold text-orange-300 ring-1 ring-orange-400/20">
                  {initial}
                </div>
                <span className="text-sm text-slate-200">Hello, {fullName}</span>
              </div>

              <button
                type="button"
                onClick={handleLogout}
                className="inline-flex items-center gap-2 rounded-full bg-orange-500 px-4 py-2 text-sm font-bold text-white transition hover:bg-orange-600"
              >
                <LogOut className="h-4 w-4" />
                Logout
              </button>
            </div>

            <div className="relative flex sm:hidden" ref={dropdownRef}>
              <button
                type="button"
                onClick={() => setMobileMenuOpen((current) => !current)}
                className="inline-flex h-10 w-10 items-center justify-center rounded-full border border-white/10 bg-white/5 text-white transition hover:bg-white/10"
                aria-label="Open navigation menu"
                aria-expanded={mobileMenuOpen}
              >
                {mobileMenuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
              </button>

              {mobileMenuOpen ? (
                <div className="absolute right-0 top-[calc(100%+0.75rem)] w-[min(18rem,calc(100vw-2rem))] overflow-hidden rounded-2xl border border-white/10 bg-slate-900/95 shadow-2xl shadow-black/40">
                  <div className="border-b border-white/10 px-4 py-3">
                    <div className="flex items-center gap-3">
                      <div className="flex h-10 w-10 items-center justify-center rounded-full bg-orange-500/20 text-sm font-bold text-orange-300 ring-1 ring-orange-400/20">
                        {initial}
                      </div>
                      <div className="min-w-0">
                        <p className="truncate text-sm font-semibold text-white">Hello, {fullName}</p>
                        <p className="text-xs text-slate-400">{user.email}</p>
                      </div>
                    </div>
                  </div>

                  <div className="p-2">
                    <Link
                      href="/my-trips"
                      onClick={() => setMobileMenuOpen(false)}
                      className="flex items-center justify-between rounded-xl px-3 py-3 text-sm font-semibold text-slate-200 transition hover:bg-white/5"
                    >
                      My Trips
                      <ChevronDown className="h-4 w-4" />
                    </Link>
                    <button
                      type="button"
                      onClick={() => {
                        setMobileMenuOpen(false);
                        handleLogout();
                      }}
                      className="mt-1 flex w-full items-center gap-2 rounded-xl px-3 py-3 text-sm font-semibold text-red-300 transition hover:bg-red-500/10"
                    >
                      <LogOut className="h-4 w-4" />
                      Logout
                    </button>
                  </div>
                </div>
              ) : null}
            </div>
          </>
        ) : null}
      </div>
    </header>
  );
}
