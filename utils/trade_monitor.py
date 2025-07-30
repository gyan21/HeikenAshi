import asyncio
from datetime import datetime, time as dtime
from ib_insync import Stock, Order
from utils.pattern_utils import check_exit_pattern, get_previous_day_data
from utils.logger import save_trade_to_log
from utils.trade_utils import load_open_trades, save_open_trades
from config.settings import PATTERN_MONITORING_START

async def monitor_trade_exit_conditions(ib, trade_info):
    """
    Monitor exit conditions for a specific trade according to new requirements
    
    Exit conditions:
    Bull Credit Spread:
    1. Stock price falls below previous day's low OR below short strike
    2. Time is 10:00 AM or later
    3. 15-minute chart shows Green-Green-Red pattern
    
    Bear Credit Spread:  
    1. Stock price rises above previous day's high OR above short strike
    2. Time is 10:00 AM or later
    3. 15-minute chart shows Red-Red-Green pattern
    """
    symbol = trade_info.get('symbol', 'SPY')
    trade_direction = trade_info.get('trade_direction')
    sell_strike = trade_info.get('sell_strike')
    quantity = trade_info.get('quantity', 1)
    
    print(f"Monitoring {trade_direction} spread exit conditions for {symbol}")
    
    # Get previous day's data
    prev_day_data = await get_previous_day_data(ib, symbol)
    if not prev_day_data:
        print("Could not get previous day data for exit monitoring")
        return False
    
    prev_high = prev_day_data['high']
    prev_low = prev_day_data['low']
    print(f"Previous day - High: {prev_high}, Low: {prev_low}")
    
    while True:
        try:
            # Check if it's after 10:00 AM
            current_time = datetime.now().time()
            if current_time < dtime(10, 0):
                print("Before 10:00 AM, waiting...")
                await asyncio.sleep(300)  # Wait 5 minutes
                continue
            
            # Get current stock price
            stock = Stock(symbol, 'SMART', 'USD')
            await ib.qualifyContractsAsync(stock)
            
            ticker = ib.reqMktData(stock, '', False, False)
            await asyncio.sleep(2)
            current_price = ticker.last if ticker.last else ticker.close
            ib.cancelMktData(stock)
            
            if not current_price:
                print("Could not get current stock price")
                await asyncio.sleep(60)
                continue
            
            print(f"Current {symbol} price: {current_price}")
            
            # Check price-based exit conditions
            should_check_pattern = False
            
            if trade_direction == 'bull':
                # Bull spread: exit if price falls below prev day low OR below short strike
                if current_price < prev_low or current_price < sell_strike:
                    print(f"Bull exit condition met: price {current_price} < prev low {prev_low} or < sell strike {sell_strike}")
                    should_check_pattern = True
            
            elif trade_direction == 'bear':
                # Bear spread: exit if price rises above prev day high OR above short strike  
                if current_price > prev_high or current_price > sell_strike:
                    print(f"Bear exit condition met: price {current_price} > prev high {prev_high} or > sell strike {sell_strike}")
                    should_check_pattern = True
            
            # If price condition is met, check the pattern
            if should_check_pattern:
                pattern_confirmed = await check_exit_pattern(ib, symbol, trade_direction)
                
                if pattern_confirmed:
                    print(f"✅ Exit pattern confirmed for {trade_direction} spread")
                    success = await execute_trade_exit(ib, trade_info, current_price, "Pattern and price exit conditions met")
                    return success
                else:
                    print("Price condition met but pattern not confirmed yet")
            
            # Wait before next check
            await asyncio.sleep(60)  # Check every minute
            
        except Exception as e:
            print(f"Error in exit monitoring: {e}")
            await asyncio.sleep(60)
            continue

async def execute_trade_exit(ib, trade_info, exit_price, exit_reason):
    """Execute the exit of a trade"""
    try:
        # Cancel the existing closing order and place market order
        close_order_id = trade_info.get('close_order_id')
        if close_order_id:
            # Find and cancel the existing close order
            for trade in ib.trades():
                if trade.order.orderId == close_order_id:
                    ib.cancelOrder(trade.order)
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
        
        return True
        
    except Exception as e:
        print(f"Error executing trade exit: {e}")
        return False

def remove_from_open_trades(order_id):
    """Remove trade from open trades list"""
    try:
        trades = load_open_trades()
        updated_trades = [t for t in trades if t.get('main_order_id') != order_id]
        save_open_trades(updated_trades)
        print(f"Removed trade {order_id} from open trades")
    except Exception as e:
        print(f"Error removing from open trades: {e}")

async def monitor_all_open_trades(ib):
    """Monitor all open trades for exit conditions"""
    try:
        open_trades = load_open_trades()
        
        if not open_trades:
            print("No open trades to monitor")
            return
        
        print(f"Monitoring {len(open_trades)} open trades")
        
        # Create monitoring tasks for each trade
        tasks = []
        for trade in open_trades:
            if trade.get('status') == 'Open':
                task = asyncio.create_task(monitor_trade_exit_conditions(ib, trade))
                tasks.append(task)
        
        if tasks:
            # Run all monitoring tasks concurrently
            await asyncio.gather(*tasks, return_exceptions=True)
        
    except Exception as e:
        print(f"Error monitoring open trades: {e}")

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
