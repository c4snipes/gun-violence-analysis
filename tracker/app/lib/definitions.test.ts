import { describe, expect, it } from "vitest";

import { evaluate, evaluateAll } from "./definitions";
import type { Incident } from "@/types/data";
import type { SourceId } from "./sources";

function makeIncident(overrides: Partial<Incident> = {}): Incident {
  return {
    id: "test-1",
    date: "2020-06-15",
    state: "Texas",
    city: "Houston",
    killed: 0,
    injured: 0,
    source: "gva",
    ...overrides,
  };
}

const ALL_SOURCES: SourceId[] = ["gva", "mother_jones", "stanford_msa", "violence_project"];

describe("evaluate — provenance", () => {
  it("returns yes for every source when the incident actually came from that source, regardless of casualty counts", () => {
    for (const source of ALL_SOURCES) {
      const incident = makeIncident({ source, killed: 0, injured: 0 });
      expect(evaluate(incident, source)).toBe("yes");
    }
  });
});

describe("evaluate — gva", () => {
  it("evaluates yes for a 4+-shot incident with no contextual condition required", () => {
    const incident = makeIncident({ source: "stanford_msa", killed: 1, injured: 3 });
    expect(evaluate(incident, "gva")).toBe("yes");
  });

  it("evaluates no when the incident is below GVA's casualty threshold", () => {
    const incident = makeIncident({ source: "stanford_msa", killed: 1, injured: 2 });
    expect(evaluate(incident, "gva")).toBe("no");
  });
});

describe("evaluate — mother_jones", () => {
  it("evaluates no when below the killed threshold", () => {
    const incident = makeIncident({ source: "gva", killed: 2, injured: 10 });
    expect(evaluate(incident, "mother_jones")).toBe("no");
  });

  it("evaluates unknown when the killed threshold clears but public-place/gang context is unrecorded", () => {
    const incident = makeIncident({ source: "gva", killed: 3, injured: 0 });
    expect(evaluate(incident, "mother_jones")).toBe("unknown");
  });
});

describe("evaluate — violence_project", () => {
  it("evaluates no when below the killed threshold", () => {
    const incident = makeIncident({ source: "gva", killed: 3, injured: 10 });
    expect(evaluate(incident, "violence_project")).toBe("no");
  });

  it("evaluates unknown when the killed threshold clears but public-location/gang context is unrecorded", () => {
    const incident = makeIncident({ source: "gva", killed: 4, injured: 0 });
    expect(evaluate(incident, "violence_project")).toBe("unknown");
  });
});

describe("evaluate — stanford_msa", () => {
  it("evaluates no when below the shot threshold, inside the coverage window", () => {
    const incident = makeIncident({ source: "gva", date: "2015-01-01", killed: 1, injured: 1 });
    expect(evaluate(incident, "stanford_msa")).toBe("no");
  });

  it("evaluates unknown when the shot threshold clears, inside the coverage window, with gang/drug context unrecorded", () => {
    const incident = makeIncident({ source: "gva", date: "2015-01-01", killed: 1, injured: 2 });
    expect(evaluate(incident, "stanford_msa")).toBe("unknown");
  });

  it("evaluates no for an incident after the project's suspension date, regardless of casualty count", () => {
    // Same shot count as the "unknown" case above, but dated after the
    // project's 2016-06-30 permanent-suspension cutoff — coverage window
    // excludes it before casualty context even matters.
    const incident = makeIncident({ source: "gva", date: "2020-01-01", killed: 1, injured: 2 });
    expect(evaluate(incident, "stanford_msa")).toBe("no");
  });

  it("evaluates no for an incident right at the coverage boundary's edge", () => {
    const justInside = makeIncident({ source: "gva", date: "2016-06-30", killed: 1, injured: 2 });
    const justOutside = makeIncident({ source: "gva", date: "2016-07-01", killed: 1, injured: 2 });
    expect(evaluate(justInside, "stanford_msa")).toBe("unknown");
    expect(evaluate(justOutside, "stanford_msa")).toBe("no");
  });
});

describe("evaluateAll", () => {
  it("evaluates every source independently for a single incident, without merging results", () => {
    const incident = makeIncident({ source: "gva", date: "2020-01-01", killed: 4, injured: 0 });
    const result = evaluateAll(incident);
    expect(result).toEqual({
      gva: "yes", // provenance
      mother_jones: "unknown", // killed >= 3, context unrecorded
      stanford_msa: "no", // outside coverage window
      violence_project: "unknown", // killed >= 4, context unrecorded
    });
  });
});
