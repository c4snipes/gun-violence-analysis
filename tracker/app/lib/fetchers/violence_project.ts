/**
 * The Violence Project fetcher.
 *
 * Source: their public download page requires a request form for the full
 * codebook. For public use they publish a subset of aggregate incident
 * data. Since there's no stable public URL, the tracker looks for a
 * locally-committed CSV at data/raw/violence_project.csv. If not present,
 * the source is marked as unavailable rather than failing the build.
 *
 * Definition: 4+ killed, excluding shooter, public location, no gang/drug
 * connection.
 *
 * To enable this source: manually download the Violence Project database
 * from theviolenceproject.org/databases/download, save the incidents sheet
 * as data/raw/violence_project.csv with columns [Date, City, State, Killed,
 * Injured, CaseID].
 */

import { readFile } from "node:fs/promises";
import { join } from "node:path";

import { parse } from "csv-parse/sync";

import type { Incident } from "@/types/data";
import { STATE_POPULATION } from "../states";
import { normalizeDate, parseIntSafe } from "./util";

const LOCAL_PATH = join(process.cwd(), "data", "raw", "violence_project.csv");

export async function fetchViolenceProject(): Promise<Incident[]> {
  let csv: string;
  try {
    csv = await readFile(LOCAL_PATH, "utf-8");
  } catch {
    // Not an error — just means the user hasn't manually added it. Return
    // empty so the tracker builds without it.
    return [];
  }

  const rows = parse(csv, { columns: true, skip_empty_lines: true }) as Record<string, string>[];

  const incidents: Incident[] = [];
  for (const row of rows) {
    const state = row.State?.trim();
    if (!state || !STATE_POPULATION[state]) continue;
    const date = normalizeDate(row.Date);
    if (!date) continue;

    incidents.push({
      id: `vp-${row.CaseID ?? `${date}-${state}`}`.replace(/\s+/g, "-"),
      date,
      state,
      city: row.City?.trim() ?? "",
      killed: parseIntSafe(row.Killed),
      injured: parseIntSafe(row.Injured),
      source: "violence_project",
    });
  }
  return incidents;
}
