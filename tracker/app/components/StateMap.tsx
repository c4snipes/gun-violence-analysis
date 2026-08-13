"use client";

import { useState } from "react";

import { formatRate, INK_RAMP, inkStep, RATE_UNIT, toDisplayRate } from "../lib/tilegrid";
import { STATE_PATHS, USMAP_VIEWBOX } from "../lib/usmap";
import type { SourceId } from "../lib/sources";
import type { StateStats } from "@/types/data";

interface Props {
  states: StateStats[];
  source: SourceId;
}

interface Readout {
  name: string;
  code: string;
  /** null when we hold no figure for the state at all, as opposed to a zero. */
  value: number | null;
  incidents: number;
  killed: number;
  injured: number;
}

/**
 * Geographic choropleth with a fixed readout, replacing the separate tile grid.
 *
 * The readout sits in a reserved row above the map rather than following the
 * cursor, so figures land in the same place every time and the layout never
 * shifts as the pointer moves. Native SVG <title> tooltips are kept as well --
 * they are what a screen reader and a touch device get.
 *
 * The equal-area tile grid this replaces existed because a geographic
 * projection sizes states by land area, over-weighting sparsely populated
 * states on a per-capita measure. That tradeoff is now stated in the caption
 * rather than answered by a second figure.
 */
export default function StateMap({ states, source }: Props) {
  const [hovered, setHovered] = useState<Readout | null>(null);

  const byState = new Map(states.map((s) => [s.state, s]));
  const values = STATE_PATHS.map((p) =>
    toDisplayRate(byState.get(p.name)?.counts_by_source[source]?.per_100k ?? 0),
  );
  const max = Math.max(...values, 0);

  return (
    <>
      <div className="map-readout" aria-live="polite">
        {hovered ? (
          <>
            <span className="map-readout-state">{hovered.name}</span>
            <span className="map-readout-value">
              {hovered.value === null ? "—" : formatRate(hovered.value)}
            </span>
            <span className="map-readout-unit">
              {hovered.value === null ? "no figure available" : RATE_UNIT}
            </span>
            {hovered.value !== null && (
              <span className="map-readout-counts">
                {hovered.incidents} incidents &middot; {hovered.killed} killed &middot;{" "}
                {hovered.injured} injured
              </span>
            )}
          </>
        ) : (
          <span className="map-readout-idle">Hover a state for its figures</span>
        )}
      </div>

      <svg
        className="statemap"
        viewBox={USMAP_VIEWBOX}
        role="img"
        aria-label={`Choropleth of incidents ${RATE_UNIT} by state, ${source} definition`}
        onMouseLeave={() => setHovered(null)}
      >
        {STATE_PATHS.map((p) => {
          const stat = byState.get(p.name);
          const counts = stat?.counts_by_source[source];
          const value = stat ? toDisplayRate(counts?.per_100k ?? 0) : null;
          // A state with no qualifying incident is not the same as a state we
          // hold no figure for. Both render dark, so the words carry the
          // distinction rather than the colour.
          const label =
            value === null
              ? `${p.name} — no figure available`
              : `${p.name} — ${formatRate(value)} ${RATE_UNIT} · ${counts?.incidents ?? 0} incidents, ` +
                `${counts?.killed ?? 0} killed, ${counts?.injured ?? 0} injured`;
          return (
            <path
              key={p.code}
              d={p.d}
              fill={INK_RAMP[inkStep(value ?? 0, max)]}
              className="statepath"
              onMouseEnter={() =>
                setHovered({
                  name: p.name,
                  code: p.code,
                  value,
                  incidents: counts?.incidents ?? 0,
                  killed: counts?.killed ?? 0,
                  injured: counts?.injured ?? 0,
                })
              }
            >
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
