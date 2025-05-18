import asyncio
from datetime import datetime, time, timedelta
from utils.ibkr_client import IBKRClient
from utils.heikin_ashi import get_regular_and_heikin_ashi_close
from utils.option_utils import (
    find_option_by_delta,
    get_option_iv,
    place_bull_spread_with_oco,
    place_bear_spread_with_oco
)
from utils.common_utils import is_dry_run, has_reached_trade_limit
from utils.excel_utils import save_trade_to_excel  # Add this import
import json
import os

ACCOUNT_VALUE = 100000
TRADE_LOG_FILE = 'trade_log.json'

def save_trade_to_log(trade_info):
    log_data = []
    if os.path.exists(TRADE_LOG_FILE):
        with open(TRADE_LOG_FILE, 'r') as f:
            log_data = json.load(f)
    # Remove any previous "Open" entry for this spread if closing
    if trade_info.get("status", "").startswith("Exited"):
        log_data = [t for t in log_data if not (
            t.get("spread") == trade_info.get("spread") and t.get("status") == "Open"
        )]
    log_data.append(trade_info)
    with open(TRADE_LOG_FILE, 'w') as f:
        json.dump(log_data, f, indent=2)
    # Remove or comment out this line:
    # save_trade_to_excel(trade_info)

def is_time_between(start, end):
    now = datetime.now().time()
    return start <= now <= end

def should_trade_now():
    return is_time_between(time(15, 45), time(16, 0))

def is_iv_favorable(iv, iv_threshold=0.25):
    # You may want to use a dynamic threshold based on historical IV
    return iv is not None and iv > iv_threshold

async def run_combined_strategy(ib, symbol, expiry, account_value, trade_log_callback=None):
    if not should_trade_now():
        print("Not in trading window.")
        return

    win_rate, position_scale = get_win_rate_and_position_scale()
    print(f"Win rate (last 2 weeks): {win_rate:.1f}%. Position scale: {position_scale*100:.0f}% of account value.")

    regular_close, ha_close = get_regular_and_heikin_ashi_close(ib, symbol)
    print(f"Regular close: {regular_close}, Heikin Ashi close: {ha_close}")

    if regular_close > ha_close:
        # Bull case: Sell PUT spread
        option = find_option_by_delta(ib, symbol, expiry, 'P', target_delta=0.20)
        if not option:
            print("No suitable PUT option found near delta 0.20.")
            return
        iv = get_option_iv(ib, option)
        if not is_iv_favorable(iv):
            print("Volatility not favorable for selling PUT spread.")
            return
        sell_strike = option.strike
        buy_strike = sell_strike - 5
        place_bull_spread_with_oco(
            ib, symbol, (sell_strike, buy_strike), expiry,
            account_value * position_scale, trade_log_callback
        )
    elif regular_close < ha_close:
        # Bear case: Sell CALL spread
        option = find_option_by_delta(ib, symbol, expiry, 'C', target_delta=0.20)
        if not option:
            print("No suitable CALL option found near delta 0.20.")
            return
        iv = get_option_iv(ib, option)
        if not is_iv_favorable(iv):
            print("Volatility not favorable for selling CALL spread.")
            return
        sell_strike = option.strike
        buy_strike = sell_strike + 5
        place_bear_spread_with_oco(
            ib, symbol, (sell_strike, buy_strike), expiry,
            account_value * position_scale, trade_log_callback
        )
    else:
        print("No clear bull or bear case.")

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

def get_win_rate_and_position_scale(trade_log_file=TRADE_LOG_FILE):
    now = datetime.now()
    two_weeks_ago = now - timedelta(days=14)
    wins = 0
    total = 0

    if not os.path.exists(trade_log_file):
        return 0.0, 0.02

    with open(trade_log_file, 'r') as f:
        trades = json.load(f)
        for trade in trades:
            try:
                trade_date = datetime.strptime(trade.get("date", ""), "%Y-%m-%d %H:%M:%S")
            except Exception:
                continue
            if trade_date < two_weeks_ago:
                continue
            if trade.get("status", "").lower().startswith("exited"):
                total += 1
                profit = trade.get("profit", None)
                if profit is not None and profit > 0:
                    wins += 1

    win_rate = (wins / total) * 100 if total > 0 else 0.0
    position_scale = 0.03 if win_rate > 70 else 0.02
    return win_rate, position_scale

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
        # Resume monitoring by calling the appropriate OCO function
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

async def main():
    if is_dry_run():
        print("🧪 Dry run mode — weekend detected. No trades will be placed.")
        return

    if has_reached_trade_limit():
        print("⚠️ Trade limit reached for today. Exiting.")
        return

    ib_client = IBKRClient()
    if not ib_client.connect():
        print("❌ Could not connect to IBKR.")
        return

    # Resume monitoring for open trades
    await resume_monitoring_open_trades(ib_client, save_trade_to_log)

    # ...then place new trades as usual...

if __name__ == "__main__":
    asyncio.run(main())