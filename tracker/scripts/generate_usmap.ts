/**
 * Precompute SVG path data for the 50 states into app/lib/usmap.ts.
 *
 * Run at development time, never at build or request time. The generated file
 * is committed, so the deployed app carries no mapping dependency at all --
 * us-atlas, topojson-client and d3-geo are devDependencies used only here.
 * This mirrors how app/lib/tilegrid.ts stores its layout as static data.
 *
 * Projection is Albers USA, which relocates Alaska and Hawaii into insets so
 * the contiguous states are not shrunk to fit them.
 *
 * Source: us-atlas (ISC licence), derived from US Census Bureau cartographic
 * boundary files, which are public domain as a US Government work.
 *
 * Usage:
 *   npx tsx scripts/generate_usmap.ts
 */

import { writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { geoAlbersUsa, geoPath } from "d3-geo";
import { feature } from "topojson-client";

import { STATE_TO_CODE } from "../app/lib/states";

const __dirname = dirname(fileURLToPath(import.meta.url));
const OUT = join(__dirname, "..", "app", "lib", "usmap.ts");

const WIDTH = 960;
const HEIGHT = 600;

async function main(): Promise<void> {
  // us-atlas ships TopoJSON; 10m is the middle resolution -- enough detail to
  // read as a real map without bloating the committed file.
  const topology = (await import("us-atlas/states-10m.json", {
    with: { type: "json" },
  })) as unknown as { default: any };
  const topo = topology.default ?? topology;

  const states = feature(topo, topo.objects.states) as unknown as {
    features: Array<{ properties: { name: string }; geometry: unknown }>;
  };

  const projection = geoAlbersUsa().fitSize([WIDTH, HEIGHT], states as never);
  const toPath = geoPath(projection);

  const rows: string[] = [];
  const skipped: string[] = [];

  for (const f of states.features) {
    const name = f.properties.name;
    const code = STATE_TO_CODE[name];
    if (!code) {
      // DC, Puerto Rico and other territories: this project covers the 50
      // states only, matching the rest of the codebase.
      skipped.push(name);
      continue;
    }
    const d = toPath(f as never);
    if (!d) {
      skipped.push(`${name} (no projected geometry)`);
      continue;
    }
    rows.push(
      `  { code: ${JSON.stringify(code)}, name: ${JSON.stringify(name)}, d: ${JSON.stringify(d)} },`,
    );
  }

  if (rows.length !== 50) {
    throw new Error(`Expected 50 states, generated ${rows.length}. Skipped: ${skipped.join(", ")}`);
  }

  const out = `/**
 * Geographic SVG paths for the 50 states, Albers USA projection.
 *
 * GENERATED FILE -- do not edit by hand.
 * Regenerate with: npx tsx scripts/generate_usmap.ts
 *
 * Committed rather than computed so the deployed app carries no mapping
 * dependency. Source: us-atlas (ISC), from US Census Bureau cartographic
 * boundary files (public domain).
 *
 * Read app/lib/tilegrid.ts before choosing between these two renderings: the
 * equal-area tile grid exists because a geographic map sizes states by land
 * area, which over-weights large, sparsely populated states on a per-capita
 * measure. Both are provided; the choice is editorial, not technical.
 */

export const USMAP_VIEWBOX = "0 0 ${WIDTH} ${HEIGHT}";

export interface StatePath {
  code: string;
  name: string;
  /** SVG path 'd' attribute in the ${WIDTH}x${HEIGHT} viewBox above. */
  d: string;
}

export const STATE_PATHS: StatePath[] = [
${rows.join("\n")}
];
`;

  await writeFile(OUT, out);
  console.log(`Wrote ${rows.length} state paths to ${OUT}`);
  if (skipped.length) console.log(`Skipped (not in the 50 states): ${skipped.join(", ")}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
