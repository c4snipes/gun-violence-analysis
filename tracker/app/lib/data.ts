import { readFile } from "node:fs/promises";
import { join } from "node:path";

import type { CitationsFile, Incident, TrackerSnapshot } from "@/types/data";

const DATA_DIR = join(process.cwd(), "public", "data");

/**
 * Load the current snapshot, or null if the refresh job has never run.
 *
 * Returning null rather than throwing matters for the first deploy: the data
 * files are produced by the scheduled workflow and committed afterwards, so
 * on a fresh clone they do not exist yet. A build that dies on a missing
 * snapshot cannot produce the site that the workflow later populates.
 */
export async function loadSnapshot(): Promise<TrackerSnapshot | null> {
  return readJson<TrackerSnapshot>(join(DATA_DIR, "snapshot.json"));
}

export async function loadIncidents(): Promise<Incident[]> {
  return (await readJson<Incident[]>(join(DATA_DIR, "incidents.json"))) ?? [];
}

/**
 * Citations are optional enrichment, so a missing file resolves to {} rather
 * than null: unlike a missing snapshot, it never needs to block rendering.
 */
export async function loadCitations(): Promise<CitationsFile> {
  return (await readJson<CitationsFile>(join(DATA_DIR, "citations.json"))) ?? {};
}

async function readJson<T>(path: string): Promise<T | null> {
  try {
    return JSON.parse(await readFile(path, "utf-8")) as T;
  } catch (err) {
    if ((err as NodeJS.ErrnoException).code === "ENOENT") return null;
    throw err;
  }
}
