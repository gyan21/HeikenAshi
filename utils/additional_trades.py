import asyncio
from datetime import datetime, timedelta
from ib_insync import Option
from utils.pattern_utils import check_additional_entry_pattern
from utils.delta_option_finder import find_both_options_for_spread, calculate_spread_premium
from utils.trade_executor import create_spread_order, create_close_order
from utils.logger import save_trade_to_log
from config.settings import MIN_PREMIUM_NEXT_DAY, SPREAD_WIDTH

async def check_additional_trade_opportunity(ib, symbol, expiry, previous_trade_direction):
    """
    Check for additional trade opportunities on the next day
    
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
    
    # Find suitable options
    options_data = await find_both_options_for_spread(ib, symbol, expiry)
    
    if previous_trade_direction == 'bull':
        # Bull direction: continue with Put credit spreads
        if not options_data.get('put'):
            print("No suitable Put option found for additional Bull trade")
            return None
            
        put_data = options_data['put']
        sell_option = put_data['option']
        buy_strike = sell_option.strike - SPREAD_WIDTH
        buy_option = Option(symbol, expiry, buy_strike, 'P', 'SMART')
        
    else:  # bear
        # Bear direction: continue with Call credit spreads
        if not options_data.get('call'):
            print("No suitable Call option found for additional Bear trade")
            return None
            
        call_data = options_data['call']
        sell_option = call_data['option']
        buy_strike = sell_option.strike + SPREAD_WIDTH
        buy_option = Option(symbol, expiry, buy_strike, 'C', 'SMART')
    
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
        
        # Create closing order
        close_order = await create_close_order(combo, quantity)
        
        # Place orders
        main_trade = ib.placeOrder(combo, main_order)
        await asyncio.sleep(2)
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
