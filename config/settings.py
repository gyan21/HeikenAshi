import os
from datetime import time
from .config_manager import ConfigManager

# Initialize config manager
config_manager = ConfigManager()

# Load trading configuration
TRADING_CONFIG = config_manager.config

# ==================== ACCOUNT & TRADE SETTINGS ====================
ACCOUNT_VALUE = TRADING_CONFIG.get('backtest_settings', {}).get('initial_capital', 50000)
DEFAULT_TRADE_QUANTITY = TRADING_CONFIG.get('trade_settings', {}).get('main_trade_qty', 30)

# ==================== SPREAD SETTINGS ====================
SPREAD_POINTS = TRADING_CONFIG.get('trade_settings', {}).get('spread_points', 10)
SPREAD_WIDTH = TRADING_CONFIG.get('trade_settings', {}).get('spread_width', 10)  # Same as spread_points

# ==================== CREDIT SETTINGS ====================
MAIN_TRADE_CREDIT = TRADING_CONFIG.get('trade_settings', {}).get('main_trade_credit', 45)
ADDITIONAL_TRADE_1_CREDIT = TRADING_CONFIG.get('trade_settings', {}).get('additional_trade_1_credit', 45)
ADDITIONAL_TRADE_2_CREDIT = TRADING_CONFIG.get('trade_settings', {}).get('additional_trade_2_credit', 25)

# ==================== PREMIUM TIER SETTINGS ====================
MIN_PREMIUM_TIER_1 = TRADING_CONFIG.get('trade_settings', {}).get('min_premium_tier_1', 0.05)
MIN_PREMIUM_TIER_2 = TRADING_CONFIG.get('trade_settings', {}).get('min_premium_tier_2', 0.10)
MIN_PREMIUM_TIER_3 = TRADING_CONFIG.get('trade_settings', {}).get('min_premium_tier_3', 0.20)

# ==================== ADDITIONAL PREMIUM SETTINGS ====================
MIN_PREMIUM_NEXT_DAY = TRADING_CONFIG.get('trade_settings', {}).get('min_premium_next_day', 0.15)
MIN_PREMIUM_NEXT_DAY_AFTER_12 = TRADING_CONFIG.get('trade_settings', {}).get('min_premium_next_day_after_12', 0.10)
MIN_PREMIUM_NEXT_DAY_BEFORE_12 = TRADING_CONFIG.get('trade_settings', {}).get('min_premium_next_day_before_12', 0.20)

# ==================== DELTA SETTINGS ====================
DELTA_SEARCH_RANGE = TRADING_CONFIG.get('option_settings', {}).get('delta_search_range', 5)
TARGET_DELTA = TRADING_CONFIG.get('option_settings', {}).get('target_delta', 30)
MIN_DELTA = TRADING_CONFIG.get('option_settings', {}).get('min_delta', 15)
MAX_DELTA = TRADING_CONFIG.get('option_settings', {}).get('max_delta', 45)
DELTA_TOLERANCE = TRADING_CONFIG.get('option_settings', {}).get('delta_tolerance', 5)

# ==================== TRADING TIME SETTINGS ====================
TRADE_EXECUTION_START = time(15, 55)  # 3:55 PM ET - Main strategy
TRADE_EXECUTION_END = time(16, 0)     # 4:00 PM ET - Main strategy
MARKET_OPEN = time(9, 30)             # 9:30 AM ET
MARKET_CLOSE = time(16, 0)            # 4:00 PM ET
ADDITIONAL_SCAN_START = time(9, 30)   # 9:30 AM ET - Additional opportunities
ADDITIONAL_SCAN_END = time(15, 0)     # 3:00 PM ET - Additional opportunities

# ==================== PATTERN MONITORING SETTINGS ====================
PATTERN_MONITORING_START = time(9, 30)   # 9:30 AM ET - Start monitoring patterns
PATTERN_MONITORING_END = time(16, 0)     # 4:00 PM ET - End monitoring patterns
TRADE_MONITORING_START = time(9, 30)    # 9:30 AM ET - Start monitoring trades
TRADE_MONITORING_END = time(16, 0)      # 4:00 PM ET - End monitoring trades

# ==================== WIN RATE & QUANTITY MANAGEMENT ====================
WIN_RATE_THRESHOLD = TRADING_CONFIG.get('trade_settings', {}).get('win_rate_threshold', 0.7)
WIN_RATE_WINDOW = TRADING_CONFIG.get('trade_settings', {}).get('win_rate_window', 10)
INCREMENT_QTY = TRADING_CONFIG.get('trade_settings', {}).get('increment_qty', 5)

# ==================== MACD INDICATOR SETTINGS ====================
MACD_FAST = TRADING_CONFIG.get('indicators', {}).get('macd', {}).get('fast', 12)
MACD_SLOW = TRADING_CONFIG.get('indicators', {}).get('macd', {}).get('slow', 26)
MACD_SIGNAL = TRADING_CONFIG.get('indicators', {}).get('macd', {}).get('signal', 9)

# ==================== IBKR CONNECTION SETTINGS ====================
IBKR_HOST = TRADING_CONFIG.get('data_settings', {}).get('host', '127.0.0.1')
IBKR_PORT = TRADING_CONFIG.get('data_settings', {}).get('port', 7497)
CLIENT_ID = TRADING_CONFIG.get('data_settings', {}).get('client_id', 1)

# ==================== COMMISSION & COSTS ====================
COMMISSION_PER_TRADE = TRADING_CONFIG.get('backtest_settings', {}).get('commission_per_trade', 1.0)

# ==================== DEBUG & LOGGING SETTINGS ====================
DEBUG = TRADING_CONFIG.get('debug_settings', {}).get('debug_mode', False)
VERBOSE_LOGGING = TRADING_CONFIG.get('debug_settings', {}).get('verbose_logging', True)
LOG_LEVEL = TRADING_CONFIG.get('debug_settings', {}).get('log_level', 'INFO')
SAVE_TRADE_LOGS = TRADING_CONFIG.get('debug_settings', {}).get('save_trade_logs', True)

# ==================== FILE PATHS ====================
TRADE_QUANTITY_CONFIG_FILE = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), 
    'config', 
    'trade_quantity.json'
)

# ==================== FALLBACK DEFAULTS ====================
# If option_settings doesn't exist in config, use hardcoded defaults
if 'option_settings' not in TRADING_CONFIG:
    print("⚠️ option_settings not found in config, using defaults")
    DELTA_SEARCH_RANGE = 5
    TARGET_DELTA = 30
    MIN_DELTA = 15
    MAX_DELTA = 45
    DELTA_TOLERANCE = 5

# If debug_settings doesn't exist in config, use hardcoded defaults
if 'debug_settings' not in TRADING_CONFIG:
    DEBUG = False
    VERBOSE_LOGGING = True
    LOG_LEVEL = 'INFO'
    SAVE_TRADE_LOGS = True

# ==================== STARTUP INFO ====================
print(f"✅ Trading settings loaded:")
print(f"   💰 Account Value: ${ACCOUNT_VALUE:,}")
print(f"   📊 Default Quantity: {DEFAULT_TRADE_QUANTITY}")
print(f"   🎯 Spread Points: {SPREAD_POINTS}")
print(f"   📏 Spread Width: {SPREAD_WIDTH}")
print(f"   💵 Main Trade Credit: ${MAIN_TRADE_CREDIT}")
print(f"   💎 Premium Tiers: ${MIN_PREMIUM_TIER_1} / ${MIN_PREMIUM_TIER_2} / ${MIN_PREMIUM_TIER_3}")
print(f"   💰 Next Day Premiums: General=${MIN_PREMIUM_NEXT_DAY}, Before12=${MIN_PREMIUM_NEXT_DAY_BEFORE_12}, After12=${MIN_PREMIUM_NEXT_DAY_AFTER_12}")
print(f"   🔺 Delta Settings: Target={TARGET_DELTA}, Range=±{DELTA_SEARCH_RANGE}, Min={MIN_DELTA}, Max={MAX_DELTA}")
print(f"   ⏰ Trade Execution: {TRADE_EXECUTION_START.strftime('%H:%M')} - {TRADE_EXECUTION_END.strftime('%H:%M')} ET")
print(f"   📈 Market Hours: {MARKET_OPEN.strftime('%H:%M')} - {MARKET_CLOSE.strftime('%H:%M')} ET")
print(f"   🔍 Additional Scan: {ADDITIONAL_SCAN_START.strftime('%H:%M')} - {ADDITIONAL_SCAN_END.strftime('%H:%M')} ET")
print(f"   👁️ Pattern Monitor: {PATTERN_MONITORING_START.strftime('%H:%M')} - {PATTERN_MONITORING_END.strftime('%H:%M')} ET")
print(f"   📊 Trade Monitor: {TRADE_MONITORING_START.strftime('%H:%M')} - {TRADE_MONITORING_END.strftime('%H:%M')} ET")
print(f"   🐛 Debug Mode: {'ON' if DEBUG else 'OFF'}")
print(f"   📝 Log Level: {LOG_LEVEL}")
print(f"   🔗 IBKR Connection: {IBKR_HOST}:{IBKR_PORT} (Client ID: {CLIENT_ID})")
print(f"   📁 Trade Quantity Config: {TRADE_QUANTITY_CONFIG_FILE}")

# Debug output to help troubleshoot config loading
if DEBUG:
    print(f"\n🔍 Config sections found: {list(TRADING_CONFIG.keys())}")
    if 'option_settings' in TRADING_CONFIG:
        print(f"🔍 Option settings: {TRADING_CONFIG['option_settings']}")
    if 'debug_settings' in TRADING_CONFIG:
        print(f"🔍 Debug settings: {TRADING_CONFIG['debug_settings']}")