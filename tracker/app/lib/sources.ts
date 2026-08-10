/**
 * Registry of mass shooting and gun violence datasets.
 *
 * Every dataset here has its own definition of "mass shooting" and its own
 * coverage window. They must NOT be merged into a single count without
 * losing information. The tracker treats each as a separate series and
 * shows counts side-by-side rather than combining them.
 *
 * References:
 *   - Booty et al., "Describing a 'mass shooting': the role of databases in
 *     understanding burden," Injury Epidemiology (2019)
 *   - Bridges, Tober & Brazzell, "Database discrepancies in understanding the
 *     burden of mass shootings in the United States, 2013-2020," Lancet
 *     Regional Health – Americas (2023) 22:100504. Compared five databases
 *     over 2013-2020: 3,155 discrete incidents in total, but only 25 (0.008%)
 *     appear in all five. Counts for the same window range from 57 (Mother
 *     Jones) to 2,950 (Gun Violence Archive) — the ~52x spread this site's
 *     no-merging rule exists to respect.
 */

export type SourceId = "gva" | "mother_jones" | "stanford_msa" | "violence_project";

export interface DataSource {
  id: SourceId;
  name: string;
  publisher: string;
  url: string;
  definition: string;
  coverage: string;
  updateCadence: "real-time" | "daily" | "on-event" | "archived";
  license: string;
  // Whether the frontend should include this source in the "live" tally.
  // Archived sources are shown for historical context but not counted as current.
  live: boolean;
}

export const SOURCES: Record<SourceId, DataSource> = {
  gva: {
    id: "gva",
    name: "Gun Violence Archive",
    publisher: "Gun Violence Archive (non-profit)",
    url: "https://www.gunviolencearchive.org",
    definition:
      "Four or more victims shot (injured OR killed), not including any " +
      "shooter who may also have been shot. Includes gang, domestic, and " +
      "drug-related incidents in any location (public or private).",
    coverage: "2013 to present",
    updateCadence: "real-time",
    license: "Attribution required; commercial use restricted",
    live: true,
  },
  mother_jones: {
    id: "mother_jones",
    name: "Mother Jones",
    publisher: "Mother Jones magazine",
    url: "https://www.motherjones.com/politics/2012/12/mass-shootings-mother-jones-full-data/",
    definition:
      "Three or more people killed (four or more before 2013), not " +
      "including the shooter, in a single incident in a public place. " +
      "Excludes gang activity, armed robbery, and domestic violence " +
      "occurring in private homes.",
    coverage: "1982 to present (definition threshold changed in 2013)",
    updateCadence: "on-event",
    license: "Attribution required for reuse",
    live: true,
  },
  stanford_msa: {
    id: "stanford_msa",
    name: "Stanford MSA",
    publisher: "Stanford Geospatial Center",
    url: "https://github.com/StanfordGeospatialCenter/MSA",
    definition:
      "Three or more victims shot (not necessarily killed), not including " +
      "the shooter. Excludes identifiably gang, drug, or organized-crime " +
      "related shootings. Focus is on the shooting incident, not the " +
      "resulting mass murder.",
    coverage: "1966 to 2016 (project permanently suspended)",
    updateCadence: "archived",
    license: "Creative Commons Attribution 4.0",
    live: false,
  },
  violence_project: {
    id: "violence_project",
    name: "The Violence Project",
    publisher: "The Violence Project (funded by NIJ)",
    url: "https://www.theviolenceproject.org/mass-shooter-database/",
    definition:
      "Four or more people killed, excluding the shooter, in a public " +
      "location, with no connection to underlying criminal activity such " +
      "as gangs or drugs. Focus is on the perpetrator, with 200+ life-" +
      "history variables per case.",
    coverage: "1966 to present",
    updateCadence: "on-event",
    license: "Free for research/journalism; access request required",
    live: true,
  },
};

/**
 * Not implemented as a tracker source but documented for reference:
 *
 *   FBI Active Shooter Report — Federal definition. "An individual actively
 *   engaged in killing or attempting to kill people in a populated area."
 *   Requires ongoing active shooting, so undercounts incidents where the
 *   shooter is stopped or flees quickly.
 *
 *   FBI Supplementary Homicide Report (SHR) — Uses the mass murder
 *   definition (four or more killed). Aggregated annually, not per
 *   incident, so unsuitable for real-time tracking.
 */
