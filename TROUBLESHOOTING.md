# Troubleshooting: What Your Daily Summary Is Telling You

You don't need to read code to use this. Find the phrase you're seeing,
read what it means, and what (if anything) to do.

---

### I don't see all three workflows in the Actions tab

**What it means:** most likely, the `.github` folder didn't upload —
files/folders starting with a dot are hidden by default on most
computers and silently get skipped during drag-and-drop uploads.

**What to do:** turn on "show hidden files" (Windows: File Explorer →
View → Show → Hidden items; Mac: `Cmd+Shift+.` in Finder), then re-upload
just the `.github` folder via **Add file → Upload files**. See
`QUICKSTART.md` Part 2 for the full steps.

---

### The Forecast Refresh schedule times look strange/uneven

**What it means:** this is intentional, not a bug. NOAA's forecast
bulletin (the one with the percentile data this bot needs) publishes at
00, 01, 07, 12, 13, 19 UTC — a genuinely irregular schedule, confirmed
directly against NOAA's own documentation. Forecast Refresh is timed to
match those exact hours (plus a short buffer), rather than a clean,
evenly-spaced interval.

---

### "no usable NBM percentile data for station" appears often in logs

**What it means:** the forecast bulletin didn't have complete percentile
data for that station on that run — could be a temporary NOAA data gap,
or (less likely, but worth ruling out if this happens on every run) a
sign the bulletin format changed since this was built.

**What to do:** if it happens occasionally, no action needed — the bot
correctly skips rather than guesses. If it happens on every single run
for every city, share a recent log excerpt and it's worth investigating.

---

### "⚠ N scan(s) flagged a POSITION MISMATCH"

**What it means:** the bot's own records disagree with what Kalshi shows
as your actual open positions. This is one of the two conditions that
also triggers an immediate alert (a separate GitHub Issue titled "🚨
Predict Weather Bot Alert"), so you may have already seen this.

**What to do:** don't trust that day's P&L numbers until this clears.
In paper mode this is lower-stakes (no real money involved) but still
worth noticing, since it may point to a bug worth fixing before going live.
If you're in live mode, log into Kalshi directly and compare your actual
positions against what the bot's report claims.

---

### "🚨 Predict Weather Bot Alert" (a separate GitHub Issue, not a comment)

**What it means:** either a position mismatch (above) or the daily loss
limit was hit. This is designed to reach you the same day, not wait for
tomorrow's summary.

**What to do:** open the issue and read the specific message. If it's the
daily loss limit, the bot has already stopped opening new trades for the
rest of that day on its own — no action is required, but it's worth
understanding why before the next trading day.

---

### "Scans run today: 0" (or a much lower number than expected)

**What it means:** the scheduled GitHub Action didn't run, or ran and
failed before finishing.

**What to do:** click the **Actions** tab in your repo → **Price
Check** or **Forecast Refresh** → look for a run with a red ✗. Click it to see the error message
near the bottom of the log. Common causes: a typo in a GitHub secret
(re-check Part 3 of `QUICKSTART.md`), or Kalshi's site being briefly
unavailable — the latter usually resolves itself by the next scheduled run.

---

### "New positions opened today: 0" for several days in a row

**What it means:** on its own, this isn't a problem — the bot is
supposed to reject the vast majority of candidates. Long stretches with
no trades are expected and not a sign of malfunction.

**What to do:** nothing, usually. If you want to check whether the
thresholds are simply too strict for your risk tolerance, `min_probability_gap`
and `min_composite_score` in `config.yaml` control how selective it is —
lowering them (carefully) means more trades, not necessarily better ones.

---

### The daily P&L sparkline looks completely flat

**What it means:** either no trades have settled yet (normal in the
first days), or something is silently preventing trades from resolving.

**What to do:** check "Positions settled today" in the same report over
several days. If it stays at 0 while "New positions opened" is greater
than 0 for more than a few days, something may be wrong with settlement
timing — feel free to share the daily summary text and I can help
diagnose it.

---

### "no_forecast_available" or similar showing up if you look at raw logs

**What it means:** NOAA's forecast data doesn't cover this specific
market yet (common for same-day markets — this is intentional, not a bug).

**What to do:** nothing. The bot is correctly declining to guess rather
than trade on missing data.

---

### I changed something in `config.yaml` and now nothing works

**What to do:** YAML (the format `config.yaml` uses) is picky about
spacing — it uses indentation (spaces at the start of a line) to show
structure, similar to an outline. If you added or removed a line, make
sure the spacing matches the lines around it exactly. When in doubt,
paste your changed section back to me and I can check it.
