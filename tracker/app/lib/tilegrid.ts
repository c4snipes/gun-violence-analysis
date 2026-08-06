/**
 * Equal-area tile grid layout for the 50 states.
 *
 * Row/column positions on a 12x8 grid, following the conventional US tile
 * grid arrangement. Every state gets one identical square, which is the
 * point: a geographic choropleth sizes states by land area, so Montana and
 * Wyoming dominate the visual field while carrying almost no population.
 * For a per-capita rate that inverts the message.
 *
 * The District of Columbia is omitted because the underlying dataset covers
 * the 50 states only. Adding a DC tile would imply a figure we don't have.
 *
 * Coordinates are 1-indexed to drop straight into CSS grid-column/grid-row.
 */

export interface Tile {
  code: string;
  state: string;
  col: number;
  row: number;
}

export const TILE_GRID: Tile[] = [
  { code: "AK", state: "Alaska", col: 1, row: 1 },
  { code: "ME", state: "Maine", col: 12, row: 1 },

  { code: "VT", state: "Vermont", col: 11, row: 2 },
  { code: "NH", state: "New Hampshire", col: 12, row: 2 },

  { code: "WA", state: "Washington", col: 1, row: 3 },
  { code: "ID", state: "Idaho", col: 2, row: 3 },
  { code: "MT", state: "Montana", col: 3, row: 3 },
  { code: "ND", state: "North Dakota", col: 4, row: 3 },
  { code: "MN", state: "Minnesota", col: 5, row: 3 },
  { code: "WI", state: "Wisconsin", col: 6, row: 3 },
  { code: "MI", state: "Michigan", col: 7, row: 3 },
  { code: "NY", state: "New York", col: 10, row: 3 },
  { code: "RI", state: "Rhode Island", col: 11, row: 3 },
  { code: "MA", state: "Massachusetts", col: 12, row: 3 },

  { code: "OR", state: "Oregon", col: 1, row: 4 },
  { code: "NV", state: "Nevada", col: 2, row: 4 },
  { code: "WY", state: "Wyoming", col: 3, row: 4 },
  { code: "SD", state: "South Dakota", col: 4, row: 4 },
  { code: "IA", state: "Iowa", col: 5, row: 4 },
  { code: "IL", state: "Illinois", col: 6, row: 4 },
  { code: "IN", state: "Indiana", col: 7, row: 4 },
  { code: "OH", state: "Ohio", col: 8, row: 4 },
  { code: "PA", state: "Pennsylvania", col: 9, row: 4 },
  { code: "NJ", state: "New Jersey", col: 10, row: 4 },
  { code: "CT", state: "Connecticut", col: 11, row: 4 },

  { code: "CA", state: "California", col: 1, row: 5 },
  { code: "UT", state: "Utah", col: 2, row: 5 },
  { code: "CO", state: "Colorado", col: 3, row: 5 },
  { code: "NE", state: "Nebraska", col: 4, row: 5 },
  { code: "MO", state: "Missouri", col: 5, row: 5 },
  { code: "KY", state: "Kentucky", col: 6, row: 5 },
  { code: "WV", state: "West Virginia", col: 7, row: 5 },
  { code: "VA", state: "Virginia", col: 8, row: 5 },
  { code: "MD", state: "Maryland", col: 9, row: 5 },
  { code: "DE", state: "Delaware", col: 10, row: 5 },

  { code: "AZ", state: "Arizona", col: 2, row: 6 },
  { code: "NM", state: "New Mexico", col: 3, row: 6 },
  { code: "KS", state: "Kansas", col: 4, row: 6 },
  { code: "AR", state: "Arkansas", col: 5, row: 6 },
  { code: "TN", state: "Tennessee", col: 6, row: 6 },
  { code: "NC", state: "North Carolina", col: 7, row: 6 },
  { code: "SC", state: "South Carolina", col: 8, row: 6 },

  { code: "OK", state: "Oklahoma", col: 4, row: 7 },
  { code: "LA", state: "Louisiana", col: 5, row: 7 },
  { code: "MS", state: "Mississippi", col: 6, row: 7 },
  { code: "AL", state: "Alabama", col: 7, row: 7 },
  { code: "GA", state: "Georgia", col: 8, row: 7 },

  { code: "HI", state: "Hawaii", col: 1, row: 8 },
  { code: "TX", state: "Texas", col: 4, row: 8 },
  { code: "FL", state: "Florida", col: 9, row: 8 },
];

export const TILE_COLS = 12;
export const TILE_ROWS = 8;

/** Five-step ink ramp, darkest to lightest. Index 0 means no incidents. */
export const INK_RAMP = ["#141416", "#26262b", "#3c3c3e", "#5e5b56", "#a99d85"];

export function inkStep(value: number, max: number): number {
  if (value <= 0 || max <= 0) return 0;
  const step = Math.ceil((value / max) * (INK_RAMP.length - 1));
  return Math.min(step, INK_RAMP.length - 1);
}
