import time
import json
import os
from datetime import datetime, time as dtime, timedelta
from utils.ibkr_client import IBKRClient
from utils.heikin_ashi import get_regular_and_heikin_ashi_close
from utils.common_utils import is_dry_run, has_reached_trade_limit
from utils.excel_utils import save_trade_to_excel
from utils.trade_utils import log_trade_close, load_open_trades, find_option_by_delta, find_options_by_delta
from utils.option_utils    import place_bull_spread_with_oco, place_bear_spread_with_oco, get_option_iv
from utils.logger import TRADE_LOG_FILE, save_trade_to_log
from utils.option_utils import get_next_option_expiry
from utils.trade_utils import is_market_hours
ACCOUNT_VALUE = 100000
def is_time_between(start, end):
    now = datetime.now().time()
    return start <= now <= end

def should_trade_now():
    # return is_time_between(dtime(15, 45), dtime(16, 0))
    return 1

def is_iv_favorable(iv, iv_threshold=0.25):
    return iv is not None and iv > iv_threshold

def run_combined_strategy(ib, symbol, expiry, account_value, trade_log_callback=None):
    """
    Checks the delta of the option at 48, 53, and 57 minutes of the hour,
    and sells the spread if the sell side option has delta close to 0.20.
    """
    from datetime import datetime

    # Only run during the allowed window
    if not should_trade_now():
        print("Not in trading window.")
        return

    win_rate, position_scale = get_win_rate_and_position_scale()
    print(f"Win rate (last 2 weeks): {win_rate:.1f}%. Position scale: {position_scale*100:.0f}% of account value.")

    regular_close, ha_close = get_regular_and_heikin_ashi_close(ib.ib, symbol)
    print(f"Regular close: {regular_close}, Heikin Ashi close: {ha_close}")

    # Minutes to check: 47, 52, 57
    check_minutes = [47, 52, 57]
    already_tried = set()

    while True:
        now = datetime.now()
        minute = now.minute
        # Gyanesh if minute in check_minutes and minute not in already_tried:
        already_tried.add(minute)
        print(f"⏰ Checking at {minute} minutes past the hour...")

        if regular_close > ha_close:
            # Bull case: Sell multiple PUT spreads
            options = find_options_by_delta(ib.ib, symbol, expiry, 'P', min_delta=0.20, max_delta=0.30)
            if not options:
                print("No suitable PUT options found with delta in [0.20, 0.30).")
            else:
                for option, delta in options:
                    iv = get_option_iv(ib.ib, option)
                    if not is_iv_favorable(iv):
                        print(f"Volatility not favorable for PUT {option.strike}.")
                        continue
                    sell_strike = option.strike
                    buy_strike = sell_strike - 5
                    place_bull_spread_with_oco(
                        ib.ib, symbol, (sell_strike, buy_strike), expiry,
                        account_value * position_scale, trade_log_callback
                    )
                    print(f"✅ Sold PUT spread at strike {sell_strike} (delta {delta:.2f})")
        elif regular_close < ha_close:
            # Bear case: Sell multiple CALL spreads
            options = find_options_by_delta(ib.ib, symbol, expiry, 'C', min_delta=0.20, max_delta=0.30)
            if not options:
                print("No suitable CALL options found with delta in [0.20, 0.30).")
            else:
                for option, delta in options:
                    iv = get_option_iv(ib.ib, option)
                    if not is_iv_favorable(iv):
                        print(f"Volatility not favorable for CALL {option.strike}.")
                        continue
                    sell_strike = option.strike
                    buy_strike = sell_strike + 5
                    place_bear_spread_with_oco(
                        ib.ib, symbol, (sell_strike, buy_strike), expiry,
                        account_value * position_scale, trade_log_callback
                    )
                    print(f"✅ Sold CALL spread at strike {sell_strike} (delta {delta:.2f})")
        else:
            print("No clear bull or bear case.")

        # Exit loop if all minutes have been checked or time window is over
        if len(already_tried) == len(check_minutes) or not should_trade_now():
            print("Finished all checks or trading window ended.")
            break

        time.sleep(20) # Check every 20 seconds for the next minute

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

    with open(trade_log_file, 'r') as f:
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

def resume_monitoring_open_trades(ib, trade_log_callback=None):
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

def main():
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

    # Set market data type based on market hours
    if is_market_hours():
        ib_client.ib.reqMarketDataType(1)  # Live
        print("✅ Using LIVE market data")
    else:
        ib_client.ib.reqMarketDataType(2)  # Frozen
        print("✅ Using FROZEN market data (after hours)")

    # Resume monitoring for open trades
    resume_monitoring_open_trades(ib_client, save_trade_to_log)

    symbol = 'SPY'
    expiry = get_next_option_expiry(ib_client.ib, symbol)
    print(f"Next option expiry: {expiry}")
    if not expiry:
        print("❌ Could not find a valid option expiry.")
        return

    # Run strategy every minute during trading window
    while should_trade_now():
        run_combined_strategy(ib_client, symbol, expiry, ACCOUNT_VALUE, save_trade_to_log)
        time.sleep(60)

if __name__ == "__main__":
    main()