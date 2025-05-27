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
