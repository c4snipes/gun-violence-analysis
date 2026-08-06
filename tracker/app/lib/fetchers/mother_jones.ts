/**
 * Mother Jones fetcher.
 *
 * Source: public Google Sheet exported as CSV.
 * Definition: 3+ killed (4+ before 2013), public place, indiscriminate.
 * Failure mode: sheet URL is stable, but the sheet ID could rotate. On any
 * error we return an empty array and let the caller mark the source stale.
 */

import { parse } from "csv-parse/sync";

import type { Incident } from "@/types/data";
import { parseStateFromLocation, normalizeDate, parseIntSafe } from "./util";

const SHEET_ID = "1b9o6uDO18sLxBqPwl_Gh9bnhW-ev_dABH83M5Vb5L8o";
const URL = `https://docs.google.com/spreadsheets/d/${SHEET_ID}/export?format=csv`;

export async function fetchMotherJones(): Promise<Incident[]> {
  const res = await fetch(URL, { redirect: "follow" });
  if (!res.ok) throw new Error(`Mother Jones fetch failed: ${res.status}`);
  const csv = await res.text();

  const rows = parse(csv, {
    columns: true,
    skip_empty_lines: true,
    relax_column_count: true,
  }) as Record<string, string>[];

  const incidents: Incident[] = [];
  for (const row of rows) {
    const state = parseStateFromLocation(row.location ?? "");
    if (!state) continue;
    const date = normalizeDate(row.date);
    if (!date) continue;

    incidents.push({
      id: `mj-${slug(row.case ?? date + state)}`,
      date,
      state,
      city: (row.location ?? "").split(",")[0]?.trim() ?? "",
      killed: parseIntSafe(row.fatalities),
      injured: parseIntSafe(row.injured),
      source: "mother_jones",
      url: row.sources?.split(";")[0]?.trim(),
      summary: row.summary?.trim() || undefined,
    });
  }
  return incidents;
}

function slug(s: string): string {
  return s.toLowerCase().replace(/[^a-z0-9]+/g, "-").slice(0, 60);
}
