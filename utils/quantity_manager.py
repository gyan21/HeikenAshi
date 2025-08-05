import json
import os
from datetime import datetime, timedelta
from config.settings import DEFAULT_TRADE_QUANTITY, TRADE_QUANTITY_CONFIG_FILE
from utils.logger import TRADE_LOG_FILE
from config.config_manager import config_manager

def load_trade_quantity():
    """Load current trade quantity from configuration file"""
    if os.path.exists(TRADE_QUANTITY_CONFIG_FILE):
        try:
            with open(TRADE_QUANTITY_CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
                return config.get('quantity', DEFAULT_TRADE_QUANTITY)
        except Exception as e:
            print(f"Error loading trade quantity config: {e}")
    return DEFAULT_TRADE_QUANTITY

def save_trade_quantity(quantity):
    """Save trade quantity to configuration file"""
    config = {
        'quantity': quantity,
        'updated': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'auto_updated': True
    }
    try:
        with open(TRADE_QUANTITY_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)
        print(f"Trade quantity updated to {quantity} contracts")
    except Exception as e:
        print(f"Error saving trade quantity config: {e}")

def calculate_win_rate_last_10_trades():
    """Calculate win rate for the last 10 closed trades"""
    if not os.path.exists(TRADE_LOG_FILE):
        return 0.0, 0
    
    try:
        with open(TRADE_LOG_FILE, 'r', encoding='utf-8') as f:
            trades = json.load(f)
        
        # Filter closed trades only
        closed_trades = [
            t for t in trades 
            if t.get("status", "").lower().startswith("exited") and 
            "profit" in t
        ]
        
        if not closed_trades:
            return 0.0, 0
        
        # Sort by date descending and take last 10
        closed_trades.sort(key=lambda x: x.get("date", ""), reverse=True)
        last_10_trades = closed_trades[:10]
        
        if len(last_10_trades) < 10:
            return 0.0, len(last_10_trades)
        
        # Calculate win rate
        wins = sum(1 for trade in last_10_trades if trade.get("profit", 0) > 0)
        win_rate = (wins / len(last_10_trades)) * 100
        
        return win_rate, len(last_10_trades)
    
    except Exception as e:
        print(f"Error calculating win rate: {e}")
        return 0.0, 0

def update_trade_quantity_if_needed():
    """
    Update trade quantity based on win rate performance.
    If win rate >= 70% for last 10 trades, increase quantity by 10 contracts.
    """
    win_rate, trade_count = calculate_win_rate_last_10_trades()
    
    if trade_count < 10:
        print(f"Only {trade_count} closed trades available. Need 10 trades for quantity adjustment.")
        return load_trade_quantity()
    
    current_quantity = load_trade_quantity()
    
    if win_rate >= 70.0:
        new_quantity = current_quantity + 10
        save_trade_quantity(new_quantity)
        print(f"Win rate: {win_rate:.1f}% >= 70%. Increasing quantity from {current_quantity} to {new_quantity} contracts.")
        return new_quantity
    else:
        print(f"Win rate: {win_rate:.1f}% < 70%. Keeping current quantity: {current_quantity} contracts.")
        return current_quantity

def get_current_trade_quantity():
    """
    Get current trade quantity with performance-based adjustment
    """
    return config_manager.get_current_trade_quantity()

def get_quantity_info():
    """Get detailed quantity information"""
    stats = config_manager.get_recent_trade_statistics()
    current_quantity = config_manager.get('trade_quantity.default_quantity')
    
    return {
        'current_quantity': current_quantity,
        'recent_win_rate': stats.get('win_rate', 0),
        'recent_trades': stats.get('total_trades', 0),
        'target_win_rate': config_manager.get('trade_quantity.target_win_rate') * 100,
        'min_quantity': config_manager.get('trade_quantity.min_quantity'),
        'max_quantity': config_manager.get('trade_quantity.max_quantity')
    }
