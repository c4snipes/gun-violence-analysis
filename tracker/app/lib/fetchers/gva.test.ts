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
    const incidents = await fetchGVA();

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
    await expect(fetchGVA()).rejects.toThrow(/GVA fetch failed: 503/);
  });

  it("throws when the header row is missing entirely", async () => {
    const html = await loadFixture();
    const mutated = html.replace(/<thead>[\s\S]*?<\/thead>/, "");
    mockFetchWith(mutated);
    await expect(fetchGVA()).rejects.toThrow(/no <th> header row found/);
  });

  it("throws when columns are reordered (state/city swapped in the header)", async () => {
    const html = await loadFixture();
    const mutated = html
      .replace("<th>State</th>", "<th>__PLACEHOLDER__</th>")
      .replace("<th>City Or County</th>", "<th>State</th>")
      .replace("<th>__PLACEHOLDER__</th>", "<th>City Or County</th>");
    mockFetchWith(mutated);
    await expect(fetchGVA()).rejects.toThrow(/expected header column 2 to contain "state"/);
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
    await expect(fetchGVA()).rejects.toThrow(/row has 10 cells but the header has 11/);
  });

  it("throws when a data row has fewer cells than the parser reads", async () => {
    const html = await loadFixture();
    const mutated = html.replace(
      /<tr class="odd">\s*<td>3548001<\/td>[\s\S]*?<\/tr>/,
      "<tr class=\"odd\"><td>a</td><td>b</td><td>c</td></tr>",
    );
    mockFetchWith(mutated);
    await expect(fetchGVA()).rejects.toThrow(/need at least 7 cells per data row, got 3/);
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
    const incidents = await fetchGVA();
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
    await expect(fetchGVA()).rejects.toThrow(/"# killed" cell was not a valid non-negative integer/);
  });

  it("throws when the header matches but every row is filtered out", async () => {
    const html = await loadFixture();
    // Blank out every state cell so all rows fail the state-lookup check.
    const mutated = html.replace(/<td>(Texas|OH|District of Columbia|Georgia|California)<\/td>/g, "<td>Nowhereland</td>");
    mockFetchWith(mutated);
    await expect(fetchGVA()).rejects.toThrow(/zero data rows were parsed/);
  });
});
