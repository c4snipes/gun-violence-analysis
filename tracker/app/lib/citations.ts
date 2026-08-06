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
