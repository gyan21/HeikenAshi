from datetime import datetime
import json
import os
from typing import List, Dict, Any

from utils.logger import save_trade_to_log

def log_trade_close(trade, open_price, close_price, quantity, trade_type, status, reason):
    profit = (close_price - open_price) * quantity if trade_type == "bull" else (open_price - close_price) * quantity
    profit_pct = (profit / (open_price * quantity)) * 100 if open_price else 0
    log_entry = {
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "spread": trade.get("spread"),
        "open_price": open_price,
        "close_price": close_price,
        "profit": profit,
        "profit_pct": profit_pct,
        "status": status,
        "close_reason": reason,
        "quantity": quantity
    }
    save_trade_to_log(log_entry)
    # Only log closed trades to Excel
    from utils.excel_utils import save_trade_to_excel
    save_trade_to_excel(log_entry)

def is_market_hours():
    """
    Check if current time is within market hours (9:30 AM - 4:00 PM ET).
    
    Returns:
        bool: True if market is open, False otherwise
    """
    from config.settings import MARKET_OPEN, MARKET_CLOSE
    
    now = datetime.now()
    current_time = now.time()
    
    # Check if it's a weekday (Monday = 0, Sunday = 6)
    if now.weekday() >= 5:  # Saturday or Sunday
        return False
    
    # Check if current time is within market hours
    return MARKET_OPEN <= current_time <= MARKET_CLOSE

def load_open_trades():
    """
    Load open trades from the open trades file.
    
    Returns:
        list: List of open trade dictionaries
    """
    open_trades_file = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), 
        'data', 
        'open_trades.json'
    )
    
    try:
        if os.path.exists(open_trades_file):
            with open(open_trades_file, 'r') as f:
                open_trades = json.load(f)
                print(f"📋 Loaded {len(open_trades)} open trades from {open_trades_file}")
                return open_trades
        else:
            print(f"📋 No open trades file found at {open_trades_file}")
            return []
    except Exception as e:
        print(f"❌ Error loading open trades: {e}")
        return []

def save_open_trades(open_trades):
    """
    Save open trades to the open trades file.
    
    Args:
        open_trades (list): List of open trade dictionaries
    """
    open_trades_file = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), 
        'data', 
        'open_trades.json'
    )
    
    try:
        # Ensure data directory exists
        os.makedirs(os.path.dirname(open_trades_file), exist_ok=True)
        
        with open(open_trades_file, 'w') as f:
            json.dump(open_trades, f, indent=2, default=str)
        print(f"💾 Saved {len(open_trades)} open trades to {open_trades_file}")
    except Exception as e:
        print(f"❌ Error saving open trades: {e}")

def load_closed_trades():
    """
    Load closed trades from the closed trades file.
    
    Returns:
        list: List of closed trade dictionaries
    """
    closed_trades_file = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), 
        'data', 
        'closed_trades.json'
    )
    
    try:
        if os.path.exists(closed_trades_file):
            with open(closed_trades_file, 'r') as f:
                closed_trades = json.load(f)
                print(f"📋 Loaded {len(closed_trades)} closed trades from {closed_trades_file}")
                return closed_trades
        else:
            print(f"📋 No closed trades file found at {closed_trades_file}")
            return []
    except Exception as e:
        print(f"❌ Error loading closed trades: {e}")
        return []

def save_closed_trades(closed_trades):
    """
    Save closed trades to the closed trades file.
    
    Args:
        closed_trades (list): List of closed trade dictionaries
    """
    closed_trades_file = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), 
        'data', 
        'closed_trades.json'
    )
    
    try:
        # Ensure data directory exists
        os.makedirs(os.path.dirname(closed_trades_file), exist_ok=True)
        
        with open(closed_trades_file, 'w') as f:
            json.dump(closed_trades, f, indent=2, default=str)
        print(f"💾 Saved {len(closed_trades)} closed trades to {closed_trades_file}")
    except Exception as e:
        print(f"❌ Error saving closed trades: {e}")

def add_open_trade(trade_data):
    """
    Add a single trade to the open trades file.
    
    Args:
        trade_data (dict): Trade data dictionary
    """
    open_trades = load_open_trades()
    open_trades.append(trade_data)
    save_open_trades(open_trades)

def add_closed_trade(trade_data):
    """
    Add a single trade to the closed trades file.
    
    Args:
        trade_data (dict): Trade data dictionary
    """
    closed_trades = load_closed_trades()
    closed_trades.append(trade_data)
    save_closed_trades(closed_trades)

def remove_open_trade(trade_id):
    """
    Remove a trade from open trades by ID.
    
    Args:
        trade_id (str): Trade ID to remove
        
    Returns:
        dict: Removed trade data or None if not found
    """
    open_trades = load_open_trades()
    
    for i, trade in enumerate(open_trades):
        if trade.get('trade_id') == trade_id:
            removed_trade = open_trades.pop(i)
            save_open_trades(open_trades)
            print(f"🗑️ Removed trade {trade_id} from open trades")
            return removed_trade
    
    print(f"⚠️ Trade {trade_id} not found in open trades")
    return None

def get_recent_win_rate(window=10):
    """
    Calculate win rate from recent closed trades.
    
    Args:
        window (int): Number of recent trades to consider
        
    Returns:
        float: Win rate as decimal (0.0 to 1.0)
    """
    closed_trades = load_closed_trades()
    
    if len(closed_trades) < window:
        # Not enough trades for calculation
        return 0.0
    
    # Get the most recent trades
    recent_trades = closed_trades[-window:]
    
    # Count wins (profit > 0)
    wins = sum(1 for trade in recent_trades if trade.get('profit', 0) > 0)
    
    win_rate = wins / len(recent_trades)
    print(f"📊 Recent win rate: {wins}/{len(recent_trades)} = {win_rate:.2%}")
    
    return win_rate

def move_trade_to_closed(trade_id, exit_price=None, profit=None, exit_reason="manual"):
    """
    Move a trade from open to closed trades.
    
    Args:
        trade_id (str): Trade ID to move
        exit_price (float): Exit price for the trade
        profit (float): Profit/loss for the trade
        exit_reason (str): Reason for closing the trade
    """
    # Remove from open trades
    trade_data = remove_open_trade(trade_id)
    
    if trade_data:
        # Add exit information
        trade_data['exit_timestamp'] = datetime.now().isoformat()
        trade_data['exit_price'] = exit_price
        trade_data['profit'] = profit
        trade_data['exit_reason'] = exit_reason
        trade_data['status'] = 'closed'
        
        # Add to closed trades
        add_closed_trade(trade_data)
        print(f"📈 Moved trade {trade_id} to closed trades")
    else:
        print(f"❌ Could not move trade {trade_id} - not found in open trades")

def get_trade_by_id(trade_id):
    """
    Get trade data by trade ID from open trades.
    
    Args:
        trade_id (str): Trade ID to find
        
    Returns:
        dict: Trade data or None if not found
    """
    open_trades = load_open_trades()
    
    for trade in open_trades:
        if trade.get('trade_id') == trade_id:
            return trade
    
    return None

def update_trade(trade_id, updates):
    """
    Update trade data in open trades.
    
    Args:
        trade_id (str): Trade ID to update
        updates (dict): Dictionary of fields to update
    """
    open_trades = load_open_trades()
    
    for trade in open_trades:
        if trade.get('trade_id') == trade_id:
            trade.update(updates)
            save_open_trades(open_trades)
            print(f"📝 Updated trade {trade_id}")
            return True
    
    print(f"⚠️ Trade {trade_id} not found for update")
    return False
