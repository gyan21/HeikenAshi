# Configuration for Heikin-Ashi Credit Spread Trading Algorithm
ACCOUNT_VALUE = 100_000
RISK_PER_TRADE = 0.02
MAX_TRADES_PER_DAY = 2

# Trade quantity configuration
DEFAULT_TRADE_QUANTITY = 30
TRADE_QUANTITY_CONFIG_FILE = "trade_quantity_config.json"

# Spread configuration
SPREAD_WIDTH = 10  # Points
MIN_PREMIUM_TIER_1 = 55  # First attempt minimum premium per contract
MIN_PREMIUM_TIER_2 = 45  # Fallback minimum premium per contract
MIN_PREMIUM_NEXT_DAY = 25  # Next day additional trade minimum premium

# Delta search configuration
DELTA_SEARCH_RANGE = [0.24, 0.23, 0.22, 0.21, 0.20]

# Trading times (ET)
TRADE_EXECUTION_START = "15:55"  # 3:55 PM ET
TRADE_EXECUTION_END = "16:00"    # 4:00 PM ET
FALLBACK_EXECUTION_END = "16:00" # 4:00 PM ET
PATTERN_MONITORING_START = "10:00"  # 10:00 AM ET

# Exit pattern requirements
BULL_EXIT_PATTERN = ["green", "green", "red"]  # GGR for 15-min candles
BEAR_EXIT_PATTERN = ["red", "red", "green"]    # RRG for 15-min candles

# Additional trade patterns (next day)
BULL_ADDITIONAL_PATTERN = ["red", "red", "green"]  # RRG for bull trades
BEAR_ADDITIONAL_PATTERN = ["green", "green", "red"] # GGR for bear trades