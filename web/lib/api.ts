"use client";
import { supabase } from "./supabase";

export const API = (process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

export class ApiError extends Error {}

async function token(): Promise<string | null> {
  const { data } = await supabase().auth.getSession();
  return data.session?.access_token ?? null;
}

export async function api<T = any>(path: string, init: RequestInit = {}): Promise<T> {
  const t = await token();
  const headers: Record<string, string> = { ...(init.headers as Record<string, string>) };
  if (t) headers["Authorization"] = `Bearer ${t}`;
  if (init.body && !(init.body instanceof FormData)) headers["Content-Type"] = "application/json";
  let r: Response;
  try {
    r = await fetch(API + path, { ...init, headers });
  } catch {
    throw new ApiError(`The ForgeAI API is not reachable at ${API}.`);
  }
  if (!r.ok) {
    let detail = r.statusText;
    try { detail = (await r.json()).detail ?? detail; } catch { /* not JSON */ }
    throw new ApiError(`${r.status}: ${typeof detail === "string" ? detail : JSON.stringify(detail)}`);
  }
  const ct = r.headers.get("content-type") || "";
  return (ct.includes("json") ? r.json() : r.blob()) as Promise<T>;
}

export const get = <T = any>(p: string) => api<T>(p);
export const post = <T = any>(p: string, body?: any) =>
  api<T>(p, { method: "POST", body: body instanceof FormData ? body : JSON.stringify(body ?? {}) });

export async function download(path: string, filename: string) {
  const blob = await api<Blob>(path);
  const b = blob instanceof Blob ? blob : new Blob([JSON.stringify(blob, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(b);
  const a = document.createElement("a");
  a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}

export async function waitJob(id: string, onMsg: (m: string[]) => void): Promise<any> {
  for (;;) {
    const j = await get(`/jobs/${id}`);
    onMsg(j.messages || []);
    if (j.status === "completed") return j.result;
    if (j.status === "failed") throw new ApiError(j.error || "job failed");
    await new Promise((r) => setTimeout(r, 2000));
  }
}

export const pct = (x?: number | null) => (x === null || x === undefined ? "n/a" : `${(x * 100).toFixed(1)}%`);
