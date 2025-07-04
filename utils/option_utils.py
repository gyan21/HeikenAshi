from ib_insync import Option, Contract, ComboLeg, Order, Stock
import numpy as np
import asyncio
from datetime import datetime, date
import json
import os
import time

OPEN_TRADES_FILE = "open_trades.json"
QUANTITY = 1  # Default quantity for trades, can be adjusted
RISK_PERCENTAGE = 0.02  # Default risk percentage for trades


def save_open_trade(trade):
    trades = load_open_trades()
    # Avoid duplicates
    if not any(t.get("order_id") == trade.get("order_id") for t in trades):
        trades.append(trade)
        with open(OPEN_TRADES_FILE, "w", encoding="utf-8") as f:
            json.dump(trades, f, indent=2)

def remove_open_trade(order_id):
    trades = load_open_trades()
    trades = [t for t in trades if t.get("order_id") != order_id]
    with open(OPEN_TRADES_FILE, "w", encoding="utf-8") as f:
        json.dump(trades, f, indent=2)

def load_open_trades():
    if not os.path.exists(OPEN_TRADES_FILE):
        return []
    with open(OPEN_TRADES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

async def monitor_stop_trigger(ib, combo, sell_leg, buy_leg, symbol, sell_strike, buy_strike, expiry, quantity, tp_trade, mid_credit, trade_type, theta_diff, parent_id, trade_log_callback=None):
    from utils.trade_utils import log_trade_close   
    print(datetime.now().strftime("%Y-%m-%d %H:%M:%S") +    
        f" monitor_stop_trigger Monitoring {trade_type} spread {symbol} {sell_strike}/{buy_strike} {expiry}...")
        
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
        # print(vars(close_order))
        ib.placeOrder(combo, close_order)
        if tp_trade:
            ib.cancelOrder(tp_trade.order)
        log_trade_close(
            trade={"spread": f"{symbol} {sell_strike}/{buy_strike} {expiry}"},
            open_price=mid_credit,
            close_price=spread_price if spread_price is not None else 0,
            quantity=quantity,
            trade_type=trade_type,
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
        remove_open_trade(parent_id)

    # 1-min bar exit (only after 10am)
    try:
        bars = await ib.reqHistoricalDataAsync(
            Stock(symbol, 'SMART', 'USD'),
            endDateTime='',
            durationStr='300 S',  # 5 minutes
            barSizeSetting='1 min',
            whatToShow='TRADES',
            useRTH=True,
            formatDate=1
        )
    except ConnectionError as e:
        print(f"[monitor_stop_trigger] ConnectionError while requesting historical data: {e}")
        # Optionally: break or return to stop this monitor, or sleep and retry
    except Exception as e:
        print(f"[monitor_stop_trigger] Unexpected error while requesting historical data: {e}")
    now = datetime.now()
    if now.hour >= 10:
        if sell_leg.right == 'C':
            # Bear spread: stop if price > sell_strike
            if bars and bars[-1].close > sell_strike:
                print(f"🛑 1-min close > {sell_strike} detected at {bars[-1].close}")
                close_order = Order(action='BUY', orderType='MKT', totalQuantity=quantity,transmit=True)
                nuke_vol_fields(close_order)
                # print(vars(close_order))
                ib.placeOrder(combo, close_order)
                if tp_trade:
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
                remove_open_trade(parent_id)
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
                # print(vars(close_order))
                ib.placeOrder(combo, close_order)
                if tp_trade:
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
                remove_open_trade(parent_id)

def clean_magic_numbers(order):
    REQUIRED_FIELDS = {'totalQuantity', 'orderId', 'clientId', 'permId', 'action', 'orderType', 'lmtPrice', 'transmit'}
    for key, value in list(order.__dict__.items()):
        if key not in REQUIRED_FIELDS:
            if isinstance(value, float) and abs(value) > 1e+307:
                setattr(order, key, None)
            if isinstance(value, int) and value > 2e9:
                setattr(order, key, None)

def get_option_iv(ib, option):
    data = ib.reqMktData(option, '', False, False)
    ib.sleep(2)
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

async def place_and_save_when_filled(
    ib, combo, order, quantity, symbol, sell_strike, buy_strike, mid_credit, expiry,
    sell_leg, buy_leg, theta_diff, trade_Type, trade_log_callback=None):
    
    print(datetime.now().strftime("%Y-%m-%d %H:%M:%S") + f" place_and_save_when_filled for {symbol} with expiry {expiry}...")
    if not should_trade_now():
        return None
    # Place the order
    trade = ib.placeOrder(combo, order)
    # Wait for fill or terminal status
    while trade.orderStatus.status not in ("Filled", "ApiCancelled", "Cancelled", "Inactive"):
        await asyncio.sleep(1)
    parent_id = trade.order.orderId

    if trade.orderStatus.status == "Filled":
        # Now place the take-profit order
        take_profit = Order(
            action='BUY',
            orderType='LMT',
            totalQuantity=quantity,
            lmtPrice=0.05,
            parentId=parent_id,
            ocaGroup=f"{symbol}_OCO",
            ocaType=1,
            tif='GTC',
            transmit=True
        )
        nuke_vol_fields(take_profit)
        tp_trade = ib.placeOrder(combo, take_profit)
        tp_order_id = tp_trade.order.orderId

        log_entry = {
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "spread": f"{symbol} {sell_strike}/{buy_strike} {expiry}",
            "type": trade_Type,
            "symbol": symbol,
            "sell_strike": sell_strike,
            "buy_strike": buy_strike,
            "expiry": expiry,
            "open_price": mid_credit,
            "quantity": quantity,
            "close_reason": "Pending TP/OCO",
            "status": "Open",
            "order_id": parent_id,
            "tp_order_id": tp_order_id,
            "theta_diff": theta_diff
        }
        if trade_log_callback:
            trade_log_callback(log_entry)
        save_open_trade(log_entry)
        print(f"✅ Trade {trade.order.orderId} filled and saved.")
    else:
        print(f"⚠️ Trade {trade.order.orderId} not filled (status: {trade.orderStatus.status}), not saved.")
    
async def place_bull_spread_with_oco(ib, symbol, strike_pair, expiry, account_value, trade_log_callback=None):
    from utils.trade_utils import log_trade_close
    sell_strike, buy_strike = strike_pair
    if sell_strike < buy_strike:
        sell_strike, buy_strike = buy_strike, sell_strike
    sell_leg = Option(symbol, expiry, sell_strike, 'P', 'SMART')
    buy_leg = Option(symbol, expiry, buy_strike, 'P', 'SMART')
    await ib.qualifyContractsAsync(sell_leg, buy_leg)
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
    await asyncio.sleep(2)
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
    quantity = max(1, int((account_value * RISK_PERCENTAGE) // max_loss))
    quantity = QUANTITY
    lmt_price = -abs(mid_credit)
    parent_order = Order(
        action='BUY',
        orderType='LMT',
        totalQuantity=quantity,
        lmtPrice=lmt_price,
        tif='DAY',
        transmit=True
    )
    parent_order = clean_limit_order(parent_order)
    print("SELL strike:", sell_leg.strike, "BUY strike:", buy_leg.strike)
    print("Mid credit:", mid_credit)
    spread_width = abs(sell_strike - buy_strike)
    if mid_credit >= spread_width:
        print(f"[ERROR] Riskless combo detected: credit ({mid_credit}) >= width ({spread_width}) -- aborting order.")
        return None

    asyncio.create_task(
        place_and_save_when_filled(ib, combo, parent_order, quantity, symbol, sell_strike, buy_strike, mid_credit, expiry, sell_leg, buy_leg, theta_diff, "Bull", trade_log_callback)
    )
    return {
        "spread": f"{symbol}_{sell_strike}_{buy_strike}_{expiry}",
        "order_id": parent_order.orderId,
        "credit": mid_credit,
        "quantity": quantity
    }

async def place_bear_spread_with_oco(ib, symbol, strike_pair, expiry, account_value, trade_log_callback=None):
    from utils.trade_utils import log_trade_close
    sell_strike, buy_strike = strike_pair
    if sell_strike > buy_strike:
        sell_strike, buy_strike = buy_strike, sell_strike
    sell_leg = Option(symbol, expiry, sell_strike, 'C', 'SMART')
    buy_leg = Option(symbol, expiry, buy_strike, 'C', 'SMART')
    await ib.qualifyContractsAsync(sell_leg, buy_leg)
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
    await asyncio.sleep(2)
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
    max_loss = (buy_strike - sell_strike) - mid_credit
    quantity = max(1, int((account_value * RISK_PERCENTAGE) // max_loss))
    quantity = QUANTITY
    lmt_price = -abs(mid_credit)
    parent_order = Order(
        action='BUY',
        orderType='LMT',
        totalQuantity=quantity,
        lmtPrice=lmt_price,
        tif='DAY',
        transmit=True
    )
    parent_order = clean_limit_order(parent_order)
    print("SELL strike:", sell_leg.strike, "BUY strike:", buy_leg.strike)
    print("Mid credit:", mid_credit)
    # print(vars(parent_order))
    spread_width = abs(sell_strike - buy_strike)
    if mid_credit >= spread_width:
        print(f"[ERROR] Riskless combo detected: credit ({mid_credit}) >= width ({spread_width}) -- aborting order.")
        return None

    asyncio.create_task(
        place_and_save_when_filled(ib, combo, parent_order, quantity, symbol, sell_strike, buy_strike, mid_credit, expiry, sell_leg, buy_leg, theta_diff, "Bear", trade_log_callback)
    )
    return {
        "spread": f"{symbol}_{sell_strike}_{buy_strike}_{expiry}",
        "order_id": parent_order.orderId,
        "credit": mid_credit,
        "quantity": quantity
    }


async def resume_monitoring_open_trades(ib, trade_log_callback=None):
    print(datetime.now().strftime("%Y-%m-%d %H:%M:%S") + " THREAD-Resuming monitoring for open trades...")
    open_trades = load_open_trades()    
    for trade in open_trades:
        symbol = trade["symbol"]
        sell_strike = float(trade["sell_strike"])
        buy_strike = float(trade["buy_strike"])
        expiry = trade["expiry"]
        quantity = int(trade["quantity"])
        trade_type = trade.get("type", "bull")
        mid_credit = trade.get("open_price", 0)
        parent_id = trade.get("order_id")
        theta_diff = trade.get("theta_diff")
        right = 'P' if trade_type == "bull" else 'C'
        sell_leg = Option(symbol, expiry, sell_strike, right, 'SMART')
        buy_leg = Option(symbol, expiry, buy_strike, right, 'SMART')
        await ib.qualifyContractsAsync(sell_leg, buy_leg)
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
        tp_order_id = trade.get("tp_order_id")
        tp_trade = None
        if tp_order_id:
            # Find the trade/order by orderId
            for t in ib.trades():
                if t.order.orderId == tp_order_id:
                    tp_trade = t
                    break
        await monitor_stop_trigger(ib, combo, sell_leg, buy_leg, symbol, sell_strike, buy_strike, expiry, quantity, tp_trade, mid_credit, trade_type, theta_diff, parent_id, trade_log_callback)
    
async def get_next_option_expiry(ib, symbol):
    contract = Stock(symbol, 'SMART', 'USD')
    await ib.qualifyContractsAsync(contract)
    chains = await ib.reqSecDefOptParamsAsync(contract.symbol, '', contract.secType, contract.conId)
    if not chains:
        return None
    expiries = sorted(list(set(chains[0].expirations)))
    today = date.today()
    for expiry_str in expiries:
        expiry_date = datetime.strptime(expiry_str, "%Y%m%d").date()
        if expiry_date > today:
            return expiry_str
    return None

async def find_options_by_delta(ib, symbol, expiry=None, right='C', min_delta=0.20, max_delta=0.30):
    contract = Stock(symbol, 'SMART', 'USD')
    await ib.qualifyContractsAsync(contract)
    chain = await ib.reqSecDefOptParamsAsync(contract.symbol, '', contract.secType, contract.conId)
    if not chain:
        print(f"[WARN] No option chain found for {symbol}")
        return []
    expiries = sorted(list(set(chain[0].expirations)))
    today = date.today()
    if expiry is None:
        for expiry_str in expiries:
            expiry_date = datetime.strptime(expiry_str, "%Y%m%d").date()
            if expiry_date > today:
                expiry = expiry_str
                break
    if not expiry:
        print(f"[WARN] No valid expiry found for {symbol}")
        return []
    ticker = ib.reqMktData(contract, '', False, False)
    await asyncio.sleep(2)
    price = ticker.marketPrice() if hasattr(ticker, 'marketPrice') else None
    ib.cancelMktData(contract)
    if price is None or price <= 0:
        print(f"[WARN] Could not get current price for {symbol}")
        return []
    from ib_insync import Option
    details = await ib.reqContractDetailsAsync(Option(symbol, expiry, 0, right, 'SMART'))
    valid_strikes = sorted({cd.contract.strike for cd in details if abs(cd.contract.strike - price) <= 10})
    if not valid_strikes:
        print(f"[WARN] No valid strikes found for {symbol} {expiry} {right}")
        return []
    atm_idx = min(range(len(valid_strikes)), key=lambda i: abs(valid_strikes[i] - price))
    matching_options = []
    start_time = time.time()
    if right.upper() == 'P':
        strike_range = range(atm_idx, -1, -1)
    else:
        strike_range = range(atm_idx, len(valid_strikes))
    for idx in strike_range:
        strike = valid_strikes[idx]
        option = Option(symbol, expiry, strike, right, 'SMART')
        await ib.qualifyContractsAsync(option)
        data = ib.reqMktData(option, '', False, False)
        await asyncio.sleep(2)
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
counter = 0
def should_trade_now():
    from datetime import time
    # return is_time_between(time(15, 45), time(16, 0))
    # global counter
    # if counter < 2:
    #     counter += 1
    return 1

def is_time_between(start, end):
    now = datetime.now().time()
    return start <= now <= end