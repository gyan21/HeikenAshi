# backtesting/create_backtest_config.py
import json
import shutil
from pathlib import Path
import os

def create_backtest_config():
    """Create backtesting configuration from main config"""
    
    # Ensure directories exist
    Path("config").mkdir(parents=True, exist_ok=True)  # Remove "backtesting/" since we're already in that folder
    
    # Check if main config exists
    main_config_path = "../config/trading_config.json"
    if not os.path.exists(main_config_path):
        print(f"❌ Main config file not found at: {main_config_path}")
        return False
    
    # Copy main config as base  
    backtest_config_path = "config/backtest_config.json"  # Fixed path
    shutil.copy(main_config_path, backtest_config_path)
    
    # Load and modify for backtesting
    with open(backtest_config_path, 'r') as f:
        config = json.load(f)
    
    # Backtest-specific modifications
    config["backtest_settings"] = {
        "symbol": "SPY",
        "start_date": "2023-01-01",
        "end_date": "2024-08-01",
        "initial_capital": 100000,
        "commission_per_trade": 2.0,
        "slippage": 0.01,
        "volatility_assumption": 0.25,
        "pattern_confirmation_rate": 0.30
    }
    
    # Disable debug mode for backtesting
    config["logging_settings"]["debug_mode"] = False
    
    # Save the backtest config
    with open(backtest_config_path, 'w') as f:
        json.dump(config, f, indent=4)
    
    print(f"✅ Backtest configuration created at: {backtest_config_path}")
    return True

if __name__ == "__main__":
    create_backtest_config()