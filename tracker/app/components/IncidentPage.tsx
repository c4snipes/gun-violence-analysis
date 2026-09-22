"use client";

import { createContext, useContext, useState } from "react";

export const INCIDENT_PAGE_SIZE = 8;

interface PageState {
  page: number;
  setPage: (n: number) => void;
  /** Total rows being paged over, so consumers can agree on the page count. */
  total: number;
}

const Ctx = createContext<PageState | null>(null);

/**
 * Shared paging state for Table 1 and its citation footnotes.
 *
 * The two live in different parts of the page -- the table inside the figures
 * section, the footnotes in their own block near the foot -- but they describe
 * the same eight rows. Before paging that was implicit, because the table was
 * always the newest eight. Now the footnotes have to follow whichever page is
 * showing, or they annotate rows the reader cannot see.
 *
 * That is not hypothetical: the first version of this paged the table but left
 * the footnotes covering all 433 incidents, and the block filled with dozens of
 * "search local coverage" links for incidents nowhere on screen.
 *
 * A context rather than lifting the markup: keeping the citation block visually
 * separate from the numbered source footnotes is deliberate -- it is
 * unconfirmed evidence, not a fifth dataset -- and that separation is worth
 * more than the simplicity of nesting it under the table.
 */
export function IncidentPageProvider({
  total,
  children,
}: {
  total: number;
  children: React.ReactNode;
}) {
  const [page, setPage] = useState(0);
  return <Ctx.Provider value={{ page, setPage, total }}>{children}</Ctx.Provider>;
}

export function useIncidentPage(): PageState & {
  pageCount: number;
  /** Clamped page index, for data that shrank under a mounted component. */
  current: number;
  start: number;
  end: number;
} {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useIncidentPage must be used inside IncidentPageProvider");

  const pageCount = Math.max(1, Math.ceil(ctx.total / INCIDENT_PAGE_SIZE));
  const current = Math.min(ctx.page, pageCount - 1);
  const start = current * INCIDENT_PAGE_SIZE;
  return { ...ctx, pageCount, current, start, end: start + INCIDENT_PAGE_SIZE };
}
