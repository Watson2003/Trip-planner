"use client";

import Cookies from "js-cookie";

import type { User } from "@/types/auth";

const TOKEN_COOKIE_NAME = "roadmind_auth_token";
const TOKEN_EXPIRY_DAYS = 1;

type JwtPayload = {
  exp?: number;
  user_id?: number;
  id?: number;
  username?: string;
  email?: string;
  full_name?: string;
  sub?: string;
};

function base64UrlDecode(value: string) {
  const normalized = value.replace(/-/g, "+").replace(/_/g, "/");
  const padded = normalized + "=".repeat((4 - (normalized.length % 4)) % 4);

  if (typeof window === "undefined") {
    return Buffer.from(padded, "base64").toString("utf8");
  }

  return window.atob(padded);
}

function decodePayload(token: string): JwtPayload | null {
  const parts = token.split(".");
  if (parts.length < 2) return null;

  try {
    return JSON.parse(base64UrlDecode(parts[1])) as JwtPayload;
  } catch {
    return null;
  }
}

function isTokenExpired(token: string) {
  const payload = decodePayload(token);
  if (!payload?.exp) return true;
  return Date.now() >= payload.exp * 1000;
}

export function saveToken(token: string) {
  Cookies.set(TOKEN_COOKIE_NAME, token, {
    expires: TOKEN_EXPIRY_DAYS,
    sameSite: "strict",
    secure: typeof window !== "undefined" ? window.location.protocol === "https:" : false,
  });
}

export function getToken(): string | null {
  return Cookies.get(TOKEN_COOKIE_NAME) ?? null;
}

export function removeToken() {
  Cookies.remove(TOKEN_COOKIE_NAME);
}

export function isLoggedIn(): boolean {
  const token = getToken();
  return Boolean(token && !isTokenExpired(token));
}

export function getAuthHeaders(): { Authorization?: string } {
  const token = getToken();
  if (!token || isTokenExpired(token)) {
    return {};
  }

  return { Authorization: `Bearer ${token}` };
}

export function getUser(): User | null {
  const token = getToken();
  if (!token || isTokenExpired(token)) return null;

  const payload = decodePayload(token);
  if (!payload) return null;

  const email = payload.email ?? payload.sub;
  const userId = payload.user_id ?? payload.id;
  if (!email || typeof userId !== "number") return null;

  const username = payload.username ?? email.split("@")[0] ?? "";

  return {
    id: userId,
    username,
    email,
    full_name: payload.full_name ?? "",
  };
}
