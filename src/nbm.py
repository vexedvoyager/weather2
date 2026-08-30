"""
Fetches and parses NOAA's National Blend of Models (NBM) PROBABILISTIC
(NBP) text bulletin.

v1 of this bot fetched the NBH ("Hourly") bulletin, which does NOT contain
percentile data - it only has deterministic values. The percentile fields
(TXNP1/2/5/7/9 for the 10th/25th/50th/75th/90th percentile of daily
max/min temperature) live in a different bulletin entirely: NBP.

Confirmed directly against NOAA's official element-key documentation and
service change notices (not inferred):
  TXNP1 = 10th percentile max/min temp, F
  TXNP2 = 25th percentile max/min temp, F
  TXNP5 = 50th percentile max/min temp, F
  TXNP7 = 75th percentile max/min temp, F
  TXNP9 = 90th percentile max/min temp, F
  (Minimum is listed at the 12z column, Maximum at the 00z column)

NBP's publish schedule is NOT hourly and NOT a clean 4x/day. As of NBM
v5.0 (operational since May 2026), confirmed via NOAA's current service
change notice: NBP is issued at 00, 01, 07, 12, 13, 19 UTC - six times a
day, at irregular spacing. (Older documentation from NBM v4.x described
NBP running all 24 hours; this changed with v5.0. If NOAA changes this
again, RUN_HOURS below is the one place to update it - grep for its uses.)

Docs: https://blend.nomads.ncep.noaa.gov
"""
import logging
import re
from datetime import datetime, timedelta, timezone

import requests

logger = logging.getLogger(__name__)

NBM_BASE = (
    "https://blend.nomads.ncep.noaa.gov/blend.{date}/t{hour:02d}z/text/"
    "blend_nbptx.t{hour:02d}z"
)

# Confirmed current NBP publish schedule (NBM v5.0, since May 2026).
# Irregular by design - not every-6-hours, not hourly.
RUN_HOURS = [19, 13, 12, 7, 1, 0]

PERCENTILE_FIELD_MAP = {
    "TXNP1": "p10",
    "TXNP2": "p25",
    "TXNP5": "p50",
    "TXNP7": "p75",
    "TXNP9": "p90",
}


def _candidate_runs(now: datetime, max_lookback_hours: int = 30):
    """Yield (run_date, run_hour) candidates, most recent first, using
    NBP's actual irregular schedule rather than assuming even spacing."""
    now = now.astimezone(timezone.utc)
    cursor = now
    seen = 0
    while seen < max_lookback_hours:
        for hour in sorted(RUN_HOURS, reverse=True):
            candidate = cursor.replace(hour=hour, minute=0, second=0, microsecond=0)
            if candidate <= now:
                yield candidate.date(), hour
        cursor -= timedelta(days=1)
        seen += 24


def fetch_latest_bulletin(now: datetime = None, timeout: int = 30) -> tuple[str, str]:
    """
    Fetch the most recent available NBP text bulletin.

    Returns (bulletin_text, run_identifier) where run_identifier is a
    string like "2026-08-24T13Z" for logging/traceability.

    Raises RuntimeError if no recent run is fetchable.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    last_error = None
    for run_date, run_hour in _candidate_runs(now):
        url = NBM_BASE.format(date=run_date.strftime("%Y%m%d"), hour=run_hour)
        try:
            resp = requests.get(url, timeout=timeout)
            resp.raise_for_status()
            run_id = f"{run_date.isoformat()}T{run_hour:02d}Z"
            logger.info("nbm_fetch success run=%s url=%s", run_id, url)
            return resp.text, run_id
        except requests.RequestException as e:
            last_error = e
            logger.debug("nbm_fetch miss run=%s-%02dz error=%s", run_date, run_hour, e)
            continue

    raise RuntimeError(
        f"Could not fetch any NBP bulletin in the lookback window. Last error: {last_error}"
    )


def parse_station_maxt(bulletin_text: str, station_id: str) -> dict | None:
    """
    Extract MaxT (daily max temperature) percentile forecasts for a station
    from an NBP bulletin.

    station_id: 4-character ICAO code, e.g. 'KMDW'

    Returns a dict like:
        {
            "forecast_hours": [24, 36, 48, ...],   # hours from model run time
            "p10": [68, 70, 72, ...],
            "p25": [...],
            "p50": [...],
            "p75": [...],
            "p90": [...],
        }
    or None if the station wasn't found, or if the expected percentile
    fields weren't present - skip the market rather than guess.
    """
    lines = bulletin_text.splitlines()

    station_pattern = re.compile(rf"^{re.escape(station_id)}\s", re.IGNORECASE)
    station_start = None
    for i, line in enumerate(lines):
        if station_pattern.match(line):
            station_start = i
            break

    if station_start is None:
        logger.warning("nbm_parse station_not_found station=%s", station_id)
        return None

    # Find where the NEXT station's block begins, so we never accidentally
    # read past our station's data into the next one's. NBM station header
    # lines look like "KBWI NBM V5.0 NBP GUIDANCE 5/18/2026 1300 UTC".
    next_station_pattern = re.compile(r"^[A-Z0-9]{3,4}\s+NBM\s+V", re.IGNORECASE)
    station_end = len(lines)
    for i in range(station_start + 1, len(lines)):
        if next_station_pattern.match(lines[i]):
            station_end = i
            break
    block = lines[station_start:station_end]

    # Find the forecast-HOUR header row within the station block. This
    # must be the "FHR" row (elapsed hours since the model run started),
    # NOT the "UTC" row - the UTC row just cycles 00/06/12/18 repeatedly
    # and does not tell us how far into the future each column is.
    forecast_hours = None
    fhr_line = None
    for line in block[:10]:
        if line.strip().upper().startswith("FHR"):
            fhr_line = line
            hour_tokens = re.findall(r"\d+", line)
            if hour_tokens:
                forecast_hours = [int(h) for h in hour_tokens]
                break

    if fhr_line is None or forecast_hours is None:
        logger.warning("nbm_parse no_fhr_row station=%s", station_id)
        return None

    # CRITICAL: NBM text bulletins are fixed-width. Percentile rows like
    # MaxT only print a value in the column matching the relevant forecast
    # hour (e.g. the 00Z column for a max) and leave OTHER columns blank -
    # not zero, not omitted, just whitespace. A naive line.split() collapses
    # that whitespace and silently shifts every subsequent value into the
    # wrong column. To avoid this, we derive each column's fixed character
    # position from the FHR header row itself, then read every data row at
    # those exact character offsets rather than splitting on whitespace.
    column_spans = [m.span() for m in re.finditer(r"\d+", fhr_line)]

    def read_row_by_column(line: str) -> list:
        values = []
        for start, end in column_spans:
            # Numeric tokens in data rows are right-justified within a
            # column of the same width as the header token, so we widen
            # the read window slightly to the left to catch right-aligned
            # values that start before the header token's own start
            # position (e.g. a 2-digit value under a 1-digit hour header).
            window_start = max(0, start - 2)
            segment = line[window_start:end].strip()
            if segment == "" or segment == "-" or not re.fullmatch(r"-?\d+", segment):
                values.append(None)
            else:
                values.append(int(segment))
        return values

    percentile_rows = {}
    for line in block:
        stripped_start = line.strip()
        if not stripped_start:
            continue
        label = stripped_start.split()[0].upper() if stripped_start.split() else ""

        if label in PERCENTILE_FIELD_MAP:
            percentile_rows[PERCENTILE_FIELD_MAP[label]] = read_row_by_column(line)

    missing = set(PERCENTILE_FIELD_MAP.values()) - set(percentile_rows.keys())
    if missing:
        logger.warning(
            "nbm_parse incomplete_percentiles station=%s missing=%s "
            "(found=%s) - skipping rather than guessing",
            station_id, missing, list(percentile_rows.keys()),
        )
        return None

    result = {"forecast_hours": forecast_hours}
    result.update(percentile_rows)
    return result


def get_forecast_for_target_hour(
    parsed: dict, target_forecast_hour: int, tolerance_hours: int = 6
) -> dict | None:
    """
    From a parsed station dict, pull the percentile values closest to
    target_forecast_hour (the forecast hour corresponding to the Kalshi
    contract's settlement day).

    NBP's forecast-hour spacing is coarser than NBH's (this bulletin
    covers a longer range with less granularity), so the default
    tolerance here is wider than the previous NBH-based version used.

    Returns {"p10": val, "p25": val, "p50": val, "p75": val, "p90": val}
    or None if nothing within tolerance_hours is available, or if any
    matched value is a missing placeholder (None).
    """
    hours = parsed.get("forecast_hours")
    if not hours:
        return None

    best_idx, best_diff = None, None
    for idx, h in enumerate(hours):
        diff = abs(h - target_forecast_hour)
        if best_diff is None or diff < best_diff:
            best_idx, best_diff = idx, diff

    if best_idx is None or best_diff > tolerance_hours:
        return None

    out = {}
    for key in ("p10", "p25", "p50", "p75", "p90"):
        values = parsed.get(key)
        if not values or best_idx >= len(values) or values[best_idx] is None:
            return None
        out[key] = values[best_idx]
    return out
