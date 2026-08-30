# Known Limitations

Being upfront about what this is and isn't. Worth noting: even the
fully-built, professionally maintained paid product this project drew on
for structure had **no validated edge** as of its own most recent public
status page. Nothing here should be read as "the free version is
behind" — nobody in this picture has a proven track record yet.

## Status

v2.0, no real trades placed. 48 automated tests cover the trap-prone
logic (probability math, DST bucketing, settlement accounting,
strike-type parsing, NBM fixed-width column alignment, 429 backoff).

## What changed from v1, and why it matters

v1 had a real, live correctness bug: it fetched NOAA's NBH ("Hourly")
bulletin, which does not contain percentile data at all. This almost
certainly meant every market was silently skipped at the "no forecast
coverage" gate for the bot's entire v1 run — the zero-trades outcome
observed during v1 usage is now explained by this, not (only) by the
edge thresholds being strict. v2.0 fetches the correct bulletin (NBP)
with field names confirmed directly against NOAA's documentation.

While fixing that, a second, related bug was found and fixed: NBM
bulletins are fixed-width text with intentionally blank columns (a
percentile value only prints at the relevant forecast hour). The
original parsing approach used simple whitespace-splitting, which
silently shifts values into the wrong column whenever a row has gaps.
v2.0 parses by exact character position instead, derived from the
header row. This is covered by dedicated regression tests in
`tests/test_nbm_parsing.py`.

## What's now confirmed vs. still a best guess

**Confirmed directly against official documentation:**
- Kalshi's REST base URL, RSA-PSS signing parameters
- Kalshi's dollar-string price fields, bid-only orderbook structure,
  strike-type-aware threshold fields
- NBM's TXNP1/2/5/7/9 percentile field names
- NBP's current (NBM v5.0, since May 2026) publish schedule: 00, 01, 07,
  12, 13, 19 UTC

**Still a best guess, not yet verified against a live account:**
- The exact Kalshi series-ticker prefix for each city (e.g. `KXHIGHLAX`
  for Los Angeles) — if wrong, that city's scan will simply return zero
  markets and log it clearly, rather than trade on a wrong assumption

## Specific known gaps

- **No slippage modeling in paper mode.** Assumes fills at the displayed
  ask/bid.
- **GitHub Actions scheduling is best-effort**, even at 5-minute
  intervals. Real run frequency may be lower than configured, especially
  during high platform load. See `IMPROVEMENTS.md` for the plan if this
  proves to be a persistent problem.
- **The backtest has real limits**: it uses NOAA's public historical
  archive, which may have gaps; it can't reconstruct spread/volume/
  order-book conditions as they existed at decision time, only whether
  the probability model would have been well-calibrated against what
  actually happened.
- **Single forecast source.** Only NBM is used (deliberately — a
  hand-rolled multi-model ensemble was the exact approach that scored
  worse than a naive base-rate guess in the research this project drew on).
- **Column-width parsing is derived, not hardcoded**, from each
  bulletin's own header row rather than assuming a fixed number of
  characters — this should be robust to minor NOAA formatting changes,
  but hasn't been verified against a live bulletin from this environment
  (network access here doesn't reach NOAA's servers). Watch early
  Forecast Refresh logs for `nbm_parse` warnings.

## Bug classes this was deliberately built to avoid

- Silent `dict.get(key, default)` fallbacks hiding API response shape
  mismatches
- Settlement updates that touch pnl but not status
- Treating "void" outcomes as losses
- DST-related date bucketing errors
- Wrong settlement station guesses — verified against Kalshi's live
  market metadata every forecast refresh
- Wrong strike-price field for "between" (range) markets
- Wrong NOAA bulletin type / silently misaligned forecast columns (the
  two bugs found and fixed in this version)

## What to actually watch for in your daily summaries

See `TROUBLESHOOTING.md` for a full phrase-by-phrase guide. The short version:
- Any `POSITION MISMATCH` alert — investigate before trusting that day's numbers
- A daily loss limit alert — expected to occasionally happen
- A backtest that doesn't beat the naive base rate — treat as a serious
  signal to pause before going live
- `nbm_parse` warnings appearing on every single run — worth investigating
