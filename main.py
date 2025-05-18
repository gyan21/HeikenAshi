import asyncio
from datetime import datetime, time
from utils.ibkr_client import IBKRClient
from utils.heikin_ashi import get_regular_and_heikin_ashi_close
from utils.option_utils import (
    find_option_by_delta,
    get_option_iv,
    place_bull_spread_with_oco,
    place_bear_spread_with_oco
)
from utils.common_utils import is_dry_run, has_reached_trade_limit
import json
import os

ACCOUNT_VALUE = 100000
TRADE_LOG_FILE = 'trade_log.json'

def save_trade_to_log(trade_info):
    log_data = []
    if os.path.exists(TRADE_LOG_FILE):
        with open(TRADE_LOG_FILE, 'r') as f:
            log_data = json.load(f)
    log_data.append(trade_info)
    with open(TRADE_LOG_FILE, 'w') as f:
        json.dump(log_data, f, indent=2)

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
        place_bull_spread_with_oco(ib, symbol, (sell_strike, buy_strike), expiry, account_value, trade_log_callback)
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
        place_bear_spread_with_oco(ib, symbol, (sell_strike, buy_strike), expiry, account_value, trade_log_callback)
    else:
        print("No clear bull or bear case.")

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

    symbol = 'SPY'
    expiry = None  # Set this to the next expiry date string, e.g., '20240520'
    await run_combined_strategy(ib_client, symbol, expiry, ACCOUNT_VALUE, save_trade_to_log)
    ib_client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())