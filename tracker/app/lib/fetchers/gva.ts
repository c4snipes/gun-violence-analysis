/**
 * Gun Violence Archive fetcher.
 *
 * Source: HTML scrape of the mass-shooting reports page. GVA has no public
 * API and their terms restrict commercial use, so this tracker only pulls
 * their published aggregate reports (not per-incident scraping at scale).
 *
 * Definition: 4+ victims shot (injured OR killed), not including shooter.
 *
 * Failure mode: HTML structure can change without notice. On parse failure
 * we return an empty array; the caller marks the source stale and reuses
 * yesterday's committed data.
 */

import type { Incident } from "@/types/data";
import { STATE_ABBR, STATE_POPULATION } from "../states";
import { normalizeDate, parseIntSafe, stripHtml } from "./util";

const REPORT_URL = "https://www.gunviolencearchive.org/reports/mass-shooting";

export async function fetchGVA(): Promise<Incident[]> {
  const res = await fetch(REPORT_URL, {
    headers: { "User-Agent": "gun-violence-tracker (github.com/c4snipes)" },
  });
  if (!res.ok) throw new Error(`GVA fetch failed: ${res.status}`);
  const html = await res.text();

  const rowRegex = /<tr[^>]*>([\s\S]*?)<\/tr>/g;
  const cellRegex = /<td[^>]*>([\s\S]*?)<\/td>/g;
  const incidents: Incident[] = [];
  let rowMatch: RegExpExecArray | null;

  while ((rowMatch = rowRegex.exec(html))) {
    const cells: string[] = [];
    let cellMatch: RegExpExecArray | null;
    while ((cellMatch = cellRegex.exec(rowMatch[1]))) {
      cells.push(stripHtml(cellMatch[1]).trim());
    }
    if (cells.length < 7) continue;

    const [, dateStr, stateStr, city, , killedStr, injuredStr] = cells;
    const date = normalizeDate(dateStr);
    if (!date) continue;

    const state =
      stateStr in STATE_ABBR ? STATE_ABBR[stateStr] : STATE_POPULATION[stateStr] ? stateStr : null;
    if (!state) continue;

    incidents.push({
      id: `gva-${date}-${state.toLowerCase().replace(/\s+/g, "-")}-${city.toLowerCase().replace(/\s+/g, "-")}`,
      date,
      state,
      city,
      killed: parseIntSafe(killedStr),
      injured: parseIntSafe(injuredStr),
      source: "gva",
    });
  }
  return incidents;
}
