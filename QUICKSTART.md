# Quick Start (no GitHub or Python experience needed)

This walks through everything, click by click. It should take about 20
minutes. If a term is unfamiliar, it's explained the first time it comes up.

**This is v2.0.** If you're migrating from a v1 repo, this is a fresh
setup, not an upgrade — see the note at the very bottom.

---

## Part 1: Get your Kalshi credentials

"API credentials" are just a username/password pair, but for a computer
program instead of a person.

1. Log into your Kalshi account at kalshi.com
2. Click your account/profile icon → find **Settings**
3. Look for a section called **API Keys** (sometimes under "Developer"
   or "Advanced")
4. Click **Create new API key** (wording may vary slightly)
5. Kalshi will show you two things:
   - A **Key ID** — a short string of letters/numbers. Copy this somewhere.
   - A **private key file** — Kalshi will offer to download this as a
     file (it'll look like a block of text starting with
     `-----BEGIN PRIVATE KEY-----`). **Download it and save it somewhere
     safe on your computer.** Kalshi will not show it to you again.

You now have both pieces you'll need in Part 3.

---

## Part 2: Create a place on GitHub to hold this project

"GitHub" is a website that stores code and can run it for you on a
schedule, for free. A "repository" (or "repo") is just a folder that
lives there.

1. Go to github.com and create a free account if you don't have one
2. Click the **+** icon in the top-right corner → **New repository**
3. Give it any name, e.g. `my-weather-bot`
4. Select **Public**.

   **Why public this time:** GitHub gives private repos a limited free
   monthly budget of "Actions minutes" (the compute time your bot's
   automated runs use). This bot's price-check runs every 5 minutes,
   which would exceed that free budget on a private repo and start
   costing real money. Public repos get unlimited free Actions minutes.

   **What "public" actually exposes:** anyone can see `config.yaml`
   (which cities you're watching, your budget caps, your trading
   thresholds) and the bot's source code. **Your Kalshi credentials stay
   completely private regardless** — they're never stored in a file,
   only as encrypted GitHub Secrets (Part 3), which nobody but you can
   view even on a public repo. If you'd rather keep your strategy
   private and don't mind either paying past the free Actions-minutes
   allowance or running less frequently, you can choose Private instead
   — just expect the bot's price-check frequency to need to drop (e.g.
   to every 15-30 minutes) to stay within the free tier.

5. Click **Create repository**

### Uploading this project's files

1. On your new (empty) repository page, look for a link that says
   **"uploading an existing file"**
2. Unzip the file I gave you on your computer first (right-click →
   Extract, or double-click depending on your system)
3. **Before dragging files in, turn on "show hidden files"** on your
   computer (Windows: File Explorer → View → Show → Hidden items; Mac:
   `Cmd+Shift+.` in Finder). Some files in this project (like `.github`
   and `.gitignore`) start with a dot and are invisible by default —
   without this step they'll silently fail to upload.
4. Drag the **entire contents** of the unzipped folder into the browser
   window (not the folder itself — its contents: `src`, `.github`,
   `config.yaml`, `README.md`, etc.)
5. Scroll down, click **Commit changes**
6. Double check: click into your repo and confirm you see a `.github`
   folder and a `.gitignore` file at the top level. If either is
   missing, see `TROUBLESHOOTING.md`.

---

## Part 3: Tell GitHub your Kalshi credentials (safely)

These need to go somewhere GitHub can use them, but that you and only you
can see — never directly into a file in the repo.

1. In your repo, click **Settings** (top menu of the repo, not your
   account settings)
2. In the left sidebar: **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. Name: `KALSHI_KEY_ID` (exactly this — double-check spelling; GitHub
   always displays secret names in uppercase regardless of how you type
   them, which can make a typo easy to miss) → Value: paste your Key ID
   from Part 1 → **Add secret**
5. Click **New repository secret** again
6. Name: `KALSHI_PRIVATE_KEY` → Value: open the private key file you
   downloaded in a text editor (Notepad, TextEdit, etc.), select all,
   copy, and paste the **entire contents** — including the
   `-----BEGIN PRIVATE KEY-----` and `-----END PRIVATE KEY-----` lines —
   into the Value box → **Add secret**

---

## Part 4: Let GitHub write results back to your repo

The bot needs to save its trade history and daily reports back into your
repo each time it runs.

1. Still in **Settings**, click **Actions** → **General** in the left sidebar
2. Scroll to **Workflow permissions**
3. Select **"Read and write permissions"**
4. Click **Save**

---

## Part 5: Turn it on

1. Click the **Actions** tab (top menu of your repo)
2. You may see a banner saying workflows are disabled — click
   **"I understand my workflows, go ahead and enable them"**
3. You should see four workflows listed in the left sidebar: **Forecast
   Refresh**, **Price Check**, **Daily Summary**, and **Backtest**

**What each one does:**
- **Forecast Refresh** runs 6 times a day, timed to NOAA's actual
  forecast publish schedule (an irregular schedule, not evenly spaced —
  this is intentional, not a mistake if the times look odd)
- **Price Check** runs every 5 minutes, reacting to current market
  prices against the forecast Forecast Refresh already cached
- **Daily Summary** posts your daily report each morning
- **Backtest** only runs when you manually trigger it

Nothing further to install or run on your own computer.

---

## Checking on it

1. Click the **Issues** tab (top menu of your repo)
2. Look for an issue titled **"Daily Summaries"** — click it
3. Each day adds a new comment with your report in plain English

That's the one thing worth checking daily. See `TROUBLESHOOTING.md` for
what specific phrases in that report mean.

---

## Running the backtest (optional, but recommended before going live)

This checks the bot's forecasting logic against real past weather markets
to get an early read on whether it looks reasonable — no need to wait
weeks for enough paper trades to build up.

1. Click the **Actions** tab
2. Click **Backtest** in the left sidebar
3. Click **Run workflow** (a button on the right) → **Run workflow** again
   to confirm
4. Wait a few minutes, then check the **Issues** tab for a new
   "Backtest results" issue

---

## Going live (real money) — only when you're ready

Default setup is **paper trading**: simulated, no real money, ever,
until you change one line.

1. In your repo, open `config.yaml` (click on it in the file list)
2. Click the pencil/edit icon
3. Find the line `mode: "paper"` and change it to `mode: "live"`
4. Scroll down, click **Commit changes**

From this point on, real orders can be placed — but only up to the
`total_budget_usd` cap already set in that same file. Fund your Kalshi
account with only that amount (plus a small buffer), not more.

**Recommendation:** don't do this until you've read at least 1-2 weeks
of daily summaries in paper mode and they look sane to you.

---

## Note if you're migrating from a v1 repo

This is a fresh, separate repo, not an in-place upgrade. v1 had a
significant bug where the forecast model was reading the wrong NOAA data
file and likely never producing real probabilities — so there's nothing
worth carrying over from a v1 repo's trade history. Set this up as a new
repo per the steps above, and consider deleting or archiving the old one
once this one is running smoothly.
