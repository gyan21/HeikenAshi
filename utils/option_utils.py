from ib_insync import Option, Contract, ComboLeg, Order, Stock
import numpy as np
import asyncio
from datetime import datetime
from main import log_trade_close  # Ensure this import is correct

def find_option_by_delta(ib, symbol, expiry, right, target_delta=0.20, tolerance=0.05):
    # right: 'P' for put, 'C' for call
    strikes = []
    deltas = []
    options = []
    chain = ib.reqSecDefOptParams(symbol, '', symbol, 'STK')
    if not chain:
        return None
    strikes_list = sorted(chain[0].strikes)
    for strike in strikes_list:
        option = Option(symbol, expiry, strike, right, 'SMART')
        ib.qualifyContracts(option)
        data = ib.reqMktData(option, '', False, False)
        ib.sleep(0.5)
        delta = getattr(getattr(data, 'modelGreeks', None), 'delta', None)
        ib.cancelMktData(option)
        if delta is not None:
            deltas.append(abs(delta))
            strikes.append(strike)
            options.append(option)
    if not deltas:
        return None
    deltas = np.array(deltas)
    idx = (np.abs(deltas - target_delta)).argmin()
    if abs(deltas[idx] - target_delta) <= tolerance:
        return options[idx]
    return None

def get_option_iv(ib, option):
    data = ib.reqMktData(option, '', False, False)
    ib.sleep(1)
    iv = getattr(getattr(data, 'modelGreeks', None), 'impliedVol', None)
    ib.cancelMktData(option)
    return iv

def place_bear_spread_with_oco(ib, symbol, strike_pair, expiry, account_value, trade_log_callback=None):
    sell_strike, buy_strike = strike_pair
    sell_leg = Option(symbol, expiry, sell_strike, 'C', 'SMART')
    buy_leg = Option(symbol, expiry, buy_strike, 'C', 'SMART')
    ib.qualifyContracts(sell_leg, buy_leg)
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
        transmit=False
    )
    trade = ib.placeOrder(combo, parent_order)
    ib.sleep(1)
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
    tp_trade = ib.placeOrder(combo, take_profit)
    print(f"📤 Placed spread SELL {sell_strike}C / BUY {buy_strike}C @ {mid_credit}")
    print("🎯 Take-profit set at 0.05")

    async def monitor_stop_trigger():
        print(f"📡 Watching 1-min close for stop above {sell_strike} and theta diff OCO")
        while True:
            sell_data_live = ib.reqMktData(sell_leg, '', False, False)
            buy_data_live = ib.reqMktData(buy_leg, '', False, False)
            ib.sleep(2)
            ib.cancelMktData(sell_leg)
            ib.cancelMktData(buy_leg)
            try:
                spread_price = round(((sell_data_live.bid + sell_data_live.ask) / 2 - (buy_data_live.bid + buy_data_live.ask) / 2), 2)
            except:
                spread_price = None

            # Theta diff exit
            if theta_diff is not None and spread_price is not None and spread_price < theta_diff:
                print(f"🛑 Spread price {spread_price} < theta diff {theta_diff:.4f}, closing spread.")
                close_order = Order(
                    action='BUY',
                    orderType='MKT',
                    totalQuantity=quantity,
                    transmit=True
                )
                ib.placeOrder(combo, close_order)
                ib.cancelOrder(tp_trade.order)
                log_trade_close(
                    trade={"spread": f"{symbol} {sell_strike}/{buy_strike} {expiry}"},
                    open_price=mid_credit,
                    close_price=spread_price if spread_price is not None else 0,
                    quantity=quantity,
                    trade_type="bear",
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

            # 1-min bar exit
            bars = ib.reqHistoricalData(
                Stock(symbol, 'SMART', 'USD'),
                endDateTime='',
                durationStr='5 mins',
                barSizeSetting='1 min',
                whatToShow='TRADES',
                useRTH=True,
                formatDate=1
            )
            if bars and bars[-1].close > sell_strike:
                print(f"🛑 1-min close > {sell_strike} detected at {bars[-1].close}")
                close_order = Order(
                    action='BUY',
                    orderType='MKT',
                    totalQuantity=quantity,
                    transmit=True
                )
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
                        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "spread": f"{symbol} {sell_strike}/{buy_strike} {expiry}",
                        "open_price": mid_credit,
                        "close_reason": "1-min close above short strike",
                        "status": "Exited manually",
                        "quantity": quantity
                    })
                break
            await asyncio.sleep(60)

    asyncio.create_task(monitor_stop_trigger())

    log_entry = {
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "spread": f"{symbol} {sell_strike}/{buy_strike} {expiry}",
        "open_price": mid_credit,
        "close_reason": "Pending TP/OCO",
        "status": "Open",
        "quantity": quantity
    }
    if trade_log_callback:
        trade_log_callback(log_entry)
    return {
        "spread": f"{symbol}_{sell_strike}_{buy_strike}_{expiry}",
        "order_id": parent_id,
        "credit": mid_credit,
        "quantity": quantity
    }

def place_bull_spread_with_oco(ib, symbol, strike_pair, expiry, account_value, trade_log_callback=None):
    sell_strike, buy_strike = strike_pair
    sell_leg = Option(symbol, expiry, sell_strike, 'P', 'SMART')
    buy_leg = Option(symbol, expiry, buy_strike, 'P', 'SMART')
    ib.qualifyContracts(sell_leg, buy_leg)
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
    max_loss = (sell_strike - buy_strike) - mid_credit
    quantity = max(1, int((account_value * 0.02) // max_loss))
    parent_order = Order(
        action='SELL',
        orderType='LMT',
        totalQuantity=quantity,
        lmtPrice=mid_credit,
        transmit=False
    )
    trade = ib.placeOrder(combo, parent_order)
    ib.sleep(1)
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
    tp_trade = ib.placeOrder(combo, take_profit)
    print(f"📤 Placed spread SELL {sell_strike}P / BUY {buy_strike}P @ {mid_credit}")
    print("🎯 Take-profit set at 0.05")

    async def monitor_stop_trigger():
        print(f"📡 Watching 1-min close for stop under {sell_strike} and theta diff OCO")
        while True:
            sell_data_live = ib.reqMktData(sell_leg, '', False, False)
            buy_data_live = ib.reqMktData(buy_leg, '', False, False)
            ib.sleep(2)
            ib.cancelMktData(sell_leg)
            ib.cancelMktData(buy_leg)
            try:
                spread_price = round(((sell_data_live.bid + sell_data_live.ask) / 2 - (buy_data_live.bid + buy_data_live.ask) / 2), 2)
            except:
                spread_price = None

            # Theta diff exit
            if theta_diff is not None and spread_price is not None and spread_price < theta_diff:
                print(f"🛑 Spread price {spread_price} < theta diff {theta_diff:.4f}, closing spread.")
                close_order = Order(
                    action='BUY',
                    orderType='MKT',
                    totalQuantity=quantity,
                    transmit=True
                )
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

            # 1-min bar exit
            bars = ib.reqHistoricalData(
                Stock(symbol, 'SMART', 'USD'),
                endDateTime='',
                durationStr='5 mins',
                barSizeSetting='1 min',
                whatToShow='TRADES',
                useRTH=True,
                formatDate=1
            )
            if bars and bars[-1].close < sell_strike:
                print(f"🛑 1-min close < {sell_strike} detected at {bars[-1].close}")
                close_order = Order(
                    action='BUY',
                    orderType='MKT',
                    totalQuantity=quantity,
                    transmit=True
                )
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
                        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "spread": f"{symbol} {sell_strike}/{buy_strike} {expiry}",
                        "open_price": mid_credit,
                        "close_reason": "1-min close below short strike",
                        "status": "Exited manually",
                        "quantity": quantity
                    })
                break
            await asyncio.sleep(60)

    asyncio.create_task(monitor_stop_trigger())

    log_entry = {
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "spread": f"{symbol} {sell_strike}/{buy_strike} {expiry}",
        "open_price": mid_credit,
        "close_reason": "Pending TP/OCO",
        "status": "Open",
        "quantity": quantity
    }
    if trade_log_callback:
        trade_log_callback(log_entry)
    return {
        "spread": f"{symbol}_{sell_strike}_{buy_strike}_{expiry}",
        "order_id": parent_id,
        "credit": mid_credit,
        "quantity": quantity
    }