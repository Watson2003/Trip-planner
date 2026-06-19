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
    <main className="flex min-h-screen items-center justify-center bg-slate-50 text-slate-950">
      <div className="flex flex-col items-center gap-4 rounded-[2rem] border border-slate-200 bg-white px-8 py-10 shadow-xl backdrop-blur-xl">
        <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-blue-50 text-blue-700 ring-1 ring-blue-100">
          <Route className="h-8 w-8" />
        </div>
        <div className="text-center">
          <h1 className="text-2xl font-black tracking-tight">Signing you out</h1>
          <p className="mt-2 text-sm text-slate-500">Your session is being cleared and you&apos;ll be redirected.</p>
        </div>
        <div className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-4 py-2 text-sm font-medium text-slate-700">
          <Loader2 className="h-4 w-4 animate-spin text-blue-600" />
          Redirecting to login
        </div>
      </div>
    </main>
  );
}
