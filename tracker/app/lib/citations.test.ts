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
    const entry: CitationEntry = {
      queried_at: "2026-01-05T00:00:00Z",
      had_results: false,
      match: null,
    };
    expect(footnoteForCitation(makeIncident(), entry)).toBeNull();
  });

  it("returns a hedged search-link footnote when results existed but none passed the strict gate", () => {
    const entry: CitationEntry = {
      queried_at: "2026-01-05T00:00:00Z",
      had_results: true,
      match: null,
    };
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
    const result = await mergeCitations({}, [makeIncident()], lookup, 25, 0);
    expect(lookup).toHaveBeenCalledTimes(1);
    expect(result[makeIncident().id]).toMatchObject({ had_results: false, match: null });
    expect(result[makeIncident().id].queried_at).toBeTruthy();
  });

  it("does not re-query an incident that already has an entry, even a zero-result one", async () => {
    const existing: CitationsFile = {
      [makeIncident().id]: { queried_at: "2026-01-01T00:00:00Z", had_results: false, match: null },
    };
    const lookup = vi.fn().mockResolvedValue({ had_results: true, match: null });
    const result = await mergeCitations(existing, [makeIncident()], lookup, 25, 0);
    expect(lookup).not.toHaveBeenCalled();
    expect(result[makeIncident().id]).toEqual(existing[makeIncident().id]);
  });

  it("skips an incident without writing an entry when the lookup throws, so it is retried next run", async () => {
    const lookup = vi.fn().mockRejectedValue(new Error("GDELT fetch failed: 503"));
    const result = await mergeCitations({}, [makeIncident()], lookup, 25, 0);
    expect(result[makeIncident().id]).toBeUndefined();
  });

  it("stops querying once the per-run cap is reached, leaving the rest uncached for a later run", async () => {
    const incidents = Array.from({ length: 5 }, (_, i) =>
      makeIncident({ id: `incident-${i}` }),
    );
    const lookup = vi.fn().mockResolvedValue({ had_results: false, match: null });
    const result = await mergeCitations({}, incidents, lookup, 2, 0);
    expect(lookup).toHaveBeenCalledTimes(2);
    // Budget is spent on the first two (incidents arrive newest-first).
    expect(Object.keys(result)).toEqual(["incident-0", "incident-1"]);
  });

  it("does not spend cap budget on incidents that are already cached", async () => {
    const incidents = Array.from({ length: 4 }, (_, i) =>
      makeIncident({ id: `incident-${i}` }),
    );
    const existing: CitationsFile = {
      "incident-0": { queried_at: "2026-01-01T00:00:00Z", had_results: false, match: null },
      "incident-1": { queried_at: "2026-01-01T00:00:00Z", had_results: false, match: null },
    };
    const lookup = vi.fn().mockResolvedValue({ had_results: false, match: null });
    const result = await mergeCitations(existing, incidents, lookup, 2, 0);
    expect(lookup).toHaveBeenCalledTimes(2);
    expect(Object.keys(result).sort()).toEqual([
      "incident-0",
      "incident-1",
      "incident-2",
      "incident-3",
    ]);
  });

  it("processes multiple incidents independently, mixing new and already-cached", async () => {
    const cached = makeIncident({ id: "cached-1" });
    const fresh = makeIncident({ id: "fresh-1", city: "Fresno", state: "California" });
    const existing: CitationsFile = {
      "cached-1": { queried_at: "2026-01-01T00:00:00Z", had_results: false, match: null },
    };
    const lookup = vi.fn().mockResolvedValue({ had_results: false, match: null });
    const result = await mergeCitations(existing, [cached, fresh], lookup, 25, 0);
    expect(lookup).toHaveBeenCalledTimes(1);
    expect(lookup).toHaveBeenCalledWith(fresh);
    expect(Object.keys(result)).toEqual(["cached-1", "fresh-1"]);
  });
});
