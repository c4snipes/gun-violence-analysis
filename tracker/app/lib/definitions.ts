/**
 * Evaluate a single incident against each dataset's definition.
 *
 * This is deliberately three-valued. Our incident records carry casualty
 * counts but not the contextual facts several definitions turn on: whether
 * the location was public, whether the shooting was gang, drug, robbery or
 * domestic related. Those cannot be recovered from a casualty count.
 *
 * So a definition can be:
 *   "yes"     the incident provably qualifies (it came from that dataset,
 *             or it clears a threshold that has no contextual condition)
 *   "no"      the incident provably fails the casualty threshold
 *   "unknown" it clears the threshold but the contextual condition is not
 *             recorded in our data
 *
 * Rendering "unknown" as a match would overstate. Rendering it as a miss
 * would understate. It gets its own glyph.
 */

import type { Incident } from "@/types/data";
import type { SourceId } from "./sources";

export type Match = "yes" | "no" | "unknown";

export const MATCH_GLYPH: Record<Match, string> = {
  yes: "\u25CF",
  no: "\u2014",
  unknown: "\u25CB",
};

export const MATCH_LABEL: Record<Match, string> = {
  yes: "meets this definition",
  no: "does not meet the casualty threshold",
  unknown: "clears the threshold, but the contextual condition is unrecorded",
};

export function evaluate(incident: Incident, source: SourceId): Match {
  // Provenance is proof: the publisher applied their own criteria.
  if (incident.source === source) return "yes";

  const shot = incident.killed + incident.injured;

  switch (source) {
    case "gva":
      // 4+ shot, no contextual condition at all, so the count decides it.
      return shot >= 4 ? "yes" : "no";

    case "mother_jones":
      // 3+ killed AND public place AND not gang/robbery/domestic.
      if (incident.killed < 3) return "no";
      return "unknown";

    case "violence_project":
      // 4+ killed AND public location AND no gang/drug connection.
      if (incident.killed < 4) return "no";
      return "unknown";

    case "stanford_msa":
      // 3+ shot, excludes gang/drug/organised crime. Coverage ended 2016,
      // so anything later is outside the window regardless of casualties.
      if (new Date(incident.date) > new Date("2016-06-30")) return "no";
      if (shot < 3) return "no";
      return "unknown";
  }
}

export function evaluateAll(incident: Incident): Record<SourceId, Match> {
  return {
    gva: evaluate(incident, "gva"),
    mother_jones: evaluate(incident, "mother_jones"),
    stanford_msa: evaluate(incident, "stanford_msa"),
    violence_project: evaluate(incident, "violence_project"),
  };
}
