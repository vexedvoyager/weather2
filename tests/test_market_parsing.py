from src.market_parsing import extract_threshold, build_market_snapshot, _best_level_size


def test_greater_or_equal_uses_floor_strike():
    market = {"strike_type": "greater_or_equal", "floor_strike": 80.0, "cap_strike": None}
    result = extract_threshold(market)
    assert result == {"kind": "single", "value": 80.0}


def test_greater_uses_floor_strike():
    market = {"strike_type": "greater", "floor_strike": 75.5, "cap_strike": None}
    result = extract_threshold(market)
    assert result == {"kind": "single", "value": 75.5}


def test_less_or_equal_uses_cap_strike():
    market = {"strike_type": "less_or_equal", "floor_strike": None, "cap_strike": 60.0}
    result = extract_threshold(market)
    assert result == {"kind": "single", "value": 60.0}


def test_between_uses_both_floor_and_cap():
    market = {"strike_type": "between", "floor_strike": 78.0, "cap_strike": 80.0}
    result = extract_threshold(market)
    assert result == {"kind": "between", "floor": 78.0, "cap": 80.0}


def test_missing_required_field_returns_none_not_a_guess():
    market = {"strike_type": "greater_or_equal", "floor_strike": None, "cap_strike": None}
    assert extract_threshold(market) is None


def test_unrecognized_strike_type_returns_none():
    market = {"strike_type": "functional", "floor_strike": 1, "cap_strike": 2}
    assert extract_threshold(market) is None


def test_best_level_size_reads_last_element_ascending_order():
    # Kalshi orderbook levels are ascending by price; best bid is the LAST one.
    levels = [["0.10", "5.00"], ["0.20", "3.00"], ["0.55", "12.00"]]
    assert _best_level_size(levels) == 12


def test_best_level_size_empty_list():
    assert _best_level_size([]) == 0


def test_build_market_snapshot_derives_ask_from_opposite_bid():
    market = {
        "yes_bid_dollars": "0.5600",
        "no_bid_dollars": "0.4200",
        "volume_24h_fp": "150.00",
    }
    orderbook = {
        "yes_dollars": [["0.50", "10.00"], ["0.56", "25.00"]],
        "no_dollars": [["0.40", "8.00"], ["0.42", "15.00"]],
    }
    snap = build_market_snapshot("TEST-TICKER", market, orderbook)

    assert snap.yes_bid_cents == 56
    assert snap.no_bid_cents == 42
    # YES ask should be 100 - no_bid = 100 - 42 = 58
    assert snap.yes_ask_cents == 58
    # NO ask should be 100 - yes_bid = 100 - 56 = 44
    assert snap.no_ask_cents == 44
    assert snap.volume_24h == 150
    assert snap.yes_bid_size == 25
    assert snap.no_bid_size == 15
