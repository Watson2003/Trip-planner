"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Menu, Moon, Route, Sun, X, LogOut } from "lucide-react";

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

  return (
    <header className="sticky top-0 z-50 border-b border-[#1a1a1a] bg-black/95 text-white backdrop-blur-sm">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
        <Link href="/" className="flex items-center gap-2 font-bold text-lg text-white">
          <Route className="h-5 w-5 text-[#D4AF37]" />
          <span>RoadMind AI</span>
        </Link>

        {user ? (
          <>
            <div className="hidden items-center gap-4 sm:flex">
              {onToggleTheme ? (
                <button
                  type="button"
                  onClick={onToggleTheme}
                  className="inline-flex items-center gap-2 rounded-xl border border-[#2a2a2a] bg-[#111111] px-3 py-1.5 text-sm text-[#a0a0a0] transition hover:border-[#D4AF37] hover:bg-[#1a1a1a] hover:text-[#D4AF37]"
                  aria-label="Toggle theme"
                >
                  {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
                </button>
              ) : null}

              <Link href="/my-trips" className="text-sm text-[#a0a0a0] transition hover:text-[#D4AF37]">
                My Trips
              </Link>

              <div className="flex items-center gap-2 rounded-full border border-[#2a2a2a] bg-[#111111] px-3 py-1.5">
                <div className="flex h-8 w-8 items-center justify-center rounded-full bg-[#D4AF37] text-sm font-bold text-black">
                  {initial}
                </div>
                <span className="max-w-[160px] truncate text-sm text-white">Hello, {fullName}</span>
              </div>

              <button
                type="button"
                onClick={handleLogout}
                className="inline-flex items-center gap-1 rounded-lg border border-[#2a2a2a] bg-[#1a1a1a] px-3 py-1.5 text-sm font-semibold text-white transition-colors hover:bg-[#2a2a2a]"
              >
                <LogOut className="h-4 w-4" />
                Logout
              </button>
            </div>

            <div className="relative flex sm:hidden" ref={dropdownRef}>
              <button
                type="button"
                onClick={() => setMobileMenuOpen((current) => !current)}
                className="inline-flex h-10 w-10 items-center justify-center rounded-xl border border-[#2a2a2a] bg-[#111111] text-white transition hover:border-[#D4AF37] hover:bg-[#1a1a1a]"
                aria-label="Open navigation menu"
                aria-expanded={mobileMenuOpen}
              >
                {mobileMenuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
              </button>

              {mobileMenuOpen ? (
                <div className="absolute left-0 right-0 top-16 border-b border-[#1a1a1a] bg-black px-4 py-4">
                  <div className="flex flex-col gap-3">
                    <div className="flex items-center gap-3 rounded-2xl border border-[#2a2a2a] bg-[#111111] px-3 py-3">
                      <div className="flex h-10 w-10 items-center justify-center rounded-full bg-[#D4AF37] text-sm font-bold text-black">
                        {initial}
                      </div>
                      <div className="min-w-0">
                        <p className="truncate text-sm font-semibold text-white">Hello, {fullName}</p>
                        <p className="truncate text-xs text-[#888888]">{user.email}</p>
                      </div>
                    </div>

                    <Link
                      href="/my-trips"
                      onClick={() => setMobileMenuOpen(false)}
                      className="rounded-xl border border-[#2a2a2a] bg-[#111111] px-3 py-3 text-sm font-semibold text-white transition hover:border-[#D4AF37] hover:bg-[#1a1a1a] hover:text-[#D4AF37]"
                    >
                      My Trips
                    </Link>

                    <button
                      type="button"
                      onClick={() => {
                        setMobileMenuOpen(false);
                        handleLogout();
                      }}
                      className="inline-flex items-center justify-center gap-2 rounded-xl border border-[#2a2a2a] bg-[#1a1a1a] px-3 py-3 text-sm font-semibold text-white transition hover:bg-[#2a2a2a]"
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
