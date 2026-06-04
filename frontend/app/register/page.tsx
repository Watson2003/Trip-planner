"use client";

import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Eye, EyeOff, Loader2, Route } from "lucide-react";

import { saveToken, isLoggedIn } from "@/lib/auth";
import type { AuthResponse, RegisterForm } from "@/types/auth";

const INITIAL_FORM: RegisterForm = {
  username: "",
  email: "",
  password: "",
  full_name: "",
  confirmPassword: "",
};

type FieldErrors = Partial<Record<keyof RegisterForm | "server", string>>;

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function readServerMessage(payload: unknown, fallback: string) {
  if (payload && typeof payload === "object" && "detail" in payload) {
    const detail = (payload as { detail?: unknown }).detail;
    if (typeof detail === "string" && detail.trim()) return detail;
    if (Array.isArray(detail)) {
      const message = detail
        .map((item) => {
          if (typeof item === "string") return item;
          if (item && typeof item === "object" && "msg" in item) return String((item as { msg?: unknown }).msg ?? "");
          return "";
        })
        .filter(Boolean)
        .join("; ");
      if (message) return message;
    }
  }
  return fallback;
}

function validate(form: RegisterForm): FieldErrors {
  const errors: FieldErrors = {};

  if (!form.full_name.trim()) errors.full_name = "Full name is required";
  if (!form.username.trim()) errors.username = "Username is required";
  if (!form.email.trim()) errors.email = "Email is required";
  else if (!EMAIL_PATTERN.test(form.email.trim())) errors.email = "Enter a valid email address";
  if (!form.password) errors.password = "Password is required";
  else if (form.password.length < 8) errors.password = "Password must be at least 8 characters";
  if (!form.confirmPassword) errors.confirmPassword = "Please confirm your password";
  else if (form.confirmPassword !== form.password) errors.confirmPassword = "Passwords do not match";

  return errors;
}

function FieldError({ message }: { message?: string }) {
  if (!message) return null;
  return <p className="text-sm text-red-300">{message}</p>;
}

export default function RegisterPage() {
  const router = useRouter();
  const [form, setForm] = useState<RegisterForm>(INITIAL_FORM);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [serverError, setServerError] = useState("");

  useEffect(() => {
    if (isLoggedIn()) {
      router.replace("/");
    }
  }, [router]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setServerError("");

    const nextErrors = validate(form);
    setFieldErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) return;

    setLoading(true);

    try {
      const registerResponse = await fetch("/api/auth/register", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          username: form.username.trim(),
          email: form.email.trim(),
          password: form.password,
          full_name: form.full_name.trim(),
        }),
      });

      if (!registerResponse.ok) {
        const payload = await registerResponse.json().catch(() => null);
        throw new Error(readServerMessage(payload, "Unable to create account"));
      }

      const loginResponse = await fetch("/api/auth/login", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          email: form.email.trim(),
          password: form.password,
        }),
      });

      if (!loginResponse.ok) {
        const payload = await loginResponse.json().catch(() => null);
        throw new Error(readServerMessage(payload, "Account created, but sign in failed"));
      }

      const loginData = (await loginResponse.json()) as AuthResponse;
      saveToken(loginData.access_token);
      router.replace("/");
    } catch (error) {
      setServerError(error instanceof Error ? error.message : "Unable to create account");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="relative min-h-screen overflow-hidden bg-slate-950 text-white">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,_rgba(249,115,22,0.25),_transparent_35%),radial-gradient(circle_at_bottom_right,_rgba(59,130,246,0.18),_transparent_32%),linear-gradient(180deg,#020617_0%,#0f172a_55%,#111827_100%)]" />
      <div className="absolute inset-0 opacity-25 [background-image:linear-gradient(rgba(148,163,184,0.15)_1px,transparent_1px),linear-gradient(90deg,rgba(148,163,184,0.15)_1px,transparent_1px)] [background-size:56px_56px]" />

      <div className="relative mx-auto flex min-h-screen w-full max-w-md items-center px-4 py-12 sm:px-0">
        <section className="w-full rounded-[2rem] border border-white/10 bg-slate-950/80 p-6 shadow-2xl shadow-black/40 backdrop-blur-xl sm:p-8">
          <div className="mb-8 text-center">
            <div className="mb-4 inline-flex h-14 w-14 items-center justify-center rounded-2xl bg-orange-500/15 text-orange-400 ring-1 ring-orange-400/20">
              <Route className="h-7 w-7" />
            </div>
            <h1 className="text-3xl font-black tracking-tight text-white">RoadMind AI</h1>
            <p className="mt-2 text-sm leading-6 text-slate-400">
              Create your account to start planning trips.
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <label htmlFor="full_name" className="text-sm font-medium text-slate-200">
                Full Name
              </label>
              <input
                id="full_name"
                type="text"
                autoComplete="name"
                value={form.full_name}
                onChange={(event) => {
                  setForm((current) => ({ ...current, full_name: event.target.value }));
                  setFieldErrors((current) => ({ ...current, full_name: undefined, server: undefined }));
                }}
                className="w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-white outline-none transition placeholder:text-slate-500 focus:border-orange-400 focus:bg-white/8"
                placeholder="Your full name"
              />
              <FieldError message={fieldErrors.full_name} />
            </div>

            <div className="space-y-2">
              <label htmlFor="username" className="text-sm font-medium text-slate-200">
                Username
              </label>
              <input
                id="username"
                type="text"
                autoComplete="username"
                value={form.username}
                onChange={(event) => {
                  setForm((current) => ({ ...current, username: event.target.value }));
                  setFieldErrors((current) => ({ ...current, username: undefined, server: undefined }));
                }}
                className="w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-white outline-none transition placeholder:text-slate-500 focus:border-orange-400 focus:bg-white/8"
                placeholder="Choose a username"
              />
              <FieldError message={fieldErrors.username} />
            </div>

            <div className="space-y-2">
              <label htmlFor="email" className="text-sm font-medium text-slate-200">
                Email
              </label>
              <input
                id="email"
                type="email"
                autoComplete="email"
                value={form.email}
                onChange={(event) => {
                  setForm((current) => ({ ...current, email: event.target.value }));
                  setFieldErrors((current) => ({ ...current, email: undefined, server: undefined }));
                }}
                className="w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-white outline-none transition placeholder:text-slate-500 focus:border-orange-400 focus:bg-white/8"
                placeholder="you@example.com"
              />
              <FieldError message={fieldErrors.email} />
            </div>

            <div className="space-y-2">
              <label htmlFor="password" className="text-sm font-medium text-slate-200">
                Password
              </label>
              <div className="flex items-stretch overflow-hidden rounded-2xl border border-white/10 bg-white/5 transition focus-within:border-orange-400 focus-within:bg-white/8">
                <input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  autoComplete="new-password"
                  value={form.password}
                  onChange={(event) => {
                    const password = event.target.value;
                    setForm((current) => ({ ...current, password }));
                    setFieldErrors((current) => ({
                      ...current,
                      password: undefined,
                      confirmPassword:
                        current.confirmPassword && current.confirmPassword !== password
                          ? "Passwords do not match"
                          : undefined,
                      server: undefined,
                    }));
                  }}
                  className="min-w-0 flex-1 bg-transparent px-4 py-3 text-white outline-none placeholder:text-slate-500"
                  placeholder="Create a password"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((current) => !current)}
                  className="inline-flex items-center justify-center px-4 text-slate-400 transition hover:text-white"
                  aria-label={showPassword ? "Hide password" : "Show password"}
                >
                  {showPassword ? <EyeOff className="h-5 w-5" /> : <Eye className="h-5 w-5" />}
                </button>
              </div>
              <FieldError message={fieldErrors.password} />
            </div>

            <div className="space-y-2">
              <label htmlFor="confirmPassword" className="text-sm font-medium text-slate-200">
                Confirm Password
              </label>
              <div className="flex items-stretch overflow-hidden rounded-2xl border border-white/10 bg-white/5 transition focus-within:border-orange-400 focus-within:bg-white/8">
                <input
                  id="confirmPassword"
                  type={showConfirmPassword ? "text" : "password"}
                  autoComplete="new-password"
                  value={form.confirmPassword}
                  onChange={(event) => {
                    setForm((current) => ({ ...current, confirmPassword: event.target.value }));
                    setFieldErrors((current) => ({ ...current, confirmPassword: undefined, server: undefined }));
                  }}
                  className="min-w-0 flex-1 bg-transparent px-4 py-3 text-white outline-none placeholder:text-slate-500"
                  placeholder="Confirm your password"
                />
                <button
                  type="button"
                  onClick={() => setShowConfirmPassword((current) => !current)}
                  className="inline-flex items-center justify-center px-4 text-slate-400 transition hover:text-white"
                  aria-label={showConfirmPassword ? "Hide confirm password" : "Show confirm password"}
                >
                  {showConfirmPassword ? <EyeOff className="h-5 w-5" /> : <Eye className="h-5 w-5" />}
                </button>
              </div>
              <FieldError message={fieldErrors.confirmPassword} />
            </div>

            {serverError ? (
              <div className="w-full rounded-2xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-200">
                {serverError}
              </div>
            ) : null}

            <button
              type="submit"
              disabled={loading}
              className="inline-flex w-full items-center justify-center gap-2 rounded-2xl bg-orange-500 px-5 py-3.5 text-sm font-bold text-white transition hover:bg-orange-600 disabled:cursor-not-allowed disabled:opacity-70"
            >
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              {loading ? "Creating account..." : "Create Account"}
            </button>
          </form>

          <p className="mt-6 text-center text-sm text-slate-400">
            Already have an account?{" "}
            <Link href="/login" className="font-semibold text-orange-400 transition hover:text-orange-300">
              Sign In
            </Link>
          </p>
        </section>
      </div>
    </main>
  );
}
