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

  // 25s: GDELT's public endpoint is frequently slow to first byte, and a
  // timeout that fires before it answers just burns the run's lookup budget
  // without producing a result.
  const res = await fetchWithTimeout(`${DOC_API_URL}?${params.toString()}`, {}, 25_000);
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
