import Link from "next/link";
import { Compass, Home } from "lucide-react";

export default function NotFoundPage() {
  return (
    <main className="flex min-h-screen items-center justify-center px-4 py-16">
      <div className="w-full max-w-xl rounded-[2rem] border border-white/80 bg-white/75 p-8 text-center shadow-glow backdrop-blur-xl dark:border-slate-800 dark:bg-slate-900/80">
        <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-orange-100 text-orange-600 dark:bg-orange-950/50 dark:text-orange-300">
          <Compass className="h-6 w-6" />
        </div>
        <p className="text-sm font-semibold uppercase tracking-[0.25em] text-orange-600 dark:text-orange-300">404</p>
        <h1 className="mt-3 text-3xl font-black tracking-tight text-slate-950 dark:text-white">
          This road seems to lead nowhere.
        </h1>
        <p className="mt-3 text-base leading-7 text-slate-600 dark:text-slate-300">
          The page you&apos;re looking for does not exist, may have moved, or is temporarily unavailable.
        </p>
        <Link
          href="/"
          className="mt-8 inline-flex items-center gap-2 rounded-2xl bg-slate-950 px-5 py-3 text-sm font-semibold text-white transition hover:bg-slate-800"
        >
          <Home className="h-4 w-4" />
          Back to RoadMind AI
        </Link>
      </div>
    </main>
  );
}
