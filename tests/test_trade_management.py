import os
import sys
import asyncio

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from utils import trade_utils
from utils import option_utils


def test_save_and_remove_open_trade(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    entry1 = {
        "symbol": "SPY",
        "sell_strike": 400,
        "buy_strike": 395,
        "expiry": "20240101",
        "open_price": 0.5,
        "quantity": 1,
    }
    trade_utils.save_open_trades([entry1])
    assert trade_utils.load_open_trades() == [entry1]
    entry2 = {
        "symbol": "SPY",
        "sell_strike": 450,
        "buy_strike": 455,
        "expiry": "20240101",
        "open_price": 0.6,
        "quantity": 1,
    }
    trade_utils.save_open_trades([entry1, entry2])
    trade_utils.remove_open_trade("SPY", 400, 395, "20240101")
    assert trade_utils.load_open_trades() == [entry2]


def test_resume_monitoring_open_trades(monkeypatch):
    trades = [
        {
            "symbol": "SPY",
            "sell_strike": 400,
            "buy_strike": 395,
            "expiry": "20240101",
            "quantity": 1,
            "open_price": 0.5,
            "type": "bull",
        },
        {
            "symbol": "SPY",
            "sell_strike": 450,
            "buy_strike": 455,
            "expiry": "20240101",
            "quantity": 2,
            "open_price": 0.6,
            "type": "bear",
        },
    ]

    called = []

    def fake_place_bull(ib, symbol, strikes, expiry, account_value, cb):
        called.append(("bull", symbol, strikes, expiry, account_value))

    def fake_place_bear(ib, symbol, strikes, expiry, account_value, cb):
        called.append(("bear", symbol, strikes, expiry, account_value))

    monkeypatch.setattr(trade_utils, "load_open_trades", lambda: trades)
    monkeypatch.setattr(option_utils, "place_bull_spread_with_oco", fake_place_bull)
    monkeypatch.setattr(option_utils, "place_bear_spread_with_oco", fake_place_bear)
    monkeypatch.setattr(trade_utils, "place_bull_spread_with_oco", fake_place_bull)
    monkeypatch.setattr(trade_utils, "place_bear_spread_with_oco", fake_place_bear)

    asyncio.run(trade_utils.resume_monitoring_open_trades(None))

    assert ("bull", "SPY", (400, 395), "20240101", 0.5 * 1) in called
    assert ("bear", "SPY", (450, 455), "20240101", 0.6 * 2) in called

