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

/**
 * One page's worth of incidents, plus the raw GVA incident ids seen on it.
 *
 * The ids are returned separately because they are used only to de-duplicate
 * across pages; the emitted Incident.id keeps its original date/state/city
 * form, which the citations cache is keyed on.
 */
interface ParsedPage {
  incidents: Incident[];
  gvaIds: string[];
  oldestDate: string | null;
}

function parsePage(html: string): ParsedPage {
  const headers = extractHeaderCells(html);
  assertTableShape(headers);

  const rowRegex = /<tr[^>]*>([\s\S]*?)<\/tr>/g;
  const cellRegex = /<td[^>]*>([\s\S]*?)<\/td>/g;
  const incidents: Incident[] = [];
  const gvaIds: string[] = [];
  let oldestDate: string | null = null;
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

    const [gvaId, dateStr, stateStr, city, , killedStr, injuredStr] = cells;
    const date = normalizeDate(dateStr);
    if (!date) continue; // isolated bad date on one row; not a structural signal

    // Tracked before the state filter, so the page's true date span is known
    // even when every row on it falls outside the 50 states. Otherwise the
    // crawl could not tell "this page is older than the cutoff" from "this
    // page happened to be all territories".
    if (oldestDate === null || date < oldestDate) oldestDate = date;
    gvaIds.push(gvaId);

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

  return { incidents, gvaIds, oldestDate };
}

/**
 * Crawl settings. The report is a Drupal Views table paged with ?page=N,
 * zero-indexed, 25 rows a page, newest first -- verified against the live site.
 */
const PAGE_SIZE = 25;
// A year runs about 415 incidents at the observed rate of 8 a week, so ~17
// pages. 40 is generous headroom that still bounds a runaway crawl; if the
// cutoff logic ever broke, this is what stops it walking to 2014.
const MAX_PAGES = 40;
// GVA returned 403 to a second request made seconds after the first, so the
// crawl is deliberately slow. ~17 pages at 1.5s is about 25 seconds, which is
// nothing against a nightly job and is the difference between being a polite
// client and being blocked.
const PAGE_DELAY_MS = 1500;
const MAX_RETRIES = 3;
const RETRY_BASE_MS = 4000;

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/**
 * The report is scoped to a CALENDAR YEAR, not a rolling window.
 *
 * /reports/mass-shooting is titled "Mass Shootings in 2026" and starts at
 * 1 January; ?year=2025 serves the prior year the same way. So a 365-day
 * window spans two of these reports for most of the year, and crawling only
 * the current one silently truncates to year-to-date -- in September that is
 * nine months presented as twelve.
 */
function pageUrl(year: number, page: number, currentYear: number): string {
  const params = new URLSearchParams();
  if (year !== currentYear) params.set("year", String(year));
  if (page > 0) params.set("page", String(page));
  const qs = params.toString();
  return qs ? `${REPORT_URL}?${qs}` : REPORT_URL;
}

async function fetchPage(
  year: number,
  page: number,
  currentYear: number,
  fetchImpl: typeof fetch,
  retryBaseMs: number,
): Promise<string> {
  const url = pageUrl(year, page, currentYear);

  for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
    const res = await fetchImpl(url, {
      headers: { "User-Agent": "gun-violence-tracker (github.com/c4snipes)" },
    });
    if (res.ok) return res.text();

    // 403 here is rate limiting rather than a permanent refusal -- the same
    // URL succeeds when approached more slowly -- so it backs off like a 429
    // instead of failing outright.
    const retriable = res.status === 403 || res.status === 429 || res.status >= 500;
    if (!retriable || attempt === MAX_RETRIES) {
      throw new Error(`GVA fetch failed: ${res.status} on ${year} page ${page}`);
    }
    if (retryBaseMs > 0) await sleep(retryBaseMs * 2 ** attempt);
  }
  throw new Error(`GVA fetch failed: exhausted retries on ${year} page ${page}`);
}

export interface FetchGVAOptions {
  /** How far back to crawl. Matches the tracker's rolling window. */
  sinceDays?: number;
  /** Injectable for tests; defaults to global fetch. */
  fetchImpl?: typeof fetch;
  /** Injectable for tests so they do not wait out the real throttle. */
  delayMs?: number;
  /** Injectable so tests can pin the cutoff rather than drift with the clock. */
  now?: Date;
  /** Injectable so tests do not sit through real exponential backoff. */
  retryBaseMs?: number;
}

/**
 * Every qualifying incident within the window, walked across the pager.
 *
 * WHY THIS PAGES AT ALL
 * It used to fetch one page and stop, so the tracker reported whatever the
 * newest 25 incidents were -- about three weeks -- as a 365-day count. The
 * giveaway was that the total read exactly 25 both before and after a
 * seven-week outage: it was pinned to the page size, not to the window.
 *
 * PARTIAL RESULTS ARE KEPT, NOT DISCARDED
 * If page 0 parses and page 9 fails, the incidents already collected are
 * returned rather than thrown away. Eight pages of real data beats none, and
 * the staleness guard in app/lib/staleness.ts still catches the case where the
 * crawl degrades so far that nothing recent arrives. A structural failure on
 * the FIRST page still throws, because that means the table shape changed and
 * every page will be wrong the same way.
 */
export async function fetchGVA(opts: FetchGVAOptions = {}): Promise<Incident[]> {
  const {
    sinceDays = 365,
    fetchImpl = fetch,
    delayMs = PAGE_DELAY_MS,
    now = new Date(),
    retryBaseMs = RETRY_BASE_MS,
  } = opts;

  const cutoff = new Date(now);
  cutoff.setDate(cutoff.getDate() - sinceDays);
  const cutoffISO = cutoff.toISOString().slice(0, 10);

  const collected: Incident[] = [];
  const seen = new Set<string>();

  const currentYear = now.getFullYear();
  const cutoffYear = cutoff.getFullYear();
  let firstRequest = true;
  let reachedCutoff = false;

  for (let year = currentYear; year >= cutoffYear && !reachedCutoff; year--) {
    for (let page = 0; page < MAX_PAGES; page++) {
      if (!firstRequest && delayMs > 0) await sleep(delayMs);
      firstRequest = false;

      let parsed: ParsedPage;
      try {
        parsed = parsePage(await fetchPage(year, page, currentYear, fetchImpl, retryBaseMs));
      } catch (err) {
        // The very first request failing means the source or the parse is
        // broken, and there is nothing partial to salvage.
        if (year === currentYear && page === 0) throw err;
        console.warn(
          `  GVA ${year} page ${page} failed, keeping ${collected.length} incidents: ${err}`,
        );
        reachedCutoff = true; // stop crawling rather than hammer a failing source
        break;
      }

      // An empty page is the end of this year's pager.
      if (parsed.gvaIds.length === 0) break;

      for (let i = 0; i < parsed.incidents.length; i++) {
        const inc = parsed.incidents[i];
        if (inc.date < cutoffISO) continue;
        // New incidents published mid-crawl shift rows down a page, which can
        // show the same incident twice. GVA's own incident id is stable, so it
        // is what de-duplicates -- the emitted id is not unique per incident by
        // construction (two shootings in one city on one day share it).
        const key = parsed.gvaIds[i] ?? `${inc.date}|${inc.state}|${inc.city}`;
        if (seen.has(key)) continue;
        seen.add(key);
        collected.push(inc);
      }

      // Rows are newest first, so once a page's oldest row predates the
      // cutoff, every later page and every earlier year does too.
      if (parsed.oldestDate !== null && parsed.oldestDate < cutoffISO) {
        reachedCutoff = true;
        break;
      }
      // A short page is this year's last.
      if (parsed.gvaIds.length < PAGE_SIZE) break;
    }
  }

  if (collected.length === 0) {
    throw new Error(
      "GVA parse failed: pages fetched and headers matched, but no incidents fell " +
        `within the last ${sinceDays} days`,
    );
  }

  return collected;
}
