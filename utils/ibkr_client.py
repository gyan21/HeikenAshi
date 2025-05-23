from ib_insync import Option, ContractDetails
from datetime import datetime, timedelta
from ib_insync import *
from ib_insync import Option
from utils.trade_utils import is_market_hours

class IBKRClient:
    def __init__(self, host='127.0.0.1', port=7497, clientId=1):
        self.ib = IB()
        self.host = host
        self.port = port
        self.clientId = clientId

    def connect(self):
        try:
            self.ib.connect(self.host, self.port, clientId=self.clientId)
                # Set market data type based on market hours
            if is_market_hours():
                self.ib.reqMarketDataType(1)  # Live
                print("✅ Using LIVE market data")
            else:
                self.ib.reqMarketDataType(2)  # Frozen
                print("✅ Using FROZEN market data (after hours)")
            return True
        except Exception as e:
            print(f"Connection error: {e}")
            return False

    def disconnect(self):
        self.ib.disconnect()

    def get_daily_close(self, symbol):
        contract = Stock(symbol, 'SMART', 'USD')
        bars = self.ib.reqHistoricalData(
            contract,
            endDateTime='',
            durationStr='2 D',
            barSizeSetting='1 day',
            whatToShow='TRADES',
            useRTH=True,
            formatDate=1
        )
        return bars[-1].close if bars else None

    def get_intraday_low(self, symbol):
        contract = Stock(symbol, 'SMART', 'USD')
        bars = self.ib.reqHistoricalData(
            contract,
            endDateTime='',
            durationStr='1 D',
            barSizeSetting='5 mins',
            whatToShow='TRADES',
            useRTH=True,
            formatDate=1
        )
        return min(bar.low for bar in bars) if bars else None


    def get_option_chain(self, symbol, expiry_hint=''):
        """
        Get the option chain using a qualified stock contract.
        """
        # First get the stock contract
        stock_contract = Stock(symbol, 'SMART', 'USD')
        qualified = self.ib.qualifyContracts(stock_contract)

        if not qualified:
            raise Exception(f"Could not qualify stock contract for {symbol}")

        conId = qualified[0].conId
        chains = self.ib.reqSecDefOptParams(
            symbol,
            '',
            'STK',
            conId
        )
        return chains


    def get_options_by_delta(self, symbol, expiry, delta_target=0.20):
        option_chain = self.ib.reqContractDetails(Option(symbol, expiry, 0, 'P', 'SMART'))
        result = []
        for detail in option_chain:
            greeks = detail.derivativeSecDefaults
            if greeks:
                delta = abs(greeks.get('delta', 0))
                result.append((delta, detail.contract))
        result.sort(key=lambda x: abs(x[0] - delta_target))
        return result[0][1] if result else None
    
    from ib_insync import Option
    from datetime import datetime, timedelta

    def find_put_with_delta(self, symbol, target_delta=0.20, delta_tolerance=0.10):
        from ib_insync import Option
        from datetime import datetime

        chains = self.get_option_chain(symbol)
        if not chains or not chains[0].expirations:
            raise Exception("No option chain available.")

        today = datetime.now().date()
        next_day_expiry = None
        for exp in sorted(chains[0].expirations):
            exp_date = datetime.strptime(exp, "%Y%m%d").date()
            if exp_date > today:
                next_day_expiry = exp
                break
        if not next_day_expiry:
            next_day_expiry = sorted(chains[0].expirations)[0]  # fallback

        strikes = sorted(chains[0].strikes)
        contracts = [Option(symbol, next_day_expiry, strike, 'P', 'SMART') for strike in strikes]
        qualified = self.ib.qualifyContracts(*contracts)

        market_data = self.ib.reqMktData(qualified, '', False, False)
        self.ib.sleep(2)
        self.ib.cancelMktData(*qualified)

        closest = None
        min_diff = float("inf")
        for contract, data in zip(qualified, market_data):
            if not data.modelGreeks or data.modelGreeks.delta is None:
                continue
            delta = abs(data.modelGreeks.delta)
            diff = abs(delta - target_delta)
            if diff <= delta_tolerance and diff < min_diff:
                min_diff = diff
                closest = contract

        if not closest:
            raise Exception("No suitable option found within delta tolerance.")
        return closest
