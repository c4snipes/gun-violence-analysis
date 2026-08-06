/**
 * Stanford MSA fetcher.
 *
 * Source: raw CSV from the archived GitHub repo. Project is permanently
 * suspended (coverage ends 2016), so this data never changes. We still
 * fetch it once so users can see the historical series alongside live
 * sources.
 *
 * Definition: 3+ shot (not necessarily killed), excludes shooter, excludes
 * identifiably gang/drug/organized-crime incidents.
 */

import { parse } from "csv-parse/sync";

import type { Incident } from "@/types/data";
import { STATE_POPULATION } from "../states";
import { normalizeDate, parseIntSafe } from "./util";

const CSV_URL =
  "https://raw.githubusercontent.com/StanfordGeospatialCenter/MSA/master/Data/Stanford_MSA_Database.csv";

export async function fetchStanfordMSA(): Promise<Incident[]> {
  const res = await fetch(CSV_URL);
  if (!res.ok) throw new Error(`Stanford MSA fetch failed: ${res.status}`);
  // The Stanford CSV has some non-UTF8 bytes in older rows; decode leniently.
  const buf = await res.arrayBuffer();
  const csv = new TextDecoder("utf-8", { fatal: false }).decode(buf);

  const rows = parse(csv, {
    columns: true,
    skip_empty_lines: true,
    relax_column_count: true,
    relax_quotes: true,
  }) as Record<string, string>[];

  const incidents: Incident[] = [];
  for (const row of rows) {
    const stateRaw = (row["Location"] ?? "").split(",").pop()?.trim();
    if (!stateRaw || !STATE_POPULATION[stateRaw]) continue;

    const date = normalizeDate(row["Date"]);
    if (!date) continue;

    incidents.push({
      id: `stanford-${row["CaseID"] ?? date + stateRaw}`,
      date,
      state: stateRaw,
      city: (row["Location"] ?? "").split(",")[0]?.trim() ?? "",
      killed: parseIntSafe(row["Number of Civilian Fatalities"]),
      injured: parseIntSafe(row["Number of Civilian Injured"]),
      source: "stanford_msa",
      summary: row["Title"]?.trim() || undefined,
    });
  }
  return incidents;
}
