# Predict Weather Bot v2.0

An automated weather-market trading bot for Kalshi, built to run for free
on GitHub Actions — no server, no Python installation, no coding
required to operate it day to day.

**New here? Start with [`QUICKSTART.md`](QUICKSTART.md)** — a click-by-click
setup guide that assumes no GitHub or Python experience.

**This is speculative software, not financial advice.** Read
[`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md) before ever switching out
of paper-trading mode. You can lose the full amount you deploy.

**Migrating from v1?** This is a fresh, separate repo — see the note at
the bottom of `QUICKSTART.md`. v1 had a significant bug (reading the
wrong NOAA data file) that means its trade history isn't worth carrying
forward.

---

## What's new in v2.0

- **Fixed a real bug**: v1 fetched NOAA's "Hourly" (NBH) bulletin, which
  doesn't contain the percentile data the probability model needs at all.
  v2.0 fetches the correct bulletin (NBP) with confirmed field names.
- **Fixed a second, related bug found while verifying the above**: NBM
  bulletins are fixed-width text with intentionally blank columns; naive
  whitespace parsing silently shifted values into the wrong forecast
  hour. v2.0 parses by exact column position instead, with dedicated
  regression tests for this specific failure mode.
- **Corrected the Kalshi API base URL** to the one in their current
  official documentation (the old one was an undocumented but
  still-functioning legacy alias).
- **Two-tier scanning**: a "Forecast Refresh" tier runs 6x/day, matched
  to NOAA's actual (irregular) publish schedule; a "Price Check" tier
  runs every 5 minutes against the cached forecast, so paper trading
  reacts to price movements roughly as often as live trading would.
- **Public repo** (a deliberate choice — see `QUICKSTART.md` Part 2 for
  why), which removes the GitHub Actions cost ceiling that a 5-minute
  schedule would hit on a private repo.
- **429 rate-limit handling** with exponential backoff, per Kalshi's
  documented token-bucket limiter.
- **No backtest feature** — an earlier version of v2.0 included one, but
  it was removed after confirming NOAA doesn't keep more than about a
  week of the needed forecast archive available anywhere for free. See
  `IMPROVEMENTS.md` for the full reasoning. Paper trading is the source
  of truth for validation now.

---

## What this does, in one paragraph

Every 5 minutes, it checks current Kalshi weather-market prices against
a forecast-derived probability (refreshed 6x/day, matching NOAA's actual
publish schedule) — and, if the gap between model and market is large
enough and a few quality checks pass, opens a small position. It starts
in **paper mode** (simulated, no real money) and stays there until you
deliberately switch it. Each morning, it posts a plain-English summary to
a GitHub Issue you can read without touching any code.

---

## Where to find things

| I want to... | Go to... |
|---|---|
| Set this up for the first time | [`QUICKSTART.md`](QUICKSTART.md) |
| Understand what a phrase in my daily summary means | [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md) |
| Know what this can't do yet, or what's unproven | [`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md) |
| See what's planned for the next version | [`IMPROVEMENTS.md`](IMPROVEMENTS.md) |
| Adjust cities, budget, or risk settings | `config.yaml` (every line has a comment) |

---

## What's included

- **Weather bot** for 5 cities (Chicago, New York, Miami, Austin, Los
  Angeles) — configurable in `config.yaml`
- **Paper and live trading modes**, one line to switch, hard budget caps
  in either mode
- **Daily summary** posted automatically as a GitHub Issue comment,
  including a quick-glance P&L sparkline
- **Same-day alerts** (a separate GitHub Issue) if a position mismatch or
  the daily loss limit occurs
- **48 automated tests**, including dedicated regression coverage for
  the fixed-width column parsing bug found while building this version

---

## Running tests locally (optional — only if you want to verify changes)

```bash
pip install -r requirements.txt pytest
pytest tests/ -v
```

You don't need to do this to use the bot day-to-day; it's only relevant
if you (or I, on your behalf) change the underlying code.
