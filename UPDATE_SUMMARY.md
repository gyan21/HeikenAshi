# Heikin-Ashi Trading Algorithm - Update Summary

## What Was Changed

I have completely updated your Heikin-Ashi trading algorithm according to your new requirements. Here's a comprehensive summary of the changes:

## 🔄 Major Algorithm Changes

### 1. **Trade Execution Timing**
- **OLD**: Multiple checks at 47, 52, 57 minutes past the hour
- **NEW**: Single execution window at 3:55 PM - 4:00 PM ET daily

### 2. **Option Selection Method**
- **OLD**: Delta range search (0.20-0.30)
- **NEW**: Precise delta targeting: 0.24 → 0.23 → 0.22 → 0.21 → 0.20 (in order)
- **NEW**: Independent search for Call and Put options

### 3. **Trade Direction Logic**
- **OLD**: Basic comparison of regular vs Heikin-Ashi close
- **NEW**: 
  ```
  If dailyClosePrice > dailyCloseHA: Bull Credit Spread (Sell Put)
  Else: Bear Credit Spread (Sell Call)
  ```

### 4. **Spread Configuration**
- **OLD**: 5-point spreads
- **NEW**: 10-point spreads
- **NEW**: Premium requirements: $55 primary, $45 fallback

### 5. **Quantity Management**
- **OLD**: Percentage-based position sizing with 2-week win rate scaling
- **NEW**: Fixed quantity (30 contracts) with automatic increases (+10) when win rate ≥ 70% for last 10 trades

## 🆕 Brand New Features

### 1. **Advanced Exit Logic**
- **Bull Spreads**: Exit only when ALL conditions met:
  - Price below previous day's low OR below short strike
  - Time ≥ 10:00 AM
  - 15-minute chart shows Green-Green-Red pattern

- **Bear Spreads**: Exit only when ALL conditions met:
  - Price above previous day's high OR above short strike  
  - Time ≥ 10:00 AM
  - 15-minute chart shows Red-Red-Green pattern

### 2. **Next-Day Additional Trades**
- Monitors for additional opportunities using same direction as previous day
- Pattern requirements:
  - Bull: Red-Red-Green pattern for entry
  - Bear: Green-Green-Red pattern for entry
- Minimum $25 premium requirement
- Smaller position sizes (1/3 of main trade)

### 3. **Enhanced Pattern Detection**
- 15-minute candlestick pattern analysis
- Color determination (red/green/doji)
- Previous day data integration
- Pattern confirmation for entries and exits

### 4. **Comprehensive Logging System**
New logging fields per your requirements:
- Trade Date
- dailyClosePrice - dailyCloseHA difference
- Spread Legs (formatted as C620/C630)
- Trade Open/Close Times
- Trade Quantity
- Delta values for both legs
- Sell/Buy Prices
- Net P/L and P/L Labels

## 📁 New File Structure

### New Utility Files Created:
1. **`utils/quantity_manager.py`** - Manages trade quantities and win rate calculations
2. **`utils/pattern_utils.py`** - Handles 15-minute pattern detection and analysis
3. **`utils/delta_option_finder.py`** - New delta-based option selection system
4. **`utils/trade_executor.py`** - Main trade execution logic for 3:55 PM trades
5. **`utils/trade_monitor.py`** - Advanced exit condition monitoring
6. **`utils/additional_trades.py`** - Next-day opportunity scanning and execution

### Updated Files:
1. **`main.py`** - Completely restructured with new strategy components
2. **`config/settings.py`** - Enhanced with all new configuration parameters
3. **`utils/logger.py`** - Enhanced logging with required fields and formatting
4. **`README.md`** - Comprehensive documentation of new algorithm
5. **`requirements.txt`** - Added pytz for timezone handling

## ⚙️ Configuration Changes

### New Settings Added:
```python
DEFAULT_TRADE_QUANTITY = 30
SPREAD_WIDTH = 10
MIN_PREMIUM_TIER_1 = 55  # $55 per contract
MIN_PREMIUM_TIER_2 = 45  # $45 per contract  
MIN_PREMIUM_NEXT_DAY = 25  # $25 per contract
DELTA_SEARCH_RANGE = [0.24, 0.23, 0.22, 0.21, 0.20]
TRADE_EXECUTION_START = "15:55"  # 3:55 PM ET
TRADE_EXECUTION_END = "16:00"    # 4:00 PM ET
PATTERN_MONITORING_START = "10:00"  # 10:00 AM ET
```

## 🔧 Technical Improvements

### 1. **Modular Architecture**
- Separated concerns into focused utility modules
- Cleaner, more maintainable code structure
- Better error handling and logging

### 2. **Timezone Handling**
- Proper Eastern Time handling for all trading times
- Market hours validation
- Time-based execution controls

### 3. **Pattern Recognition System**
- Advanced 15-minute chart analysis
- Multi-candle pattern detection
- Previous day data integration

### 4. **Robust Trade Monitoring**
- Continuous position monitoring
- Multiple exit condition verification
- Resumable monitoring after restarts

## 🧪 Testing

- Created comprehensive test suite (`test_algorithm.py`)
- All components tested and verified
- Configuration validation
- Import verification
- Logic testing for all major functions

## 📊 Key Algorithm Flow

1. **Daily (3:55 PM ET)**:
   - Calculate Heikin-Ashi values
   - Determine trade direction (Bull/Bear)
   - Find options with target deltas
   - Execute trade if premium requirements met
   - Place automatic $0.05 close order

2. **Next Day (Market Hours)**:
   - Monitor for additional trade patterns
   - Execute additional trades if confirmed
   - Monitor all open positions for exit conditions

3. **Continuous**:
   - Track win rates and adjust quantities
   - Log all trade activities
   - Monitor exit conditions with pattern confirmation

## 🚀 Ready to Use

The algorithm is now fully updated according to your specifications and ready for deployment. All tests pass, and the modular structure makes it easy to maintain and extend in the future.

To run the algorithm:
```bash
python main.py
```

To test the components:
```bash
python test_algorithm.py
```
