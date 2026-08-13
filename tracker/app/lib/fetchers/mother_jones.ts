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
    // The sheet has TWO columns named 'location': column 1 is "City, State"
    // and column 7 is the venue type ("Workplace", "Other", ...). With
    // columns:true csv-parse keeps the last, so row.location was "Other" and
    // parseStateFromLocation rejected every row -- the source silently
    // returned zero incidents and the dashboard reported it as uncollected.
    // De-duplicate by suffixing repeats, so the first keeps its bare name.
    columns: (header: string[]) => {
      const seen = new Map<string, number>();
      return header.map((h) => {
        const n = seen.get(h) ?? 0;
        seen.set(h, n + 1);
        return n === 0 ? h : `${h}_${n}`;
      });
    },
    skip_empty_lines: true,
    relax_column_count: true,
  }) as Record<string, string>[];

  if (rows.length === 0) {
    throw new Error("Mother Jones sheet parsed to zero rows");
  }

  // Misspellings present in the published sheet. The analysis package patches
  // the same two rows (see analysis/src/gun_violence/data.py); without this the
  // Baton Rouge incident is silently dropped and the tracker's 2013-2020 count
  // comes to 55 where the published literature reports 57.
  const LOCATION_FIXES: Record<string, string> = {
    "Baton Rouge, Lousiana": "Baton Rouge, Louisiana",
  };

  const incidents: Incident[] = [];
  for (const row of rows) {
    const rawLocation = LOCATION_FIXES[row.location ?? ""] ?? row.location ?? "";
    // Washington, D.C. resolves to nothing on purpose: this project covers the
    // 50 states only, so DC is excluded here as it is everywhere else.
    const state = parseStateFromLocation(rawLocation);
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
