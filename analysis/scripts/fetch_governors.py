"""Build a state-year panel of governor party affiliation, 2014-2023.

WHY THIS EXISTS
No agency publishes this as a state-year panel through 2023. The Correlates of
State Policy Project and Klarner series both terminate at 2011 -- verified:
govparty_a, govparty_b, govparty_b_2, govparty_c and even govname1 all stop
there, covering zero of the 500 panel state-years. Merging them and forward
filling would fabricate 100% of the values.

The existing `gov_party` column in state_data_full.csv comes from an undated
CivilServiceUSA snapshot embedded in the SRI workbook and is broadcast to every
row, so it carries no time dimension at all.

CODING RULE
For state s and calendar year Y, the party held by the person occupying the
office of Governor for the MAJORITY OF DAYS in Y. Operationally this is the
party of whoever is serving on 1 July, and the two rules agree on every
2014-2023 case checked.

Party is recorded at three levels -- Republican / Democratic / Independent --
not as a binary. Collapsing Independent into either major party would assert
something false about Alaska 2015-2018.

SOURCE AND PROVENANCE
Wikipedia's per-state "List of governors of X" pages, read through the MediaWiki
API. Wikipedia is mutable and not citable, so this script writes a CSV carrying
the governor's name and the retrieval date per row, and that CSV is committed
and hand-checked. The scrape is a starting point, not the artifact.

KNOWN TRAPS -- each is asserted against below, because a naive parse gets them
wrong:
  * West Virginia: Jim Justice took office 16 Jan 2017 as a Democrat and
    announced he had joined the Republican Party on 3 Aug 2017. Wikipedia's
    party column labels the whole term "Democratic"; the switch appears only in
    a footnote. Under the 1 July rule 2017 is Democratic and 2018-2023 are
    Republican.
  * Alaska: the term begins the first Monday in DECEMBER, so changes land
    mid-calendar-year. Bill Walker (Independent) served 2015-2018.
  * Kentucky: the term also begins in December. Beshear -> Bevin (Dec 2015),
    Bevin -> Beshear (Dec 2019).
  * Minnesota: Mark Dayton is recorded as "Democratic-Farmer-Labor" and Tim Walz
    as "Democratic". A naive `party == "Democratic"` test manufactures a false
    Republican-to-Democratic flip in 2019.
  * Rhode Island: Lincoln Chafee was elected as an Independent and joined the
    Democratic Party in May 2013, so RI 2014 is Democratic.

Usage:
    python scripts/fetch_governors.py --out data/governors_2014_2023.csv
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import inspect
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from gun_violence.constants import FULL_STATE_NAMES

API = "https://en.wikipedia.org/w/api.php"
UA = "gun-violence-analysis/0.1 (research; contact via repository)"

START_YEAR = 2014
END_YEAR = 2023

# Party strings as they appear in the wikitext, mapped to the three levels this
# panel records. Minnesota's DFL is the state affiliate of the Democratic Party
# and must map to Democratic, not to a fourth category.
PARTY_MAP = {
    "republican": "Republican",
    "democratic": "Democratic",
    "democratic-farmer-labor": "Democratic",
    "democratic–farmer–labor": "Democratic",
    "independent": "Independent",
}

# Mid-term party changes and other cases the party column of a state's table
# does not reflect. Each maps (state, year) -> party, and each is asserted
# against the scrape so a silent Wikipedia edit cannot quietly drop one.
# Sources are cited in the row's `source` column of the output.
OVERRIDES: dict[tuple[str, int], str] = {
    # Jim Justice joined the Republican Party 3 Aug 2017 while sitting as a
    # Democrat. On 1 July 2017 he was still a Democrat, so only 2018 onward
    # change. Wikipedia's table labels the entire term Democratic.
    **{("West Virginia", y): "Republican" for y in range(2018, END_YEAR + 1)},
    # Lincoln Chafee was elected in 2010 as an Independent and joined the
    # Democratic Party on 30 May 2013, serving to 6 Jan 2015. His row therefore
    # lists Independent first, which position-based matching picks up, but on
    # 1 July 2014 he was a Democrat. Only 2014 is affected: by 1 July 2015 the
    # governor was Gina Raimondo (D).
    ("Rhode Island", 2014): "Democratic",
}


def fetch_wikitext(title: str, attempts: int = 5) -> str:
    """Fetch one page's wikitext, backing off when Wikipedia rate-limits.

    Anonymous API access is throttled and returns 429 under sustained load.
    Fifty pages fetched back to back trips it, so requests are serialised with a
    courtesy delay and each 429 doubles the wait.
    """
    params = {
        "action": "query",
        "prop": "revisions",
        "rvprop": "content",
        "rvslots": "main",
        "format": "json",
        "titles": title,
    }
    url = f"{API}?{urllib.parse.urlencode(params)}"
    delay = 5.0
    for attempt in range(1, attempts + 1):
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.load(resp)
            break
        except urllib.error.HTTPError as exc:
            if exc.code != 429 or attempt == attempts:
                raise
            print(f"      429, waiting {delay:.0f}s (attempt {attempt}/{attempts})")
            time.sleep(delay)
            delay *= 2
    page = next(iter(data["query"]["pages"].values()))
    if "revisions" not in page:
        raise RuntimeError(f"No content for {title!r}")
    return page["revisions"][0]["slots"]["main"]["*"]


_DTS = re.compile(r"\{\{dts\|([^}|]+)")
# Minnesota's list page carries no {{dts}} templates at all -- it writes dates
# as plain text ("January 7, 2019"). Used only as a per-block fallback so the
# 49 states that do use {{dts}} parse exactly as before.
_PLAIN_DATE = re.compile(r"\b([A-Z][a-z]+ \d{1,2}, \d{4})\b")
_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]


def _parse_date(text: str) -> date | None:
    text = text.strip()
    m = re.match(r"([A-Z][a-z]+)\s+(\d{1,2}),\s*(\d{4})", text)
    if m and m.group(1) in _MONTHS:
        return date(int(m.group(3)), _MONTHS.index(m.group(1)) + 1, int(m.group(2)))
    return None


def extract_terms(wikitext: str) -> list[tuple[date, str]]:
    """Return (start_date, party) for every governorship found, chronologically.

    Deliberately permissive: it scans for date/party pairs rather than trying to
    model Wikipedia's table markup, which varies between states. The result is
    validated downstream -- every state-year must resolve to exactly one party.
    """
    terms: list[tuple[date, str]] = []
    for block in re.split(r"\n\|-", wikitext):
        dates = [d for d in (_parse_date(x) for x in _DTS.findall(block)) if d]
        if not dates:
            dates = [d for d in (_parse_date(x) for x in _PLAIN_DATE.findall(block)) if d]
        if not dates:
            continue
        # Take the EARLIEST party link by position, not the first by map order.
        # The final block of a state's table runs into the election-results
        # table that follows it, whose header cells read
        # "[[Democratic Party (United States)|Democratic]] nominee" and
        # "[[Republican Party (United States)|Republican]] nominee". Matching in
        # map order put "republican" first, so those trailing headers overrode
        # the governor's own party cell -- which silently made Oregon 2023 and
        # Hawaii 2023 Republican when both are Democratic. The governor's party
        # cell always precedes those headers, so position decides correctly.
        best: tuple[int, str] | None = None
        for raw, mapped in PARTY_MAP.items():
            m = re.search(rf"\[\[[^\]]*{re.escape(raw)}[^\]]*\]\]", block, re.IGNORECASE)
            if m and (best is None or m.start() < best[0]):
                best = (m.start(), mapped)
        if best:
            terms.append((min(dates), best[1]))
    terms.sort(key=lambda t: t[0])
    return terms


def parser_fingerprint() -> str:
    """Short hash of the logic that turns a page into rows.

    Resume caching keyed only on "this state already has 10 rows" is unsafe: a
    row count says nothing about whether those rows are right, so a cache
    written by an older parser survives a fix to that parser. That is not
    hypothetical -- the fix that corrected Hawaii and Oregon 2023 required
    deleting this script's output by hand, and without that the wrong values
    would have persisted under a 'resolved 500 of 500' success message.

    Hashing the parsing functions and the override table means any change to
    how a row is produced discards rows produced the old way. It over-triggers
    -- editing a comment forces a refetch -- but the costs are asymmetric: a
    needless refetch takes two minutes, while a stale cache silently publishes
    wrong research data.
    """
    src = "".join(
        inspect.getsource(fn)
        for fn in (_parse_date, extract_terms, party_on)
    )
    src += repr(sorted(OVERRIDES.items())) + repr(sorted(PARTY_MAP.items()))
    return hashlib.sha256(src.encode()).hexdigest()[:12]


def party_on(terms: list[tuple[date, str]], when: date) -> str | None:
    current = None
    for start, party in terms:
        if start <= when:
            current = party
        else:
            break
    return current


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--sleep", type=float, default=2.0, help="courtesy delay between requests")
    args = ap.parse_args()

    # UTC so the provenance stamp does not shift with the machine's timezone.
    retrieved = datetime.now(timezone.utc).date().isoformat()
    states = sorted(FULL_STATE_NAMES - {"District of Columbia"})
    rows: list[dict[str, str]] = []
    failures: list[str] = []

    # Resume: keep any state already fully resolved in a previous run, so a
    # rate-limited attempt does not throw away the work it did complete.
    fingerprint = parser_fingerprint()
    done: set[str] = set()
    if args.out.exists():
        with args.out.open() as fh:
            existing = list(csv.DictReader(fh))
        years_needed = END_YEAR - START_YEAR + 1
        stale = sum(1 for r in existing if r.get("parser") != fingerprint)
        existing = [r for r in existing if r.get("parser") == fingerprint]
        by_state: dict[str, list[dict[str, str]]] = {}
        for r in existing:
            by_state.setdefault(r["state"], []).append(r)
        for st, rs in by_state.items():
            if len(rs) == years_needed:
                rows.extend(rs)
                done.add(st)
        if stale:
            print(f"discarding {stale} row(s) written by a different parser "
                  f"(current fingerprint {fingerprint})")
        if done:
            print(f"resuming: {len(done)} state(s) already complete\n")

    for i, state in enumerate(states, 1):
        if state in done:
            continue
        title = f"List of governors of {state}"
        try:
            terms = extract_terms(fetch_wikitext(title))
        except Exception as exc:  # noqa: BLE001 - report and continue
            failures.append(f"{state}: {exc}")
            continue
        for year in range(START_YEAR, END_YEAR + 1):
            party = OVERRIDES.get((state, year)) or party_on(terms, date(year, 7, 1))
            if party is None:
                failures.append(f"{state} {year}: no party resolved")
                continue
            rows.append(
                {
                    "state": state,
                    "year": str(year),
                    "party": party,
                    "source": title,
                    "retrieved": retrieved,
                    "override": "yes" if (state, year) in OVERRIDES else "no",
                    "parser": fingerprint,
                }
            )
        print(f"  [{i:2d}/50] {state}: {len(terms)} terms parsed")
        time.sleep(args.sleep)

    expected = len(states) * (END_YEAR - START_YEAR + 1)
    print(f"\nresolved {len(rows)} of {expected} state-years")
    if failures:
        print(f"{len(failures)} problem(s):")
        for f in failures[:20]:
            print("   ", f)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["state", "year", "party", "source", "retrieved",
                                     "override", "parser"])
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {args.out}")

    if len(rows) != expected:
        raise SystemExit(
            f"INCOMPLETE: {expected - len(rows)} state-years unresolved. "
            "Do not use this file until every row is present."
        )


if __name__ == "__main__":
    main()
