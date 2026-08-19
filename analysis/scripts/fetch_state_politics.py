"""Build a state-year panel of Attorney General party and legislative control.

WHY THIS SOURCE
No machine-readable authoritative panel exists for 2014-2023. Verified during
design:
  * Correlates of State Policy / Klarner -- political variables end 2010-2016;
    the best (ranney4_control) covers 3 of 10 years, most end 2011.
  * NCSL -- the partisan-composition page is current-year only, and the
    per-year archive URLs return 200 but render nothing at all, 0 tables.
  * Ballotpedia -- 202 bot gate.
  * NAAG -- 403, current members only.
  * agstudies.org -- current-AG profile pages, ~1.4KB, no history, no tables.
  * Book of the States -- has both party and an authoritative
    'Method of selection' column, but only 2022 and 2023 are online.

Wikipedia's "Political party strength in X" pages carry Governor, Attorney
General and both legislative chambers in one year-indexed table, so a single
fetch per state yields every remaining political variable.

THE ROWSPAN TRAP
These tables use rowspan heavily: an official who serves several years appears
once, spanning those rows. Texas 2016 has two cells and 2018 has none, because
everything above carries down. Reading cells positionally therefore misaligns
almost every row. This script expands rowspan and colspan into a full grid
before reading anything.

VALIDATION
The same table carries Governor, which was already built and hand-checked
against five documented traps in fetch_governors.py. This script cross-checks
its Governor column against data/governors_2014_2023.csv and reports any
disagreement, so a parsing error surfaces as a mismatch rather than as quietly
wrong data.

NEBRASKA
Nebraska's legislature is officially nonpartisan and unicameral. Its
legislative control is recorded as "Nonpartisan", never as a party, and never
imputed from registration figures.

Usage:
    python scripts/fetch_state_politics.py --out data/state_politics_2014_2023.csv
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from gun_violence.constants import FULL_STATE_NAMES

API = "https://en.wikipedia.org/w/api.php"
UA = "gun-violence-analysis/0.1 (research; contact via repository)"
START_YEAR, END_YEAR = 2014, 2023

# Wikipedia titles that are not "Political party strength in {state}". The plain
# Georgia title is an article about the country, and it is not a redirect, so
# redirects=1 does not reach the state's page.
TITLE_OVERRIDES = {
    "Georgia": "Political party strength in Georgia (U.S. state)",
    "Washington": "Political party strength in Washington (state)",
    "New York": "Political party strength in New York (state)",
}

# AG party is only an independently determined political variable where the AG
# is popularly elected. In seven states it is not, and recording an appointed
# AG's party as if it were equivalent would conflate two different things --
# the appointee's party is downstream of whoever appointed them.
#
# Source: Wikipedia, "State attorney general", which states "43 states have an
# elected attorney general", that the AG is "appointed by the governor" in
# Alaska, Hawaii, New Hampshire, New Jersey and Wyoming, that in Maine it "is
# elected by the state Legislature", and that in Tennessee it "is appointed by
# the Tennessee Supreme Court". 5 + 1 + 1 = 7, and 50 - 7 = 43, which matches
# that article's own count.
AG_SELECTION = {
    "Alaska": "Appointed by governor",
    "Hawaii": "Appointed by governor",
    "New Hampshire": "Appointed by governor",
    "New Jersey": "Appointed by governor",
    "Wyoming": "Appointed by governor",
    "Maine": "Elected by legislature",
    "Tennessee": "Appointed by supreme court",
}


def fetch_html(page: str, attempts: int = 5) -> str:
    """Rendered HTML for a page, with backoff on Wikipedia's 429 throttle."""
    params = {"action": "parse", "format": "json", "prop": "text", "redirects": "1", "page": page}
    url = f"{API}?{urllib.parse.urlencode(params)}"
    delay = 5.0
    for attempt in range(1, attempts + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.load(resp)
            if "error" in data:
                raise RuntimeError(data["error"].get("info", "unknown API error"))
            return data["parse"]["text"]["*"]
        except urllib.error.HTTPError as exc:
            if exc.code != 429 or attempt == attempts:
                raise
            print(f"      429, waiting {delay:.0f}s")
            time.sleep(delay)
            delay *= 2
    raise RuntimeError("unreachable")


def _text(cell_html: str) -> str:
    txt = re.sub(r"<sup.*?</sup>", " ", cell_html, flags=re.DOTALL)  # footnote markers
    txt = re.sub(r"<[^>]+>", " ", txt)
    return re.sub(r"\s+", " ", html.unescape(txt)).strip()


def expand_table(table_html: str) -> list[list[str]]:
    """Expand an HTML table into a rectangular grid, honouring rowspan/colspan.

    Without this, a year whose officials all carry over from the previous row
    has fewer cells than columns and everything shifts left.
    """
    grid: list[list[str | None]] = []
    pending: dict[tuple[int, int], str] = {}  # (row, col) -> value from a span

    rows = re.findall(r"<tr.*?</tr>", table_html, re.DOTALL)
    for r_i, row in enumerate(rows):
        while len(grid) <= r_i:
            grid.append([])
        out = grid[r_i]
        col = 0
        for cell in re.findall(r"<t[hd][^>]*>.*?</t[hd]>", row, re.DOTALL):
            while (r_i, col) in pending:
                while len(out) <= col:
                    out.append(None)
                out[col] = pending.pop((r_i, col))
                col += 1
            m_rs = re.search(r'rowspan="?(\d+)', cell)
            m_cs = re.search(r'colspan="?(\d+)', cell)
            rs = int(m_rs.group(1)) if m_rs else 1
            cs = int(m_cs.group(1)) if m_cs else 1
            val = _text(cell)
            for dc in range(cs):
                while len(out) <= col + dc:
                    out.append(None)
                out[col + dc] = val
                for dr in range(1, rs):
                    pending[(r_i + dr, col + dc)] = val
            col += cs
        while (r_i, col) in pending:
            while len(out) <= col:
                out.append(None)
            out[col] = pending.pop((r_i, col))
            col += 1
    return [[c if c is not None else "" for c in row] for row in grid]


_PARTY_TAG = re.compile(r"\((R|D|I|DFL|Ind\.?)\)", re.IGNORECASE)
_PARTY_FROM_TAG = {"r": "Republican", "d": "Democratic", "dfl": "Democratic",
                   "i": "Independent", "ind": "Independent", "ind.": "Independent"}


def party_of(cell: str) -> str | None:
    m = _PARTY_TAG.search(cell)
    if not m:
        return None
    return _PARTY_FROM_TAG.get(m.group(1).lower().rstrip("."))


_SEATS = re.compile(r"(\d+)\s*([RDI])\b", re.IGNORECASE)


def chamber_control(cell: str) -> str | None:
    """Majority party from a '20R, 11D' style seat count."""
    counts: dict[str, int] = {}
    for n, p in _SEATS.findall(cell):
        counts[p.upper()] = counts.get(p.upper(), 0) + int(n)
    if not counts:
        return None
    top = max(counts.values())
    winners = [p for p, v in counts.items() if v == top]
    if len(winners) > 1:
        return "Split"
    return {"R": "Republican", "D": "Democratic", "I": "Independent"}[winners[0]]


# A column naming a federal body must never be read as the state legislature.
# 'U.S. Senate (Class I)' contains 'senate', so a plain substring match would
# silently record the federal delegation as state Senate control.
_FEDERAL = ("u.s.", "us ", "united states", "congress", "electoral")

# The AG column is spelled at least three ways across the 50 pages:
# "Attorney General" (Texas), "Attorney Gen." (Iowa), "Atty. Gen." (Georgia).
_AG_LABEL = re.compile(r"\batt(?:y|orney)\.?\s*gen", re.IGNORECASE)


def _is_state_chamber(label: str, *names: str) -> bool:
    if any(f in label for f in _FEDERAL):
        return False
    return any(n in label for n in names)


def find_columns(grid: list[list[str]]) -> tuple[int, dict[str, int]] | None:
    """Locate the header row carrying 'Attorney General' and map column indices.

    Header labels vary between states -- Alabama writes 'State Senate' and
    'State House' where Texas writes 'Senate' and 'House', and several states
    use 'Assembly' or 'House of Delegates'. Matching is therefore by substring,
    guarded against the federal columns on the same row.

    Scans every row rather than the first few: some states' tables begin with
    several empty spacer rows before the header.
    """
    for r_i, row in enumerate(grid):
        joined = [c.lower().strip() for c in row]
        if not any(_AG_LABEL.search(c) for c in joined):
            continue
        # A Wikipedia article ends with large navigation templates, and those
        # navboxes mention "attorney general" in passing. Iowa's table 9 is the
        # footer box -- 'Topics | Archaeology | Regions | Largest cities' -- and
        # matching it produced zero usable years while masking the real table.
        # The data table always has a Year column; a navbox never does.
        if not any(c == "year" or c.startswith("year") for c in joined):
            continue
        cols: dict[str, int] = {}
        for c_i, c in enumerate(joined):
            if (c == "year" or c.startswith("year")) and "year" not in cols:
                cols["year"] = c_i
            elif _AG_LABEL.search(c) and "attorney_general" not in cols:
                cols["attorney_general"] = c_i
            elif "governor" in c and "lt" not in c and "lieutenant" not in c \
                    and "governor" not in cols:
                cols["governor"] = c_i
            elif _is_state_chamber(c, "senate") and "senate" not in cols:
                cols["senate"] = c_i
            elif _is_state_chamber(c, "house", "assem", "delegates") \
                    and "house" not in cols:
                cols["house"] = c_i
        if "attorney_general" in cols:
            return r_i, cols
    return None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--governors", type=Path, default=Path("data/governors_2014_2023.csv"))
    ap.add_argument("--sleep", type=float, default=2.0)
    args = ap.parse_args()

    retrieved = datetime.now(timezone.utc).date().isoformat()
    states = sorted(FULL_STATE_NAMES - {"District of Columbia"})

    rows: list[dict[str, str]] = []
    done: set[str] = set()
    if args.out.exists():
        with args.out.open() as fh:
            existing = list(csv.DictReader(fh))
        by_state: dict[str, list[dict[str, str]]] = {}
        for r in existing:
            by_state.setdefault(r["state"], []).append(r)
        for st, rs in by_state.items():
            if len(rs) == END_YEAR - START_YEAR + 1:
                rows.extend(rs)
                done.add(st)
        if done:
            print(f"resuming: {len(done)} state(s) already complete\n")

    problems: list[str] = []
    for i, state in enumerate(states, 1):
        if state in done:
            continue
        page = TITLE_OVERRIDES.get(state, f"Political party strength in {state}")
        try:
            grid_tables = [expand_table(t) for t in
                           re.findall(r"<table.*?</table>", fetch_html(page), re.DOTALL)]
        except Exception as exc:  # noqa: BLE001
            problems.append(f"{state}: fetch failed: {exc}")
            continue

        found = 0
        # Score candidates and take the richest: the real table carries Year,
        # Governor, Attorney General and both chambers, while a stray match
        # carries only one or two of them.
        candidates = []
        for grid in grid_tables:
            hit = find_columns(grid)
            if hit:
                candidates.append((len(hit[1]), grid, hit))
        candidates.sort(key=lambda c: -c[0])
        for _, grid, hit in candidates:
            hdr_i, cols = hit
            for row in grid[hdr_i + 1:]:
                y_i = cols.get("year", 0)
                if not row or y_i >= len(row) or not row[y_i].strip():
                    continue
                m = re.match(r"^(\d{4})", row[y_i].strip())
                if not m:
                    continue
                year = int(m.group(1))
                if not (START_YEAR <= year <= END_YEAR):
                    continue

                def cell(key: str, _row: list[str] = row, _cols: dict[str, int] = cols) -> str:
                    """Read a named column from this row.

                    Loop variables are bound as defaults so the closure cannot
                    capture a later iteration's values.
                    """
                    idx = _cols.get(key)
                    return _row[idx] if idx is not None and idx < len(_row) else ""

                sen = chamber_control(cell("senate"))
                hou = chamber_control(cell("house"))
                if state == "Nebraska":
                    sen = hou = leg = "Nonpartisan"
                elif sen and hou:
                    leg = sen if sen == hou else "Split"
                else:
                    leg = ""

                rows.append({
                    "state": state,
                    "year": str(year),
                    "ag_party": party_of(cell("attorney_general")) or "",
                    "ag_selection": AG_SELECTION.get(state, "Elected"),
                    "senate_control": sen or "",
                    "house_control": hou or "",
                    "legislature_control": leg,
                    "governor_party_check": party_of(cell("governor")) or "",
                    "source": page,
                    "retrieved": retrieved,
                })
                found += 1
            if found:
                break

        # A year can appear on more than one row when an officeholder changed
        # mid-term -- Alabama 2017 has two, Luther Strange having resigned as
        # Attorney General. Collapse them, but only when they agree. A genuine
        # disagreement means the party changed hands during the year and the
        # 1 July rule cannot be resolved from a year-indexed table, so it is
        # reported rather than silently resolved to whichever row came last.
        merged: dict[int, dict[str, str]] = {}
        conflicts: list[int] = []
        for r in [r for r in rows if r["state"] == state]:
            y = int(r["year"])
            prev = merged.get(y)
            if prev is None:
                merged[y] = r
                continue
            for key in ("ag_party", "senate_control", "house_control", "governor_party_check"):
                if prev[key] and r[key] and prev[key] != r[key] and y not in conflicts:
                    conflicts.append(y)
                # keep whichever row actually carries a value
                prev[key] = prev[key] or r[key]
            prev["legislature_control"] = prev["legislature_control"] or r["legislature_control"]
            prev["ag_selection"] = prev["ag_selection"] or r["ag_selection"]
        rows = [r for r in rows if r["state"] != state] + [merged[y] for y in sorted(merged)]
        for y in conflicts:
            problems.append(f"{state} {y}: mid-year party change, needs manual resolution")

        n = len(merged)
        if n != END_YEAR - START_YEAR + 1:
            problems.append(f"{state}: {n} of 10 years")
        print(f"  [{i:2d}/50] {state}: {n} years" + (f"  ({len(conflicts)} conflict)" if conflicts else ""))
        time.sleep(args.sleep)

    rows.sort(key=lambda r: (r["state"], int(r["year"])))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fields = ["state", "year", "ag_party", "ag_selection", "senate_control", "house_control",
              "legislature_control", "governor_party_check", "source", "retrieved"]
    with args.out.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    expected = len(states) * (END_YEAR - START_YEAR + 1)
    print(f"\nresolved {len(rows)} of {expected} state-years -> {args.out}")

    # Cross-check Governor against the already-verified series.
    if args.governors.exists():
        with args.governors.open() as fh:
            gov = {(r["state"], r["year"]): r["party"] for r in csv.DictReader(fh)}
        checked = mismatched = 0
        examples: list[str] = []
        for r in rows:
            want = gov.get((r["state"], r["year"]))
            got = r["governor_party_check"]
            if want and got:
                checked += 1
                if want != got:
                    mismatched += 1
                    if len(examples) < 8:
                        examples.append(f"{r['state']} {r['year']}: governors={want} politics={got}")
        print(f"governor cross-check: {checked - mismatched}/{checked} agree")
        for e in examples:
            print("   MISMATCH", e)

    coverage = {k: sum(1 for r in rows if r[k]) for k in
                ("ag_party", "legislature_control", "senate_control", "house_control")}
    print("non-empty:", coverage)
    if problems:
        print(f"\n{len(problems)} problem(s):")
        for p in problems[:20]:
            print("   ", p)


if __name__ == "__main__":
    main()
