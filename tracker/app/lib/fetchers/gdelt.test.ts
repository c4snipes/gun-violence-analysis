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

  it("rejects a city name that appears only inside a longer word", () => {
    // Ada, Oklahoma vs "Canada"; Kent, Ohio vs "Kentucky"; Rome, Georgia vs
    // "Jerome". Plain substring matching accepts all three.
    const cases = [
      { city: "Ada", state: "Oklahoma", title: "Canada announces border policy amid Oklahoma gun talks" },
      { city: "Kent", state: "Ohio", title: "Kentucky and Ohio police discuss a shooting response plan" },
      { city: "Rome", state: "Georgia", title: "Jerome and Georgia officials review a shooting report" },
    ];
    for (const { city, state, title } of cases) {
      const result = findStrictMatch(
        [{ url: "https://x.com/a", title, domain: "x.com", seendate: "20260104T000000Z" }],
        makeIncident({ city, state }),
      );
      expect(result, `"${city}" should not match "${title}"`).toBeNull();
    }
  });

  it("still accepts the city as a whole word next to punctuation", () => {
    const result = findStrictMatch(
      [
        {
          url: "https://x.com/a",
          title: "Shooting in Ada, Oklahoma leaves four injured",
          domain: "x.com",
          seendate: "20260104T000000Z",
        },
      ],
      makeIncident({ city: "Ada", state: "Oklahoma" }),
    );
    expect(result).not.toBeNull();
  });

  it("rejects a headline naming the right city and state that is not about a shooting", () => {
    // Independence, Missouri: "Missouri towns celebrate Independence Day"
    // names both as whole words while being about fireworks.
    const result = findStrictMatch(
      [
        {
          url: "https://x.com/a",
          title: "Missouri towns celebrate Independence Day with fireworks",
          domain: "x.com",
          seendate: "20260104T000000Z",
        },
      ],
      makeIncident({ city: "Independence", state: "Missouri" }),
    );
    expect(result).toBeNull();
  });

  it("handles multi-word city names as a whole phrase", () => {
    const result = findStrictMatch(
      [
        {
          url: "https://x.com/a",
          title: "Police report a shooting in Grand Haven, Michigan",
          domain: "x.com",
          seendate: "20260104T000000Z",
        },
      ],
      makeIncident({ city: "Grand Haven", state: "Michigan" }),
    );
    expect(result).not.toBeNull();
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
