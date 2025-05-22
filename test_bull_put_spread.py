from ib_insync import IB, Stock, Option, ComboLeg, Contract, Order
from datetime import datetime

ib = IB()
ib.connect('127.0.0.1', 7497, clientId=1)
ib.reqMarketDataType(1)

# Step 1: Setup
symbol = 'SPY'
sell_strike = 590
buy_strike = 585
quantity = 1
limit_price = 0.50

# Step 2: Get Expiry
stock = Stock(symbol, 'SMART', 'USD')
ib.qualifyContracts(stock)
chain = ib.reqSecDefOptParams(symbol, '', 'STK', stock.conId)
expiry = sorted(chain[0].expirations)[0]
print(f"📅 Expiry: {expiry}")

# Step 3: Qualify legs
sell_option = Option(symbol, expiry, sell_strike, 'P', 'SMART')
buy_option = Option(symbol, expiry, buy_strike, 'P', 'SMART')
ib.qualifyContracts(sell_option, buy_option)

# Step 4: Build combo legs
legs = [
    ComboLeg(conId=sell_option.conId, ratio=1, action='SELL', exchange='SMART'),
    ComboLeg(conId=buy_option.conId, ratio=1, action='BUY', exchange='SMART')
]

# Step 5: Create BAG combo
combo = Contract()
combo.symbol = symbol
combo.secType = 'BAG'
combo.currency = 'USD'
combo.exchange = 'SMART'
combo.comboLegs = legs

print(f"Combo Contract: {combo}")

# Step 6: Create and send LMT order (NO volatility!)
order = Order(
    action='SELL',
    orderType='LMT',
    totalQuantity=quantity,
    lmtPrice=limit_price,
    transmit=True
)

print("📤 Placing order...")
trade = ib.placeOrder(combo, order)
ib.sleep(2)

# Step 7: Status
print(f"🧾 Order Status: {trade.orderStatus.status}")
print(f"Filled: {trade.orderStatus.filled}, Remaining: {trade.orderStatus.remaining}")