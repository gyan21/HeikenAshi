import asyncio
import time
import json
import os
from datetime import datetime, time as dtime, timedelta
from utils.ibkr_client import IBKRClient
from utils.heikin_ashi import get_regular_and_heikin_ashi_close
from utils.trade_executor import execute_daily_trade, should_execute_daily_trade
from utils.trade_monitor import monitor_all_open_trades, should_monitor_trades
from utils.additional_trades import scan_for_additional_opportunities, should_scan_additional_opportunities
from utils.option_utils import get_next_option_expiry
from utils.logger import save_trade_to_log
from config.settings import ACCOUNT_VALUE

async def run_heikin_ashi_strategy(ib, symbol, expiry):
    """
    Main Heikin-Ashi based credit spread trading strategy
    Executes at 3:55 PM ET daily
    """
    if not should_execute_daily_trade():
        return
    
    print(f"🔄 Running Heikin-Ashi strategy for {symbol}")
    
    try:
        # Get regular close and Heikin-Ashi close
        daily_close_price, daily_close_ha = await get_regular_and_heikin_ashi_close(ib, symbol)
        
        print(f"Daily close price: {daily_close_price}")
        print(f"Daily Heikin-Ashi close: {daily_close_ha}")
        
        # Execute the trade based on new requirements
        trade_result = await execute_daily_trade(
            ib, symbol, expiry, daily_close_price, daily_close_ha
        )
        
        if trade_result:
            print("✅ Daily trade executed successfully")
            # Log the price comparison for trade records
            price_diff = daily_close_price - daily_close_ha
            print(f"Price difference (dailyClosePrice - dailyCloseHA): {price_diff:.2f}")
        else:
            print("❌ Daily trade not executed")
            
    except Exception as e:
        print(f"Error in Heikin-Ashi strategy: {e}")

async def run_additional_opportunities_scanner(ib, symbol, expiry):
    """
    Scan for additional trading opportunities during market hours
    """
    if not should_scan_additional_opportunities():
        return
    
    print(f"🔍 Scanning for additional opportunities for {symbol}")
    
    try:
        result = await scan_for_additional_opportunities(ib, symbol, expiry)
        if result:
            print("✅ Additional trade opportunity executed")
        else:
            print("ℹ️ No additional opportunities found")
    except Exception as e:
        print(f"Error scanning additional opportunities: {e}")

async def run_trade_monitoring(ib):
    """
    Monitor open trades for exit conditions
    """
    if not should_monitor_trades():
        return
    
    try:
        await monitor_all_open_trades(ib)
    except Exception as e:
        print(f"Error in trade monitoring: {e}")

async def main_strategy_loop(ib_client, symbol, expiry, interval=60):
    """Main strategy loop that runs all components"""
    print(f"🚀 Starting Heikin-Ashi Credit Spread Trading Algorithm")
    print(f"Symbol: {symbol}, Expiry: {expiry}")
    
    while True:
        loop_start = time.time()
        
        try:
            current_time = datetime.now()
            print(f"\n⏰ Strategy check at {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
            
            # Run different components based on time
            tasks = []
            
            # 1. Main Heikin-Ashi strategy (3:55-4:00 PM ET)
            if should_execute_daily_trade():
                tasks.append(run_heikin_ashi_strategy(ib_client.ib, symbol, expiry))
            
            # 2. Additional opportunities scanner (9:30 AM - 3:00 PM ET)
            if should_scan_additional_opportunities():
                tasks.append(run_additional_opportunities_scanner(ib_client.ib, symbol, expiry))
            
            # 3. Trade monitoring (during market hours)
            if should_monitor_trades():
                tasks.append(run_trade_monitoring(ib_client.ib))
            
            # Run applicable tasks
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            else:
                print("Outside trading hours - waiting...")
            
        except Exception as e:
            print(f"Error in main strategy loop: {e}")
        
        # Wait for next iteration
        elapsed = time.time() - loop_start
        sleep_time = max(0, interval - elapsed)
        await asyncio.sleep(sleep_time)

async def main():
    """Main entry point"""
    print("=" * 60)
    print("HEIKIN-ASHI CREDIT SPREAD TRADING ALGORITHM")
    print("=" * 60)
    
    # Connect to IBKR
    ib_client = IBKRClient()
    if not await ib_client.connect():
        print("❌ Could not connect to IBKR.")
        return

    print("✅ Connected to IBKR successfully")
    
    # Configuration
    symbol = 'SPY'
    expiry = await get_next_option_expiry(ib_client.ib, symbol)
    print(f"Trading symbol: {symbol}")
    print(f"Next option expiry: {expiry}")
    
    if not expiry:
        print("❌ Could not find a valid option expiry.")
        ib_client.disconnect()
        return

    try:
        # Run the main strategy loop
        await main_strategy_loop(ib_client, symbol, expiry)
        
    except KeyboardInterrupt:
        print("\n🛑 Strategy stopped by user")
    except Exception as e:
        print(f"❌ Unexpected error in main: {e}")
    finally:
        ib_client.disconnect()
        print("🔌 Disconnected from IBKR")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Program terminated by user")
    except Exception as e:
        print(f"❌ Fatal error: {e}")