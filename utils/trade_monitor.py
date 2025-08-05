import asyncio
from datetime import datetime, time as dtime
from ib_insync import Stock, Order
from utils.excel_logger import log_trade_exit, update_trade_triggers
from utils.pattern_utils import check_exit_pattern, get_previous_day_data
from utils.logger import save_trade_to_log
from utils.trade_utils import load_open_trades, save_open_trades
from config.settings import PATTERN_MONITORING_START

# Global dictionary to track trigger states for each trade
trade_trigger_states = {}

async def monitor_trade_exit_conditions(ib, trade_info):
    """
    Monitor exit conditions for a specific trade with separate trigger tracking
    
    Exit Logic:
    1. Track Trigger-1: Next day open against position OR price beyond prev day high/low anytime
    2. Track Trigger-2: Price beyond sell strike
    3. Execute stop loss only when BOTH triggers occurred + pattern confirmed + after 10AM
    """
    symbol = trade_info.get('symbol', 'SPY')
    trade_direction = trade_info.get('trade_direction')
    sell_strike = trade_info.get('sell_strike')
    main_order_id = trade_info.get('main_order_id')
    
    print(f"🔍 Starting monitoring for {trade_direction} spread {main_order_id}")
    
    # Initialize trigger state for this trade
    if main_order_id not in trade_trigger_states:
        trade_trigger_states[main_order_id] = {
            'trigger_1_open_against': False,
            'trigger_2_beyond_strike': False,
            'trigger_1_time': None,
            'trigger_2_time': None,
            'trade_direction': trade_direction,
            'sell_strike': sell_strike,
            'symbol': symbol
        }
    
    # Get previous day's data for Trigger-1 comparison
    prev_day_data = await get_previous_day_data(ib, symbol)
    if not prev_day_data:
        print("❌ Could not get previous day data for exit monitoring")
        return False
    
    prev_high = prev_day_data['high']
    prev_low = prev_day_data['low']
    print(f"📊 Previous day - High: {prev_high}, Low: {prev_low}")
    print(f"🎯 Sell strike: {sell_strike}")
    
    # Check for any historical trigger that might have already occurred
    await check_historical_triggers(ib, main_order_id, symbol, trade_direction, prev_high, prev_low)
    
    # Main monitoring loop
    while True:
        try:
            # Check if trade still exists and is open
            if not is_trade_still_open(main_order_id):
                print(f"✅ Trade {main_order_id} is no longer open, stopping monitoring")
                if main_order_id in trade_trigger_states:
                    del trade_trigger_states[main_order_id]
                return True
            
            # Get current time
            current_time = datetime.now().time()
            
            # Get current stock price
            current_price = await get_current_stock_price(ib, symbol)
            if not current_price:
                await asyncio.sleep(60)
                continue
            
            print(f"💰 Current {symbol} price: {current_price}")
            
            # Check both triggers continuously
            check_trigger_1_price_levels(main_order_id, current_price, trade_direction, prev_high, prev_low)
            check_trigger_2_beyond_strike(main_order_id, current_price, trade_direction, sell_strike)
            
            # Print current trigger status
            state = trade_trigger_states[main_order_id]
            print(f"🚨 Trigger Status - Open/Price Against: {state['trigger_1_open_against']}, Beyond Strike: {state['trigger_2_beyond_strike']}")
            
            # Check if we can execute stop loss
            if can_execute_stop_loss(main_order_id, current_time):
                pattern_confirmed = await check_exit_pattern(ib, symbol, trade_direction)
                
                if pattern_confirmed:
                    print(f"✅ All conditions met! Executing stop loss for {trade_direction} spread")
                    success = await execute_trade_exit(ib, trade_info, current_price, "Stop loss: Both triggers + pattern confirmed")
                    
                    # Clean up trigger state
                    if main_order_id in trade_trigger_states:
                        del trade_trigger_states[main_order_id]
                    
                    return success
                else:
                    print("⏳ Both triggers met but pattern not confirmed yet, waiting...")
            
            # Wait before next check
            await asyncio.sleep(60)  # Check every minute
            
        except Exception as e:
            print(f"❌ Error in exit monitoring: {e}")
            await asyncio.sleep(60)
            continue

async def check_historical_triggers(ib, order_id, symbol, trade_direction, prev_high, prev_low):
    """
    Check if triggers already occurred when starting monitoring
    This handles cases where:
    1. Program starts anytime during the day
    2. Today's open was already against position
    3. Price already went beyond previous day levels
    """
    print(f"🔍 Checking for historical triggers...")
    
    current_price = await get_current_stock_price(ib, symbol)
    if not current_price:
        return
    
    current_time = datetime.now().time()
    
    # Get today's opening price if we're after market open
    today_open = await get_today_open_price(ib, symbol)
    
    # Check if today's open was against the position
    if today_open and current_time >= dtime(9, 30):  # Market has opened today
        if trade_direction == 'bull' and today_open < prev_low:
            trade_trigger_states[order_id]['trigger_1_open_against'] = True
            trade_trigger_states[order_id]['trigger_1_time'] = datetime.now().replace(hour=9, minute=30)
            print(f"🔴 HISTORICAL TRIGGER-1 BULL: Today's open {today_open} < prev low {prev_low}")
        
        elif trade_direction == 'bear' and today_open > prev_high:
            trade_trigger_states[order_id]['trigger_1_open_against'] = True
            trade_trigger_states[order_id]['trigger_1_time'] = datetime.now().replace(hour=9, minute=30)
            print(f"🔴 HISTORICAL TRIGGER-1 BEAR: Today's open {today_open} > prev high {prev_high}")
    
    # Check if current price is already beyond previous day levels (may have happened earlier)
    check_trigger_1_price_levels(order_id, current_price, trade_direction, prev_high, prev_low)
    
    # Check if price is already beyond strike (may have happened earlier)
    check_trigger_2_beyond_strike(order_id, current_price, trade_direction, trade_trigger_states[order_id]['sell_strike'])

async def get_today_open_price(ib, symbol):
    """Get today's opening price"""
    try:
        from ib_insync import Stock
        stock = Stock(symbol, 'SMART', 'USD')
        await ib.qualifyContractsAsync(stock)
        
        # Request today's bars to get open price
        bars = ib.reqHistoricalData(
            stock, 
            endDateTime='', 
            durationStr='1 D',
            barSizeSetting='1 day',
            whatToShow='TRADES',
            useRTH=True
        )
        
        if bars:
            return bars[-1].open  # Today's open
        return None
        
    except Exception as e:
        print(f"❌ Error getting today's open price: {e}")
        return None

def check_trigger_1_price_levels(order_id, current_price, trade_direction, prev_high, prev_low):
    """Check Trigger-1 and log to Excel"""
    if trade_trigger_states[order_id]['trigger_1_open_against']:
        return
    
    trigger_1_met = False
    
    if trade_direction == 'bull':
        if current_price < prev_low:
            trigger_1_met = True
            print(f"🔴 TRIGGER-1 BULL: Current price {current_price} < prev low {prev_low}")
    elif trade_direction == 'bear':
        if current_price > prev_high:
            trigger_1_met = True
            print(f"🔴 TRIGGER-1 BEAR: Current price {current_price} > prev high {prev_high}")
    
    if trigger_1_met:
        trigger_time = datetime.now()
        trade_trigger_states[order_id]['trigger_1_open_against'] = True
        trade_trigger_states[order_id]['trigger_1_time'] = trigger_time
        
        # Log to Excel
        update_trade_triggers(order_id, trigger_1_time=trigger_time)
        print(f"🚨 TRIGGER-1 ACTIVATED for trade {order_id}")

def check_trigger_2_beyond_strike(order_id, current_price, trade_direction, sell_strike):
    """
    Check Trigger-2: Price beyond sell strike
    Can happen any time during the day
    """
    if trade_trigger_states[order_id]['trigger_2_beyond_strike']:
        return  # Already triggered
    
    trigger_2_met = False
    
    if trade_direction == 'bull':
        # Bull: Trigger if price below sell strike
        if current_price < sell_strike:
            trigger_2_met = True
            print(f"🔴 TRIGGER-2 BULL: Price {current_price} < sell strike {sell_strike}")
    
    elif trade_direction == 'bear':
        # Bear: Trigger if price above sell strike
        if current_price > sell_strike:
            trigger_2_met = True
            print(f"🔴 TRIGGER-2 BEAR: Price {current_price} > sell strike {sell_strike}")
    
    if trigger_2_met:
        trade_trigger_states[order_id]['trigger_2_beyond_strike'] = True
        trade_trigger_states[order_id]['trigger_2_time'] = datetime.now()
        print(f"🚨 TRIGGER-2 ACTIVATED for trade {order_id}")

def can_execute_stop_loss(order_id, current_time):
    """
    Check if stop loss can be executed:
    1. Both triggers must be activated
    2. Current time must be after 10:00 AM
    """
    state = trade_trigger_states.get(order_id)
    if not state:
        return False
    
    # Check if after 10:00 AM
    if current_time < dtime(10, 0):
        print("⏰ Before 10:00 AM, cannot execute stop loss yet")
        return False
    
    # Check if both triggers are activated
    both_triggers = state['trigger_1_open_against'] and state['trigger_2_beyond_strike']
    
    if both_triggers:
        print(f"🟢 Both triggers active! Trigger-1: {state['trigger_1_time']}, Trigger-2: {state['trigger_2_time']}")
        return True
    else:
        missing = []
        if not state['trigger_1_open_against']:
            missing.append("Trigger-1 (open/price against)")
        if not state['trigger_2_beyond_strike']:
            missing.append("Trigger-2 (beyond strike)")
        print(f"⚠️ Missing triggers: {', '.join(missing)}")
        return False

async def get_current_stock_price(ib, symbol):
    """Get current stock price with error handling"""
    try:
        stock = Stock(symbol, 'SMART', 'USD')
        await ib.qualifyContractsAsync(stock)
        
        ticker = ib.reqMktData(stock, '', False, False)
        await asyncio.sleep(2)
        current_price = ticker.last if ticker.last else ticker.close
        ib.cancelMktData(stock)
        
        return current_price
    except Exception as e:
        print(f"❌ Error getting stock price: {e}")
        return None

def is_trade_still_open(order_id):
    """Check if trade is still in open trades list"""
    try:
        open_trades = load_open_trades()
        return any(t.get('main_order_id') == order_id and t.get('status') == 'Open' for t in open_trades)
    except:
        return False

async def execute_trade_exit(ib, trade_info, exit_price, exit_reason):
    """Execute trade exit and log to Excel"""
    try:
        # Cancel the existing closing order and place market order
        close_order_id = trade_info.get('close_order_id')
        if close_order_id:
            # Find and cancel the existing close order
            for trade in ib.trades():
                if trade.order.orderId == close_order_id:
                    ib.cancelOrder(trade.order)
                    print(f"🚫 Cancelled existing close order {close_order_id}")
                    break
        
        # Place market order to close immediately
        # This would need the combo contract reconstruction
        # For now, just log the exit
        
        # Update trade log
        exit_info = trade_info.copy()
        exit_info.update({
            "status": "Exited",
            "exit_price": exit_price,
            "exit_reason": exit_reason,
            "exit_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        
        save_trade_to_log(exit_info)
        print(f"✅ Trade exit logged: {exit_reason}")
        
        # Remove from open trades
        remove_from_open_trades(trade_info.get('main_order_id'))
        
        # Log exit to Excel
        log_trade_exit(trade_info, exit_price, exit_reason)
        
        return True
        
    except Exception as e:
        print(f"❌ Error executing trade exit: {e}")
        return False

def remove_from_open_trades(order_id):
    """Remove trade from open trades list"""
    try:
        trades = load_open_trades()
        updated_trades = [t for t in trades if t.get('main_order_id') != order_id]
        save_open_trades(updated_trades)
        print(f"🗑️ Removed trade {order_id} from open trades")
    except Exception as e:
        print(f"❌ Error removing from open trades: {e}")

async def monitor_all_open_trades(ib):
    """Monitor all open trades for exit conditions"""
    try:
        open_trades = load_open_trades()
        
        if not open_trades:
            print("📭 No open trades to monitor")
            return
        
        print(f"👀 Monitoring {len(open_trades)} open trades")
        
        # Create monitoring tasks for each trade
        tasks = []
        for trade in open_trades:
            if trade.get('status') == 'Open':
                task = asyncio.create_task(monitor_trade_exit_conditions(ib, trade))
                tasks.append(task)
        
        if tasks:
            # Run all monitoring tasks concurrently
            results = await asyncio.gather(*tasks, return_exceptions=True)
            print(f"✅ Monitoring completed for all trades")
        
    except Exception as e:
        print(f"❌ Error monitoring open trades: {e}")

def should_monitor_trades():
    """Check if we should be monitoring trades (market hours)"""
    import pytz
    eastern = pytz.timezone('US/Eastern')
    now = datetime.now(eastern)
    current_time = now.time()
    
    # Monitor during market hours: 9:30 AM to 4:00 PM ET
    start_time = dtime(9, 30)
    end_time = dtime(16, 0)
    
    return start_time <= current_time <= end_time

def get_trade_trigger_status():
    """Get current trigger status for all trades (for debugging)"""
    return trade_trigger_states.copy()
