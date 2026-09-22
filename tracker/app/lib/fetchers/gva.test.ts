import { readFile } from "node:fs/promises";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchGVA } from "./gva";

const __dirname = dirname(fileURLToPath(import.meta.url));
const FIXTURE_PATH = join(__dirname, "__fixtures__", "gva-report-page.html");

async function loadFixture(): Promise<string> {
  return readFile(FIXTURE_PATH, "utf-8");
}

function mockFetchWith(html: string, ok = true, status = 200): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok,
      status,
      text: async () => html,
    })),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("fetchGVA", () => {
  it("parses well-shaped rows and skips rows that fail row-level checks, not the whole page", async () => {
    mockFetchWith(await loadFixture());
    const incidents = await fetchGVA({ delayMs: 0 });

    // 5 fixture rows: DC is skipped (outside 50-state scope), TBD-date row
    // is skipped (unparseable date), leaving 3 valid incidents.
    expect(incidents).toHaveLength(3);
    expect(incidents.map((i) => i.city)).toEqual(["Houston", "Columbus", "Fresno"]);

    const houston = incidents.find((i) => i.city === "Houston")!;
    expect(houston.state).toBe("Texas");
    expect(houston.killed).toBe(1);
    expect(houston.injured).toBe(4);
    expect(houston.source).toBe("gva");

    // State given as an abbreviation in the fixture is normalized to full name.
    const columbus = incidents.find((i) => i.city === "Columbus")!;
    expect(columbus.state).toBe("Ohio");
  });

  it("throws when the HTTP request fails, rather than returning an empty array silently", async () => {
    mockFetchWith("", false, 503);
    // retryBaseMs 0: a 503 is retriable and would otherwise sit through real
    // exponential backoff before reporting the failure.
    await expect(fetchGVA({ retryBaseMs: 0 })).rejects.toThrow(/GVA fetch failed: 503/);
  });

  it("throws when the header row is missing entirely", async () => {
    const html = await loadFixture();
    const mutated = html.replace(/<thead>[\s\S]*?<\/thead>/, "");
    mockFetchWith(mutated);
    await expect(fetchGVA({ delayMs: 0 })).rejects.toThrow(/no <th> header row found/);
  });

  it("throws when columns are reordered (state/city swapped in the header)", async () => {
    const html = await loadFixture();
    const mutated = html
      .replace("<th>State</th>", "<th>__PLACEHOLDER__</th>")
      .replace("<th>City Or County</th>", "<th>State</th>")
      .replace("<th>__PLACEHOLDER__</th>", "<th>City Or County</th>");
    mockFetchWith(mutated);
    await expect(fetchGVA({ delayMs: 0 })).rejects.toThrow(/expected header column 2 to contain "state"/);
  });

  it("throws when a data row disagrees with the header's column count", async () => {
    const html = await loadFixture();
    // Drop the "Address" cell from the Houston row. It still clears the
    // seven-cell minimum, but no longer matches the eleven-column header --
    // which means the columns after it have shifted left and the indices the
    // parser trusts now point at the wrong values.
    const mutated = html.replace(
      "<td>1200 Block of Main St</td>\n      <td>1</td>\n      <td>4</td>",
      "<td>1</td>\n      <td>4</td>",
    );
    mockFetchWith(mutated);
    await expect(fetchGVA({ delayMs: 0 })).rejects.toThrow(/row has 10 cells but the header has 11/);
  });

  it("throws when a data row has fewer cells than the parser reads", async () => {
    const html = await loadFixture();
    const mutated = html.replace(
      /<tr class="odd">\s*<td>3548001<\/td>[\s\S]*?<\/tr>/,
      "<tr class=\"odd\"><td>a</td><td>b</td><td>c</td></tr>",
    );
    mockFetchWith(mutated);
    await expect(fetchGVA({ delayMs: 0 })).rejects.toThrow(/need at least 7 cells per data row, got 3/);
  });

  it("tolerates columns appended to the right of the ones it reads", async () => {
    // THE REGRESSION. GVA appended Suspects Killed / Injured / Arrested and
    // Operations, taking the table from seven columns to eleven. An exact
    // cell-count guard threw on every data row, so the scrape failed for six
    // weeks while the site served cached figures behind a "most recent run
    // failed" footnote -- honest, and still easy to miss.
    //
    // Appending cannot move indices 1, 2, 3, 5 and 6, so it must not be fatal.
    // Inserting before them would, and the header check above catches that.
    const html = await loadFixture();
    const mutated = html
      .replace("<th>Operations</th>", "<th>Operations</th>\n      <th>Newly Added</th>")
      .replace(/<td><a href="\/incident\/(\d)">View Incident<\/a><\/td>/g,
        '<td><a href="/incident/$1">View Incident</a></td>\n      <td>extra</td>');

    mockFetchWith(mutated);
    const incidents = await fetchGVA({ delayMs: 0 });
    expect(incidents.length).toBeGreaterThan(0);
    // And the values still come from the right columns.
    const houston = incidents.find((i) => i.city === "Houston");
    expect(houston).toMatchObject({ state: "Texas", killed: 1, injured: 4 });
  });

  it("throws when a killed/injured cell is not a valid non-negative integer", async () => {
    const html = await loadFixture();
    const mutated = html.replace(
      "<td>1200 Block of Main St</td>\n      <td>1</td>\n      <td>4</td>",
      "<td>1200 Block of Main St</td>\n      <td>unknown</td>\n      <td>4</td>",
    );
    mockFetchWith(mutated);
    await expect(fetchGVA({ delayMs: 0 })).rejects.toThrow(/"# killed" cell was not a valid non-negative integer/);
  });

  it("throws when the header matches but every row is filtered out", async () => {
    const html = await loadFixture();
    // Blank out every state cell so all rows fail the state-lookup check.
    const mutated = html.replace(/<td>(Texas|OH|District of Columbia|Georgia|California)<\/td>/g, "<td>Nowhereland</td>");
    mockFetchWith(mutated);
    await expect(fetchGVA({ delayMs: 0 })).rejects.toThrow(/no incidents fell within the last 365 days/);
  });
});

/**
 * Paging across the report.
 *
 * The fetcher used to request one page and stop, so the tracker reported the
 * newest 25 incidents -- about three weeks -- as a 365-day count. The tell was
 * that the total read exactly 25 both before and after a seven-week outage: it
 * was pinned to the page size, not the window.
 */
describe("fetchGVA pagination", () => {
  const NOW = new Date("2026-09-22T12:00:00Z");

  /** A full 25-row page whose rows are numbered from `startId` and dated back
   *  one day at a time from `startDate`. */
  function page(startId: number, startDate: string, rows = 25): string {
    const header =
      "<table><thead><tr>" +
      ["Incident ID", "Incident Date", "State", "City Or County", "Address",
       "Victims Killed", "Victims Injured", "Suspects Killed", "Suspects Injured",
       "Suspects Arrested", "Operations"].map((h) => `<th>${h}</th>`).join("") +
      "</tr></thead><tbody>";
    const body = Array.from({ length: rows }, (_, i) => {
      const d = new Date(startDate);
      d.setDate(d.getDate() - i);
      const human = d.toLocaleDateString("en-US", {
        month: "long", day: "numeric", year: "numeric", timeZone: "UTC",
      });
      return "<tr>" +
        [String(startId + i), human, "Texas", `City${startId + i}`, "1 Main St",
         "1", "4", "0", "0", "0", "view"].map((c) => `<td>${c}</td>`).join("") +
        "</tr>";
    }).join("");
    return header + body + "</tbody></table>";
  }

  /**
   * Serves `pages` for the CURRENT year and an empty pager for any earlier
   * year. The report is year-scoped, so the crawl legitimately probes the
   * prior year once it exhausts this one; a mock that ignored ?year= would
   * serve 2026's rows as 2025's and hide that.
   */
  function mockPages(pages: string[]): ReturnType<typeof vi.fn> {
    const empty = page(9000, "2020-01-01", 0);
    const spy = vi.fn(async (url: string) => {
      const year = Number(/[?&]year=(\d+)/.exec(url)?.[1] ?? NOW.getFullYear());
      const n = Number(/[?&]page=(\d+)/.exec(url)?.[1] ?? 0);
      const html = year === NOW.getFullYear() ? (pages[n] ?? empty) : empty;
      return { ok: true, status: 200, text: async () => html };
    });
    vi.stubGlobal("fetch", spy);
    return spy as unknown as ReturnType<typeof vi.fn>;
  }

  it("crosses into the previous year, because the report is year-scoped", async () => {
    // /reports/mass-shooting covers a calendar year, so in September a
    // 365-day window needs last year's report too. Crawling only the current
    // one silently truncates to year-to-date.
    const spy = vi.fn(async (url: string) => {
      const year = Number(/[?&]year=(\d+)/.exec(url)?.[1] ?? 2026);
      const html =
        year === 2026
          ? page(3000, "2026-01-20", 10) // short page: 2026 exhausted
          : page(4000, "2025-12-31", 10); // prior year still inside the window
      return { ok: true, status: 200, text: async () => html };
    });
    vi.stubGlobal("fetch", spy);

    const out = await fetchGVA({ now: NOW, delayMs: 0 });
    const urls = spy.mock.calls.map((c) => String(c[0]));

    expect(urls.some((u) => /year=2025/.test(u))).toBe(true);
    expect(out.some((i) => i.date.startsWith("2025-"))).toBe(true);
  });

  it("walks past the first page instead of stopping at 25", async () => {
    const spy = mockPages([
      page(3000, "2026-09-20"),
      page(3100, "2026-08-26"),
      page(3200, "2026-08-01"),
    ]);
    const out = await fetchGVA({ now: NOW, delayMs: 0 });

    expect(out.length).toBeGreaterThan(25);
    expect(spy.mock.calls[0][0]).not.toMatch(/page=/);
    expect(spy.mock.calls[1][0]).toMatch(/page=1$/);
  });

  it("stops once a page predates the window rather than walking to 2014", async () => {
    const spy = mockPages([
      page(3000, "2026-09-20"),
      // Entirely outside a 365-day window from NOW.
      page(3100, "2024-05-01"),
      page(3200, "2024-04-01"),
    ]);
    const out = await fetchGVA({ now: NOW, delayMs: 0 });

    expect(spy).toHaveBeenCalledTimes(2);
    expect(out.every((i) => i.date >= "2025-09-22")).toBe(true);
  });

  it("treats a short page as the end of that YEAR, not of the crawl", async () => {
    // A short page means this year's pager is exhausted. The window may still
    // extend into the prior year, so the crawl moves on rather than stopping.
    const spy = mockPages([page(3000, "2026-09-20"), page(3100, "2026-08-26", 7)]);
    await fetchGVA({ now: NOW, delayMs: 0 });

    const urls = spy.mock.calls.map((c) => String(c[0]));
    expect(urls).toHaveLength(3);
    expect(urls[2]).toMatch(/year=2025/);
  });

  it("keeps what it has when a later page fails, rather than losing everything", async () => {
    // Eight pages of real data beats none. The staleness guard still catches a
    // crawl that degrades so far nothing recent arrives.
    const good = page(3000, "2026-09-20");
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        const n = Number(/[?&]page=(\d+)/.exec(url)?.[1] ?? 0);
        if (n === 0) return { ok: true, status: 200, text: async () => good };
        return { ok: false, status: 500, text: async () => "" };
      }),
    );

    const out = await fetchGVA({ now: NOW, delayMs: 0, retryBaseMs: 0 });
    expect(out).toHaveLength(25);
  });

  it("still throws when the FIRST page fails, since nothing is salvageable", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false, status: 500, text: async () => "" })));
    await expect(fetchGVA({ now: NOW, delayMs: 0, retryBaseMs: 0 })).rejects.toThrow(
      /GVA fetch failed: 500/,
    );
  });

  it("retries a 403 instead of giving up, because it means slow down", async () => {
    let calls = 0;
    const good = page(3000, "2026-09-20", 3);
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        calls += 1;
        if (calls === 1) return { ok: false, status: 403, text: async () => "" };
        return { ok: true, status: 200, text: async () => good };
      }),
    );

    // sinceDays 30 keeps the cutoff inside the current year, so the crawl does
    // not also probe 2025 and the call count stays about the retry.
    const out = await fetchGVA({ now: NOW, delayMs: 0, retryBaseMs: 0, sinceDays: 30 });
    expect(calls).toBe(2);
    expect(out).toHaveLength(3);
  });

  it("de-duplicates an incident that shifts pages mid-crawl", async () => {
    // A new incident published while paging pushes rows down, so the same
    // incident can appear on two consecutive pages. GVA's own id catches it.
    const p0 = page(3000, "2026-09-20");
    const p1 = page(3024, "2026-08-27"); // overlaps p0's last row by one id
    mockPages([p0, p1]);

    const out = await fetchGVA({ now: NOW, delayMs: 0 });
    expect(new Set(out.map((i) => i.id)).size).toBe(out.length);
  });
});
