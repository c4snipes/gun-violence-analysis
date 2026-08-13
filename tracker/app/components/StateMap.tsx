import { formatRate, INK_RAMP, inkStep, RATE_UNIT, toDisplayRate } from "../lib/tilegrid";
import { STATE_PATHS, USMAP_VIEWBOX } from "../lib/usmap";
import type { SourceId } from "../lib/sources";
import type { StateStats } from "@/types/data";

interface Props {
  states: StateStats[];
  source: SourceId;
}

/**
 * Geographic choropleth of the 50 states.
 *
 * Shares INK_RAMP and inkStep with StateTileGrid so the two renderings encode
 * the same value with the same colour, and a reader can move between them
 * without relearning the scale.
 *
 * Note the tradeoff documented in tilegrid.ts: a geographic projection sizes
 * each state by land area, so Montana, Wyoming and Alaska carry far more
 * visual weight than their populations warrant on a per-capita measure. The
 * caption in page.tsx states this; the map is offered because geographic
 * adjacency is legible in a way an abstract grid is not.
 */
export default function StateMap({ states, source }: Props) {
  const byState = new Map(states.map((s) => [s.state, s]));
  const values = STATE_PATHS.map((p) =>
    toDisplayRate(byState.get(p.name)?.counts_by_source[source]?.per_100k ?? 0),
  );
  const max = Math.max(...values, 0);

  return (
    <>
      <svg
        className="statemap"
        viewBox={USMAP_VIEWBOX}
        role="img"
        aria-label={`Choropleth of incidents ${RATE_UNIT} by state, ${source} definition`}
      >
        {STATE_PATHS.map((p) => {
          const stat = byState.get(p.name);
          const value = toDisplayRate(stat?.counts_by_source[source]?.per_100k ?? 0);
          const counts = stat?.counts_by_source[source];
          // A state with no qualifying incident is not the same as a state we
          // have no figure for. Both render dark, so the tooltip carries the
          // distinction in words rather than relying on colour alone.
          const label = stat
            ? `${p.name} — ${formatRate(value)} ${RATE_UNIT} · ` +
              `${counts?.incidents ?? 0} incidents, ${counts?.killed ?? 0} killed, ` +
              `${counts?.injured ?? 0} injured`
            : `${p.name} — no figure available`;
          return (
            <path key={p.code} d={p.d} fill={INK_RAMP[inkStep(value, max)]} className="statepath">
              <title>{label}</title>
            </path>
          );
        })}
      </svg>
      <div className="ramp">
        <span>0</span>
        <div className="ramp-swatches">
          {INK_RAMP.map((c) => (
            <span key={c} style={{ background: c }} />
          ))}
        </div>
        <span>{formatRate(max)}</span>
      </div>
    </>
  );
}
