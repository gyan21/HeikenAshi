import asyncio
from utils.ibkr_client import IBKRClient
from utils.heikin_ashi import is_bull_case
from utils.option_utils import place_bull_spread_with_oco
from utils.common_utils import is_dry_run, has_reached_trade_limit
from datetime import datetime
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

async def main():
    if is_dry_run():
        print("🧪 Dry run mode — weekend detected. No trades will be placed.")
        ib_client.disconnect()
        return

    if has_reached_trade_limit():
        print("⚠️ Trade limit reached for today. Exiting.")
        ib_client.disconnect()
        return

    ib_client = IBKRClient()
    if not ib_client.connect():
        print("❌ Could not connect to IBKR.")
        return

    if not is_bull_case(ib_client):
        print("📉 Bear case detected — skipping trade.")
        ib_client.disconnect()
        return

    symbol = 'SPY'
    expiry = ib_client.find_expiry_for_next_day(symbol)

    # === Spread 1: Based on today's low
    today_low = int(ib_client.get_today_low(symbol))
    spread_1 = (today_low, today_low - 5)

    print(f"🚀 Placing spread 1 (based on low): {spread_1} expiring {expiry}")
    trade_info_1 = place_bull_spread_with_oco(
        ib=ib_client.ib,
        symbol=symbol,
        strike_pair=spread_1,
        expiry=expiry,
        account_value=ACCOUNT_VALUE,
        trade_log_callback=save_trade_to_log
    )

    # === Spread 2: Based on delta ≈ 0.20
    try:
        delta_option = ib_client.find_put_with_delta(symbol, target_delta=0.20)
        strike_2 = int(float(delta_option.strike))
        spread_2 = (strike_2, strike_2 - 5)

        print(f"🚀 Placing spread 2 (delta≈0.20): {spread_2} expiring {expiry}")
        trade_info_2 = place_bull_spread_with_oco(
            ib=ib_client.ib,
            symbol=symbol,
            strike_pair=spread_2,
            expiry=expiry,
            account_value=ACCOUNT_VALUE,
            trade_log_callback=save_trade_to_log
        )

    except Exception as e:
        print(f"⚠️ Failed to place spread 2 (delta ≈ 0.20): {e}")

    while True:
        await asyncio.sleep(60)

if __name__ == "__main__":
    asyncio.run(main())
#     ib_client.disconnect()