"""
Verifies settlement stations against Kalshi's own market metadata rather
than trusting a hardcoded city->airport guess.

Why this matters: Kalshi settles Chicago temperature contracts on Midway
(KMDW), not O'Hare (KORD). Houston settles on Hobby (KHOU), not Bush
Intercontinental. Getting this wrong means forecasting the wrong station
entirely while looking completely fine in the logs.

config.yaml's "expected_station" is a starting guess. This module confirms
it against the live market's settlement details before the bot ever prices
a contract for that city. If verification fails, the city is skipped for
that run (logged clearly) rather than traded on an unconfirmed guess.
"""
import logging

from src.kalshi_client import KalshiClient

logger = logging.getLogger(__name__)


def verify_station(client: KalshiClient, market_ticker: str, expected_station: str) -> bool:
    """
    Pulls a market's settlement details and checks whether expected_station
    appears in it. Kalshi's settlement source description typically
    includes the station name/ICAO code.

    Returns True if confirmed, False otherwise (and logs why).
    """
    try:
        market = client.get_market(market_ticker)
    except Exception as e:
        logger.warning(
            "station_verify_failed ticker=%s reason=api_error error=%s",
            market_ticker, e,
        )
        return False

    settlement_source = str(market.get("settlement_sources", market.get("rules_primary", "")))

    if expected_station.upper() in settlement_source.upper():
        logger.debug(
            "station_verify_ok ticker=%s station=%s", market_ticker, expected_station
        )
        return True

    logger.warning(
        "station_verify_MISMATCH ticker=%s expected=%s settlement_source=%r — "
        "skipping this city until mapping is confirmed manually",
        market_ticker, expected_station, settlement_source,
    )
    return False
