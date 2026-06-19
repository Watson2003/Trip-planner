"use client";

import { useEffect } from "react";
import Link from "next/link";
import { TriangleAlert, Home } from "lucide-react";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <html lang="en">
      <body className="min-h-screen bg-slate-50 text-slate-950">
        <main className="flex min-h-screen items-center justify-center px-4 py-16">
          <div className="w-full max-w-xl rounded-[2rem] border border-slate-200 bg-white p-8 text-center shadow-card backdrop-blur-xl">
            <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-rose-50 text-rose-600">
              <TriangleAlert className="h-6 w-6" />
            </div>
            <p className="text-sm font-semibold uppercase tracking-[0.25em] text-rose-600">Application error</p>
            <h1 className="mt-3 text-3xl font-black tracking-tight">Something broke on the road.</h1>
            <p className="mt-3 text-base leading-7 text-slate-500">
              We hit a runtime error while rendering the app. You can try again or return to the home page.
            </p>
            <div className="mt-8 flex flex-wrap justify-center gap-3">
              <button
                type="button"
                onClick={reset}
                className="rounded-2xl bg-[#0071e3] px-5 py-3 text-sm font-semibold text-white transition hover:bg-[#0077ed]"
              >
                Try again
              </button>
              <Link
                href="/"
                className="inline-flex items-center gap-2 rounded-2xl border border-slate-200 bg-white px-5 py-3 text-sm font-semibold text-slate-700 transition hover:border-slate-300 hover:bg-slate-50 hover:text-slate-950"
              >
                <Home className="h-4 w-4" />
                Home
              </Link>
            </div>
          </div>
        </main>
      </body>
    </html>
  );
}
