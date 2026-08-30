"""
Backtests the bot's probability model against ALREADY-SETTLED Kalshi
markets, using archived NOAA NBP (Probabilistic) bulletins - the same
bulletin type the live bot now uses (see src/nbm.py for why NBH, used in
v1, was the wrong bulletin entirely).

This mirrors the audit methodology described in the source material this
project drew on: Brier score against actual outcomes, compared to the
Brier score of simply predicting the historical base rate. If the model
scores WORSE than the base rate, that's a serious red flag worth knowing
before deploying any real money.

LIMITATIONS (see KNOWN_LIMITATIONS.md for the full list):
  - NOAA's live NBP endpoint only keeps a rolling window of bulletins.
    Older runs must come from NOAA's public archive (noaa-nbm-pds S3
    bucket), same text format, different URL.
  - This cannot reconstruct the exact spread/volume/order-book conditions
    that existed at the time - only whether the probability model itself
    would have been well-calibrated against what actually happened.
  - Kalshi's historical markets endpoint availability and exact settled
    field values are used as documented; if Kalshi's schema differs,
    individual markets are skipped and logged rather than guessed at.
"""
import logging
from datetime import datetime, timedelta, timezone

import requests

from src import nbm, probability
from src.kalshi_client import KalshiClient
from src.market_parsing import extract_threshold

logger = logging.getLogger(__name__)

NBM_ARCHIVE_BASE = (
    "https://noaa-nbm-pds.s3.amazonaws.com/blend.{date}/t{hour:02d}z/text/"
    "blend_nbptx.t{hour:02d}z"
)


def fetch_archived_bulletin(run_date, run_hour: int, timeout: int = 30):
    """
    Fetches a historical NBP bulletin from NOAA's public archive rather
    than the live rolling-window endpoint. Returns None (not an
    exception) if that specific run isn't archived.
    """
    url = NBM_ARCHIVE_BASE.format(date=run_date.strftime("%Y%m%d"), hour=run_hour)
    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as e:
        # INFO, not DEBUG: this needs to be visible in a normal run's log -
        # a wrong archive URL pattern would otherwise fail completely silently.
        logger.info("archived bulletin unavailable url=%s error=%s", url, e)
        return None


def _nearest_run_before(close_time: datetime):
    """
    NBP's confirmed current publish schedule (NBM v5.0, since May 2026)
    is irregular: 00, 01, 07, 12, 13, 19 UTC - see src/nbm.py RUN_HOURS.
    Pick the most recent of those at least 24 hours before market close.
    """
    target = close_time - timedelta(hours=24)
    candidates = [h for h in nbm.RUN_HOURS if h <= target.hour]
    if candidates:
        run_hour = max(candidates)
        run_date = target.date()
    else:
        run_hour = max(nbm.RUN_HOURS)
        run_date = (target - timedelta(days=1)).date()
    return run_date, run_hour


def _evaluate_market(market: dict, station: str, sigma_multiplier: float) -> tuple:
    """
    Shared per-market evaluation used by both the historical-tier and
    live-tier (fallback) fetch paths.

    Returns (result_dict_or_None, rejection_reason_or_None) - the reason
    is always populated when the result is None, so callers can tally
    WHY markets were rejected instead of only knowing that they were.
    This funnel visibility is what pinpointed the historical-tier vs.
    live-tier issue earlier, and is needed again here to find the next
    bottleneck rather than guessing at it.
    """
    result = market.get("result")
    if result not in ("yes", "no"):
        return None, f"result_field_not_yes_or_no (was: {result!r})"

    threshold = extract_threshold(market)
    if threshold is None:
        return None, (
            f"extract_threshold_failed (strike_type={market.get('strike_type')!r}, "
            f"floor_strike={market.get('floor_strike')!r}, cap_strike={market.get('cap_strike')!r})"
        )

    close_time_str = market.get("close_time")
    if not close_time_str:
        return None, "no_close_time_field"
    try:
        close_time = datetime.fromisoformat(close_time_str.replace("Z", "+00:00"))
    except ValueError:
        return None, f"close_time_unparseable ({close_time_str!r})"

    run_date, run_hour = _nearest_run_before(close_time)
    bulletin = fetch_archived_bulletin(run_date, run_hour)
    if bulletin is None:
        return None, f"archived_bulletin_unavailable (run={run_date}T{run_hour:02d}Z)"

    parsed = nbm.parse_station_maxt(bulletin, station)
    if parsed is None:
        return None, f"nbm_parse_failed_for_station (station={station}, run={run_date}T{run_hour:02d}Z)"

    run_dt = datetime(run_date.year, run_date.month, run_date.day, run_hour, tzinfo=timezone.utc)
    target_hour = int((close_time - run_dt).total_seconds() // 3600)

    pct = nbm.get_forecast_for_target_hour(parsed, target_hour)
    if pct is None:
        return None, f"no_forecast_at_target_hour (target_hour={target_hour})"

    if threshold["kind"] == "single":
        model_prob = probability.probability_of_exceeding(pct, threshold["value"], sigma_multiplier)
    else:
        model_prob = probability.probability_within_range(
            pct, threshold["floor"], threshold["cap"], sigma_multiplier
        )

    actual = 1.0 if result == "yes" else 0.0
    return {
        "ticker": market.get("ticker"),
        "model_prob": model_prob,
        "actual": actual,
        "close_time": close_time_str,
    }, None


def backtest_city(
    client: KalshiClient, series_prefix: str, station: str,
    sigma_multiplier: float, max_markets: int = 200,
) -> dict:
    """
    Runs the backtest for one city's series. Returns a report dict with
    per-market predictions plus summary statistics.

    Tries Kalshi's /historical/markets endpoint first. Kalshi partitions
    data into "live" and "historical" tiers with a time-based cutoff
    (see GET /historical/cutoff in their docs) - daily-settling weather
    markets may not have aged past that cutoff yet, in which case
    /historical/markets legitimately returns nothing, not an error. If
    that happens, this falls back to the regular /markets endpoint
    filtered to a terminal (finalized) status, which covers recently
    settled markets still in the "live" tier.
    """
    results = []
    source_used = None
    rejection_counts = {}

    def _tally(evaluated, reason):
        if evaluated:
            results.append(evaluated)
        else:
            rejection_counts[reason] = rejection_counts.get(reason, 0) + 1

    # --- Try the historical tier first ---------------------------------------
    cursor = None
    fetched = 0
    while fetched < max_markets:
        try:
            page = client.get_historical_markets(
                series_prefix, limit=min(100, max_markets - fetched), cursor=cursor
            )
        except Exception as e:
            logger.warning("backtest_city: /historical/markets call failed for %s: %s", series_prefix, e)
            break

        markets = page.get("markets", [])
        if not markets:
            if fetched == 0:
                logger.info(
                    "backtest_city: /historical/markets returned ZERO markets for "
                    "series=%s (succeeded, not an error - likely means these "
                    "markets haven't aged past Kalshi's historical-tier cutoff "
                    "yet). Falling back to /markets with a finalized-status filter.",
                    series_prefix,
                )
            break

        source_used = "historical"
        for market in markets:
            fetched += 1
            evaluated, reason = _evaluate_market(market, station, sigma_multiplier)
            _tally(evaluated, reason)

        cursor = page.get("cursor")
        if not cursor:
            break

    # --- Fallback: recently-settled markets still in the "live" tier ---------
    if source_used is None:
        try:
            recent_markets = client.get_markets_by_series(series_prefix, status="finalized")
        except Exception as e:
            logger.warning("backtest_city: fallback /markets?status=finalized failed for %s: %s",
                           series_prefix, e)
            recent_markets = []

        if recent_markets:
            source_used = "live (finalized)"
            logger.info(
                "backtest_city: fallback found %d finalized markets for series=%s",
                len(recent_markets), series_prefix,
            )
        for market in recent_markets[:max_markets]:
            evaluated, reason = _evaluate_market(market, station, sigma_multiplier)
            _tally(evaluated, reason)

    if rejection_counts:
        collapsed = _collapse_rejection_reasons(rejection_counts)
        logger.info("backtest_city: rejection funnel for series=%s: %s", series_prefix, collapsed)

    summary = _summarize(results)
    summary["source_used"] = source_used
    summary["rejection_funnel"] = _collapse_rejection_reasons(rejection_counts)
    return summary


def _collapse_rejection_reasons(rejection_counts: dict) -> dict:
    """Collapses detailed per-reason counts down to their category (the
    part before the parenthetical detail) for a compact summary."""
    from collections import Counter
    collapsed = Counter()
    for reason, count in rejection_counts.items():
        category = reason.split(" (")[0]
        collapsed[category] += count
    return dict(collapsed)


def _summarize(results: list) -> dict:
    n = len(results)
    if n == 0:
        return {"n": 0, "brier_model": None, "brier_base_rate": None, "base_rate": None, "results": []}

    base_rate = sum(r["actual"] for r in results) / n
    brier_model = sum((r["model_prob"] - r["actual"]) ** 2 for r in results) / n
    brier_base_rate = sum((base_rate - r["actual"]) ** 2 for r in results) / n

    return {
        "n": n,
        "brier_model": round(brier_model, 4),
        "brier_base_rate": round(brier_base_rate, 4),
        "base_rate": round(base_rate, 4),
        "beats_base_rate": brier_model < brier_base_rate,
        "results": results,
    }


def format_report(city: str, summary: dict) -> str:
    lines = [f"=== Backtest: {city} ==="]
    source = summary.get("source_used")
    if source:
        lines.append(f"Data source: {source}")

    if summary["n"] == 0:
        lines.append("No usable historical markets found (missing archive data, "
                     "settled results, or strike info). Try a different city or "
                     "check that historical NBM archive coverage exists for this period.")
        funnel = summary.get("rejection_funnel")
        if funnel:
            lines.append("")
            lines.append("Why markets were rejected (this tells you exactly where to look):")
            for reason, count in sorted(funnel.items(), key=lambda x: -x[1]):
                lines.append(f"  - {reason}: {count}")
        return "\n".join(lines)

    lines.append(f"Markets backtested: {summary['n']}")
    lines.append(f"Historical base rate (actual YES frequency): {summary['base_rate']*100:.1f}%")
    lines.append(f"Brier score, this model:      {summary['brier_model']:.4f}  (lower is better)")
    lines.append(f"Brier score, naive base rate: {summary['brier_base_rate']:.4f}")
    if summary["beats_base_rate"]:
        lines.append("✓ Model beats the naive base-rate guess on this sample.")
    else:
        lines.append(
            "⚠ Model does NOT beat the naive base-rate guess on this sample. "
            "This is exactly the warning sign described in the source material's "
            "own post-mortem — worth investigating before trusting this model live."
        )
    return "\n".join(lines)


if __name__ == "__main__":
    import os
    from src.config import load_config

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    cfg = load_config()
    key_id = os.environ.get("KALSHI_KEY_ID")
    private_key_pem = os.environ.get("KALSHI_PRIVATE_KEY")
    if not key_id or not private_key_pem:
        raise RuntimeError("KALSHI_KEY_ID and KALSHI_PRIVATE_KEY must be set to run a backtest.")

    client = KalshiClient(key_id, private_key_pem)

    for city_cfg in cfg["cities"]:
        summary = backtest_city(
            client, city_cfg["kalshi_series_prefix"], city_cfg["expected_station"],
            cfg["probability_model"]["sigma_multiplier"],
        )
        print(format_report(city_cfg["name"], summary))
        print()
