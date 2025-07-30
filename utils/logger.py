import json
import os
import pandas as pd
from datetime import datetime

LOG_PATH = 'data/trade_log.xlsx'
JSON_PATH = 'data/trade_log.json'

TRADE_LOG_FILE = 'trade_log.json'

def save_trade_to_log(trade_info):
    """
    Save trade information to JSON log file
    
    Expected trade_info fields per new requirements:
    - Trade Date
    - dailyClosePrice - dailyCloseHA
    - Spread Legs (e.g., C620/C630)
    - Trade Open Time
    - Trade Close Time  
    - Trade Quantity
    - Delta of shorted option/Delta of long option
    - Sell Price of Spread
    - Buy Price of Spread
    - Net P/L
    - P/L Label (Profit or Loss)
    """
    log_data = []
    if os.path.exists(TRADE_LOG_FILE):
        with open(TRADE_LOG_FILE, 'r', encoding="utf-8") as f:
            log_data = json.load(f)
    
    # Remove any previous "Open" entry for this spread if closing
    if trade_info.get("status", "").startswith("Exited"):
        log_data = [t for t in log_data if not (
            t.get("spread") == trade_info.get("spread") and t.get("status") == "Open"
        )]
    
    # Enhance trade info with required fields
    enhanced_trade_info = enhance_trade_info(trade_info)
    log_data.append(enhanced_trade_info)
    
    with open(TRADE_LOG_FILE, 'w', encoding="utf-8") as f:
        json.dump(log_data, f, indent=2)

def enhance_trade_info(trade_info):
    """
    Enhance trade info with additional required fields per new requirements
    """
    enhanced = trade_info.copy()
    
    # Calculate price difference if available
    if 'dailyClosePrice' in enhanced and 'dailyCloseHA' in enhanced:
        price_diff = enhanced['dailyClosePrice'] - enhanced['dailyCloseHA']
        enhanced['price_difference'] = round(price_diff, 2)
    
    # Format spread legs properly (e.g., C620/C630 or P580/P570)
    if 'spread' not in enhanced and 'sell_strike' in enhanced and 'buy_strike' in enhanced:
        option_type = enhanced.get('option_type', 'C')
        sell_strike = enhanced['sell_strike']
        buy_strike = enhanced['buy_strike']
        enhanced['spread'] = f"{option_type}{int(sell_strike)}/{option_type}{int(buy_strike)}"
    
    # Set trade open time
    if 'trade_open_time' not in enhanced:
        enhanced['trade_open_time'] = enhanced.get('date', datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    
    # Set trade close time for closed trades
    if enhanced.get('status', '').startswith('Exited') and 'trade_close_time' not in enhanced:
        enhanced['trade_close_time'] = enhanced.get('exit_date', datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    
    # Calculate P/L if not already present
    if 'net_pl' not in enhanced and 'profit' in enhanced:
        enhanced['net_pl'] = enhanced['profit']
    
    # Set P/L label
    if 'pl_label' not in enhanced:
        if enhanced.get('net_pl', 0) > 0:
            enhanced['pl_label'] = 'Profit'
        elif enhanced.get('net_pl', 0) < 0:
            enhanced['pl_label'] = 'Loss'
        else:
            enhanced['pl_label'] = 'Breakeven'
    
    # Set default values for missing fields
    if 'sell_price_spread' not in enhanced:
        enhanced['sell_price_spread'] = enhanced.get('target_premium', 0)
    
    if 'buy_price_spread' not in enhanced:
        enhanced['buy_price_spread'] = enhanced.get('exit_price', 0)
    
    return enhanced
        
def log_trade(trade_data):
    """Legacy function for backward compatibility"""
    # Log JSON
    if os.path.exists(JSON_PATH):
        with open(JSON_PATH, 'r', encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = []

    data.append(trade_data)
    with open(JSON_PATH, 'w', encoding="utf-8") as f:
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

def get_trade_summary():
    """Get summary of all trades for reporting"""
    if not os.path.exists(TRADE_LOG_FILE):
        return {
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'win_rate': 0.0,
            'total_pnl': 0.0
        }
    
    try:
        with open(TRADE_LOG_FILE, 'r', encoding='utf-8') as f:
            trades = json.load(f)
        
        # Filter closed trades only
        closed_trades = [t for t in trades if t.get('status', '').startswith('Exited')]
        
        if not closed_trades:
            return {
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0.0,
                'total_pnl': 0.0
            }
        
        winning_trades = sum(1 for t in closed_trades if t.get('net_pl', 0) > 0)
        losing_trades = sum(1 for t in closed_trades if t.get('net_pl', 0) < 0)
        total_pnl = sum(t.get('net_pl', 0) for t in closed_trades)
        win_rate = (winning_trades / len(closed_trades)) * 100 if closed_trades else 0
        
        return {
            'total_trades': len(closed_trades),
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': round(win_rate, 2),
            'total_pnl': round(total_pnl, 2)
        }
        
    except Exception as e:
        print(f"Error getting trade summary: {e}")
        return {
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'win_rate': 0.0,
            'total_pnl': 0.0
        }