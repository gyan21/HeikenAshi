from ib_insync import IB, Stock
from datetime import datetime

def calculate_heikin_ashi(candles):
    ha = []
    for i, c in enumerate(candles):
        if i == 0:
            ha_open = (c.open + c.close) / 2
        else:
            ha_open = (ha[-1].open + ha[-1].close) / 2
        ha_close = (c.open + c.high + c.low + c.close) / 4
        ha_high = max(c.high, ha_open, ha_close)
        ha_low = min(c.low, ha_open, ha_close)
        ha.append(type('Bar', (object,), dict(open=ha_open, close=ha_close, high=ha_high, low=ha_low)))
    return ha

async def get_regular_and_heikin_ashi_close(ib: IB, symbol: str):
    contract = Stock(symbol, 'SMART', 'USD')
    await ib.qualifyContractsAsync(contract)
    try:
        bars = await ib.reqHistoricalDataAsync(
        contract,
        # endDateTime=datetime.now().strftime("%Y%m%d %H:%M:%S"),
        endDateTime='',
        durationStr='5 D',
        barSizeSetting='1 day',
        whatToShow='TRADES',
        useRTH=True,
        formatDate=1
    )
    except ConnectionError as e:
        print(f"[get_regular_and_heikin_ashi_close] ConnectionError while requesting historical data: {e}")
        # Optionally: break or return to stop this monitor, or sleep and retry
    except Exception as e:
        print(f"[get_regular_and_heikin_ashi_close] Unexpected error while requesting historical data: {e}")

    if not bars or len(bars) < 2:
        raise Exception("Historical bars could not be fetched.")
    ha = calculate_heikin_ashi(bars)
    return bars[-1].close, ha[-1].close