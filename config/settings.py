# config/settings.py - Simplified to just import from config manager
from config.config_manager import config_manager

# Account settings
ACCOUNT_VALUE = config_manager.get('account_settings.account_value', 100000)
RISK_PER_TRADE = config_manager.get('account_settings.risk_per_trade', 0.02)
MAX_TRADES_PER_DAY = config_manager.get('account_settings.max_trades_per_day', 2)

# Trade quantity (dynamic based on performance)
DEFAULT_TRADE_QUANTITY = config_manager.get_current_trade_quantity()

# Spread configuration
SPREAD_WIDTH = config_manager.get('spread_settings.spread_width', 10)
MIN_PREMIUM_TIER_1 = config_manager.get('spread_settings.min_premium_tier_1', 0.55)
MIN_PREMIUM_TIER_2 = config_manager.get('spread_settings.min_premium_tier_2', 0.45)
MIN_PREMIUM_NEXT_DAY_BEFORE_12 = config_manager.get('spread_settings.min_premium_next_day_before_12', 0.50)
MIN_PREMIUM_NEXT_DAY_AFTER_12 = config_manager.get('spread_settings.min_premium_next_day_after_12', 0.35)

# Delta search configuration
DELTA_SEARCH_RANGE = config_manager.get('delta_settings.delta_search_range', [0.24, 0.23, 0.22, 0.21, 0.20])

# Trading times
TRADE_EXECUTION_START = config_manager.get('trading_times.trade_execution_start', "15:55")
TRADE_EXECUTION_END = config_manager.get('trading_times.trade_execution_end', "16:00")
FALLBACK_EXECUTION_END = config_manager.get('trading_times.fallback_execution_end', "16:00")
PATTERN_MONITORING_START = config_manager.get('trading_times.pattern_monitoring_start', "10:00")

# Exit patterns
BULL_EXIT_PATTERN = config_manager.get('exit_patterns.bull_exit_pattern', ["green", "green", "red"])
BEAR_EXIT_PATTERN = config_manager.get('exit_patterns.bear_exit_pattern', ["red", "red", "green"])

# Additional trade patterns
BULL_ADDITIONAL_PATTERN = config_manager.get('additional_trade_patterns.bull_additional_pattern', ["red", "red", "green"])
BEAR_ADDITIONAL_PATTERN = config_manager.get('additional_trade_patterns.bear_additional_pattern', ["green", "green", "red"])

# Debug mode
DEBUG = config_manager.get('logging_settings.debug_mode', True)

# Expose config manager for direct access
def get_config():
    return config_manager

def update_config(path, value):
    return config_manager.set(path, value)