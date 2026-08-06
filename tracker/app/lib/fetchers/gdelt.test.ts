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
