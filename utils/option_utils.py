from ib_insync import Option, Contract, ComboLeg, Order, Stock
import numpy as np
import asyncio
from datetime import datetime, date
import time 
from ib_insync import LimitOrder

def clean_magic_numbers(order):
    # Required fields for a basic order that must not be None:
    REQUIRED_FIELDS = {'totalQuantity', 'orderId', 'clientId', 'permId', 'action', 'orderType', 'lmtPrice', 'transmit'}
    for key, value in list(order.__dict__.items()):
        if key not in REQUIRED_FIELDS:
            if isinstance(value, float) and abs(value) > 1e+307:
                setattr(order, key, None)
            if isinstance(value, int) and value > 2e9:
                setattr(order, key, None)

            
def get_option_iv(ib, option):
    data = ib.reqMktData(option, '', False, False)
    ib.sleep(1)
    iv = getattr(getattr(data, 'modelGreeks', None), 'impliedVol', None)
    ib.cancelMktData(option)
    return iv

def nuke_vol_fields(order):
    remove_fields = [
        'volatility', 'volatilityType', 'deltaNeutralOrderType', 'deltaNeutralVolatility',
        'delta', 'deltaNeutralAuxPrice', 'deltaNeutralConId', 'deltaNeutralSettlingFirm',
        'deltaNeutralClearingAccount', 'deltaNeutralClearingIntent', 'deltaNeutralOpenClose',
        'deltaNeutralShortSale', 'deltaNeutralShortSaleSlot', 'deltaNeutralDesignatedLocation'
    ]
    for field in remove_fields:
        if field in order.__dict__:
            try:
                del order.__dict__[field]
            except Exception:
                pass


def strip_vol_fields(order):
    for field in ['volatility', 'volatilityType', 'deltaNeutralOrderType', 'deltaNeutralVolatility']:
        if hasattr(order, field):
            delattr(order, field)
            
def place_bear_spread_with_oco(ib, symbol, strike_pair, expiry, account_value, trade_log_callback=None):
    from utils.trade_utils import log_trade_close, load_open_trades
    sell_strike, buy_strike = strike_pair
    # Ensure correct order for bull put spread
    if sell_strike > buy_strike:
        sell_strike, buy_strike = buy_strike, sell_strike
        
    sell_leg = Option(symbol, expiry, sell_strike, 'C', 'SMART')
    buy_leg = Option(symbol, expiry, buy_strike, 'C', 'SMART')
    ib.qualifyContracts(sell_leg, buy_leg)
    print(f"Sell leg conId: {sell_leg.conId}, Buy leg conId: {buy_leg.conId}")
    combo = Contract(
        symbol=symbol,
        secType='BAG',
        currency='USD',
        exchange='SMART',
        comboLegs=[
            ComboLeg(conId=sell_leg.conId, ratio=1, action='SELL', exchange='SMART'),
            ComboLeg(conId=buy_leg.conId, ratio=1, action='BUY', exchange='SMART')
        ]
    )
    sell_data = ib.reqMktData(sell_leg, '', False, False)
    buy_data = ib.reqMktData(buy_leg, '', False, False)
    ib.sleep(2)
    sell_theta = getattr(getattr(sell_data, 'modelGreeks', None), 'theta', None)
    buy_theta = getattr(getattr(buy_data, 'modelGreeks', None), 'theta', None)
    ib.cancelMktData(sell_leg)
    ib.cancelMktData(buy_leg)
    try:
        mid_credit = round(((sell_data.bid + sell_data.ask) / 2 - (buy_data.bid + buy_data.ask) / 2), 2)
    except:
        mid_credit = 0.5
    if mid_credit <= 0: mid_credit = 0.5
    theta_diff = None
    if sell_theta is not None and buy_theta is not None:
        theta_diff = abs(sell_theta - buy_theta)
        print(f"Theta difference for OCO: {theta_diff:.4f}")
    else:
        print("Theta data not available, will only use price for OCO.")
    max_loss = (buy_strike - sell_strike) - mid_credit
    quantity = max(1, int((account_value * 0.02) // max_loss))
    parent_order = Order(
        action='SELL',
        orderType='LMT',
        totalQuantity=quantity,
        lmtPrice=mid_credit,
        transmit=True
    )
    nuke_vol_fields(parent_order)
    # clean_magic_numbers(parent_order)
    print(vars(parent_order))  # Confirm the keys are clean
    trade = ib.placeOrder(combo, parent_order)
    ib.sleep(2)
    print(trade)
    parent_id = trade.order.orderId
    take_profit = Order(
        action='BUY',
        orderType='LMT',
        totalQuantity=quantity,
        lmtPrice=0.05,
        parentId=parent_id,
        ocaGroup=f"{symbol}_OCO",
        ocaType=1,
        transmit=True
    )
    nuke_vol_fields(take_profit)
    # clean_magic_numbers(take_profit)
    print(vars(take_profit))  # Confirm the keys are clean
    tp_trade = ib.placeOrder(combo, take_profit)
    print(f"📤 Placed spread SELL {sell_strike}C / BUY {buy_strike}C @ {mid_credit}")
    print("🎯 Take-profit set at 0.05")

    # Log the open trade with all necessary info for resuming
    log_entry = {
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "spread": f"{symbol} {sell_strike}/{buy_strike} {expiry}",
        "type": "bear",
        "symbol": symbol,
        "sell_strike": sell_strike,
        "buy_strike": buy_strike,
        "expiry": expiry,
        "open_price": mid_credit,
        "quantity": quantity,
        "close_reason": "Pending TP/OCO",
        "status": "Open"
    }
    if trade_log_callback:
        trade_log_callback(log_entry)

    async def monitor_stop_trigger():
        print(f"📡 Watching 1-min close for stop above/below short strike and theta diff OCO")
        while True:
            sell_data_live = ib.reqMktData(sell_leg, '', False, False)
            buy_data_live = ib.reqMktData(buy_leg, '', False, False)
            await asyncio.sleep(2)
            ib.cancelMktData(sell_leg)
            ib.cancelMktData(buy_leg)
            try:
                spread_price = round(((sell_data_live.bid + sell_data_live.ask) / 2 - (buy_data_live.bid + buy_data_live.ask) / 2), 2)
            except:
                spread_price = None

            # Theta diff exit (any time)
            if theta_diff is not None and spread_price is not None and spread_price < theta_diff:
                print(f"🛑 Spread price {spread_price} < theta diff {theta_diff:.4f}, closing spread.")
                close_order = Order(
                    action='BUY',
                    orderType='MKT',
                    totalQuantity=quantity,
                    transmit=True
                )
                nuke_vol_fields(close_order)
                # clean_magic_numbers(close_order)
                print(vars(close_order))  # Confirm the keys are clean
                ib.placeOrder(combo, close_order)
                ib.cancelOrder(tp_trade.order)
                log_trade_close(
                    trade={"spread": f"{symbol} {sell_strike}/{buy_strike} {expiry}"},
                    open_price=mid_credit,
                    close_price=spread_price if spread_price is not None else 0,
                    quantity=quantity,
                    trade_type="bear" if sell_leg.right == 'C' else "bull",
                    status="Exited by theta diff",
                    reason="Spread price < theta difference"
                )
                if trade_log_callback:
                    trade_log_callback({
                        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "spread": f"{symbol} {sell_strike}/{buy_strike} {expiry}",
                        "open_price": mid_credit,
                        "close_reason": "Spread price < theta difference",
                        "status": "Exited by theta diff",
                        "quantity": quantity
                    })
                break

            # 1-min bar exit (only after 10am)
            bars = ib.reqHistoricalData(
                Stock(symbol, 'SMART', 'USD'),
                endDateTime='',
                durationStr='5 mins',
                barSizeSetting='1 min',
                whatToShow='TRADES',
                useRTH=True,
                formatDate=1
            )
            now = datetime.now()
            if now.hour >= 10:
                if sell_leg.right == 'C':
                    # Bear spread: stop if price > sell_strike
                    if bars and bars[-1].close > sell_strike:
                        print(f"🛑 1-min close > {sell_strike} detected at {bars[-1].close}")
                        close_order = Order(
                            action='BUY',
                            orderType='MKT',
                            totalQuantity=quantity,
                            transmit=True
                        )
                        nuke_vol_fields(close_order)
                        # clean_magic_numbers(close_order)
                        print(vars(close_order))  # Confirm the keys are clean
                        ib.placeOrder(combo, close_order)
                        ib.cancelOrder(tp_trade.order)
                        log_trade_close(
                            trade={"spread": f"{symbol} {sell_strike}/{buy_strike} {expiry}"},
                            open_price=mid_credit,
                            close_price=bars[-1].close,
                            quantity=quantity,
                            trade_type="bear",
                            status="Exited manually",
                            reason="1-min close above short strike"
                        )
                        if trade_log_callback:
                            trade_log_callback({
                                "date": now.strftime("%Y-%m-%d %H:%M:%S"),
                                "spread": f"{symbol} {sell_strike}/{buy_strike} {expiry}",
                                "open_price": mid_credit,
                                "close_reason": "1-min close above short strike",
                                "status": "Exited manually",
                                "quantity": quantity
                            })
                        break
                else:
                    # Bull spread: stop if price < sell_strike
                    if bars and bars[-1].close < sell_strike:
                        print(f"🛑 1-min close < {sell_strike} detected at {bars[-1].close}")
                        close_order = Order(
                            action='BUY',
                            orderType='MKT',
                            totalQuantity=quantity,
                            transmit=True
                        )
                        nuke_vol_fields(close_order)                        
                        # clean_magic_numbers(close_order)
                        print(vars(close_order))  # Confirm the keys are clean
                        ib.placeOrder(combo, close_order)
                        ib.cancelOrder(tp_trade.order)
                        log_trade_close(
                            trade={"spread": f"{symbol} {sell_strike}/{buy_strike} {expiry}"},
                            open_price=mid_credit,
                            close_price=bars[-1].close,
                            quantity=quantity,
                            trade_type="bull",
                            status="Exited manually",
                            reason="1-min close below short strike"
                        )
                        if trade_log_callback:
                            trade_log_callback({
                                "date": now.strftime("%Y-%m-%d %H:%M:%S"),
                                "spread": f"{symbol} {sell_strike}/{buy_strike} {expiry}",
                                "open_price": mid_credit,
                                "close_reason": "1-min close below short strike",
                                "status": "Exited manually",
                                "quantity": quantity
                            })
                        break
            await asyncio.sleep(60)

    import asyncio
    loop = asyncio.get_event_loop()
    loop.create_task(monitor_stop_trigger())

    return {
        "spread": f"{symbol}_{sell_strike}_{buy_strike}_{expiry}",
        "order_id": parent_id,
        "credit": mid_credit,
        "quantity": quantity
    }
def clean_limit_order(order):
    # Set fields to None if they are scalar; set to [] if they are lists.
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

def place_bull_spread_with_oco(ib, symbol, strike_pair, expiry, account_value, trade_log_callback=None):
    from utils.trade_utils import log_trade_close, load_open_trades
    sell_strike, buy_strike = strike_pair
    
    # Ensure correct order for bull put spread
    if sell_strike < buy_strike:
        sell_strike, buy_strike = buy_strike, sell_strike
        
    sell_leg = Option(symbol, expiry, sell_strike, 'P', 'SMART')
    buy_leg = Option(symbol, expiry, buy_strike, 'P', 'SMART')
    ib.qualifyContracts(sell_leg, buy_leg)
    print(f"Sell leg conId: {sell_leg.conId}, Buy leg conId: {buy_leg.conId}")
    combo = Contract(
        symbol=symbol,
        secType='BAG',
        currency='USD',
        exchange='SMART',
        comboLegs=[
            ComboLeg(conId=sell_leg.conId, ratio=1, action='SELL', exchange='SMART'),
            ComboLeg(conId=buy_leg.conId, ratio=1, action='BUY', exchange='SMART')
        ]
    )
    sell_data = ib.reqMktData(sell_leg, '', False, False)
    buy_data = ib.reqMktData(buy_leg, '', False, False)
    ib.sleep(2)
    sell_theta = getattr(getattr(sell_data, 'modelGreeks', None), 'theta', None)
    buy_theta = getattr(getattr(buy_data, 'modelGreeks', None), 'theta', None)
    ib.cancelMktData(sell_leg)
    ib.cancelMktData(buy_leg)
    print(f"sell_data bid: {sell_data.bid} ask: {sell_data.ask}")
    print(f"buy_data bid: {buy_data.bid} ask: {buy_data.ask}")
    try:
        mid_credit = round(((sell_data.bid + sell_data.ask) / 2 - (buy_data.bid + buy_data.ask) / 2), 2)
    except:
        mid_credit = 0.5
    if mid_credit <= 0: mid_credit = 0.5
    theta_diff = None
    if sell_theta is not None and buy_theta is not None:
        theta_diff = abs(sell_theta - buy_theta)
        print(f"Theta difference for OCO: {theta_diff:.4f}")
    else:
        print("Theta data not available, will only use price for OCO.")
    max_loss = (sell_strike - buy_strike) - mid_credit
    quantity = max(1, int((account_value * 0.02) // max_loss))
    lmt_price = -abs(mid_credit) 
    parent_order = Order(
        action='BUY',
        orderType='LMT',
        totalQuantity=quantity,
        lmtPrice = lmt_price + 0.02,  # Adjusted to ensure it's a limit order
        tif = 'DAY',   # or whatever is appropriate
        transmit=True
    )
    # clean_magic_numbers(parent_order)

    # parent_order = LimitOrder(
    #     action='BUY',
    #     totalQuantity=quantity,
    #     lmtPrice= lmt_price ,
    #     tif='DAY',   # or whatever is appropriate
    #     transmit=True
    # )
    parent_order = clean_limit_order(parent_order)    
    print("SELL strike:", sell_leg.strike, "BUY strike:", buy_leg.strike)
    print("Mid credit:", mid_credit)

    print(vars(parent_order))
    # Inside place_bull_spread_with_oco or before placing parent_order:
    spread_width = abs(sell_strike - buy_strike)
    if mid_credit >= spread_width:
        print(f"[ERROR] Riskless combo detected: credit ({mid_credit}) >= width ({spread_width}) -- aborting order.")
        return None
    trade = ib.placeOrder(combo, parent_order)    
    ib.sleep(2)
    print(trade)
    parent_id = trade.order.orderId
    take_profit = Order(
        action='BUY',
        orderType='LMT',
        totalQuantity=quantity,
        lmtPrice=0.05,
        parentId=parent_id,
        ocaGroup=f"{symbol}_OCO",
        ocaType=1,
        tif='GTC',  # Good 'Til Canceled
        transmit=True
    )
    nuke_vol_fields(take_profit)
    # clean_magic_numbers(take_profit)
    print(vars(take_profit))  # Confirm the keys are clean
    tp_trade = ib.placeOrder(combo, take_profit)
    print(f"📤 Placed spread SELL {sell_strike}P / BUY {buy_strike}P @ {mid_credit}")
    print("🎯 Take-profit set at 0.05")

    # Log the open trade with all necessary info for resuming
    log_entry = {
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "spread": f"{symbol} {sell_strike}/{buy_strike} {expiry}",
        "type": "bull",
        "symbol": symbol,
        "sell_strike": sell_strike,
        "buy_strike": buy_strike,
        "expiry": expiry,
        "open_price": mid_credit,
        "quantity": quantity,
        "close_reason": "Pending TP/OCO",
        "status": "Open"
    }
    if trade_log_callback:
        trade_log_callback(log_entry)

    async def monitor_stop_trigger():
        print(f"📡 Watching 1-min close for stop under {sell_strike} and theta diff OCO")
        while True:
            sell_data_live = ib.reqMktData(sell_leg, '', False, False)
            buy_data_live = ib.reqMktData(buy_leg, '', False, False)
            await asyncio.sleep(2)
            ib.cancelMktData(sell_leg)
            ib.cancelMktData(buy_leg)
            try:
                spread_price = round(((sell_data_live.bid + sell_data_live.ask) / 2 - (buy_data_live.bid + buy_data_live.ask) / 2), 2)
            except:
                spread_price = None

            # Theta diff exit (any time)
            if theta_diff is not None and spread_price is not None and spread_price < theta_diff:
                print(f"🛑 Spread price {spread_price} < theta diff {theta_diff:.4f}, closing spread.")
                close_order = Order(
                    action='BUY',
                    orderType='MKT',
                    totalQuantity=quantity,
                    transmit=True
                )
                nuke_vol_fields(close_order)
                # clean_magic_numbers(close_order)
                print(vars(close_order))  # Confirm the keys are clean
                ib.placeOrder(combo, close_order)
                ib.cancelOrder(tp_trade.order)
                log_trade_close(
                    trade={"spread": f"{symbol} {sell_strike}/{buy_strike} {expiry}"},
                    open_price=mid_credit,
                    close_price=spread_price if spread_price is not None else 0,
                    quantity=quantity,
                    trade_type="bull",
                    status="Exited by theta diff",
                    reason="Spread price < theta difference"
                )
                if trade_log_callback:
                    trade_log_callback({
                        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "spread": f"{symbol} {sell_strike}/{buy_strike} {expiry}",
                        "open_price": mid_credit,
                        "close_reason": "Spread price < theta difference",
                        "status": "Exited by theta diff",
                        "quantity": quantity
                    })
                break

            # 1-min bar exit (only after 10am)
            bars = ib.reqHistoricalData(
                Stock(symbol, 'SMART', 'USD'),
                endDateTime='',
                durationStr='5 mins',
                barSizeSetting='1 min',
                whatToShow='TRADES',
                useRTH=True,
                formatDate=1
            )
            now = datetime.now()
            if now.hour >= 10:
                if sell_leg.right == 'C':
                    # Bear spread: stop if price > sell_strike
                    if bars and bars[-1].close > sell_strike:
                        print(f"🛑 1-min close > {sell_strike} detected at {bars[-1].close}")
                        close_order = Order(
                            action='BUY',
                            orderType='MKT',
                            totalQuantity=quantity,
                            transmit=True
                        )
                        nuke_vol_fields(close_order)
                        # clean_magic_numbers(close_order)
                        print(vars(close_order))  # Confirm the keys are clean
                        ib.placeOrder(combo, close_order)
                        ib.cancelOrder(tp_trade.order)
                        log_trade_close(
                            trade={"spread": f"{symbol} {sell_strike}/{buy_strike} {expiry}"},
                            open_price=mid_credit,
                            close_price=bars[-1].close,
                            quantity=quantity,
                            trade_type="bear",
                            status="Exited manually",
                            reason="1-min close above short strike"
                        )
                        if trade_log_callback:
                            trade_log_callback({
                                "date": now.strftime("%Y-%m-%d %H:%M:%S"),
                                "spread": f"{symbol} {sell_strike}/{buy_strike} {expiry}",
                                "open_price": mid_credit,
                                "close_reason": "1-min close above short strike",
                                "status": "Exited manually",
                                "quantity": quantity
                            })
                        break
                else:
                    # Bull spread: stop if price < sell_strike
                    if bars and bars[-1].close < sell_strike:
                        print(f"🛑 1-min close < {sell_strike} detected at {bars[-1].close}")
                        close_order = Order(
                            action='BUY',
                            orderType='MKT',
                            totalQuantity=quantity,
                            transmit=True
                        )
                        nuke_vol_fields(close_order)
                        # clean_magic_numbers(close_order)
                        print(vars(close_order))  # Confirm the keys are clean
                        ib.placeOrder(combo, close_order)
                        ib.cancelOrder(tp_trade.order)
                        log_trade_close(
                            trade={"spread": f"{symbol} {sell_strike}/{buy_strike} {expiry}"},
                            open_price=mid_credit,
                            close_price=bars[-1].close,
                            quantity=quantity,
                            trade_type="bull",
                            status="Exited manually",
                            reason="1-min close below short strike"
                        )
                        if trade_log_callback:
                            trade_log_callback({
                                "date": now.strftime("%Y-%m-%d %H:%M:%S"),
                                "spread": f"{symbol} {sell_strike}/{buy_strike} {expiry}",
                                "open_price": mid_credit,
                                "close_reason": "1-min close below short strike",
                                "status": "Exited manually",
                                "quantity": quantity
                            })
                        break
            await asyncio.sleep(60)

    import asyncio
    loop = asyncio.get_event_loop()
    loop.create_task(monitor_stop_trigger())

    return {
        "spread": f"{symbol}_{sell_strike}_{buy_strike}_{expiry}",
        "order_id": parent_id,
        "credit": mid_credit,
        "quantity": quantity
    }

def get_next_option_expiry(ib, symbol):
    from ib_insync import Stock
    import datetime

    contract = Stock(symbol, 'SMART', 'USD')
    ib.qualifyContracts(contract)
    chains = ib.reqSecDefOptParams(contract.symbol, '', contract.secType, contract.conId)
    if not chains:
        return None
    expiries = sorted(list(set(chains[0].expirations)))
    today = date.today()
    for expiry_str in expiries:
        expiry_date = datetime.datetime.strptime(expiry_str, "%Y%m%d").date()
        if expiry_date > today:
            return expiry_str
    return None

def find_options_by_delta(ib, symbol, expiry=None, right='C', min_delta=0.20, max_delta=0.30):
    """
    Optimized: Start at ATM, scan up (calls) or down (puts), stop after 4 matches.
    """
    contract = Stock(symbol, 'SMART', 'USD')
    ib.qualifyContracts(contract)
    chain = ib.reqSecDefOptParams(contract.symbol, '', contract.secType, contract.conId)
    if not chain:
        print(f"[WARN] No option chain found for {symbol}")
        return []

    # Find next expiry if not provided
    expiries = sorted(list(set(chain[0].expirations)))
    today = date.today()
    if expiry is None:
        for expiry_str in expiries:
            expiry_date = datetime.datetime.strptime(expiry_str, "%Y%m%d").date()
            if expiry_date > today:
                expiry = expiry_str
                break
    if not expiry:
        print(f"[WARN] No valid expiry found for {symbol}")
        return []

    # Get current price
    ticker = ib.reqMktData(contract, '', False, False)
    ib.sleep(1)
    price = ticker.marketPrice() if hasattr(ticker, 'marketPrice') else None
    ib.cancelMktData(contract)
    if price is None or price <= 0:
        print(f"[WARN] Could not get current price for {symbol}")
        return []

    # Get valid strikes for this expiry using reqContractDetails
    from ib_insync import Option
    details = ib.reqContractDetails(Option(symbol, expiry, 0, right, 'SMART'))
    valid_strikes = sorted({cd.contract.strike for cd in details if abs(cd.contract.strike - price) <= 10})
    if not valid_strikes:
        print(f"[WARN] No valid strikes found for {symbol} {expiry} {right}")
        return []

    # Find ATM index
    atm_idx = min(range(len(valid_strikes)), key=lambda i: abs(valid_strikes[i] - price))
    matching_options = []
    start_time = time.time()

    # Direction: puts go down, calls go up
    if right.upper() == 'P':
        strike_range = range(atm_idx, -1, -1)  # ATM down to lowest
    else:
        strike_range = range(atm_idx, len(valid_strikes))  # ATM up to highest

    for idx in strike_range:
        strike = valid_strikes[idx]
        option = Option(symbol, expiry, strike, right, 'SMART')
        ib.qualifyContracts(option)
        data = ib.reqMktData(option, '', False, False)
        ib.sleep(2)
        delta = getattr(getattr(data, 'modelGreeks', None), 'delta', None)
        ib.cancelMktData(option)
        if data.modelGreeks is None:
            print(f"[ERROR] modelGreeks missing for {option}. Check market data subscription!")
        if delta is not None and min_delta <= abs(delta) < max_delta:
            print(f"[MATCH] {symbol} {expiry} {right} {strike} delta={delta:.3f}")
            matching_options.append((option, delta))

    end_time = time.time()
    print(f"[TIMER] Loop through strikes took {end_time - start_time:.2f} seconds.")

    if not matching_options:
        print(f"[INFO] No options found for {symbol} {expiry} {right} in delta range [{min_delta}, {max_delta})")
    return matching_options