import json
import os
import pandas as pd
from datetime import datetime

LOG_PATH = 'data/trade_log.xlsx'
JSON_PATH = 'data/trade_log.json'

def log_trade(trade_data):
    # Log JSON
    if os.path.exists(JSON_PATH):
        with open(JSON_PATH, 'r') as f:
            data = json.load(f)
    else:
        data = []

    data.append(trade_data)
    with open(JSON_PATH, 'w') as f:
        json.dump(data, f, indent=2)

    # Log Excel
    row = {
        "Date": datetime.now().strftime("%Y-%m-%d"),
        "Spread": trade_data["spread"],
        "Order ID": trade_data["order_id"],
        "Entry Price": trade_data["entry_price"],
        "Quantity": trade_data["quantity"]
    }

    df = pd.DataFrame([row])
    if os.path.exists(LOG_PATH):
        old = pd.read_excel(LOG_PATH)
        df = pd.concat([old, df], ignore_index=True)
    df.to_excel(LOG_PATH, index=False)