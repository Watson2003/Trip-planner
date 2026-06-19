"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Home, LogOut, Menu, MessageSquareText, MoonStar, Route, Sparkles, SunMedium, X } from "lucide-react";

import { getUser, removeToken } from "@/lib/auth";

type NavbarProps = {
  theme?: "light" | "dark";
  onToggleTheme?: () => void;
};

const NAV_LINKS = [
  { href: "/", label: "Home", icon: Home },
  { href: "/my-trips", label: "My Trips", icon: Route },
  { href: "/trip-result/itinerary", label: "Day Plan", icon: Sparkles },
  { href: "/trip-result#chat-panel", label: "Chat", icon: MessageSquareText },
] as const;

export default function Navbar({ theme, onToggleTheme }: NavbarProps) {
  const router = useRouter();
  const pathname = usePathname();
  const dropdownRef = useRef<HTMLDivElement | null>(null);
  const [mounted, setMounted] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const user = mounted ? getUser() : null;

  const fullName = user?.full_name?.trim() || user?.username || "Traveler";
  const initial = fullName.charAt(0).toUpperCase();

  const navItems = useMemo(
    () =>
      NAV_LINKS.map((link) => ({
        ...link,
        active:
          link.href === "/"
            ? pathname === "/"
            : pathname === link.href || pathname.startsWith(link.href.split("#")[0]),
      })),
    [pathname],
  );

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
    <header className="sticky top-0 z-50 border-b border-slate-200 bg-white/85 shadow-sm backdrop-blur-xl">
      <div className="mx-auto flex h-18 max-w-7xl items-center justify-between gap-3 px-4 py-3 sm:px-6 lg:px-8">
        <Link href="/" className="group flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-[#0071e3] text-white shadow-sm transition group-hover:scale-105">
            <Route className="h-5 w-5" />
          </div>
          <div className="leading-tight">
            <div className="text-lg font-black tracking-tight text-slate-950">RoadMind AI</div>
            <div className="text-xs uppercase tracking-[0.28em] text-slate-500">Travel Intelligence</div>
          </div>
        </Link>

        <nav className="hidden items-center gap-2 xl:flex">
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
                <Link
                key={item.href}
                href={item.href}
                className={[
                  "inline-flex items-center gap-2 rounded-full border px-4 py-2 text-sm font-medium transition",
                  item.active
                    ? "border-blue-200 bg-blue-50 text-blue-700"
                    : "border-slate-200 bg-white text-slate-600 hover:border-slate-300 hover:bg-slate-50 hover:text-slate-950",
                ].join(" ")}
              >
                <Icon className="h-4 w-4" />
                {item.label}
              </Link>
            );
          })}
        </nav>

        <div className="flex items-center gap-2 sm:gap-3">
          {onToggleTheme ? (
            <button
              type="button"
              onClick={onToggleTheme}
              className="inline-flex h-11 w-11 items-center justify-center rounded-2xl border border-slate-200 bg-white text-slate-600 transition hover:border-slate-300 hover:bg-slate-50 hover:text-slate-950"
              aria-label="Toggle theme"
            >
              {theme === "dark" ? <SunMedium className="h-4.5 w-4.5" /> : <MoonStar className="h-4.5 w-4.5" />}
            </button>
          ) : null}

          {user ? (
            <div className="hidden items-center gap-3 rounded-2xl border border-slate-200 bg-white px-3 py-2 lg:flex">
              <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-[#0071e3] text-sm font-black text-white">
                {initial}
              </div>
              <div className="min-w-0">
                <p className="max-w-[180px] truncate text-sm font-semibold text-slate-950">Hello, {fullName}</p>
                <p className="max-w-[180px] truncate text-xs text-slate-500">{user.email}</p>
              </div>
            </div>
          ) : null}

          {user ? (
            <button
              type="button"
              onClick={handleLogout}
              className="hidden items-center gap-2 rounded-2xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 transition hover:border-slate-300 hover:bg-slate-50 hover:text-slate-950 lg:inline-flex"
            >
              <LogOut className="h-4 w-4" />
              Logout
            </button>
          ) : null}

          <div className="relative xl:hidden" ref={dropdownRef}>
            <button
              type="button"
              onClick={() => setMobileMenuOpen((current) => !current)}
              className="inline-flex h-11 w-11 items-center justify-center rounded-2xl border border-slate-200 bg-white text-slate-700 transition hover:border-slate-300 hover:bg-slate-50 hover:text-slate-950"
              aria-label="Open navigation menu"
              aria-expanded={mobileMenuOpen}
            >
              {mobileMenuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
            </button>

            {mobileMenuOpen ? (
              <div className="absolute right-0 top-14 w-[min(92vw,22rem)] rounded-3xl border border-slate-200 bg-white p-3 shadow-xl shadow-slate-200/60 backdrop-blur-2xl">
                <div className="space-y-2">
                  {navItems.map((item) => {
                    const Icon = item.icon;
                    return (
                      <Link
                        key={item.href}
                        href={item.href}
                        onClick={() => setMobileMenuOpen(false)}
                        className={[
                          "flex items-center gap-3 rounded-2xl px-4 py-3 text-sm font-medium transition",
                          item.active
                            ? "bg-blue-50 text-blue-700"
                            : "text-slate-600 hover:bg-slate-50 hover:text-slate-950",
                        ].join(" ")}
                      >
                        <Icon className="h-4 w-4" />
                        {item.label}
                      </Link>
                    );
                  })}

                  {user ? (
                    <button
                      type="button"
                      onClick={() => {
                        setMobileMenuOpen(false);
                        handleLogout();
                      }}
                      className="flex w-full items-center justify-center gap-2 rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm font-semibold text-slate-700 transition hover:border-slate-300 hover:bg-slate-50 hover:text-slate-950"
                    >
                      <LogOut className="h-4 w-4" />
                      Logout
                    </button>
                  ) : null}
                </div>
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </header>
  );
}
