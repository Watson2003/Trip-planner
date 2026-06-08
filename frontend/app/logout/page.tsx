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
    <main className="flex min-h-screen items-center justify-center bg-black text-white">
      <div className="flex flex-col items-center gap-4 rounded-[2rem] border border-[#1a1a1a] bg-[#0a0a0a] px-8 py-10 shadow-2xl shadow-black/30 backdrop-blur-xl">
        <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-white/10 text-white ring-1 ring-white/20">
          <Route className="h-8 w-8" />
        </div>
        <div className="text-center">
          <h1 className="text-2xl font-black tracking-tight">Signing you out</h1>
          <p className="mt-2 text-sm text-[#a0a0a0]">Your session is being cleared and you&apos;ll be redirected.</p>
        </div>
        <div className="inline-flex items-center gap-2 rounded-full border border-[#2a2a2a] bg-[#111111] px-4 py-2 text-sm font-medium text-white">
          <Loader2 className="h-4 w-4 animate-spin text-white" />
          Redirecting to login
        </div>
      </div>
    </main>
  );
}
