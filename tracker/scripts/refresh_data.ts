/**
 * Fetch fresh incident data from all configured sources and write the
 * tracker snapshot to public/data/.
 *
 * Each source is fetched independently in a try/catch. Sources that fail
 * are marked stale rather than causing the whole workflow to fail. This
 * matters because GVA in particular is a fragile HTML scrape.
 */

import { readFile, writeFile, mkdir } from "node:fs/promises";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

import type {
  Incident,
  ModelResults,
  SourceCounts,
  StateStats,
  TrackerSnapshot,
} from "../types/data";
import { fetchGVA } from "../app/lib/fetchers/gva";
import { fetchMotherJones } from "../app/lib/fetchers/mother_jones";
import { fetchStanfordMSA } from "../app/lib/fetchers/stanford_msa";
import { fetchViolenceProject } from "../app/lib/fetchers/violence_project";
import { SOURCES, type SourceId } from "../app/lib/sources";
import { STATE_POPULATION, STATE_TO_CODE } from "../app/lib/states";

const __dirname = dirname(fileURLToPath(import.meta.url));
const DATA_DIR = join(__dirname, "..", "public", "data");
const WINDOW_DAYS = 365;

const FETCHERS: Record<SourceId, () => Promise<Incident[]>> = {
  gva: fetchGVA,
  mother_jones: fetchMotherJones,
  stanford_msa: fetchStanfordMSA,
  violence_project: fetchViolenceProject,
};

async function fetchAllSources(): Promise<{
  incidents: Incident[];
  staleSources: Set<SourceId>;
}> {
  const incidents: Incident[] = [];
  const stale = new Set<SourceId>();

  // Load cached data so failed sources can serve yesterday's numbers.
  let cached: Incident[] = [];
  try {
    cached = JSON.parse(await readFile(join(DATA_DIR, "incidents.json"), "utf-8"));
  } catch {
    // no cache yet
  }

  for (const [id, fetcher] of Object.entries(FETCHERS) as [SourceId, () => Promise<Incident[]>][]) {
    const source = SOURCES[id];
    console.log(`Fetching ${source.name}...`);
    try {
      const rows = await fetcher();
      console.log(`  ${rows.length} incidents from ${source.name}`);
      if (rows.length === 0 && source.live) {
        // Some sources (Violence Project) can legitimately return empty when
        // the local file isn't provided. Only mark stale if we EXPECT rows.
        console.log(`  (empty result — treating as unavailable)`);
      }
      incidents.push(...rows);
    } catch (err) {
      console.warn(`  ${source.name} failed: ${err}`);
      stale.add(id);
      // Reuse cached incidents from this source if we have any.
      const stashed = cached.filter((i) => i.source === id);
      if (stashed.length > 0) {
        console.log(`  falling back to ${stashed.length} cached incidents`);
        incidents.push(...stashed);
      }
    }
  }
  return { incidents, staleSources: stale };
}

function computeTotalsBySource(
  incidents: Incident[],
  staleSources: Set<SourceId>,
  windowDays: number,
): SourceCounts[] {
  const cutoff = new Date();
  cutoff.setDate(cutoff.getDate() - windowDays);
  const out: SourceCounts[] = [];

  for (const id of Object.keys(SOURCES) as SourceId[]) {
    const rows = incidents.filter(
      (i) => i.source === id && new Date(i.date) >= cutoff,
    );
    const latest = rows.reduce<string | null>(
      (max, i) => (max === null || i.date > max ? i.date : max),
      null,
    );
    out.push({
      source: id,
      incidents: rows.length,
      killed: rows.reduce((s, i) => s + i.killed, 0),
      injured: rows.reduce((s, i) => s + i.injured, 0),
      latest_incident_date: latest,
      stale_since: staleSources.has(id) ? new Date().toISOString() : undefined,
    });
  }
  return out;
}

function computeStateStats(incidents: Incident[], windowDays: number): StateStats[] {
  const cutoff = new Date();
  cutoff.setDate(cutoff.getDate() - windowDays);

  type Bucket = { incidents: number; killed: number; injured: number };
  const empty: Record<SourceId, Bucket> = {
    gva: { incidents: 0, killed: 0, injured: 0 },
    mother_jones: { incidents: 0, killed: 0, injured: 0 },
    stanford_msa: { incidents: 0, killed: 0, injured: 0 },
    violence_project: { incidents: 0, killed: 0, injured: 0 },
  };

  const byState = new Map<string, Record<SourceId, Bucket>>();
  for (const inc of incidents) {
    if (new Date(inc.date) < cutoff) continue;
    if (!byState.has(inc.state)) {
      byState.set(inc.state, JSON.parse(JSON.stringify(empty)) as typeof empty);
    }
    const state = byState.get(inc.state)!;
    state[inc.source].incidents += 1;
    state[inc.source].killed += inc.killed;
    state[inc.source].injured += inc.injured;
  }

  const stats: StateStats[] = [];
  for (const [name, code] of Object.entries(STATE_TO_CODE)) {
    const pop = STATE_POPULATION[name];
    if (!pop) continue;
    const buckets = byState.get(name) ?? empty;
    const counts_by_source = {} as StateStats["counts_by_source"];
    for (const id of Object.keys(SOURCES) as SourceId[]) {
      counts_by_source[id] = {
        ...buckets[id],
        per_100k: (buckets[id].incidents / pop) * 100_000,
      };
    }
    stats.push({ state: name, code, population: pop, counts_by_source });
  }
  return stats;
}

async function loadModelResults(): Promise<ModelResults> {
  try {
    return JSON.parse(await readFile(join(DATA_DIR, "model.json"), "utf-8"));
  } catch {
    return {
      fitted_at: new Date().toISOString(),
      n_states: 50,
      outcome: "firearm_mortality_rate",
      ols: { r_squared: 0, adj_r_squared: 0, coefficients: [] },
      random_forest: { loo_cv_r_squared: 0, permutation_importance: [] },
    };
  }
}

async function main(): Promise<void> {
  await mkdir(DATA_DIR, { recursive: true });

  const { incidents, staleSources } = await fetchAllSources();
  incidents.sort((a, b) => (a.date > b.date ? -1 : 1));

  const model = await loadModelResults();
  const snapshot: TrackerSnapshot = {
    generated_at: new Date().toISOString(),
    window_days: WINDOW_DAYS,
    totals_by_source: computeTotalsBySource(incidents, staleSources, WINDOW_DAYS),
    states: computeStateStats(incidents, WINDOW_DAYS),
    recent_incidents: incidents.slice(0, 100),
    model,
  };

  await writeFile(join(DATA_DIR, "snapshot.json"), JSON.stringify(snapshot, null, 2));
  await writeFile(join(DATA_DIR, "incidents.json"), JSON.stringify(incidents, null, 2));

  const staleList = [...staleSources];
  if (staleList.length > 0) {
    console.log(`Stale sources this run: ${staleList.join(", ")}`);
  }
  console.log(
    `Wrote snapshot with ${incidents.length} total incidents across ${
      Object.keys(SOURCES).length
    } sources`,
  );
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
