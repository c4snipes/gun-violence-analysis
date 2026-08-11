# GDELT News-Citation Enrichment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Attach optional, hedged local-news citations from GDELT to incidents already sourced from GVA/Mother Jones/Stanford MSA/Violence Project, without ever touching the yes/no/unknown logic in `definitions.ts`.

**Architecture:** A new fetcher (`gdelt.ts`) queries GDELT's DOC 2.0 API per newly-seen incident during the daily refresh job and writes results to a new, separate `citations.json`. A pure logic module (`citations.ts`) turns a citations entry into display copy and handles the merge/caching rules, independent of any I/O. The UI extends the site's existing footnote pattern with a visually distinct `†` marker.

**Tech Stack:** TypeScript (strict mode), Next.js 14 App Router, Vitest (already configured in this repo).

Full design rationale: [docs/plans/2026-08-06-gdelt-citations-design.md](../../plans/2026-08-06-gdelt-citations-design.md).

## Global Constraints

- `definitions.ts`'s `unknown` verdict is never resolved to `yes`/`no` by this feature; `Incident` and its consumers (`evaluateAll`, `refresh_data.ts`'s state-aggregation loop) are never modified to know citations exist.
- A GDELT article is accepted as a strict match only if its title contains **both** the incident's city name **and** state name (not either/or). No casualty-count gating — GDELT's DOC API returns short snippets only, and casualty figures in news text round/update constantly.
- Query date window is `incident.date - 1` day to `incident.date + 2` days.
- `citations.json` entries are **permanent** once written, including zero-result entries (`had_results: false`) — an incident already present as a key is never re-queried.
- A failed/timed-out GDELT lookup for one incident is skipped (no entry written, retried next run) and must never mark any of the four real sources (`gva`/`mother_jones`/`stanford_msa`/`violence_project`) stale.
- Citation marker in the UI is `†` (dagger), visually distinct from the four sources' numbered (`1`, `2`, ...) footnotes — never presented as a fifth tracked source.
- Copy must be hedged — "unconfirmed" / "possibly related" — never implying the citation confirms anything.
- No result at all from GDELT (`had_results: false`) renders as no marker at all ("absent renders as absent"), not a footnote.
- Tests are pure-function only (Vitest, no component-rendering framework — none exists in this repo and this feature isn't reason enough to add one), following the fixture-mocked-`fetch` pattern already established in `tracker/app/lib/fetchers/gva.test.ts`.

---

### Task 1: Citation types + shared fetch-timeout helper

**Files:**
- Modify: `tracker/types/data.ts` (append after the `Incident` interface, ~line 15)
- Modify: `tracker/app/lib/fetchers/util.ts` (append at end of file)
- Test: `tracker/app/lib/fetchers/util.test.ts` (create)

**Interfaces:**
- Produces: `CitationMatch`, `CitationEntry`, `CitationsFile` types (exported from `@/types/data`); `fetchWithTimeout(url: string, options?: RequestInit, timeoutMs?: number): Promise<Response>` (exported from `./util`)

- [ ] **Step 1: Add citation types to `types/data.ts`**

Insert immediately after the closing brace of the existing `Incident` interface (currently ends at line 14):

```ts
/** A single GDELT article accepted as a strict-tier match for an incident. */
export interface CitationMatch {
  title: string;
  url: string;
  source_domain: string;
  published_at: string;
}

/**
 * Cached GDELT lookup result for one incident. Present entries are
 * permanent — including had_results:false ones — so an incident already
 * keyed here is never re-queried on a later refresh run.
 */
export interface CitationEntry {
  queried_at: string; // ISO
  had_results: boolean; // true if GDELT returned >=1 raw article in the window
  match: CitationMatch | null; // null unless a result passed the strict-tier gate
}

/** citations.json shape: keyed by incident id. */
export type CitationsFile = Record<string, CitationEntry>;
```

- [ ] **Step 2: Verify the project still typechecks**

Run: `cd tracker && npx tsc --noEmit`
Expected: no output, exit code 0 (these are additive type declarations with no consumers yet, so nothing can break)

- [ ] **Step 3: Write the failing test for `fetchWithTimeout`**

Create `tracker/app/lib/fetchers/util.test.ts`:

```ts
import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchWithTimeout } from "./util";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("fetchWithTimeout", () => {
  it("resolves normally when the request completes before the timeout", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("ok", { status: 200 })),
    );
    const res = await fetchWithTimeout("https://example.com", {}, 5000);
    expect(res.status).toBe(200);
  });

  it("aborts the request once it exceeds the timeout, instead of hanging forever", async () => {
    vi.useFakeTimers();
    vi.stubGlobal(
      "fetch",
      vi.fn((_url: string, init?: RequestInit) => {
        return new Promise((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () => {
            reject(new DOMException("Aborted", "AbortError"));
          });
        });
      }),
    );

    const pending = fetchWithTimeout("https://example.com", {}, 1000);
    const assertion = expect(pending).rejects.toThrow("Aborted");
    await vi.advanceTimersByTimeAsync(1000);
    await assertion;
  });
});
```

- [ ] **Step 4: Run the test to verify it fails**

Run: `cd tracker && npx vitest run app/lib/fetchers/util.test.ts`
Expected: FAIL — `fetchWithTimeout` is not exported from `./util` (module has no such export)

- [ ] **Step 5: Implement `fetchWithTimeout`**

Append to `tracker/app/lib/fetchers/util.ts`:

```ts
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
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `cd tracker && npx vitest run app/lib/fetchers/util.test.ts`
Expected: PASS (2 tests)

- [ ] **Step 7: Commit**

```bash
git add tracker/types/data.ts tracker/app/lib/fetchers/util.ts tracker/app/lib/fetchers/util.test.ts
git commit -m "Add citation types and a shared fetch-timeout helper"
```

---

### Task 2: GDELT fetcher

**Files:**
- Create: `tracker/app/lib/fetchers/gdelt.ts`
- Create: `tracker/app/lib/fetchers/__fixtures__/gdelt-response.json`
- Test: `tracker/app/lib/fetchers/gdelt.test.ts`

**Interfaces:**
- Consumes: `fetchWithTimeout` (from Task 1, `./util`), `CitationMatch` type (from Task 1, `@/types/data`)
- Produces: `fetchGdeltCitation(incident: Incident): Promise<GdeltLookupResult>`, `findStrictMatch(articles: GdeltArticle[], incident: Incident): CitationMatch | null`, `GdeltLookupResult` type — all exported from `./gdelt`, consumed by Task 3

- [ ] **Step 1: Create the fixture**

Create `tracker/app/lib/fetchers/__fixtures__/gdelt-response.json`:

```json
{
  "articles": [
    {
      "url": "https://example-news.com/articles/houston-shooting-report",
      "title": "Police investigate shooting in Houston, Texas that left one dead",
      "seendate": "20260104T140000Z",
      "domain": "example-news.com"
    },
    {
      "url": "https://another-outlet.com/national-roundup",
      "title": "National crime roundup mentions incidents across the country",
      "seendate": "20260104T160000Z",
      "domain": "another-outlet.com"
    }
  ]
}
```

- [ ] **Step 2: Write the failing tests**

Create `tracker/app/lib/fetchers/gdelt.test.ts`:

```ts
import { readFile } from "node:fs/promises";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchGdeltCitation, findStrictMatch } from "./gdelt";
import type { Incident } from "@/types/data";

const __dirname = dirname(fileURLToPath(import.meta.url));
const FIXTURE_PATH = join(__dirname, "__fixtures__", "gdelt-response.json");

async function loadFixtureArticles() {
  const raw = JSON.parse(await readFile(FIXTURE_PATH, "utf-8"));
  return raw.articles as Array<{ url: string; title: string; domain: string; seendate: string }>;
}

function makeIncident(overrides: Partial<Incident> = {}): Incident {
  return {
    id: "gva-2026-01-04-texas-houston",
    date: "2026-01-04",
    state: "Texas",
    city: "Houston",
    killed: 1,
    injured: 4,
    source: "gva",
    ...overrides,
  };
}

function mockFetchWith(body: unknown, ok = true, status = 200): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok,
      status,
      json: async () => body,
    })),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("findStrictMatch", () => {
  it("accepts an article whose title contains both the city and the state", async () => {
    const articles = await loadFixtureArticles();
    const result = findStrictMatch(articles, makeIncident());
    expect(result).not.toBeNull();
    expect(result?.title).toBe("Police investigate shooting in Houston, Texas that left one dead");
    expect(result?.source_domain).toBe("example-news.com");
  });

  it("rejects an article that mentions neither the city nor the state", async () => {
    const articles = await loadFixtureArticles();
    const onlyGeneric = articles.filter((a) => !a.title.includes("Houston"));
    expect(findStrictMatch(onlyGeneric, makeIncident())).toBeNull();
  });

  it("rejects an article that mentions the city but not the state", async () => {
    const result = findStrictMatch(
      [
        {
          url: "https://x.com/a",
          title: "Houston sees rise in local crime",
          domain: "x.com",
          seendate: "20260104T000000Z",
        },
      ],
      makeIncident(),
    );
    expect(result).toBeNull();
  });
});

describe("fetchGdeltCitation", () => {
  it("returns had_results:false and no match when GDELT returns zero articles", async () => {
    mockFetchWith({ articles: [] });
    const result = await fetchGdeltCitation(makeIncident());
    expect(result).toEqual({ had_results: false, match: null });
  });

  it("returns had_results:true with a match when a strict match is found", async () => {
    mockFetchWith({ articles: await loadFixtureArticles() });
    const result = await fetchGdeltCitation(makeIncident());
    expect(result.had_results).toBe(true);
    expect(result.match?.title).toContain("Houston, Texas");
  });

  it("returns had_results:true with match:null when results exist but none pass the strict gate", async () => {
    const articles = await loadFixtureArticles();
    const onlyGeneric = articles.filter((a) => !a.title.includes("Houston"));
    mockFetchWith({ articles: onlyGeneric });
    const result = await fetchGdeltCitation(makeIncident());
    expect(result).toEqual({ had_results: true, match: null });
  });

  it("throws when the GDELT request fails, so the caller can skip and retry next run", async () => {
    mockFetchWith({}, false, 503);
    await expect(fetchGdeltCitation(makeIncident())).rejects.toThrow(/GDELT fetch failed: 503/);
  });
});
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd tracker && npx vitest run app/lib/fetchers/gdelt.test.ts`
Expected: FAIL — cannot find module `./gdelt`

- [ ] **Step 4: Implement the fetcher**

Create `tracker/app/lib/fetchers/gdelt.ts`:

```ts
/**
 * GDELT news-citation lookup.
 *
 * Not a tracked source: this never appears in SOURCES (sources.ts) and is
 * never imported by definitions.ts. It supplies optional, hedged citations
 * for incidents already sourced from the four canonical datasets.
 *
 * Strict-tier matching only: an article is accepted as a citation only if
 * its title contains both the incident's city and state names, within a
 * date window of incident.date -1 to +2 days. Anything looser is left to
 * the caller's search-link fallback (see app/lib/citations.ts) rather than
 * asserted as a match. See docs/plans/2026-08-06-gdelt-citations-design.md
 * for why: GDELT is unauthenticated text search with no per-incident
 * identifier, so a loose match risks a confidently-wrong citation next to
 * a real incident — worse for site credibility than showing nothing.
 */

import type { CitationMatch, Incident } from "@/types/data";
import { fetchWithTimeout } from "./util";

const DOC_API_URL = "https://api.gdeltproject.org/api/v2/doc/doc";

export interface GdeltLookupResult {
  had_results: boolean;
  match: CitationMatch | null;
}

interface GdeltArticle {
  url: string;
  title: string;
  domain: string;
  seendate: string;
}

interface GdeltResponse {
  articles?: GdeltArticle[];
}

export async function fetchGdeltCitation(incident: Incident): Promise<GdeltLookupResult> {
  const query = `"shooting" "${incident.city}" "${incident.state}"`;
  const params = new URLSearchParams({
    query,
    mode: "artlist",
    format: "json",
    sourcecountry: "US",
    startdatetime: `${shiftDate(incident.date, -1)}000000`,
    enddatetime: `${shiftDate(incident.date, 2)}000000`,
    maxrecords: "10",
  });

  const res = await fetchWithTimeout(`${DOC_API_URL}?${params.toString()}`, {}, 10_000);
  if (!res.ok) throw new Error(`GDELT fetch failed: ${res.status}`);

  const body = (await res.json()) as GdeltResponse;
  const articles = body.articles ?? [];
  if (articles.length === 0) return { had_results: false, match: null };

  return { had_results: true, match: findStrictMatch(articles, incident) };
}

export function findStrictMatch(
  articles: GdeltArticle[],
  incident: Incident,
): CitationMatch | null {
  const cityLower = incident.city.toLowerCase();
  const stateLower = incident.state.toLowerCase();
  const article = articles.find((a) => {
    const haystack = a.title.toLowerCase();
    return haystack.includes(cityLower) && haystack.includes(stateLower);
  });
  if (!article) return null;
  return {
    title: article.title,
    url: article.url,
    source_domain: article.domain,
    published_at: article.seendate,
  };
}

function shiftDate(iso: string, days: number): string {
  const d = new Date(iso);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10).replace(/-/g, "");
}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd tracker && npx vitest run app/lib/fetchers/gdelt.test.ts`
Expected: PASS (7 tests)

- [ ] **Step 6: Typecheck**

Run: `cd tracker && npx tsc --noEmit`
Expected: no output, exit code 0

- [ ] **Step 7: Commit**

```bash
git add tracker/app/lib/fetchers/gdelt.ts tracker/app/lib/fetchers/gdelt.test.ts tracker/app/lib/fetchers/__fixtures__/gdelt-response.json
git commit -m "Add GDELT strict-tier citation fetcher"
```

---

### Task 3: Citation display copy and caching logic

**Files:**
- Create: `tracker/app/lib/citations.ts`
- Test: `tracker/app/lib/citations.test.ts`

**Interfaces:**
- Consumes: `GdeltLookupResult` type (from Task 2, `./fetchers/gdelt`), `CitationEntry`/`CitationsFile` types (from Task 1, `@/types/data`)
- Produces: `footnoteForCitation(incident: Incident, entry: CitationEntry | undefined): CitationFootnote | null`, `searchLinkFor(incident: Incident): string`, `mergeCitations(existing: CitationsFile, incidents: Incident[], lookup: (incident: Incident) => Promise<GdeltLookupResult>): Promise<CitationsFile>`, `CitationFootnote` type — all exported from `./citations`, consumed by Task 4 (`mergeCitations`) and Task 5 (`footnoteForCitation`)

- [ ] **Step 1: Write the failing tests**

Create `tracker/app/lib/citations.test.ts`:

```ts
import { describe, expect, it, vi } from "vitest";

import { footnoteForCitation, mergeCitations, searchLinkFor } from "./citations";
import type { CitationEntry, CitationsFile, Incident } from "@/types/data";

function makeIncident(overrides: Partial<Incident> = {}): Incident {
  return {
    id: "gva-2026-01-04-texas-houston",
    date: "2026-01-04",
    state: "Texas",
    city: "Houston",
    killed: 1,
    injured: 4,
    source: "gva",
    ...overrides,
  };
}

describe("footnoteForCitation", () => {
  it("returns null when there is no citations entry for this incident", () => {
    expect(footnoteForCitation(makeIncident(), undefined)).toBeNull();
  });

  it("returns null when GDELT returned zero results (absent renders as absent)", () => {
    const entry: CitationEntry = { queried_at: "2026-01-05T00:00:00Z", had_results: false, match: null };
    expect(footnoteForCitation(makeIncident(), entry)).toBeNull();
  });

  it("returns a hedged search-link footnote when results existed but none passed the strict gate", () => {
    const entry: CitationEntry = { queried_at: "2026-01-05T00:00:00Z", had_results: true, match: null };
    const footnote = footnoteForCitation(makeIncident(), entry);
    expect(footnote?.kind).toBe("search-link");
    expect(footnote?.text).toBe("Search local coverage of this incident and date");
    expect(footnote?.url).toBe(searchLinkFor(makeIncident()));
  });

  it("returns a hedged match footnote, never implying confirmation, when a strict match exists", () => {
    const entry: CitationEntry = {
      queried_at: "2026-01-05T00:00:00Z",
      had_results: true,
      match: {
        title: "Police investigate shooting in Houston, Texas",
        url: "https://example-news.com/a",
        source_domain: "example-news.com",
        published_at: "20260104T140000Z",
      },
    };
    const footnote = footnoteForCitation(makeIncident(), entry);
    expect(footnote?.kind).toBe("match");
    expect(footnote?.text).toContain("unconfirmed");
    expect(footnote?.text).toContain("Police investigate shooting in Houston, Texas");
    expect(footnote?.url).toBe("https://example-news.com/a");
  });
});

describe("searchLinkFor", () => {
  it("builds a Google News search URL from the incident's city, state, and date", () => {
    const url = searchLinkFor(makeIncident());
    expect(url).toBe(
      "https://news.google.com/search?q=" + encodeURIComponent("shooting Houston Texas 2026-01-04"),
    );
  });
});

describe("mergeCitations", () => {
  it("queries and adds an entry for an incident not already in the citations file", async () => {
    const lookup = vi.fn().mockResolvedValue({ had_results: false, match: null });
    const result = await mergeCitations({}, [makeIncident()], lookup);
    expect(lookup).toHaveBeenCalledTimes(1);
    expect(result[makeIncident().id]).toMatchObject({ had_results: false, match: null });
    expect(result[makeIncident().id].queried_at).toBeTruthy();
  });

  it("does not re-query an incident that already has an entry, even a zero-result one", async () => {
    const existing: CitationsFile = {
      [makeIncident().id]: { queried_at: "2026-01-01T00:00:00Z", had_results: false, match: null },
    };
    const lookup = vi.fn().mockResolvedValue({ had_results: true, match: null });
    const result = await mergeCitations(existing, [makeIncident()], lookup);
    expect(lookup).not.toHaveBeenCalled();
    expect(result[makeIncident().id]).toEqual(existing[makeIncident().id]);
  });

  it("skips an incident without writing an entry when the lookup throws, so it is retried next run", async () => {
    const lookup = vi.fn().mockRejectedValue(new Error("GDELT fetch failed: 503"));
    const result = await mergeCitations({}, [makeIncident()], lookup);
    expect(result[makeIncident().id]).toBeUndefined();
  });

  it("processes multiple incidents independently, mixing new and already-cached", async () => {
    const cached = makeIncident({ id: "cached-1" });
    const fresh = makeIncident({ id: "fresh-1", city: "Fresno", state: "California" });
    const existing: CitationsFile = {
      "cached-1": { queried_at: "2026-01-01T00:00:00Z", had_results: false, match: null },
    };
    const lookup = vi.fn().mockResolvedValue({ had_results: false, match: null });
    const result = await mergeCitations(existing, [cached, fresh], lookup);
    expect(lookup).toHaveBeenCalledTimes(1);
    expect(lookup).toHaveBeenCalledWith(fresh);
    expect(Object.keys(result)).toEqual(["cached-1", "fresh-1"]);
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd tracker && npx vitest run app/lib/citations.test.ts`
Expected: FAIL — cannot find module `./citations`

- [ ] **Step 3: Implement**

Create `tracker/app/lib/citations.ts`:

```ts
/**
 * Display and caching logic for GDELT news-citation enrichment. Never
 * imported by definitions.ts — this is optional, hedged evidence attached
 * to an incident, not part of the four sources' yes/no/unknown logic.
 */

import type { CitationEntry, CitationsFile, Incident } from "@/types/data";
import type { GdeltLookupResult } from "./fetchers/gdelt";

export interface CitationFootnote {
  kind: "match" | "search-link";
  text: string;
  url: string;
}

export function footnoteForCitation(
  incident: Incident,
  entry: CitationEntry | undefined,
): CitationFootnote | null {
  if (!entry) return null;

  if (entry.match) {
    return {
      kind: "match",
      text: `Coverage possibly related to this incident (unconfirmed): "${entry.match.title}" — ${entry.match.source_domain}.`,
      url: entry.match.url,
    };
  }

  if (!entry.had_results) return null;

  return {
    kind: "search-link",
    text: "Search local coverage of this incident and date",
    url: searchLinkFor(incident),
  };
}

export function searchLinkFor(incident: Incident): string {
  const query = `shooting ${incident.city} ${incident.state} ${incident.date}`;
  return `https://news.google.com/search?q=${encodeURIComponent(query)}`;
}

/**
 * Merge GDELT lookups for any incident not already present in `existing`.
 * Entries are permanent once written — even had_results:false ones — so
 * an id already present is never re-queried. A lookup failure for one
 * incident is logged and skipped (no entry written) rather than aborting
 * the whole merge, so it's simply retried on the next run.
 */
export async function mergeCitations(
  existing: CitationsFile,
  incidents: Incident[],
  lookup: (incident: Incident) => Promise<GdeltLookupResult>,
): Promise<CitationsFile> {
  const citations: CitationsFile = { ...existing };

  for (const incident of incidents) {
    if (citations[incident.id]) continue;
    try {
      const result = await lookup(incident);
      citations[incident.id] = {
        queried_at: new Date().toISOString(),
        had_results: result.had_results,
        match: result.match,
      };
    } catch (err) {
      console.warn(`  GDELT lookup failed for ${incident.id}: ${err}`);
    }
  }

  return citations;
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd tracker && npx vitest run app/lib/citations.test.ts`
Expected: PASS (9 tests)

- [ ] **Step 5: Typecheck**

Run: `cd tracker && npx tsc --noEmit`
Expected: no output, exit code 0

- [ ] **Step 6: Commit**

```bash
git add tracker/app/lib/citations.ts tracker/app/lib/citations.test.ts
git commit -m "Add citation footnote copy and merge/caching logic"
```

---

### Task 4: Wire into the daily refresh script

**Files:**
- Modify: `tracker/scripts/refresh_data.ts`

**Interfaces:**
- Consumes: `mergeCitations` (Task 3, `../app/lib/citations`), `fetchGdeltCitation` (Task 2, `../app/lib/fetchers/gdelt`), `CitationsFile` type (Task 1, `../types/data`)
- Produces: `tracker/public/data/citations.json` on disk when the script runs

- [ ] **Step 1: Add the new imports**

In `tracker/scripts/refresh_data.ts`, the existing import block (lines 14–26) is:

```ts
import type {
  Incident,
  ModelResults,
  SourceCounts,
  StateStats,
  TrackerSnapshot,
} from "../types/data";
import { fetchGVA } from "../app/lib/fetchers/gva";
import { fetchMotherJones } from "../app/lib/fetchers/mother_jones";
import { fetchStanfordMSA } from "../app/lib/fetchers/stanford_msa";
import { fetchViolenceProject } from "../app/lib/fetchers/violence_project";
import { SOURCES, type SourceId } from "../app/lib/sources";
import { STATE_POPULATION, STATE_TO_CODE } from "../app/lib/states";
```

Replace it with:

```ts
import type {
  CitationsFile,
  Incident,
  ModelResults,
  SourceCounts,
  StateStats,
  TrackerSnapshot,
} from "../types/data";
import { mergeCitations } from "../app/lib/citations";
import { fetchGdeltCitation } from "../app/lib/fetchers/gdelt";
import { fetchGVA } from "../app/lib/fetchers/gva";
import { fetchMotherJones } from "../app/lib/fetchers/mother_jones";
import { fetchStanfordMSA } from "../app/lib/fetchers/stanford_msa";
import { fetchViolenceProject } from "../app/lib/fetchers/violence_project";
import { SOURCES, type SourceId } from "../app/lib/sources";
import { STATE_POPULATION, STATE_TO_CODE } from "../app/lib/states";
```

- [ ] **Step 2: Add a `loadCitations` helper and wire it into `main()`**

The existing `main()` function is:

```ts
async function main(): Promise<void> {
  await mkdir(DATA_DIR, { recursive: true });

  const { incidents, staleSources } = await fetchAllSources();
  incidents.sort((a, b) => (a.date > b.date ? -1 : 1));

  const model = await loadModelResults();
  const snapshot: TrackerSnapshot = {
    generated_at: new Date().toISOString(),
    window_days: WINDOW_DAYS,
    totals_by_source: computeTotalsBySource(incidents, staleSources, WINDOW_DAYS),
    states: computeStateStats(incidents, WINDOW_DAYS),
    recent_incidents: incidents.slice(0, 100),
    model,
  };

  await writeFile(join(DATA_DIR, "snapshot.json"), JSON.stringify(snapshot, null, 2));
  await writeFile(join(DATA_DIR, "incidents.json"), JSON.stringify(incidents, null, 2));

  const staleList = [...staleSources];
  if (staleList.length > 0) {
    console.log(`Stale sources this run: ${staleList.join(", ")}`);
  }
  console.log(
    `Wrote snapshot with ${incidents.length} total incidents across ${
      Object.keys(SOURCES).length
    } sources`,
  );
}
```

Replace it with:

```ts
async function loadCitations(): Promise<CitationsFile> {
  try {
    return JSON.parse(await readFile(join(DATA_DIR, "citations.json"), "utf-8"));
  } catch {
    return {};
  }
}

async function main(): Promise<void> {
  await mkdir(DATA_DIR, { recursive: true });

  const { incidents, staleSources } = await fetchAllSources();
  incidents.sort((a, b) => (a.date > b.date ? -1 : 1));

  const model = await loadModelResults();
  const snapshot: TrackerSnapshot = {
    generated_at: new Date().toISOString(),
    window_days: WINDOW_DAYS,
    totals_by_source: computeTotalsBySource(incidents, staleSources, WINDOW_DAYS),
    states: computeStateStats(incidents, WINDOW_DAYS),
    recent_incidents: incidents.slice(0, 100),
    model,
  };

  const existingCitations = await loadCitations();
  const citations = await mergeCitations(existingCitations, incidents, fetchGdeltCitation);
  const newCitationCount = Object.keys(citations).length - Object.keys(existingCitations).length;

  await writeFile(join(DATA_DIR, "snapshot.json"), JSON.stringify(snapshot, null, 2));
  await writeFile(join(DATA_DIR, "incidents.json"), JSON.stringify(incidents, null, 2));
  await writeFile(join(DATA_DIR, "citations.json"), JSON.stringify(citations, null, 2));

  const staleList = [...staleSources];
  if (staleList.length > 0) {
    console.log(`Stale sources this run: ${staleList.join(", ")}`);
  }
  console.log(`Looked up ${newCitationCount} new incident(s) for GDELT citations`);
  console.log(
    `Wrote snapshot with ${incidents.length} total incidents across ${
      Object.keys(SOURCES).length
    } sources`,
  );
}
```

Note: a GDELT lookup failure for one incident is caught inside `mergeCitations` itself (Task 3) and never propagates here — so a bad GDELT run cannot fail this script or mark `gva`/`mother_jones`/`stanford_msa`/`violence_project` stale, matching the constraint stated at the top of this plan.

- [ ] **Step 3: Typecheck**

Run: `cd tracker && npx tsc --noEmit`
Expected: no output, exit code 0

- [ ] **Step 4: Run the full test suite**

Run: `cd tracker && npx vitest run`
Expected: PASS, all suites (gva, definitions, util, gdelt, citations)

- [ ] **Step 5: Live end-to-end check (network required, informational — not a merge gate)**

Run: `cd tracker && npm run refresh-data`
Expected: existing per-source log lines as before, plus a new `Looked up N new incident(s) for GDELT citations` line, and `tracker/public/data/citations.json` created/updated on disk. This step hits the real GDELT API and is non-deterministic (depends on current incidents and GDELT's live index), so don't block the task on its exact output — just confirm it runs without throwing and produces a well-formed `citations.json`.

- [ ] **Step 6: Commit**

```bash
git add tracker/scripts/refresh_data.ts
git commit -m "Run GDELT citation lookups in the daily refresh script"
```

---

### Task 5: Load citations and render the `†` footnote

**Files:**
- Modify: `tracker/app/lib/data.ts`
- Modify: `tracker/app/components/IncidentMatrix.tsx`
- Modify: `tracker/app/page.tsx`

**Interfaces:**
- Consumes: `footnoteForCitation` (Task 3, `./lib/citations`), `CitationsFile` type (Task 1, `@/types/data`)
- Produces: `loadCitations(): Promise<CitationsFile>` (exported from `app/lib/data.ts`)

- [ ] **Step 1: Add `loadCitations` to `app/lib/data.ts`**

Current file:

```ts
import { readFile } from "node:fs/promises";
import { join } from "node:path";

import type { Incident, TrackerSnapshot } from "@/types/data";

const DATA_DIR = join(process.cwd(), "public", "data");

export async function loadSnapshot(): Promise<TrackerSnapshot | null> {
  return readJson<TrackerSnapshot>(join(DATA_DIR, "snapshot.json"));
}

export async function loadIncidents(): Promise<Incident[]> {
  return (await readJson<Incident[]>(join(DATA_DIR, "incidents.json"))) ?? [];
}

async function readJson<T>(path: string): Promise<T | null> {
  try {
    return JSON.parse(await readFile(path, "utf-8")) as T;
  } catch (err) {
    if ((err as NodeJS.ErrnoException).code === "ENOENT") return null;
    throw err;
  }
}
```

Replace it with:

```ts
import { readFile } from "node:fs/promises";
import { join } from "node:path";

import type { CitationsFile, Incident, TrackerSnapshot } from "@/types/data";

const DATA_DIR = join(process.cwd(), "public", "data");

export async function loadSnapshot(): Promise<TrackerSnapshot | null> {
  return readJson<TrackerSnapshot>(join(DATA_DIR, "snapshot.json"));
}

export async function loadIncidents(): Promise<Incident[]> {
  return (await readJson<Incident[]>(join(DATA_DIR, "incidents.json"))) ?? [];
}

/** Missing file (no refresh run has produced citations yet) resolves to {}, not null — this feature is additive and never blocks rendering the way a missing snapshot does. */
export async function loadCitations(): Promise<CitationsFile> {
  return (await readJson<CitationsFile>(join(DATA_DIR, "citations.json"))) ?? {};
}

async function readJson<T>(path: string): Promise<T | null> {
  try {
    return JSON.parse(await readFile(path, "utf-8")) as T;
  } catch (err) {
    if ((err as NodeJS.ErrnoException).code === "ENOENT") return null;
    throw err;
  }
}
```

- [ ] **Step 2: Add the citation marker prop to `IncidentMatrix`**

Current file:

```tsx
import { format } from "date-fns";

import { evaluateAll, MATCH_GLYPH, MATCH_LABEL } from "../lib/definitions";
import type { Incident } from "@/types/data";

const MARK_COLOR = { yes: "#d8d5cf", unknown: "#8b8880", no: "#4a4945" } as const;

export default function IncidentMatrix({ incidents }: { incidents: Incident[] }) {
  return (
    <div className="matrix">
      <div className="head">DATE</div>
      <div className="head">LOCATION</div>
      <div className="head right">KILL/INJ</div>
      <div className="head center">GVA</div>
      <div className="head center">MJ</div>

      {incidents.map((incident) => {
        const match = evaluateAll(incident);
        return (
          <Row key={incident.id} incident={incident} gva={match.gva} mj={match.mother_jones} />
        );
      })}
    </div>
  );
}

function Row({
  incident,
  gva,
  mj,
}: {
  incident: Incident;
  gva: keyof typeof MARK_COLOR;
  mj: keyof typeof MARK_COLOR;
}) {
  return (
    <>
      <div className="cell num" style={{ color: "#8b8880" }}>
        {format(new Date(incident.date), "d MMM")}
      </div>
      <div className="cell place">
        {incident.city}, {incident.state}
      </div>
      <div className="cell num right" style={{ color: "#d8d5cf" }}>
        {incident.killed}/{incident.injured}
      </div>
      <div className="cell mark" style={{ color: MARK_COLOR[gva] }} title={MATCH_LABEL[gva]}>
        {MATCH_GLYPH[gva]}
      </div>
      <div className="cell mark" style={{ color: MARK_COLOR[mj] }} title={MATCH_LABEL[mj]}>
        {MATCH_GLYPH[mj]}
      </div>
    </>
  );
}
```

Replace it with:

```tsx
import { format } from "date-fns";

import { evaluateAll, MATCH_GLYPH, MATCH_LABEL } from "../lib/definitions";
import type { Incident } from "@/types/data";

const MARK_COLOR = { yes: "#d8d5cf", unknown: "#8b8880", no: "#4a4945" } as const;

export default function IncidentMatrix({
  incidents,
  citationMarkers,
}: {
  incidents: Incident[];
  /** incident id -> marker text (e.g. "†1"), only for incidents with a citation footnote */
  citationMarkers?: Map<string, string>;
}) {
  return (
    <div className="matrix">
      <div className="head">DATE</div>
      <div className="head">LOCATION</div>
      <div className="head right">KILL/INJ</div>
      <div className="head center">GVA</div>
      <div className="head center">MJ</div>

      {incidents.map((incident) => {
        const match = evaluateAll(incident);
        return (
          <Row
            key={incident.id}
            incident={incident}
            gva={match.gva}
            mj={match.mother_jones}
            citationMark={citationMarkers?.get(incident.id)}
          />
        );
      })}
    </div>
  );
}

function Row({
  incident,
  gva,
  mj,
  citationMark,
}: {
  incident: Incident;
  gva: keyof typeof MARK_COLOR;
  mj: keyof typeof MARK_COLOR;
  citationMark?: string;
}) {
  return (
    <>
      <div className="cell num" style={{ color: "#8b8880" }}>
        {format(new Date(incident.date), "d MMM")}
      </div>
      <div className="cell place">
        {incident.city}, {incident.state}
        {citationMark && <sup className="citation-mark">{citationMark}</sup>}
      </div>
      <div className="cell num right" style={{ color: "#d8d5cf" }}>
        {incident.killed}/{incident.injured}
      </div>
      <div className="cell mark" style={{ color: MARK_COLOR[gva] }} title={MATCH_LABEL[gva]}>
        {MATCH_GLYPH[gva]}
      </div>
      <div className="cell mark" style={{ color: MARK_COLOR[mj] }} title={MATCH_LABEL[mj]}>
        {MATCH_GLYPH[mj]}
      </div>
    </>
  );
}
```

- [ ] **Step 3: Wire citations into `page.tsx`**

At the top of `tracker/app/page.tsx`, the import block is:

```tsx
import { format, formatDistanceToNow } from "date-fns";

import AwaitingData from "./components/AwaitingData";
import IncidentMatrix from "./components/IncidentMatrix";
import Masthead from "./components/Masthead";
import StateTileGrid from "./components/StateTileGrid";
import { loadSnapshot } from "./lib/data";
import { SOURCES, type SourceId } from "./lib/sources";
import type { SourceCounts } from "@/types/data";
```

Replace it with:

```tsx
import { format, formatDistanceToNow } from "date-fns";

import AwaitingData from "./components/AwaitingData";
import IncidentMatrix from "./components/IncidentMatrix";
import Masthead from "./components/Masthead";
import StateTileGrid from "./components/StateTileGrid";
import { footnoteForCitation } from "./lib/citations";
import { loadCitations, loadSnapshot } from "./lib/data";
import { SOURCES, type SourceId } from "./lib/sources";
import type { SourceCounts } from "@/types/data";
```

The start of the `Dashboard` function is:

```tsx
export default async function Dashboard() {
  const snap = await loadSnapshot();
  if (!snap) return <AwaitingData current="/" />;

  const generated = new Date(snap.generated_at);
```

Replace it with:

```tsx
export default async function Dashboard() {
  const snap = await loadSnapshot();
  if (!snap) return <AwaitingData current="/" />;
  const citations = await loadCitations();

  const generated = new Date(snap.generated_at);
```

Immediately before the `return (` that starts the JSX (right after the existing `notes`/`noteIndex` loop), add the citation-notes computation. The existing code just before `return (` is:

```tsx
  const notes: string[] = [];
  const noteIndex = new Map<SourceId, number>();
  for (const id of ORDER) {
    const note = footnoteFor(id, bySource.get(id));
    if (note) {
      notes.push(note);
      noteIndex.set(id, notes.length);
    }
  }

  return (
```

Replace it with:

```tsx
  const notes: string[] = [];
  const noteIndex = new Map<SourceId, number>();
  for (const id of ORDER) {
    const note = footnoteFor(id, bySource.get(id));
    if (note) {
      notes.push(note);
      noteIndex.set(id, notes.length);
    }
  }

  const recentIncidents = snap.recent_incidents.slice(0, 8);
  const citationNotes: string[] = [];
  const citationMarkers = new Map<string, string>();
  for (const incident of recentIncidents) {
    const footnote = footnoteForCitation(incident, citations[incident.id]);
    if (!footnote) continue;
    citationNotes.push(`${footnote.text} ${footnote.url}`);
    citationMarkers.set(incident.id, `†${citationNotes.length}`);
  }

  return (
```

The "Table 2" block currently is:

```tsx
        <div>
          <div className="table-title">Table 2 &mdash; Most recent incidents</div>
          <p className="table-note">
            Marked under every dataset whose definition the incident meets. A filled dot means it
            qualifies, an open dot means it clears the casualty threshold but the contextual
            condition is unrecorded, an em dash means it does not qualify.
          </p>
          {snap.recent_incidents.length > 0 ? (
            <IncidentMatrix incidents={snap.recent_incidents.slice(0, 8)} />
          ) : (
            <p className="table-note">No incidents recorded in the current window.</p>
          )}
        </div>
```

Replace it with (using the `recentIncidents` variable defined above, instead of re-slicing, so the citation markers always correspond exactly to the incidents actually rendered):

```tsx
        <div>
          <div className="table-title">Table 2 &mdash; Most recent incidents</div>
          <p className="table-note">
            Marked under every dataset whose definition the incident meets. A filled dot means it
            qualifies, an open dot means it clears the casualty threshold but the contextual
            condition is unrecorded, an em dash means it does not qualify.
          </p>
          {recentIncidents.length > 0 ? (
            <IncidentMatrix incidents={recentIncidents} citationMarkers={citationMarkers} />
          ) : (
            <p className="table-note">No incidents recorded in the current window.</p>
          )}
        </div>
```

The existing footnotes footer is:

```tsx
      {notes.length > 0 && (
        <footer className="footnotes">
          {notes.map((note, i) => (
            <div key={i}>
              <sup>{i + 1}</sup> {note}
            </div>
          ))}
        </footer>
      )}
```

Add a second, visually separate footer immediately after it (a `†`-marked block is never merged into the numbered list above, so a reader can't mistake it for a fifth source caveat):

```tsx
      {notes.length > 0 && (
        <footer className="footnotes">
          {notes.map((note, i) => (
            <div key={i}>
              <sup>{i + 1}</sup> {note}
            </div>
          ))}
        </footer>
      )}

      {citationNotes.length > 0 && (
        <footer className="footnotes citation-footnotes">
          <p className="table-note">Related coverage, unconfirmed:</p>
          {citationNotes.map((note, i) => (
            <div key={i}>
              <sup>{"†"}{i + 1}</sup> {note}
            </div>
          ))}
        </footer>
      )}
```

- [ ] **Step 4: Typecheck**

Run: `cd tracker && npx tsc --noEmit`
Expected: no output, exit code 0

- [ ] **Step 5: Manual visual check with a deterministic fixture (no network needed)**

Temporarily write a one-entry `tracker/public/data/citations.json` keyed to a real incident id currently in `tracker/public/data/incidents.json` (pick any id from that file), e.g.:

```json
{
  "<paste-a-real-incident-id-here>": {
    "queried_at": "2026-01-05T00:00:00Z",
    "had_results": true,
    "match": {
      "title": "Example headline mentioning the city and state",
      "url": "https://example.com/article",
      "source_domain": "example.com",
      "published_at": "20260104T140000Z"
    }
  }
}
```

Run: `cd tracker && npm run dev`, open `http://localhost:3000`, and confirm:
- The matching row in Table 2 shows a `†1` superscript next to its city/state.
- The bottom of the page shows a "Related coverage, unconfirmed:" block with the hedged copy and a working link.
- Every other row (no citation entry) shows no marker at all.

Revert `citations.json` back to whatever it contained before this manual check (or delete it, since Task 4's live run will regenerate it).

- [ ] **Step 6: Full build**

Run: `cd tracker && npx next build`
Expected: `✓ Compiled successfully`, 7/7 static routes generated (same as the rest of the site — this feature adds no new routes)

- [ ] **Step 7: Full test suite one more time**

Run: `cd tracker && npx vitest run`
Expected: PASS, all suites

- [ ] **Step 8: Commit**

```bash
git add tracker/app/lib/data.ts tracker/app/components/IncidentMatrix.tsx tracker/app/page.tsx
git commit -m "Render GDELT citation footnotes in the incident matrix"
```

---

## Self-Review Notes

- **Spec coverage:** matching (Task 2), data model + permanent caching (Tasks 1, 3, 4), pipeline integration + per-incident error isolation + timeout (Tasks 1, 2, 4), UI + hedged copy + `†` marker + absent-renders-as-absent (Task 5), testing (a test file per task, pure-function only) — all covered.
- **Type consistency checked:** `GdeltLookupResult` (Task 2) is the exact type `mergeCitations`'s `lookup` parameter expects (Task 3); `CitationEntry`/`CitationsFile`/`CitationMatch` (Task 1) are used with identical field names (`queried_at`, `had_results`, `match`, `title`, `url`, `source_domain`, `published_at`) everywhere they appear across Tasks 2–5; `footnoteForCitation`'s signature `(incident, entry)` matches how Task 5 calls it (`footnoteForCitation(incident, citations[incident.id])`, where `citations[incident.id]` is `CitationEntry | undefined` — matching the parameter type exactly).
- **No placeholders:** every step has complete, runnable code — no "add tests for the above," no "TBD."
