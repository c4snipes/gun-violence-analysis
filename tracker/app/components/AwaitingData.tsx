import Masthead from "./Masthead";

/**
 * Shown when no snapshot exists yet, which is the state of a fresh clone
 * before the scheduled refresh has run for the first time.
 *
 * Deliberately reports no figures at all rather than zeros. A zero here
 * would assert that no incident occurred, which is a claim about the world
 * rather than a statement about this site's data.
 */
export default function AwaitingData({ current }: { current: string }) {
  return (
    <>
      <Masthead current={current} />
      <h1 className="page-title">No figures yet</h1>
      <p className="page-intro">
        The scheduled collection has not produced a snapshot. This is the expected state of a fresh
        deployment: figures are gathered by a job that runs at 06:00 UTC and committed to the
        repository afterwards, so the first set appears within a day of going live.
      </p>
      <p className="page-intro" style={{ marginTop: "1.25rem" }}>
        No counts are shown in the meantime. A zero would state that no incident met a definition,
        which is not what an absent collection run establishes.
      </p>
    </>
  );
}
