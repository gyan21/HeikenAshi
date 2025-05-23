import datetime
import json
import os
import numpy as np
from ib_insync import Stock, Option
from utils.logger import save_trade_to_log

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

def find_option_by_delta(ib, symbol, expiry=None, right='C', target_delta=0.20, tolerance=0.05):
    """
    Find the option contract for the next expiry with delta in [0.20, 0.30).
    Returns the Option contract closest to target_delta within that range.
    """
    contract = Stock(symbol, 'SMART', 'USD')
    ib.qualifyContracts(contract)
    chain = ib.reqSecDefOptParams(contract.symbol, '', contract.secType, contract.conId)
    if not chain:
        return None

    # Find next expiry if not provided
    expiries = sorted(list(set(chain[0].expirations)))
    today = datetime.date.today()
    if expiry is None:
        for expiry_str in expiries:
            expiry_date = datetime.datetime.strptime(expiry_str, "%Y%m%d").date()
            if expiry_date > today:
                expiry = expiry_str
                break
    if not expiry:
        return None

    strikes_list = sorted(chain[0].strikes)
    best_option = None
    best_delta_diff = float('inf')

    for strike in strikes_list:
        option = Option(symbol, expiry, strike, right, 'SMART')
        ib.qualifyContracts(option)
        data = ib.reqMktData(option, '', False, False)
        ib.sleep(0.4)  # Reduce to 0.4s to speed up, but avoid pacing violation
        delta = getattr(getattr(data, 'modelGreeks', None), 'delta', None)
        ib.cancelMktData(option)
        if delta is not None and 0.20 <= abs(delta) < 0.30:
            delta_diff = abs(abs(delta) - target_delta)
            if delta_diff < best_delta_diff:
                best_delta_diff = delta_diff
                best_option = option
                # Early exit if perfect match
                if delta_diff < 1e-3:
                    break

    return best_option

def find_options_by_delta(ib, symbol, expiry=None, right='C', min_delta=0.20, max_delta=0.30):
    """
    Return a list of Option contracts for the next expiry with delta in [min_delta, max_delta).
    Only checks valid strikes for the expiry, within ±20 of the current price.
    Logs each checked strike and each match.
    """
    contract = Stock(symbol, 'SMART', 'USD')
    ib.qualifyContracts(contract)
    chain = ib.reqSecDefOptParams(contract.symbol, '', contract.secType, contract.conId)
    if not chain:
        print(f"[WARN] No option chain found for {symbol}")
        return []

    # Find next expiry if not provided
    expiries = sorted(list(set(chain[0].expirations)))
    today = datetime.date.today()
    if expiry is None:
        for expiry_str in expiries:
            expiry_date = datetime.datetime.strptime(expiry_str, "%Y%m%d").date()
            if expiry_date > today:
                expiry = expiry_str
                break
    if not expiry:
        print(f"[WARN] No valid expiry found for {symbol}")
        return []

    # Get current price
    ticker = ib.reqMktData(contract, '', False, False)
    ib.sleep(1)
    price = ticker.marketPrice() if hasattr(ticker, 'marketPrice') else None
    ib.cancelMktData(contract)
    if price is None or price <= 0:
        print(f"[WARN] Could not get current price for {symbol}")
        return []

    # Get valid strikes for this expiry using reqContractDetails
    from ib_insync import Option
    details = ib.reqContractDetails(Option(symbol, expiry, 0, right, 'SMART'))
    valid_strikes = sorted({cd.contract.strike for cd in details if abs(cd.contract.strike - price) <= 20})

    matching_options = []
    for strike in valid_strikes:
        print(f"[INFO] Checking strike {strike} for {symbol} {expiry} {right}")
        option = Option(symbol, expiry, strike, right, 'SMART')
        ib.qualifyContracts(option)
        data = ib.reqMktData(option, '', False, False)
        ib.sleep(0.4)  # Avoid pacing violation
        delta = getattr(getattr(data, 'modelGreeks', None), 'delta', None)
        print(f"[INFO] Delta for {symbol} {expiry} {right} {strike}: {delta} | Bid: {data.bid}, Ask: {data.ask}, Last: {data.last}")
        ib.cancelMktData(option)
        if delta is not None and min_delta <= abs(delta) < max_delta:
            print(f"[MATCH] {symbol} {expiry} {right} {strike} delta={delta:.3f}")
            matching_options.append((option, delta))

    if not matching_options:
        print(f"[INFO] No options found for {symbol} {expiry} {right} in delta range [{min_delta}, {max_delta})")
    return matching_options