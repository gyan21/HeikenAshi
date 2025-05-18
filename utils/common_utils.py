import os
import json
from datetime import datetime, date

def has_reached_trade_limit(log_file='trade_log.json', max_trades=2):
    if not os.path.exists(log_file):
        return False
    with open(log_file, 'r') as f:
        trades = json.load(f)
    today = date.today().isoformat()
    today_trades = [t for t in trades if t['date'].startswith(today)]
    return len(today_trades) >= max_trades

def is_dry_run():
    return datetime.today().weekday() >= 5  # 5 = Saturday, 6 = Sunday
