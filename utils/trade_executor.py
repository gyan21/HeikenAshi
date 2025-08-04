import asyncio
from datetime import datetime, time as dtime
from ib_insync import Option, Contract, ComboLeg, Order
from config.settings import (
    SPREAD_WIDTH, MIN_PREMIUM_TIER_1, MIN_PREMIUM_TIER_2, 
    TRADE_EXECUTION_START, TRADE_EXECUTION_END, DEBUG   
)
from utils.delta_option_finder import find_both_options_for_spread, calculate_spread_premium
from utils.quantity_manager import get_current_trade_quantity
from utils.pattern_utils import get_previous_day_data
from utils.logger import save_trade_to_log

async def determine_trade_direction(daily_close_price, daily_close_ha):
    """
    Determine trade direction based on Heikin-Ashi logic
    
    Returns:
        'bull' if dailyClosePrice > dailyCloseHA, 'bear' otherwise
    """
    if daily_close_price > daily_close_ha:
        return 'bull'
    else:
        return 'bear'

def clean_limit_order(order):
    fields_none = [
        'auxPrice', 'minQty', 'percentOffset', 'trailStopPrice',
        'trailingPercent', 'goodAfterTime', 'goodTillDate'
        #,'volatility'
    ]
    fields_list = [
        'conditions', 'orderComboLegs', 'orderMiscOptions', 'algoParams', 'smartComboRoutingParams'
    ]
    for field in fields_none:
        if hasattr(order, field):
            setattr(order, field, None)
    for field in fields_list:
        if hasattr(order, field):
            setattr(order, field, [])
    
    # Remove volatility attribute entirely
    if hasattr(order, 'volatility'):
        delattr(order, 'volatility')
        
    return order

async def create_spread_order(ib, sell_option, buy_option, quantity, premium_target, is_bull_spread=True):
    """
    Create a spread order for the given options
    
    Args:
        ib: IBKR connection
        sell_option: Option to sell (short leg)
        buy_option: Option to buy (long leg)  
        quantity: Number of contracts
        premium_target: Target premium to collect
        is_bull_spread: True for bull spread, False for bear spread
    
    Returns:
        Spread contract and order, or None if invalid
    """
    try:
        # Qualify the contracts
        await ib.qualifyContractsAsync(sell_option, buy_option)
        
        # Create the combo contract
        combo = Contract(
            symbol=sell_option.symbol,
            secType='BAG',
            currency='USD',
            exchange='SMART',
            comboLegs=[
                ComboLeg(conId=sell_option.conId, ratio=1, action='SELL', exchange='SMART'),
                ComboLeg(conId=buy_option.conId, ratio=1, action='BUY', exchange='SMART')
            ]
        )
        
        # Calculate the limit price (negative because we're buying the spread)
        limit_price = -abs(premium_target / 100)  # Convert to per-share price
        
        # Create the order
        order = Order(
            action='BUY',  # Buying the spread (selling higher premium option)
            orderType='LMT',
            totalQuantity=quantity,
            lmtPrice=limit_price,
            tif='DAY',
            transmit=True  # Don't transmit yet
        )         
        return combo, order
        
    except Exception as e:
        print(f"Error creating spread order: {e}")
        return None, None

async def create_close_order(combo, quantity):
    """Create an order to close the spread position"""
    close_order = Order(
        action='SELL',  # Selling the spread to close
        orderType='LMT',
        totalQuantity=quantity,
        lmtPrice=0.05,  # $0.05 limit as specified
        tif='GTC',
        transmit=False
    )
    return close_order

async def execute_daily_trade(ib, symbol, expiry, daily_close_price, daily_close_ha):#, trade_direction, quantity):
    """
    Execute the main daily trade based on Heikin-Ashi logic at 3:55 PM ET.

    Args:
        ib: IBKR connection
        symbol: Stock symbol
        expiry: Option expiry
        daily_close_price: Actual daily close price
        daily_close_ha: Heikin-Ashi daily close price
        trade_direction: 'bull' or 'bear' based on Heikin-Ashi logic
        quantity: Number of contracts

    Returns:
        dict with trade information or None if no trade executed
    """
    print(f"Starting daily trade execution for {symbol}")
    print(f"Daily close price: {daily_close_price}, Heikin-Ashi close: {daily_close_ha}")
    
    # Determine trade direction
    trade_direction = await determine_trade_direction(daily_close_price, daily_close_ha)
    print(f"Trade direction: {trade_direction}")
    
    # Get current trade quantity
    quantity = get_current_trade_quantity()
    print(f"Trade quantity: {quantity} contracts")

    # Find suitable options using find_both_options_for_spread
    options_data = await find_both_options_for_spread(ib, symbol, expiry, daily_close_price)

    if trade_direction == 'bull':
        # Bull direction: Use Put credit spreads
        if not options_data.get('put'):
            print("No suitable Put option found for Bull trade")
            return None

        put_data = options_data['put']
        sell_option = put_data['short_option']
        buy_option = put_data['long_option']

    else:  # bear
        # Bear direction: Use Call credit spreads
        if not options_data.get('call'):
            print("No suitable Call option found for Bear trade")
            return None

        call_data = options_data['call']
        sell_option = call_data['short_option']
        buy_option = call_data['long_option']

    # Calculate premium
    premium = await calculate_spread_premium(ib, sell_option, buy_option)
    print(f"Daily trade premium: ${premium:.2f} per contract")

    # Check if premium meets requirements
    current_time = datetime.now().time()
    cutoff_time = dtime(16, 00)  # 4:00 PM
    
    min_premium = MIN_PREMIUM_TIER_1
    if current_time >= cutoff_time:
        min_premium = MIN_PREMIUM_TIER_2
        print(f"Using fallback premium requirement: ${min_premium}")
    
    if premium < min_premium:
        print(f"Premium ${premium:.2f} below minimum ${min_premium}. Skipping trade.")
        return None

    # Create and place the trade
    combo, main_order = await create_spread_order(
        ib, sell_option, buy_option, quantity, premium,
        is_bull_spread=(trade_direction == 'bull')
    )

    if not combo or not main_order:
        print("Failed to create daily spread order")
        return None

    # Create the closing order at $0.05
    close_order = await create_close_order(combo, quantity)

    try:
        # Place the main order
        main_order = clean_limit_order(main_order)
        print(vars(main_order))  # Should NOT show 'volatility'
        main_trade = ib.placeOrder(combo, main_order)
        await asyncio.sleep(2)  # Wait for order to be processed
        
        # Place the closing order
        close_order = clean_limit_order(close_order)
        print(vars(close_order))  # Should NOT show 'volatility'
        close_trade = ib.placeOrder(combo, close_order)

        # Log the trade
        trade_info = {
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "trade_type": "Main",
            "trade_direction": trade_direction,
            "spread": f"{symbol} {sell_option.strike}/{buy_option.strike} {expiry}",
            "option_type": sell_option.right,
            "quantity": quantity,
            "target_premium": premium,
            "status": "Open",
            "sell_strike": sell_option.strike,
            "buy_strike": buy_option.strike,
            "sell_delta": options_data.get('put' if trade_direction == 'bull' else 'call', {}).get('delta'),
            "dailyClosePrice": daily_close_price,
            "dailyCloseHA": daily_close_ha,
            "main_order_id": main_trade.order.orderId,
            "close_order_id": close_trade.order.orderId
        }

        save_trade_to_log(trade_info)
        print(f"✅ Daily {trade_direction} spread trade placed successfully")

        return trade_info
        
    except Exception as e:
        print(f"Error placing spread orders: {e}")
        return None

def should_execute_daily_trade():
    """Check if we should execute the daily trade (3:55 PM ET)"""
    import pytz
    eastern = pytz.timezone('US/Eastern')
    now = datetime.now(eastern)
    current_time = now.time()
    
    # Trade execution window: 3:55 PM to 4:00 PM ET
    start_time = dtime(15, 55)  # 3:55 PM
    end_time = dtime(16, 0)     # 4:00 PM
    if DEBUG:
        return True
    else:
        return start_time <= current_time <= end_time