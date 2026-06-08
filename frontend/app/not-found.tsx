import Link from "next/link";
import { Compass, Home } from "lucide-react";

export default function NotFoundPage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-black px-4 py-16">
      <div className="w-full max-w-xl rounded-[2rem] border border-[#1a1a1a] bg-[#0a0a0a] p-8 text-center shadow-glow backdrop-blur-xl">
        <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-white text-black">
          <Compass className="h-6 w-6" />
        </div>
        <p className="text-sm font-semibold uppercase tracking-[0.25em] text-white">404</p>
        <h1 className="mt-3 text-3xl font-black tracking-tight text-white">
          This road seems to lead nowhere.
        </h1>
        <p className="mt-3 text-base leading-7 text-[#a0a0a0]">
          The page you&apos;re looking for does not exist, may have moved, or is temporarily unavailable.
        </p>
        <Link
          href="/"
          className="mt-8 inline-flex items-center gap-2 rounded-2xl bg-white px-5 py-3 text-sm font-semibold text-black transition hover:bg-[#e0e0e0]"
        >
          <Home className="h-4 w-4" />
          Back to RoadMind AI
        </Link>
      </div>
    </main>
  );
}
