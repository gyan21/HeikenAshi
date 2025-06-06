import datetime
import json
import os
import numpy as np
from ib_insync import Stock, Option
from utils.logger import save_trade_to_log
from utils.option_utils import place_bear_spread_with_oco, place_bull_spread_with_oco

TRADE_LOG_FILE = "trade_log.xlsx"  # or your preferred path/filename
def log_trade_close(trade, open_price, close_price, quantity, trade_type, status, reason):
    profit = (close_price - open_price) * quantity if trade_type == "bull" else (open_price - close_price) * quantity
    profit_pct = (profit / (open_price * quantity)) * 100 if open_price else 0
    log_entry = {
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "spread": trade.get("spread"),
        "open_price": open_price,
        "close_price": close_price,
        "profit": profit,
        "profit_pct": profit_pct,
        "status": status,
        "close_reason": reason,
        "quantity": quantity
    }
    save_trade_to_log(log_entry)
    # Only log closed trades to Excel
    from utils.excel_utils import save_trade_to_excel
    save_trade_to_excel(log_entry)
    
def load_open_trades():
    if not os.path.exists("open_trades.json"):
        return []
    with open("open_trades.json", "r", encoding="utf-8") as f:
        return json.load(f)

def is_market_hours():
    # US market hours: 9:30am to 4:00pm Eastern Time
    from datetime import datetime, time as dtime
    import pytz
    eastern = pytz.timezone('US/Eastern')
    now = datetime.now(eastern).time()
    return dtime(9, 30) <= now <= dtime(16, 0)

async def resume_monitoring_open_trades(ib, trade_log_callback=None):
    open_trades = load_open_trades()
    for trade in open_trades:
        symbol = trade["symbol"]
        sell_strike = float(trade["sell_strike"])
        buy_strike = float(trade["buy_strike"])
        expiry = trade["expiry"]
        quantity = trade["quantity"]
        open_price = trade["open_price"]
        spread_type = trade.get("type")
        if spread_type == "bull":
            place_bull_spread_with_oco(
                ib, symbol, (sell_strike, buy_strike), expiry,
                open_price * quantity, trade_log_callback
            )
        elif spread_type == "bear":
            place_bear_spread_with_oco(
                ib, symbol, (sell_strike, buy_strike), expiry,
                open_price * quantity, trade_log_callback
            )

def log_trade_close(trade, open_price, close_price, quantity, trade_type, status, reason):
    profit = (close_price - open_price) * quantity if trade_type == "bull" else (open_price - close_price) * quantity
    profit_pct = (profit / (open_price * quantity)) * 100 if open_price else 0
    log_entry = {
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "spread": trade.get("spread"),
        "open_price": open_price,
        "close_price": close_price,
        "profit": profit,
        "profit_pct": profit_pct,
        "status": status,
        "close_reason": reason,
        "quantity": quantity
    }
    # Only log closed trades to Excel
    from utils.excel_utils import save_trade_to_excel
    save_trade_to_excel(log_entry)

def save_open_trades(trades):
    with open("open_trades.json", "w", encoding="utf-8") as f:
        json.dump(trades, f, indent=2)