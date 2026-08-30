"""
SQLite trade ledger.

Known traps handled explicitly here:
  - settle_trade() updates the `status` column, not just outcome/pnl.
    A prior version of this kind of bot forgot this, and settled trades
    stayed 'open' forever, corrupting every downstream count.
  - Partial fills are tracked with their own status ('partially_filled'),
    distinct from 'accepted', so a query that only looks for 'accepted'
    doesn't silently skip partial fills that later settle for real money.
  - void outcomes are stored as their own outcome value, not coerced into
    a loss.
"""
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    city TEXT NOT NULL,
    side TEXT NOT NULL CHECK(side IN ('yes', 'no')),
    count INTEGER NOT NULL,
    entry_price_cents INTEGER NOT NULL,
    forecast_prob REAL NOT NULL,
    composite_edge_score REAL NOT NULL,
    mode TEXT NOT NULL CHECK(mode IN ('paper', 'live')),
    status TEXT NOT NULL DEFAULT 'open'
        CHECK(status IN ('open', 'partially_filled', 'settled', 'cancelled')),
    outcome TEXT CHECK(outcome IN ('yes', 'no', 'void', NULL)),
    pnl_cents INTEGER,
    fee_cents INTEGER DEFAULT 0,
    opened_at TEXT NOT NULL,
    settled_at TEXT
);

CREATE TABLE IF NOT EXISTS forecast_cache (
    ticker TEXT PRIMARY KEY,
    city TEXT NOT NULL,
    model_prob REAL NOT NULL,
    nbm_run_id TEXT NOT NULL,
    cached_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scan_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at TEXT NOT NULL,
    tickers_scanned INTEGER,
    tickers_eligible INTEGER,
    trades_opened INTEGER,
    db_open_count INTEGER,
    live_open_count INTEGER,
    position_mismatch INTEGER DEFAULT 0,
    notes TEXT
);
"""


@contextmanager
def get_connection(db_path: str):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db(db_path: str):
    with get_connection(db_path) as conn:
        conn.executescript(SCHEMA)
        conn.commit()


def insert_trade(
    db_path: str, ticker: str, city: str, side: str, count: int,
    entry_price_cents: int, forecast_prob: float, composite_edge_score: float,
    mode: str, status: str = "open",
) -> int:
    with get_connection(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO trades
                (ticker, city, side, count, entry_price_cents, forecast_prob,
                 composite_edge_score, mode, status, opened_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (ticker, city, side, count, entry_price_cents, forecast_prob,
             composite_edge_score, mode, status, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        return cur.lastrowid


def settle_trade(db_path: str, trade_id: int, outcome: str, pnl_cents: int, fee_cents: int = 0):
    """
    outcome must be one of 'yes', 'no', 'void'. void is NOT the same as a
    loss - it means the stake is returned, pnl_cents should reflect that
    (typically 0 or just -fee if any fee applied).
    """
    assert outcome in ("yes", "no", "void"), f"invalid outcome: {outcome}"
    with get_connection(db_path) as conn:
        conn.execute(
            """
            UPDATE trades
            SET outcome = ?, pnl_cents = ?, fee_cents = ?,
                status = 'settled', settled_at = ?
            WHERE id = ?
            """,
            (outcome, pnl_cents, fee_cents, datetime.now(timezone.utc).isoformat(), trade_id),
        )
        conn.commit()
        logger.info(
            "trade_settled id=%d outcome=%s pnl_cents=%d fee_cents=%d",
            trade_id, outcome, pnl_cents, fee_cents,
        )


def count_open_trades(db_path: str, city: str = None) -> int:
    query = "SELECT COUNT(*) as n FROM trades WHERE status IN ('open', 'partially_filled')"
    params = ()
    if city:
        query += " AND city = ?"
        params = (city,)
    with get_connection(db_path) as conn:
        row = conn.execute(query, params).fetchone()
        return row["n"]


def total_deployed_cents(db_path: str) -> int:
    """Sum of cost basis for currently-open positions (not yet settled)."""
    with get_connection(db_path) as conn:
        row = conn.execute(
            """
            SELECT COALESCE(SUM(count * entry_price_cents), 0) as total
            FROM trades WHERE status IN ('open', 'partially_filled')
            """
        ).fetchone()
        return row["total"]


def daily_pnl_cents(db_path: str, date_str: str) -> int:
    with get_connection(db_path) as conn:
        row = conn.execute(
            """
            SELECT COALESCE(SUM(pnl_cents), 0) as total
            FROM trades
            WHERE status = 'settled' AND settled_at LIKE ?
            """,
            (f"{date_str}%",),
        ).fetchone()
        return row["total"]


def upsert_forecast_cache(db_path: str, ticker: str, city: str, model_prob: float, nbm_run_id: str):
    with get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO forecast_cache (ticker, city, model_prob, nbm_run_id, cached_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(ticker) DO UPDATE SET
                model_prob = excluded.model_prob,
                nbm_run_id = excluded.nbm_run_id,
                cached_at = excluded.cached_at
            """,
            (ticker, city, model_prob, nbm_run_id, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()


def get_cached_forecast(db_path: str, ticker: str, max_age_hours: float) -> dict | None:
    """Returns {"model_prob": float, "nbm_run_id": str, "cached_at": str}
    if a fresh-enough cached forecast exists for this ticker, else None."""
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT model_prob, nbm_run_id, cached_at FROM forecast_cache WHERE ticker = ?",
            (ticker,),
        ).fetchone()

    if row is None:
        return None

    cached_at = datetime.fromisoformat(row["cached_at"])
    age_hours = (datetime.now(timezone.utc) - cached_at).total_seconds() / 3600
    if age_hours > max_age_hours:
        return None

    return {"model_prob": row["model_prob"], "nbm_run_id": row["nbm_run_id"], "cached_at": row["cached_at"]}


def clear_forecast_cache_for_city(db_path: str, city: str):
    """Called at the start of a forecast-refresh run for a city, so stale
    tickers (e.g. a market that closed) don't linger in the cache forever."""
    with get_connection(db_path) as conn:
        conn.execute("DELETE FROM forecast_cache WHERE city = ?", (city,))
        conn.commit()


def log_scan(
    db_path: str, tickers_scanned: int, tickers_eligible: int, trades_opened: int,
    db_open_count: int, live_open_count: int, notes: str = "",
):
    mismatch = 1 if abs(db_open_count - live_open_count) > 1 else 0
    with get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO scan_log
                (run_at, tickers_scanned, tickers_eligible, trades_opened,
                 db_open_count, live_open_count, position_mismatch, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (datetime.now(timezone.utc).isoformat(), tickers_scanned, tickers_eligible,
             trades_opened, db_open_count, live_open_count, mismatch, notes),
        )
        conn.commit()
    if mismatch:
        logger.warning(
            "POSITION MISMATCH db_open=%d live_open=%d — investigate before trusting counts",
            db_open_count, live_open_count,
        )
