import { SOURCES, type SourceId } from "./sources";
import type { SourceCounts } from "@/types/data";

/**
 * How long a source may go without a new incident before the run is failed.
 *
 * WHY THIS EXISTS
 * The GVA scrape broke in early August, when GVA appended four columns and the
 * parser's exact cell-count guard began rejecting every row. fetchGVA threw,
 * refresh_data caught it, fell back to cached incidents, and carried on. The
 * nightly job stayed green for seven weeks while the site served August
 * figures behind a "most recent run failed" footnote.
 *
 * Nothing was hidden, and nothing was noticed, because a stale tracker looks
 * exactly like a quiet one -- 25 incidents over a year is plausible. What is
 * not plausible is the SAME 25 for seven weeks, and no check said so.
 *
 * A thrown fetch already marks a source stale. This catches the other shape of
 * failure: a fetch that returns, parses, and is simply never new again -- a
 * feed that has silently stopped, or a parser quietly dropping every recent
 * row while older cached ones persist.
 *
 * THRESHOLDS ARE PER SOURCE, from observed gaps rather than a round number.
 * These sources have very different cadences, and one shared limit would
 * either cry wolf on the slow one or never fire on the fast one:
 *
 *   gva           publishes near-daily; largest observed gap 4 days.
 *                 21 days is over five times that -- loose enough never to
 *                 fire on a genuine lull, tight enough to have caught the
 *                 August break within three weeks instead of seven.
 *   mother_jones  a hand-curated set, six incidents in the last year, with
 *                 gaps up to 78 days that are entirely normal. 180 days will
 *                 not catch a short outage and is not meant to; it catches a
 *                 feed that has stopped for good.
 *
 * Sources absent from this map are exempt, and both exemptions are deliberate:
 * stanford_msa is an archive frozen at 2016, so staleness is its correct
 * state; violence_project returns nothing pending an access request, and a
 * source with no incidents at all has no recency to judge.
 */
export const MAX_QUIET_DAYS: Partial<Record<SourceId, number>> = {
  gva: 21,
  mother_jones: 180,
};

const MS_PER_DAY = 86_400_000;

/**
 * Sources that parsed cleanly but have gone quiet for longer than their
 * cadence allows. Returns one human-readable line per offender, empty when all
 * is well.
 *
 * `now` is injectable so the tests can pin a date rather than depending on how
 * old the committed fixture happens to be on the day they run.
 */
export function findStaleFeeds(totals: SourceCounts[], now: number = Date.now()): string[] {
  const problems: string[] = [];

  for (const t of totals) {
    const limit = MAX_QUIET_DAYS[t.source];
    if (limit === undefined) continue;
    // No incidents at all means nothing to date from. That is either a source
    // still coming up or one already reported stale by a thrown fetch, and in
    // both cases a recency check has nothing to say.
    if (!t.latest_incident_date) continue;

    const days = Math.floor((now - new Date(t.latest_incident_date).getTime()) / MS_PER_DAY);
    if (days > limit) {
      problems.push(
        `${SOURCES[t.source].name}: newest incident is ${t.latest_incident_date}, ` +
          `${days} days ago (limit ${limit})`,
      );
    }
  }
  return problems;
}
