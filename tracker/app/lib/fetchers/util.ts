/** Shared helpers for source fetchers. */

import { STATE_ABBR, STATE_POPULATION } from "../states";

export function parseStateFromLocation(loc: string): string | null {
  if (!loc) return null;
  const tail = loc.split(",").pop()?.trim().split(";")[0]?.trim();
  if (!tail) return null;
  if (STATE_POPULATION[tail]) return tail;
  const upper = tail.toUpperCase();
  return STATE_ABBR[upper] ?? null;
}

export function normalizeDate(d: string | undefined): string | null {
  if (!d) return null;
  const parsed = new Date(d);
  if (isNaN(parsed.getTime())) return null;
  return parsed.toISOString().slice(0, 10);
}

export function parseIntSafe(s: string | undefined): number {
  const n = parseInt(s ?? "0", 10);
  return isNaN(n) ? 0 : n;
}

export function stripHtml(s: string): string {
  return s
    .replace(/<[^>]+>/g, "")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&#039;/g, "'")
    .replace(/&quot;/g, '"');
}

/**
 * fetch() with a hard timeout. None of this repo's fetchers bound their
 * fetch() before this — a single hung request could stall the whole daily
 * refresh job indefinitely. GDELT's per-incident lookup loop (gdelt.ts) is
 * the first place that risk is realistic, so it's fixed here first.
 */
export async function fetchWithTimeout(
  url: string,
  options: RequestInit = {},
  timeoutMs = 10_000,
): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}
