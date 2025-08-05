import asyncio
from datetime import datetime, timedelta
from ib_insync import Option
from utils.pattern_utils import check_additional_entry_pattern
from utils.delta_option_finder import find_both_options_for_spread, calculate_spread_premium
from utils.trade_executor import create_spread_order, create_close_order
from utils.logger import save_trade_to_log
from config.settings import MIN_PREMIUM_NEXT_DAY, MIN_PREMIUM_NEXT_DAY_AFTER_12, MIN_PREMIUM_NEXT_DAY_BEFORE_12, SPREAD_WIDTH
from utils.pattern_utils import check_additional_entry_pattern
from utils.delta_option_finder import find_option_by_delta_range, calculate_spread_premium
from utils.trade_executor import create_spread_order, create_close_order
from utils.logger import save_trade_to_log
from utils.trade_utils import load_open_trades, save_open_trades, load_closed_trades

async def check_additional_trade_opportunity(ib, symbol, expiry, previous_trade_direction):
    """
    Check for additional trade opportunities on the next day.

    Args:
        ib: IBKR connection
        symbol: Stock symbol
        expiry: Option expiry
        previous_trade_direction: 'bull' or 'bear' from previous day's Heikin-Ashi logic

    Returns:
        dict with trade info if opportunity found, None otherwise
    """
    print(f"Checking additional trade opportunity for {previous_trade_direction} direction")

    # Check if the required pattern is present
    pattern_confirmed = await check_additional_entry_pattern(
        ib, symbol, previous_trade_direction, include_previous_day=True
    )

    if not pattern_confirmed:
        print(f"Pattern not confirmed for additional {previous_trade_direction} trade")
        return None

    print(f"✅ Pattern confirmed for additional {previous_trade_direction} trade")

    # Find suitable options using find_both_options_for_spread
    options_data = await find_both_options_for_spread(ib, symbol, expiry)

    if previous_trade_direction == 'bull':
        # Bull direction: Use Put credit spreads
        if not options_data.get('put'):
            print("No suitable Put option found for additional Bull trade")
            return None

        put_data = options_data['put']
        sell_option = put_data['short_option']
        buy_option = put_data['long_option']

    else:  # bear
        # Bear direction: Use Call credit spreads
        if not options_data.get('call'):
            print("No suitable Call option found for additional Bear trade")
            return None

        call_data = options_data['call']
        sell_option = call_data['short_option']
        buy_option = call_data['long_option']

    # Calculate premium
    premium = await calculate_spread_premium(ib, sell_option, buy_option)
    print(f"Additional trade premium: ${premium:.2f} per contract")

    # Check if premium meets minimum requirement for next-day trades
    if premium < MIN_PREMIUM_NEXT_DAY:
        print(f"Premium ${premium:.2f} below minimum ${MIN_PREMIUM_NEXT_DAY} for additional trades")
        return None

    return {
        'sell_option': sell_option,
        'buy_option': buy_option,
        'premium': premium,
        'trade_direction': previous_trade_direction,
        'delta': options_data.get('put' if previous_trade_direction == 'bull' else 'call', {}).get('delta')
    }

async def execute_additional_trade(ib, symbol, expiry, opportunity_data, quantity=None):
    """
    Execute an additional trade opportunity
    
    Args:
        ib: IBKR connection
        symbol: Stock symbol
        expiry: Option expiry
        opportunity_data: Data from check_additional_trade_opportunity
        quantity: Number of contracts (optional, will use default if None)
    """
    if not opportunity_data:
        return None
    
    try:
        sell_option = opportunity_data['sell_option']
        buy_option = opportunity_data['buy_option']
        premium = opportunity_data['premium']
        trade_direction = opportunity_data['trade_direction']
        
        # Use a smaller quantity for additional trades if not specified
        if quantity is None:
            from utils.quantity_manager import get_current_trade_quantity
            base_quantity = get_current_trade_quantity()
            quantity = max(1, base_quantity // 3)  # Use 1/3 of main trade quantity
        
        print(f"Executing additional {trade_direction} trade with {quantity} contracts")
        
        # Create spread order
        combo, main_order = await create_spread_order(
            ib, sell_option, buy_option, quantity, premium,
            is_bull_spread=(trade_direction == 'bull')
        )
        
        if not combo or not main_order:
            print("Failed to create additional spread order")
            return None
        try:
            # Create closing order
            close_order = await create_close_order(ib, quantity)
            close_order.parentId = main_order.orderId
        
            # Place orders
            main_trade = ib.placeOrder(combo, main_order)
            # Verify order status
            print(f"Order status: {main_trade.orderStatus.status}")
            if main_trade.orderStatus.status == 'Cancelled':
                print(f"Order was cancelled: {main_trade.log}")
                return None
            # Place the closing order
            close_trade = ib.placeOrder(combo, close_order)
        
            # Log the additional trade
            trade_info = {
                "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "trade_type": "Additional",
                "trade_direction": trade_direction,
                "spread": f"{symbol} {sell_option.strike}/{buy_option.strike} {expiry}",
                "option_type": sell_option.right,
                "quantity": quantity,
                "target_premium": premium,
                "status": "Open",
                "sell_strike": sell_option.strike,
                "buy_strike": buy_option.strike,
                "sell_delta": opportunity_data.get('delta'),
                "main_order_id": main_trade.order.orderId,
                "close_order_id": close_trade.order.orderId
            }
            
            save_trade_to_log(trade_info)
            print(f"✅ Additional {trade_direction} spread trade placed successfully")
            
            return trade_info
        except Exception as e:
            print(f"Error placing spread orders: {e}")
            return None
        
    except Exception as e:
        print(f"Error executing additional trade: {e}")
        return None

async def scan_for_additional_opportunities(ib, symbol, expiry):
    """
    Scan for additional trading opportunities based on previous day's trades
    
    This should run during market hours on the trading day after the main trade
    """
    try:
        # Get the last trade direction from the previous day
        from utils.logger import TRADE_LOG_FILE
        import json
        import os
        
        if not os.path.exists(TRADE_LOG_FILE):
            print("No trade log found")
            return None
        
        with open(TRADE_LOG_FILE, 'r', encoding='utf-8') as f:
            trades = json.load(f)
        
        # Find the most recent main trade (not additional)
        main_trades = [
            t for t in trades 
            if t.get('trade_type') != 'Additional' and 
            'trade_direction' in t
        ]
        
        if not main_trades:
            print("No main trades found for additional opportunity scan")
            return None
        
        # Get the most recent main trade
        latest_trade = max(main_trades, key=lambda x: x.get('date', ''))
        previous_direction = latest_trade.get('trade_direction')
        
        if not previous_direction:
            print("Could not determine previous trade direction")
            return None
        
        print(f"Scanning for additional {previous_direction} opportunities")
        
        # Check for opportunity
        opportunity = await check_additional_trade_opportunity(
            ib, symbol, expiry, previous_direction
        )
        
        if opportunity:
            print("Additional trade opportunity found!")
            return await execute_additional_trade(ib, symbol, expiry, opportunity)
        else:
            print("No additional trade opportunity found")
            return None
            
    except Exception as e:
        print(f"Error scanning for additional opportunities: {e}")
        return None

def should_scan_additional_opportunities():
    """Check if we should scan for additional opportunities (next trading day)"""
    import pytz
    eastern = pytz.timezone('US/Eastern')
    now = datetime.now(eastern)
    current_time = now.time()
    
    # Scan during market hours: 9:30 AM to 3:00 PM ET (before main trade time)
    from datetime import time as dtime
    start_time = dtime(9, 30)
    end_time = dtime(15, 0)  # Stop before main trade execution time
    
    return start_time <= current_time <= end_time


async def scan_for_additional_opportunities(ib, symbol, expiry):
    """
    Scan for additional trading opportunities with specific rules:
    1. Max 2 additional trades if H-A logic is profitable
    2. Max 1 additional trade if H-A logic is not profitable  
    3. No stop loss monitoring for additional trades
    4. Before 12pm: min $0.50 premium, After 12pm: min $0.35 premium
    """
    try:
        # Check if we can take additional trades today
        can_trade, max_additional = check_additional_trade_eligibility()
        
        if not can_trade:
            print(f"❌ No additional trades allowed today. Max reached: {max_additional}")
            return False
        
        print(f"✅ Can take up to {max_additional} more additional trades today")
        
        # Get current time to determine premium requirement
        current_time = datetime.now().time()
        min_premium = get_minimum_premium_requirement(current_time)
        print(f"💰 Minimum premium requirement: ${min_premium:.2f}")
        
        # Determine trade direction (same as main H-A strategy)
        trade_direction = await determine_additional_trade_direction(ib, symbol)
        if not trade_direction:
            print("❌ Could not determine trade direction for additional opportunity")
            return False
        
        print(f"📈 Additional trade direction: {trade_direction}")
        
        # Check pattern confirmation
        pattern_confirmed = await check_additional_entry_pattern(ib, symbol, trade_direction)
        if not pattern_confirmed:
            print(f"❌ Pattern not confirmed for additional {trade_direction} trade")
            return False
        
        print(f"✅ Pattern confirmed for additional {trade_direction} trade")
        
        # Find suitable options
        options_data = await find_additional_trade_options(ib, symbol, expiry, trade_direction)
        if not options_data:
            print("❌ No suitable options found for additional trade")
            return False
        
        # Calculate premium
        sell_option = options_data['short_option']
        buy_option = options_data['long_option'] 
        premium = await calculate_spread_premium(ib, sell_option, buy_option)
        
        print(f"💵 Additional trade premium: ${premium:.2f}")
        
        # Check if premium meets minimum requirement
        if premium < min_premium :  # Convert to cents
            print(f"❌ Premium ${premium:.2f} below minimum ${min_premium:.2f}")
            return False
        
        # Execute additional trade
        success = await execute_additional_trade(
            ib, symbol, expiry, sell_option, buy_option, 
            premium, trade_direction, min_premium
        )
        
        return success
        
    except Exception as e:
        print(f"❌ Error scanning additional opportunities: {e}")
        return False

def check_additional_trade_eligibility():
    """
    Check if we can take additional trades based on:
    1. Max 2 if H-A logic is profitable
    2. Max 1 if H-A logic is not profitable
    """
    try:
        # Get today's trades
        today_trades = get_todays_trades()
        
        # Count main and additional trades
        main_trades = [t for t in today_trades if t.get('trade_type') == 'Main']
        additional_trades = [t for t in today_trades if t.get('trade_type') == 'Additional']
        
        print(f"📊 Today's trades - Main: {len(main_trades)}, Additional: {len(additional_trades)}")
        
        # Check if H-A logic is profitable
        ha_profitable = is_heikin_ashi_profitable(main_trades)
        print(f"📈 Heikin-Ashi profitable today: {ha_profitable}")
        
        if ha_profitable:
            max_additional = 2
            can_trade = len(additional_trades) < 2
        else:
            max_additional = 1  
            can_trade = len(additional_trades) < 1
        
        remaining = max_additional - len(additional_trades)
        
        return can_trade, remaining
        
    except Exception as e:
        print(f"❌ Error checking trade eligibility: {e}")
        return False, 0

def is_heikin_ashi_profitable(main_trades):
    """
    Check if today's Heikin-Ashi main trades are profitable
    """
    try:
        if not main_trades:
            return False
        
        # For now, assume profitable if trade is open (not stopped out)
        # You can enhance this to check actual P&L
        for trade in main_trades:
            if trade.get('status') == 'Open':
                # Could add P&L check here if available
                return True
            elif trade.get('status') == 'Exited':
                # Check exit reason
                exit_reason = trade.get('exit_reason', '')
                if 'stop loss' in exit_reason.lower():
                    return False
                else:
                    return True  # Assume profitable exit
        
        return False
        
    except Exception as e:
        print(f"❌ Error checking H-A profitability: {e}")
        return False

def get_minimum_premium_requirement(current_time):
    """
    Get minimum premium based on time:
    Before 12pm: $0.50
    After 12pm: $0.35
    """
    from datetime import time as dtime
    noon = dtime(12, 0)
    
    if current_time < noon:
        return MIN_PREMIUM_NEXT_DAY_BEFORE_12  # Before 12pm
    else:
        return MIN_PREMIUM_NEXT_DAY_AFTER_12  # After 12pm

def get_todays_trades():
    """Get all trades from today"""
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        
        # Get open trades
        open_trades = load_open_trades()
        today_open = [t for t in open_trades if t.get('date', '').startswith(today)]
        
        # Get closed trades  
        closed_trades = load_closed_trades()
        today_closed = [t for t in closed_trades if t.get('date', '').startswith(today)]
        
        return today_open + today_closed
        
    except Exception as e:
        print(f"❌ Error getting today's trades: {e}")
        return []

async def determine_additional_trade_direction(ib, symbol):
    """
    Determine trade direction for additional trades
    (same logic as main H-A strategy)
    """
    try:
        from utils.heikin_ashi import get_regular_and_heikin_ashi_close
        
        daily_close_price, daily_close_ha = await get_regular_and_heikin_ashi_close(ib, symbol)
        
        if daily_close_price is None or daily_close_ha is None:
            return None
        
        if daily_close_price > daily_close_ha:
            return "bull"
        else:
            return "bear"
            
    except Exception as e:
        print(f"❌ Error determining additional trade direction: {e}")
        return None

async def find_additional_trade_options(ib, symbol, expiry, trade_direction):
    """Find options for additional trades"""
    try:
        # Use same logic as main trades but maybe different delta targets
        from ib_insync import Stock
        
        stock = Stock(symbol, 'SMART', 'USD')
        await ib.qualifyContractsAsync(stock)
        
        ticker = ib.reqMktData(stock, '', False, False)
        await asyncio.sleep(2)
        current_price = ticker.last if ticker.last else ticker.close
        ib.cancelMktData(stock)
        
        if trade_direction == "bull":
            option_type = 'P'  # Put credit spread
        else:
            option_type = 'C'  # Call credit spread
        
        # Find options with target deltas
        options_data = await find_option_by_delta_range(
            ib, symbol, expiry, option_type, current_price,
            target_deltas=[0.24, 0.23, 0.22, 0.21, 0.20],
            spread_width=10
        )
        
        return options_data
        
    except Exception as e:
        print(f"❌ Error finding additional trade options: {e}")
        return None

async def execute_additional_trade(ib, symbol, expiry, sell_option, buy_option, premium, trade_direction, min_premium):
    """
    Execute additional trade with specific rules:
    - No stop loss monitoring
    - Different order management
    """
    try:
        # Fixed quantity for additional trades
        quantity = 10  # or whatever you prefer
        
        # Create spread order
        combo, main_order = await create_spread_order(
            ib, sell_option, buy_option, quantity, min_premium, 
            is_bull_spread=(trade_direction == 'bull')
        )
        
        if not combo or not main_order:
            print("❌ Failed to create additional trade order")
            return False
        
        # Create closing order (but no stop loss monitoring)
        close_order = await create_close_order(ib, quantity)
        close_order.parentId = main_order.orderId
        
        print(f"📋 Placing additional {trade_direction} spread order...")
        
        # Place orders
        main_trade = ib.placeOrder(combo, main_order)
        await asyncio.sleep(2)
        
        close_trade = ib.placeOrder(combo, close_order)
        
        # Log the additional trade
        trade_info = {
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "trade_type": "Additional",  # Mark as additional
            "trade_direction": trade_direction,
            "spread": f"{symbol} {sell_option.strike}/{buy_option.strike} {expiry}",
            "option_type": sell_option.right,
            "quantity": quantity,
            "target_premium": premium,
            "min_premium_required": min_premium,
            "status": "Open",
            "sell_strike": sell_option.strike,
            "buy_strike": buy_option.strike,
            "main_order_id": main_trade.order.orderId,
            "close_order_id": close_trade.order.orderId,
            "monitor_stop_loss": False  # No stop loss monitoring
        }
        
        save_trade_to_log(trade_info)
        
        # Add to open trades (but won't be monitored for stop loss)
        open_trades = load_open_trades()
        open_trades.append(trade_info)
        save_open_trades(open_trades)
        
        print(f"✅ Additional {trade_direction} spread trade executed successfully")
        print(f"💰 Premium: ${premium:.2f}, Quantity: {quantity}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error executing additional trade: {e}")
        return False

# Update your trade monitor to skip additional trades
async def monitor_trade_exit_conditions(ib, trade_info):
    """
    Monitor exit conditions - skip additional trades
    """
    # Skip monitoring if it's an additional trade
    if trade_info.get('trade_type') == 'Additional':
        print(f"⏭️ Skipping stop loss monitoring for additional trade {trade_info.get('main_order_id')}")
        return True
    
    # Continue with normal monitoring for main trades
    # ... existing monitoring logic ...