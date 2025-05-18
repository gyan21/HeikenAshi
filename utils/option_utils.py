import asyncio
from ib_insync import Option, Contract, ComboLeg, Order, Stock
from datetime import datetime

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
    ib.cancelMktData(sell_leg)
    ib.cancelMktData(buy_leg)

    try:
        mid_credit = round(((sell_data.bid + sell_data.ask) / 2 - (buy_data.bid + buy_data.ask) / 2), 2)
    except:
        mid_credit = 0.5
    if mid_credit <= 0: mid_credit = 0.5

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
        print(f"📡 Watching 1-min close for stop under {sell_strike}")
        while True:
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
                log_entry = {
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "spread": f"{symbol} {sell_strike}/{buy_strike} {expiry}",
                    "open_price": mid_credit,
                    "close_reason": "1-min close below short strike",
                    "status": "Exited manually",
                    "quantity": quantity
                }
                if trade_log_callback:
                    trade_log_callback(log_entry)
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