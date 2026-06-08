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
      <body className="min-h-screen bg-black text-white">
        <main className="flex min-h-screen items-center justify-center px-4 py-16">
          <div className="w-full max-w-xl rounded-[2rem] border border-[#1a1a1a] bg-[#0a0a0a] p-8 text-center shadow-2xl backdrop-blur-xl">
            <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-red-500/15 text-red-300">
              <TriangleAlert className="h-6 w-6" />
            </div>
            <p className="text-sm font-semibold uppercase tracking-[0.25em] text-red-300">Application error</p>
            <h1 className="mt-3 text-3xl font-black tracking-tight">Something broke on the road.</h1>
            <p className="mt-3 text-base leading-7 text-[#a0a0a0]">
              We hit a runtime error while rendering the app. You can try again or return to the home page.
            </p>
            <div className="mt-8 flex flex-wrap justify-center gap-3">
              <button
                type="button"
                onClick={reset}
                className="rounded-2xl bg-white px-5 py-3 text-sm font-semibold text-black transition hover:bg-[#e0e0e0]"
              >
                Try again
              </button>
              <Link
                href="/"
                className="inline-flex items-center gap-2 rounded-2xl border border-[#2a2a2a] bg-transparent px-5 py-3 text-sm font-semibold text-white transition hover:bg-[#1a1a1a]"
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
