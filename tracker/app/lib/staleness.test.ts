import { describe, expect, it } from "vitest";

import { findStaleFeeds, MAX_QUIET_DAYS } from "./staleness";
import type { SourceCounts } from "@/types/data";

// A fixed "now" so these do not drift as the committed data ages.
const NOW = new Date("2026-09-22T12:00:00Z").getTime();

function counts(over: Partial<SourceCounts> & Pick<SourceCounts, "source">): SourceCounts {
  return {
    incidents: 10,
    killed: 5,
    injured: 20,
    latest_incident_date: "2026-09-20",
    ...over,
  };
}

describe("findStaleFeeds", () => {
  it("says nothing when every guarded source is current", () => {
    const totals = [
      counts({ source: "gva", latest_incident_date: "2026-09-20" }),
      counts({ source: "mother_jones", latest_incident_date: "2026-08-01" }),
    ];
    expect(findStaleFeeds(totals, NOW)).toEqual([]);
  });

  it("catches the failure this guard was written for", () => {
    // The real shape of the August outage: GVA parsed cleanly, returned only
    // cached rows, and went seven weeks without anything new while the job
    // stayed green.
    const totals = [counts({ source: "gva", latest_incident_date: "2026-08-04" })];
    const problems = findStaleFeeds(totals, NOW);

    expect(problems).toHaveLength(1);
    expect(problems[0]).toContain("Gun Violence Archive");
    expect(problems[0]).toContain("2026-08-04");
    expect(problems[0]).toContain("49 days ago");
  });

  it("would have fired three weeks in, not seven", () => {
    // 22 days after the last real incident -- one day past the limit.
    const justOver = new Date("2026-08-26T12:00:00Z").getTime();
    const totals = [counts({ source: "gva", latest_incident_date: "2026-08-04" })];
    expect(findStaleFeeds(totals, justOver)).toHaveLength(1);
  });

  it("does not fire on a genuine lull within the limit", () => {
    // GVA's largest observed gap is 4 days; 20 is well inside the limit and
    // must stay quiet, or the guard trains people to ignore it.
    const totals = [counts({ source: "gva", latest_incident_date: "2026-09-02" })];
    expect(findStaleFeeds(totals, NOW)).toEqual([]);
  });

  it("tolerates Mother Jones' much slower cadence", () => {
    // 78-day gaps are normal for a hand-curated set. The GVA limit would fire
    // on this constantly, which is why the thresholds are per source.
    const totals = [counts({ source: "mother_jones", latest_incident_date: "2026-07-01" })];
    expect(findStaleFeeds(totals, NOW)).toEqual([]);
    expect(MAX_QUIET_DAYS.mother_jones).toBeGreaterThan(MAX_QUIET_DAYS.gva!);
  });

  it("still catches Mother Jones when it stops for good", () => {
    const totals = [counts({ source: "mother_jones", latest_incident_date: "2025-09-01" })];
    expect(findStaleFeeds(totals, NOW)).toHaveLength(1);
  });

  it("exempts the archived and the not-yet-available", () => {
    // stanford_msa is frozen at 2016 by design, so staleness is its correct
    // state. violence_project returns nothing pending an access request, and a
    // source with no incidents has no recency to judge.
    const totals = [
      counts({ source: "stanford_msa", latest_incident_date: "2016-06-01" }),
      counts({ source: "violence_project", latest_incident_date: null, incidents: 0 }),
    ];
    expect(findStaleFeeds(totals, NOW)).toEqual([]);
  });

  it("stays silent for a guarded source that has no incidents at all", () => {
    // Distinct from being stale: there is nothing to date from, and a thrown
    // fetch already reports itself through stale_since.
    const totals = [counts({ source: "gva", latest_incident_date: null, incidents: 0 })];
    expect(findStaleFeeds(totals, NOW)).toEqual([]);
  });

  it("reports every offender, not just the first", () => {
    const totals = [
      counts({ source: "gva", latest_incident_date: "2026-08-04" }),
      counts({ source: "mother_jones", latest_incident_date: "2025-01-01" }),
    ];
    expect(findStaleFeeds(totals, NOW)).toHaveLength(2);
  });
});
