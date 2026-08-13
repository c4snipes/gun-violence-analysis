import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchMotherJones } from "./mother_jones";

/**
 * The published sheet has TWO columns named `location`. Column 1 is
 * "City, State"; column 7 is the venue type. csv-parse with `columns: true`
 * keeps the last of a duplicate name, so `row.location` was "Other" and every
 * row failed the state lookup -- the fetcher returned zero incidents and the
 * dashboard rendered that as "not collected" rather than as a fault.
 *
 * The header below reproduces that duplication exactly.
 */
const HEADER =
  "case,location,date,summary,fatalities,injured,total_victims,location,age_of_shooter";

function row(caseName: string, place: string, date: string, fatalities: number, injured: number) {
  return `${caseName},"${place}",${date},summary,${fatalities},${injured},${
    fatalities + injured
  },Other,30`;
}

function mockCsv(body: string): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({ ok: true, status: 200, text: async () => body })),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("fetchMotherJones", () => {
  it("reads the first 'location' column, not the duplicate venue-type column", async () => {
    mockCsv([HEADER, row("Test shooting", "Twin Falls, Idaho", "8/1/2026", 3, 1)].join("\n"));
    const incidents = await fetchMotherJones();
    expect(incidents).toHaveLength(1);
    expect(incidents[0].state).toBe("Idaho");
    expect(incidents[0].city).toBe("Twin Falls");
    expect(incidents[0].killed).toBe(3);
  });

  it("patches the 'Lousiana' misspelling present in the source sheet", async () => {
    // Without the fix this row is dropped and the 2013-2020 total comes to 55
    // where the published literature reports 57.
    mockCsv([HEADER, row("Baton Rouge", "Baton Rouge, Lousiana", "7/17/2016", 3, 3)].join("\n"));
    const incidents = await fetchMotherJones();
    expect(incidents).toHaveLength(1);
    expect(incidents[0].state).toBe("Louisiana");
  });

  it("excludes District of Columbia, which is outside this project's 50-state scope", async () => {
    mockCsv([HEADER, row("DC shooting", "Washington, D.C.", "9/16/2013", 12, 3)].join("\n"));
    await expect(fetchMotherJones()).resolves.toHaveLength(0);
  });

  it("throws rather than returning empty when the sheet parses to no rows", async () => {
    // An empty result previously read as "this source has no incidents", which
    // is a different claim from "the fetch failed".
    mockCsv(HEADER);
    await expect(fetchMotherJones()).rejects.toThrow(/parsed to zero rows/);
  });

  it("throws when the HTTP request fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok: false, status: 503, text: async () => "" })),
    );
    await expect(fetchMotherJones()).rejects.toThrow(/Mother Jones fetch failed: 503/);
  });
});
