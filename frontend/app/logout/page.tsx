"use client";

import { useEffect } from "react";
import { Loader2, Route } from "lucide-react";

import { removeToken } from "@/lib/auth";

export default function LogoutPage() {
  useEffect(() => {
    removeToken();
    window.location.replace("/login");
  }, []);

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-950 text-white">
      <div className="flex flex-col items-center gap-4 rounded-[2rem] border border-white/10 bg-white/5 px-8 py-10 shadow-2xl shadow-black/30 backdrop-blur-xl">
        <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-orange-500/15 text-orange-400 ring-1 ring-orange-400/20">
          <Route className="h-8 w-8" />
        </div>
        <div className="text-center">
          <h1 className="text-2xl font-black tracking-tight">Signing you out</h1>
          <p className="mt-2 text-sm text-slate-400">Your session is being cleared and you&apos;ll be redirected.</p>
        </div>
        <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm font-medium text-slate-200">
          <Loader2 className="h-4 w-4 animate-spin text-orange-400" />
          Redirecting to login
        </div>
      </div>
    </main>
  );
}
