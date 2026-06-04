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

  useEffect(() => {
    if (!isLoggedIn()) {
      router.push("/login");
      return;
    }

    setChecking(false);
  }, [router]);

  if (checking) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-slate-950 text-white">
        <div className="flex items-center gap-3 rounded-2xl border border-white/10 bg-white/5 px-5 py-4 shadow-2xl shadow-black/30 backdrop-blur">
          <Loader2 className="h-5 w-5 animate-spin text-orange-400" />
          <span className="text-sm font-medium text-slate-200">Checking your session...</span>
        </div>
      </main>
    );
  }

  return <>{children}</>;
}
