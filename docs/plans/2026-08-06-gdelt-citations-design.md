# GDELT news-citation enrichment — design

Status: validated in brainstorming, not yet implemented.

## Purpose

Surface local/regional news coverage next to incidents already sourced from
the four canonical datasets (GVA, Mother Jones, Stanford MSA, Violence
Project), as public-facing evidence a reader can inspect themselves. This is
**not** a fifth tracked source and it never resolves `definitions.ts`'s
`unknown` verdict to `yes`/`no` — that three-valued logic, and the tests that
protect it, are untouched by this feature. Context clears from unrecorded to
"here's what's been found," not to "confirmed."

## Why this shape (premortem findings)

The main risk isn't technical fragility, it's a *confident wrong match* —
GDELT is unauthenticated text search with no per-incident identifiers to
match against, so it can return an article about a different shooting in the
same city. On a site whose credibility rests on precision (equal-weighted
sources, three-valued definitions, no headline number), a wrong citation
sitting next to a real incident is worse than showing nothing. That risk
drove two decisions below: a strict/fallback tier instead of "always show
GDELT's top match," and hedged, visually distinct copy instead of presenting
citations as verification.

## Matching

New fetcher: `tracker/app/lib/fetchers/gdelt.ts`, using GDELT's DOC 2.0 API
(`https://api.gdeltproject.org/api/v2/doc/doc`, no key required).

**Strict tier** — query `"shooting" "{city}" "{state}"`, `sourcecountry=US`,
date window `incident.date - 1` to `incident.date + 2` (covers report lag /
timezone without inviting unrelated same-city stories). A result is accepted
only if its title/snippet contains **both** the city name **and** the state
name. Casualty-count matching was considered and dropped — GDELT's DOC API
only returns short snippets, not full text, and news figures round/update
constantly, so gating on a number there would be over-fitting to noisy data.

**Fallback** — when no result clears the strict bar, don't show a specific
article. Instead compute a plain search-link URL from data already on the
incident (city, state, date) — no extra API call, no matching-accuracy risk,
because the site never asserts a specific article is about this incident.

**Zero GDELT results in the window at all** → no marker, matching the site's
existing "absent renders as absent" rule.

## Data model

`tracker/public/data/citations.json`, committed daily alongside
`snapshot.json`/`incidents.json`/`model.json`:

```ts
type CitationsFile = Record<string /* incident id */, {
  queried_at: string; // ISO — makes even zero-result lookups permanent
  had_results: boolean; // true if GDELT returned >=1 raw article in the window
  match: null | { title: string; url: string; source_domain: string; published_at: string };
  // match is null whenever the strict tier found nothing. The UI then
  // checks had_results: true falls back to a computed search link
  // (something was found, just not confidently matched); false shows no
  // marker at all ("absent renders as absent" — nothing was found).
}>;
```

Kept as a file separate from `Incident`/`incidents.json` on purpose:
`Incident` flows through `definitions.ts`, `evaluateAll`, and the
state-aggregation loop in `refresh_data.ts`. None of them need to know this
concept exists, and keeping it out entirely means it structurally cannot leak
into the yes/no/unknown logic no matter how the code evolves later.

## Pipeline integration

In `scripts/refresh_data.ts`, after `fetchAllSources()` resolves and
`incidents` is final (not inside the `FETCHERS` registry — GDELT isn't a
source of incidents, it's per-incident enrichment that has to run after the
incident list is known):

1. Load existing `citations.json` (same try/catch-empty pattern already used
   for `incidents.json`).
2. For each incident **not already present as a key**, call
   `fetchGdeltCitation(incident)`. Already-seen ids — including zero-result
   ones — are never re-queried. Coverage of an incident that got nothing
   yesterday essentially never appears tomorrow; re-querying forever wastes
   API budget for no benefit, and daily volume then scales with *new*
   incidents per day, not the full 365-day window.
3. Each per-incident call is independently try/caught. A failed/rate-limited
   request logs a warning and skips that one incident this run — no entry
   written, retried next run — but never fails the job and never marks any
   of the four real sources stale. GDELT failing is "try again tomorrow," not
   a dashboard-visible stale glyph.
4. Wrap the fetch in a timeout (new `fetchWithTimeout` helper in
   `fetchers/util.ts`) — a per-incident loop is exactly where one hung
   request would otherwise stall the whole daily job indefinitely. None of
   the four existing fetchers bound their `fetch()` today; this is the first
   place it actually bites, so it's worth fixing now rather than after.

## UI

Extends the existing footnote pattern in `app/page.tsx` (`notes` /
`noteIndex` / `<sup>`) rather than adding a new interaction model —
`IncidentMatrix` is a CSS Grid of divs, not a `<table>`, so a per-row
`<details>` disclosure would need real layout surgery; the footnote pattern
needs none.

Citations get their own marker, **`†`**, distinct from the four sources'
numbered footnotes — visually unmistakable as a different *kind* of thing,
not a fifth data source claiming equal standing with GVA/Mother
Jones/Stanford MSA/Violence Project.

Copy is explicit either way, never implying confirmation:
- Strict match: `† Coverage possibly related to this incident (unconfirmed): "{title}" — {source_domain}.`
- Fallback: `† Search local coverage of this incident and date →` (links to the computed search URL).
- No marker at all when GDELT returned nothing in the window — same "absent
  renders as absent" rule the rest of the site already follows.

## Testing

Pure-function tests only, matching the existing pattern (`gva.test.ts`,
`definitions.test.ts`) — no component-rendering framework exists in this repo
and one feature isn't reason enough to add one.

- `gdelt.test.ts` (fixture-mocked GDELT responses): strict tier accepts
  city+state-in-window; rejects and falls back when only one term matches or
  the date is outside the window; zero results → no marker; a failed/timed-out
  request skips that incident without writing an entry or failing the job.
- Caching logic in the refresh script: already-cached ids aren't re-queried;
  new ids are; zero-result lookups get a permanent `queried_at` stamp too.
- `footnoteForCitation(incident, citationsEntry)` as an isolated pure
  function, tested for its three output shapes: strict-match hedged copy,
  fallback search-link copy, and no output.

## Known limitations (documented, not solved, in v1)

- No filtering of named-minor or otherwise sensitive content in GDELT
  snippets — unfiltered news text, surfaced with hedged copy but not
  reviewed.
- Matching is per-incident text search with no ground-truth linkage; the
  strict tier reduces but does not eliminate false positives.

## Known follow-ups (out of scope here)

Surfaced during this design pass, tracked for later:

- No CI runs `npm test`/`typecheck`/`lint`/`next build` on PRs — only the
  data-refresh cron exists today. The tests this feature (and the two just
  added for GVA/definitions) rely on have no enforcement behind them.
- No `engines` field in `tracker/package.json` — directly caused the
  `--loader tsx` bug found and fixed this session; same class of drift risk
  applies here.
- `npm audit`: 5 high-severity findings rolling up to Next.js 14.2.35,
  fixed in Next 16 — a deliberate major-version upgrade decision, not a side
  effect of this feature.
- `analysis/`: single-year (2020) snapshot, no panel data across years —
  already named in `analysis/README.md`'s "Known limitations." Panel data
  would separate a state's *level* from its *trend* and grow n beyond 50.
- `analysis/`: two documented predictor gaps worth prioritizing when that
  work resumes — trauma-care access (targets the explicitly-named
  shot-vs-died confound) and a gun law strictness index (targets the
  explicitly-named registration-vs-strictness measurement problem). Likely
  sources, unverified: HRSA's Area Health Resources Files or CDC's trauma
  center location data for drive-time-to-Level-I/II-trauma-center by state;
  Giffords Law Center's annual state gun law scorecard
  (giffords.org/lawcenter/resources/scorecard) for the strictness index.
  Both need to be confirmed as actually fetchable/licensable before
  `constants.py`/`build_dataset.py` changes start — this is a data-sourcing
  task, not a coding task, and should happen first.
