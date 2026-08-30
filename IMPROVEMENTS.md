# Improvements for Next Version

A running list of things to fold into the next rebuild — gathered from
real usage, not speculative "nice to haves."

---

## Open items

### 1. Verify the `KXHIGHLAX` series prefix for Los Angeles

**Why:** best-guess extrapolation from the naming pattern of the other
four cities, never confirmed against Kalshi's live API.

**Proposed fix:** once Forecast Refresh has run a few times, check the
logs for "found ZERO markets" warnings for Los Angeles specifically. If
persistent, find the real prefix via Kalshi's `/series` endpoint.

**Priority:** medium — fails safe (skips the city) if wrong.

---

### 2. Monitor whether the 5-minute Price Check schedule is actually reliable

**Why:** GitHub's cron scheduling is documented as best-effort even at
its minimum 5-minute interval. v1 saw significant slippage at a 15-minute
interval (roughly 2 runs in 12 hours against a configured ~48).

**Proposed fix (only if this turns out to be a real problem):** an
external pinger (e.g. cron-job.org) calling GitHub's API to trigger the
workflow, bypassing GitHub's own scheduler reliability. Explicitly not
built into v2.0 — decided to observe real behavior at 5 minutes first
rather than pre-solve an unconfirmed problem.

**Priority:** low until observed data says otherwise.

---

### 3. GitHub Pages dashboard

**Why:** a visual dashboard (real P&L chart, open positions table,
per-city breakdown) would be a nicer daily check-in than reading GitHub
Issue comments.

**Priority:** low — explicitly deferred by choice.

---

### 4. Verify column-width parsing against a real live NBP bulletin

**Why:** the fixed-width parsing logic in `src/nbm.py` was built and
tested against a synthetic bulletin constructed to match NOAA's
documented format, since this environment can't reach NOAA's servers
directly. It should be correct, but "should be" isn't the same as
"confirmed against a real file."

**Proposed fix:** once Forecast Refresh has run in production, spot-check
a few real trades' logged `cached_model_prob` values against the actual
NBP bulletin for that run, by hand, at least once.

**Priority:** medium-high — this is the most consequential piece of
logic in the bot and the one most recently changed.

---

## Log of resolved issues (for context, not action)

**From v1 setup (GitHub/workflow mechanics):**
- `.github`, `.gitignore`, `data/.gitkeep` are dotfiles invisible during
  drag-and-drop uploads unless hidden files are shown — documented in
  `QUICKSTART.md`
- `git add data/alerts/` failed on an empty/nonexistent folder — fixed
  with `mkdir -p` + placeholder file before the add
- `gh issue create --json` isn't a valid flag — fixed by parsing the
  plain URL output instead
- `KALSHI_ID_KEY` vs `KALSHI_KEY_ID` naming mismatch — user-side typo;
  reminder that GitHub always displays secret names in uppercase
  regardless of how they're typed, which can mask other typos

**From v2.0 verification (found before any code shipped, not in production):**
- v1 fetched the wrong NBM bulletin (NBH instead of NBP) — NBH contains
  no percentile data, meaning the probability model almost certainly
  never produced real output during v1's entire run. Root-cause fixed.
- NBM bulletins are fixed-width with intentionally blank columns; naive
  whitespace-splitting silently misaligned values into the wrong
  forecast hour. Fixed with column-position-based parsing; covered by
  regression tests.
- Kalshi's documented production base URL is `external-api.kalshi.com`,
  not the `api.elections.kalshi.com` alias v1 used (which still worked,
  but wasn't the documented one). Fixed.
- NBP's publish schedule changed with NBM v5.0 (May 2026) from an
  all-24-hours cadence to an irregular 6x/day schedule (00, 01, 07, 12,
  13, 19 UTC). Confirmed against the current service change notice and
  built the Forecast Refresh schedule around it.
- No handling for Kalshi's 429 rate-limit responses — added exponential
  backoff, tested.
