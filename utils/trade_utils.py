from datetime import datetime
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
    
def load_open_trades(trade_log_file=TRADE_LOG_FILE):
    open_trades = []
    if not os.path.exists(trade_log_file):
        return open_trades
    with open(trade_log_file, 'r') as f:
        trades = json.load(f)
        for trade in trades:
            if trade.get("status") == "Open":
                open_trades.append(trade)
    return open_trades

def is_market_hours():
    # US market hours: 9:30am to 4:00pm Eastern Time
    from datetime import datetime, time as dtime
    import pytz
    eastern = pytz.timezone('US/Eastern')
    now = datetime.now(eastern).time()
    return dtime(9, 30) <= now <= dtime(16, 15)

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