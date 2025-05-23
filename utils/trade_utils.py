import datetime
import os
import numpy as np
from ib_insync import Stock, Option
from logger import save_trade_to_log
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

def find_option_by_delta(ib, symbol, expiry, right, target_delta=0.20, tolerance=0.05):
    # right: 'P' for put, 'C' for call
    strikes = []
    deltas = []
    options = []
    contract = Stock(symbol, 'SMART', 'USD')
    ib.qualifyContracts(contract)
    chain = ib.reqSecDefOptParams(contract.symbol, '', contract.secType, contract.conId)
    if not chain:
        return None
    strikes_list = sorted(chain[0].strikes)
    for strike in strikes_list:
        option = Option(symbol, expiry, strike, right, 'SMART')
        ib.qualifyContracts(option)
        data = ib.reqMktData(option, '', False, False)
        ib.sleep(0.5)
        delta = getattr(getattr(data, 'modelGreeks', None), 'delta', None)
        ib.cancelMktData(option)
        if delta is not None:
            deltas.append(abs(delta))
            strikes.append(strike)
            options.append(option)
    if not deltas:
        return None
    deltas = np.array(deltas)
    idx = (np.abs(deltas - target_delta)).argmin()
    if abs(deltas[idx] - target_delta) <= tolerance:
        return options[idx]
    return None