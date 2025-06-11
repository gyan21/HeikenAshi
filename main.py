import asyncio
import time
import json
import os
from datetime import datetime, time as dtime, timedelta
from utils.ibkr_client import IBKRClient
from utils.heikin_ashi import get_regular_and_heikin_ashi_close
from utils.common_utils import is_dry_run, has_reached_trade_limit
from utils.trade_utils import load_open_trades
from utils.option_utils import find_options_by_delta, should_trade_now
from utils.option_utils import place_bull_spread_with_oco, place_bear_spread_with_oco, get_option_iv
from utils.logger import TRADE_LOG_FILE, save_trade_to_log
from utils.option_utils import get_next_option_expiry
from utils.trade_utils import is_market_hours
from utils.option_utils import resume_monitoring_open_trades

ACCOUNT_VALUE = 100000

async def run_combined_strategy(ib, symbol, expiry, account_value, trade_log_callback=None):
    """
    Checks the delta of the option at 47, 52, and 57 minutes of the hour,
    and sells the spread if the sell side option has delta close to 0.20.
    """
    print(datetime.now().strftime("%Y-%m-%d %H:%M:%S") + f" run_combined_strategy for {symbol} with expiry {expiry}...")

    # Only run during the allowed window
    if not should_trade_now():
        print("Not in trading window.")
        return

    win_rate, position_scale = get_win_rate_and_position_scale()
    print(f"Win rate (last 2 weeks): {win_rate:.1f}%. Position scale: {position_scale*100:.0f}% of account value.")

    regular_close, ha_close = await get_regular_and_heikin_ashi_close(ib.ib, symbol)
    print(f"Regular close: {regular_close}, Heikin Ashi close: {ha_close}")

    check_minutes = [47, 52, 57]
    already_tried = set()

    now = datetime.now()
    minute = now.minute
    if minute in check_minutes and minute not in already_tried:
        already_tried.add(minute)
        print(f"⏰ Checking at {minute} minutes past the hour...")

    if regular_close > ha_close:
        # Bull case: Sell multiple PUT spreads
        options = await find_options_by_delta(ib.ib, symbol, expiry, 'P', min_delta=0.20, max_delta=0.30)
        if not options:
            print("No suitable PUT options found with delta in [0.20, 0.30).")
        else:
            for option, delta in options:
                sell_strike = option.strike
                buy_strike = sell_strike - 5
                await place_bull_spread_with_oco(
                    ib.ib, symbol, (sell_strike, buy_strike), expiry,
                    account_value * position_scale, trade_log_callback
                )
                print(f"✅ Sold PUT spread at strike {sell_strike} (delta {delta:.2f})")
    elif regular_close < ha_close:
        # Bear case: Sell multiple CALL spreads
        options = await find_options_by_delta(ib.ib, symbol, expiry, 'C', min_delta=0.20, max_delta=0.30)
        if not options:
            print("No suitable CALL options found with delta in [0.20, 0.30).")
        else:
            for option, delta in options:
                sell_strike = option.strike
                buy_strike = sell_strike + 5
                await place_bear_spread_with_oco(
                    ib.ib, symbol, (sell_strike, buy_strike), expiry,
                    account_value * position_scale, trade_log_callback
                )
                print(f"✅ Sold CALL spread at strike {sell_strike} (delta {delta:.2f})")
    else:
        print("No clear bull or bear case.")

    # Exit loop if all minutes have been checked or time window is over
    if len(already_tried) == len(check_minutes) or not should_trade_now():
        print("Finished all checks or trading window ended.")
    

def get_win_rate_and_position_scale(trade_log_file=TRADE_LOG_FILE):
    """
    Calculates win rate for the last 2 weeks of closed trades.
    Starts at 2% position size. For every 2-week period with win rate > 70%,
    increases position size by 1% (cumulative), up to a maximum of 5%.
    """
    now = datetime.now()
    position_scale = 0.02 # Start at 2%
    max_scale = 0.05      # Max 5%

    if not os.path.exists(trade_log_file):
        return 0.0, position_scale

    with open(trade_log_file, 'r', encoding="utf-8") as f:
        trades = json.load(f)

    # Only consider closed trades
    trades = [t for t in trades if t.get("status", "").lower().startswith("exited")]
    if not trades:
        return 0.0, position_scale

    # Sort trades by date ascending
    trades = sorted(trades, key=lambda t: t.get("date", ""))

    # Find the earliest and latest trade date
    try:
        earliest_date = datetime.strptime(trades[0]["date"], "%Y-%m-%d %H:%M:%S")
        latest_date = datetime.strptime(trades[-1]["date"], "%Y-%m-%d %H:%M:%S")
    except Exception:
        return 0.0, position_scale

    # Step through 2-week windows, scaling up if win rate > 70%
    window_start = earliest_date
    while window_start < latest_date:
        window_end = window_start + timedelta(days=14)
        window_trades = [
            t for t in trades
            if window_start <= datetime.strptime(t["date"], "%Y-%m-%d %H:%M:%S") < window_end
        ]
        if window_trades:
            wins = sum(1 for t in window_trades if t.get("profit", 0) > 0)
            win_rate = (wins / len(window_trades)) * 100
            if win_rate > 70 and position_scale < max_scale:
                position_scale += 0.01
        window_start = window_end

    # For the current 2-week window, return its win rate
    two_weeks_ago = now - timedelta(days=14)
    current_window_trades = [
        t for t in trades
        if two_weeks_ago <= datetime.strptime(t["date"], "%Y-%m-%d %H:%M:%S") <= now
    ]
    if current_window_trades:
        wins = sum(1 for t in current_window_trades if t.get("profit", 0) > 0)
        win_rate = (wins / len(current_window_trades)) * 100
    else:
        win_rate = 0.0

    # Cap position_scale at 5%
    position_scale = min(position_scale, max_scale)
    return win_rate, position_scale

async def run_strategy_periodically(ib_client, symbol, expiry, interval=60):
    """Run strategy every X seconds"""
    while True:
        try:
            if not is_dry_run() and should_trade_now():
                await run_combined_strategy(ib_client, symbol, expiry, ACCOUNT_VALUE, save_trade_to_log)
                print(datetime.now().strftime("%Y-%m-%d %H:%M:%S") + " Strategy executed")
        except Exception as e:
            print(f"Error in strategy execution: {e}")
        await asyncio.sleep(interval)
        
async def main():
    ib_client = IBKRClient()
    if not await ib_client.connect():
        print("❌ Could not connect to IBKR.")
        return

    symbol = 'SPY'
    expiry = await get_next_option_expiry(ib_client.ib, symbol)
    print(f"Next option expiry: {expiry}")
    if not expiry:
        print("❌ Could not find a valid option expiry.")
        return

    # Start monitoring and strategy tasks
    monitoring_task = asyncio.create_task(
        resume_monitoring_open_trades(ib_client.ib, save_trade_to_log)
    )
    strategy_task = asyncio.create_task(
        run_strategy_periodically(ib_client, symbol, expiry)
    )

    try:
        await asyncio.gather(monitoring_task, strategy_task)
    except asyncio.CancelledError:
        print("Shutting down gracefully...")
    except Exception as e:
        print(f"Unexpected error: {e}")
    finally:
        ib_client.disconnect()
        print("Disconnected from IBKR")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Program stopped by user")