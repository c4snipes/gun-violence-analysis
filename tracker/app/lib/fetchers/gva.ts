/**
 * Gun Violence Archive fetcher.
 *
 * Source: HTML scrape of the mass-shooting reports page. GVA has no public
 * API and their terms restrict commercial use, so this tracker only pulls
 * their published aggregate reports (not per-incident scraping at scale).
 *
 * Definition: 4+ victims shot (injured OR killed), not including shooter.
 *
 * Failure mode: HTML structure can change without notice. Before trusting
 * the positional column mapping below, we check the table header still
 * says what we think it says. If the header is missing, reordered, or a
 * row's cell count / killed-injured values don't look like what a GVA row
 * should look like, we throw rather than return a partial or silently
 * wrong-shaped result. The caller (scripts/refresh_data.ts) catches that,
 * marks the source stale, and falls back to yesterday's committed data.
 */

import type { Incident } from "@/types/data";
import { STATE_ABBR, STATE_POPULATION } from "../states";
import { normalizeDate, stripHtml } from "./util";

const REPORT_URL = "https://www.gunviolencearchive.org/reports/mass-shooting";

// Positional schema we rely on when destructuring each row's cells. The
// highest index read is 6 (# injured), so a row needs at least seven cells.
//
// This was an EXACT count of 7, and GVA appending four columns -- Suspects
// Killed, Suspects Injured, Suspects Arrested, Operations -- made every data
// row throw. The scrape had been failing for six weeks while the site went on
// serving cached figures behind a "most recent run failed" footnote: the
// failure was reported honestly and still went unnoticed, because a stale
// tracker looks exactly like a quiet one.
//
// An exact count was the wrong invariant. It is HEADER_SCHEMA below that
// protects the indices, by checking the columns are named what we expect, and
// a column inserted before index 6 would fail it loudly. Appending columns to
// the right of the ones we read cannot move them, so it should not be fatal.
const MIN_CELL_COUNT = 7;
const HEADER_SCHEMA: Array<{ index: number; mustInclude: string }> = [
  { index: 1, mustInclude: "date" },
  { index: 2, mustInclude: "state" },
  { index: 3, mustInclude: "city" },
  { index: 5, mustInclude: "killed" },
  { index: 6, mustInclude: "injured" },
];

function extractHeaderCells(html: string): string[] {
  const headerRowMatch = html.match(/<tr[^>]*>\s*(?:<th[\s\S]*?<\/th>\s*)+<\/tr>/i);
  if (!headerRowMatch) return [];
  const cells: string[] = [];
  const thRegex = /<th[^>]*>([\s\S]*?)<\/th>/g;
  let m: RegExpExecArray | null;
  while ((m = thRegex.exec(headerRowMatch[0]))) {
    cells.push(stripHtml(m[1]).trim().toLowerCase());
  }
  return cells;
}

function assertTableShape(headers: string[]): void {
  if (headers.length === 0) {
    throw new Error("GVA parse failed: no <th> header row found in report page");
  }
  for (const { index, mustInclude } of HEADER_SCHEMA) {
    const cell = headers[index];
    if (!cell || !cell.includes(mustInclude)) {
      throw new Error(
        `GVA parse failed: expected header column ${index} to contain "${mustInclude}", ` +
          `got ${JSON.stringify(cell ?? null)} (full header row: ${JSON.stringify(headers)})`,
      );
    }
  }
}

function parseCount(s: string | undefined, field: string, rawCells: string[]): number {
  const trimmed = s?.trim() ?? "";
  const n = Number(trimmed);
  if (trimmed === "" || !Number.isInteger(n) || n < 0) {
    throw new Error(
      `GVA parse failed: "${field}" cell was not a valid non-negative integer: ` +
        `${JSON.stringify(s)} (row: ${JSON.stringify(rawCells)})`,
    );
  }
  return n;
}

export async function fetchGVA(): Promise<Incident[]> {
  const res = await fetch(REPORT_URL, {
    headers: { "User-Agent": "gun-violence-tracker (github.com/c4snipes)" },
  });
  if (!res.ok) throw new Error(`GVA fetch failed: ${res.status}`);
  const html = await res.text();

  const headers = extractHeaderCells(html);
  assertTableShape(headers);

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
    if (cells.length === 0) continue; // header row or non-data <tr>, no <td>s
    if (cells.length < MIN_CELL_COUNT) {
      throw new Error(
        `GVA parse failed: need at least ${MIN_CELL_COUNT} cells per data row, got ` +
          `${cells.length} (row: ${JSON.stringify(cells)})`,
      );
    }
    // The table must stay rectangular. A data row that disagrees with the
    // header it was validated against means the columns no longer line up,
    // which is the case where the named-header check cannot save the indices.
    if (headers.length > 0 && cells.length !== headers.length) {
      throw new Error(
        `GVA parse failed: row has ${cells.length} cells but the header has ` +
          `${headers.length} (row: ${JSON.stringify(cells)})`,
      );
    }

    const [, dateStr, stateStr, city, , killedStr, injuredStr] = cells;
    const date = normalizeDate(dateStr);
    if (!date) continue; // isolated bad date on one row; not a structural signal

    const state =
      stateStr in STATE_ABBR ? STATE_ABBR[stateStr] : STATE_POPULATION[stateStr] ? stateStr : null;
    if (!state) continue; // e.g. DC or a territory outside our 50-state scope

    incidents.push({
      id: `gva-${date}-${state.toLowerCase().replace(/\s+/g, "-")}-${city.toLowerCase().replace(/\s+/g, "-")}`,
      date,
      state,
      city,
      killed: parseCount(killedStr, "# killed", cells),
      injured: parseCount(injuredStr, "# injured", cells),
      source: "gva",
    });
  }

  if (incidents.length === 0) {
    throw new Error(
      "GVA parse failed: header matched the expected schema but zero data rows were parsed",
    );
  }

  return incidents;
}
