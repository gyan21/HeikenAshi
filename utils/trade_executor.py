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
        'auxPrice', 'volatility', 'minQty', 'percentOffset', 'trailStopPrice',
        'trailingPercent', 'goodAfterTime', 'goodTillDate'
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
    return order

def validate_order(order):
    """Validate an order before submission"""
    if not isinstance(order, Order):
        raise ValueError("Not a valid Order object")
    
    if hasattr(order, 'volatility'):
        raise ValueError("Order contains volatility attribute")
    
    if order.orderType == 'LMT' and order.lmtPrice is None:
        raise ValueError("Limit order requires lmtPrice")
    
    return True

async def create_spread_order(ib, sell_option, buy_option, quantity, premium_target, is_bull_spread=True):
    """Create a spread order with minimal fields to avoid volatility issues"""
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
        
        # Create proper Order object
        order = Order()
        order.action = 'BUY'
        order.orderType = 'LMT'
        order.totalQuantity = quantity
        order.lmtPrice = round(-abs(premium_target / 100), 2)
        order.tif = 'DAY'
        order.transmit = True
        
        #order = clean_limit_order(order);
        
        return combo, order
        
    except Exception as e:
        print(f"Error creating spread order: {e}")
        return None, None

async def create_close_order(ib, quantity):
    """Create an order to close the spread position"""
    try:
        # Create proper Order object
        close_order = Order()
        close_order.action = 'SELL'
        close_order.orderType = 'LMT'
        close_order.totalQuantity = quantity
        close_order.lmtPrice = 0.05
        close_order.tif = 'GTC'
        close_order.transmit = False
        
        #close_order = clean_limit_order(close_order);
        
        return close_order
        
    except Exception as e:
        print(f"Error creating close order: {e}")
        return None

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

    try:
        # Place the main order
        #main_order = clean_limit_order(main_order)

        print(vars(main_order))  # Should NOT show 'volatility'
        
        # Create the closing order at $0.05
        close_order = await create_close_order(ib, quantity)
        close_order.parentId = main_order.orderId

        main_trade = ib.placeOrder(combo, main_order)
        
        # Verify order status
        print(f"Order status: {main_trade.orderStatus.status}")
        if main_trade.orderStatus.status == 'Cancelled':
            print(f"Order was cancelled: {main_trade.log}")
            return None
        # Place the closing order
        close_trade = ib.placeOrder(combo, close_order)

        # Log the trade
        print("📋 Creating trade info...")
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
        
        print("📋 Saving trade to log...")
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
