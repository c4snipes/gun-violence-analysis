import { TILE_GRID, TILE_COLS, INK_RAMP, inkStep } from "../lib/tilegrid";
import type { SourceId } from "../lib/sources";
import type { StateStats } from "@/types/data";

interface Props {
  states: StateStats[];
  source: SourceId;
}

export default function StateTileGrid({ states, source }: Props) {
  const byState = new Map(states.map((s) => [s.state, s]));
  const values = TILE_GRID.map(
    (t) => byState.get(t.state)?.counts_by_source[source]?.per_100k ?? 0,
  );
  const max = Math.max(...values, 0);

  return (
    <>
      <div className="tilegrid" style={{ gridTemplateColumns: `repeat(${TILE_COLS}, 1fr)` }}>
        {TILE_GRID.map((tile) => {
          const value = byState.get(tile.state)?.counts_by_source[source]?.per_100k ?? 0;
          const step = inkStep(value, max);
          const light = step >= 3;
          return (
            <div
              key={tile.code}
              className="tile"
              style={{
                gridColumn: tile.col,
                gridRow: tile.row,
                background: INK_RAMP[step],
              }}
              title={`${tile.state}: ${value.toFixed(2)} per 100,000`}
            >
              <span className="tile-code" style={{ color: light ? "#141416" : "#8b8880" }}>
                {tile.code}
              </span>
              <span className="tile-value" style={{ color: light ? "#3c3c3e" : "#6d6b66" }}>
                {value > 0 ? value.toFixed(1) : "\u00B7"}
              </span>
            </div>
          );
        })}
      </div>
      <div className="ramp">
        <span>0</span>
        <div className="ramp-swatches">
          {INK_RAMP.map((c) => (
            <span key={c} style={{ background: c }} />
          ))}
        </div>
        <span>{max.toFixed(1)}</span>
      </div>
    </>
  );
}
