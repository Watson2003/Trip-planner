"use client";

import { useEffect, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";

import { isLoggedIn } from "@/lib/auth";

type AuthGuardProps = {
  children: ReactNode;
};

export default function AuthGuard({ children }: AuthGuardProps) {
  const router = useRouter();
  const [checking, setChecking] = useState(true);
  const [authenticated, setAuthenticated] = useState(false);

  useEffect(() => {
    const loggedIn = isLoggedIn();
    setAuthenticated(loggedIn);

    if (!loggedIn) {
      setChecking(false);
      router.replace("/login");
      return;
    }

    setChecking(false);
  }, [router]);

  if (checking) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-black text-white">
        <div className="flex items-center gap-3 rounded-2xl border border-[#1a1a1a] bg-[#0a0a0a] px-5 py-4 shadow-2xl shadow-black/30 backdrop-blur">
          <Loader2 className="h-5 w-5 animate-spin text-[#D4AF37]" />
          <span className="text-sm font-medium text-[#a0a0a0]">Checking your session...</span>
        </div>
      </main>
    );
  }

  if (!authenticated) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-black text-white">
        <div className="flex items-center gap-3 rounded-2xl border border-[#1a1a1a] bg-[#0a0a0a] px-5 py-4 shadow-2xl shadow-black/30 backdrop-blur">
          <Loader2 className="h-5 w-5 animate-spin text-[#D4AF37]" />
          <span className="text-sm font-medium text-[#a0a0a0]">Redirecting to login...</span>
        </div>
      </main>
    );
  }

  return <>{children}</>;
}
