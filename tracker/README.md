# Tracker

Next.js front end for the gun violence tracker. Deployed to Vercel. Reads pre-computed JSON committed by the daily refresh workflow at the repo root.

Part of a monorepo. See [../README.md](../README.md) for the whole project and [../analysis](../analysis) for the statistical package this consumes.

## Running locally

```bash
npm install
python scripts/refit_model.py --out public/data/model.json
npm run refresh-data
npm run dev
```

`refit_model.py` imports from `../analysis/src`, so install the analysis package first (`cd ../analysis && pip install -e .`).

## Pages

| Route | Contents |
|---|---|
| `/` | Four source panels, state tile grid, recent incident matrix, footnotes |
| `/sources` | Each dataset's definition, coverage, cadence, and terms |
| `/model` | Coefficient table with intervals, permutation importance |
| `/about` | Method and limitations |

## Design

Laid out as a statistical release rather than a dashboard: hairline rules instead of cards, IBM Plex Serif for prose and Mono for figures, numbered footnotes carrying the caveats.

Two rules the layout exists to enforce:

**No single headline number.** The four sources sit in equal columns. Promoting one to a hero figure would imply the others are variants of it rather than answers to different questions.

**Absent data reads as absent.** A source with no figure shows an em dash and a reason, never a zero. A zero asserts that nothing happened.

## Definition matching

`app/lib/definitions.ts` evaluates each incident against all four definitions and returns one of three results, not a boolean.

| Result | Glyph | Meaning |
|---|---|---|
| `yes` | filled dot | Qualifies. Either it came from that dataset, or it clears a threshold with no contextual condition |
| `no` | em dash | Provably fails the casualty threshold |
| `unknown` | open dot | Clears the threshold, but the contextual condition is not recorded in our data |

The third case exists because most definitions turn on facts a casualty count cannot supply. Mother Jones requires a public place and excludes gang, robbery, and domestic incidents. Nothing in a scraped count of killed and injured establishes any of that. Rendering unknown as a match would overstate the count; rendering it as a miss would understate it.

## State tile grid

`app/lib/tilegrid.ts` holds a 12x8 equal-area layout of the 50 states.

A geographic choropleth sizes each state by land area, so Montana, Wyoming, and Alaska dominate while carrying almost no population. For a per-capita rate that inverts the message the map is supposed to carry. Equal tiles cost geographic precision and buy accurate visual weight.

DC is omitted because the underlying dataset covers the 50 states only. A DC tile would imply a figure that doesn't exist.

## Deploying

Vercel must be pointed at this subdirectory:

**Project Settings → General → Root Directory → `tracker`**

Otherwise the build runs at the repo root, finds no `package.json`, and fails.

## Data files

`public/data/` holds `snapshot.json`, `incidents.json`, and `model.json`, all committed by CI rather than generated at build time. Pages use ISR with `revalidate = 3600`, so the deployed site picks up new data within an hour of a commit without a redeploy.
