"use client";

import { useIncidentPage } from "./IncidentPage";
import type { CitationFootnote } from "../lib/citations";

/**
 * Citation footnotes for the incidents currently on screen.
 *
 * Numbering restarts per page, and deliberately: a dagger marker in the table
 * points at a note in this block, so the two only line up if both describe the
 * same eight rows. Global numbering would leave a reader on page 7 looking at
 * †1 in the table and a note about an incident from page 1.
 *
 * Kept visually distinct from the numbered source footnotes above it. These are
 * unconfirmed automated matches, not one of the four datasets, and the styling
 * should agree with the copy rather than lend them authority.
 */
export default function CitationFootnotes({
  notes,
}: {
  /** One entry per incident, index-aligned with the full incident list. */
  notes: (CitationFootnote | null)[];
}) {
  const { start, end } = useIncidentPage();
  const visible = notes.slice(start, end).filter((n): n is CitationFootnote => n !== null);

  if (visible.length === 0) return null;

  return (
    <footer className="footnotes citation-footnotes">
      <p className="table-note">
        Related news coverage, matched automatically and unconfirmed. Not one of the four
        datasets, and it does not resolve any definition above.
      </p>
      {visible.map((note, i) => (
        <div key={note.url}>
          <sup>{`†${i + 1}`}</sup> {note.text}{" "}
          <a href={note.url} target="_blank" rel="noopener noreferrer">
            {note.url}
          </a>
        </div>
      ))}
    </footer>
  );
}
