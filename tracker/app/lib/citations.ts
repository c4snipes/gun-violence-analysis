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

  // Nothing was found at all — render nothing, matching the site's rule that
  // absent data reads as absent rather than as a weak or empty result.
  if (!entry.had_results) return null;

  // Coverage exists but none of it cleared the strict-match bar. Hand the
  // reader a search rather than asserting any particular article is about
  // this incident.
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
 * Cap on how many *new* GDELT lookups one run performs.
 *
 * Lookups are sequential and network-bound, so an uncapped run over a full
 * backlog is unbounded in wall-clock time — the first run against a
 * populated tracker has hundreds of uncached incidents and will not finish
 * inside a CI job. Because cache entries are permanent, a capped run simply
 * backfills a little further each day. Incidents arrive sorted newest-first,
 * so the cap always spends its budget on the incidents most likely to be
 * displayed.
 */
/**
 * Give every incident a genuinely unique id, suffixing any duplicate.
 *
 * Source ids are not reliably unique: GVA ids are built from date+state+city,
 * which collides when one city has two incidents on one day, and the Stanford
 * CSV reuses CaseIDs (the committed data contains two such collisions today).
 * Anything keyed by incident id inherits that collision — the citation cache
 * would attach one incident's article to a different incident permanently,
 * the dagger markers would desync from their footnotes, and React would see
 * duplicate keys in the incident table.
 */
export function ensureUniqueIds(incidents: Incident[]): Incident[] {
  const seen = new Map<string, number>();
  return incidents.map((incident) => {
    const count = seen.get(incident.id) ?? 0;
    seen.set(incident.id, count + 1);
    return count === 0 ? incident : { ...incident, id: `${incident.id}-${count + 1}` };
  });
}

export const MAX_NEW_LOOKUPS_PER_RUN = 10;

/**
 * Pause between consecutive GDELT requests.
 *
 * GDELT's public DOC API is unauthenticated and rate-limited. Its own 429
 * body states the rule: "Please limit requests to one every 5 seconds."
 * This is set to double that minimum, because exceeding it puts the caller
 * in a penalty window where even correctly-spaced requests keep 429ing.
 * Combined with the permanent cache, a slow-but-successful run beats a fast
 * run that 429s on most of its lookups.
 */
export const LOOKUP_DELAY_MS = 10_000;

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Merge GDELT lookups for any incident not already present in `existing`.
 * Entries are permanent once written — even had_results:false ones — so
 * an id already present is never re-queried. A lookup failure for one
 * incident is logged and skipped (no entry written) rather than aborting
 * the whole merge, so it's simply retried on the next run.
 *
 * At most `maxNewLookups` new incidents are queried per call; the rest are
 * left uncached for a later run and the shortfall is logged rather than
 * passing silently.
 */
export async function mergeCitations(
  existing: CitationsFile,
  incidents: Incident[],
  lookup: (incident: Incident) => Promise<GdeltLookupResult>,
  maxNewLookups: number = MAX_NEW_LOOKUPS_PER_RUN,
  delayMs: number = LOOKUP_DELAY_MS,
): Promise<CitationsFile> {
  const citations: CitationsFile = { ...existing };
  let budget = maxNewLookups;
  let deferred = 0;
  let queried = 0;

  for (const incident of incidents) {
    if (citations[incident.id]) continue;
    if (budget <= 0) {
      deferred += 1;
      continue;
    }
    budget -= 1;
    if (queried > 0 && delayMs > 0) await sleep(delayMs);
    queried += 1;
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

  if (deferred > 0) {
    console.log(
      `  ${deferred} uncached incident(s) deferred past this run's ${maxNewLookups}-lookup cap`,
    );
  }

  return citations;
}
