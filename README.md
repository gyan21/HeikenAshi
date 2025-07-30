# Heikin-Ashi Based Credit Spread Trading Algorithm

## Overview

This algorithm automates the execution and management of credit spread options trades using a combination of Heikin-Ashi candlestick logic, delta-based option selection, and candle pattern-based trade exit rules. It includes dynamic position sizing based on win-rate performance, automated trade placement at the end of the day, optional additional trades the next day, and robust logging and recovery mechanisms.

## Key Features

### 1. Dynamic Trade Quantity Management
- **Default quantity**: 30 contracts per trade
- **Automatic adjustment**: If win rate ≥ 70% for last 10 trades, quantity increases by 10 contracts
- **Configuration**: Quantity settings saved in `trade_quantity_config.json`

### 2. Daily Execution Logic (3:55 PM ET)
#### Heikin-Ashi Calculation
- Computes Heikin-Ashi candle for today using regular OHLC values
- Stores both `dailyCloseHA` (Heikin-Ashi close) and `dailyClosePrice` (actual daily close)

#### Option Selection
- Searches for Call and Put options with delta close to 0.24
- If not found, searches in descending order: 0.23 → 0.22 → 0.21 → 0.20
- Independent search for Call and Put options

#### Trade Direction Logic
```
If dailyClosePrice > dailyCloseHA:
    Enter Bull Credit Spread (Sell Put Spread)
Else:
    Enter Bear Credit Spread (Sell Call Spread)
```

### 3. Trade Specifications
- **Spread width**: 10 points
- **Premium targets**: 
  - Primary: At least $55 per contract (3:55-4:00 PM)
  - Fallback: At least $45 per contract (if needed by 4:00 PM)
- **Auto-close**: $0.05 limit order placed immediately after entry

### 4. Advanced Exit Logic
#### Bull Credit Spread Exit Conditions
Exit only if ALL conditions are met:
1. Stock price falls below previous day's low OR below short strike price
2. Time is 10:00 AM or later
3. 15-minute chart confirms Green-Green-Red pattern

#### Bear Credit Spread Exit Conditions  
Exit only if ALL conditions are met:
1. Stock price rises above previous day's high OR above short strike price
2. Time is 10:00 AM or later
3. 15-minute chart confirms Red-Red-Green pattern

### 5. Additional Trade Opportunities (Next Day)
- **Direction**: Same as previous day's Heikin-Ashi determination
- **Pattern confirmation**:
  - Bull trades: Wait for Red-Red-Green pattern (15-minute chart)
  - Bear trades: Wait for Green-Green-Red pattern (15-minute chart)
- **Premium requirement**: At least $25 per contract
- **Timing**: During market hours (9:30 AM - 3:00 PM ET)

### 6. Comprehensive Trade Logging
Each trade logs the following fields:
- Trade Date
- dailyClosePrice - dailyCloseHA
- Spread Legs (e.g., C620/C630 for call spread with strikes 620 and 630)
- Trade Open Time
- Trade Close Time
- Trade Quantity
- Delta of shorted option/Delta of long option
- Sell Price of Spread
- Buy Price of Spread
- Net P/L
- P/L Label (Profit or Loss)

## File Structure

```
├── main.py                          # Main application entry point
├── config/
│   └── settings.py                  # Configuration parameters
├── utils/
│   ├── ibkr_client.py              # IBKR connection management
│   ├── heikin_ashi.py              # Heikin-Ashi calculations
│   ├── quantity_manager.py         # Trade quantity management
│   ├── delta_option_finder.py      # Delta-based option selection
│   ├── pattern_utils.py            # Pattern detection utilities
│   ├── trade_executor.py           # Trade execution logic
│   ├── trade_monitor.py            # Exit condition monitoring
│   ├── additional_trades.py        # Next-day opportunity scanner
│   ├── logger.py                   # Trade logging utilities
│   └── [other utility files]
└── requirements.txt                 # Python dependencies
```

## Configuration

### Key Settings (config/settings.py)
- `DEFAULT_TRADE_QUANTITY`: Starting quantity (30 contracts)
- `SPREAD_WIDTH`: Spread width in points (10)
- `MIN_PREMIUM_TIER_1`: Primary premium target ($55)
- `MIN_PREMIUM_TIER_2`: Fallback premium target ($45)
- `MIN_PREMIUM_NEXT_DAY`: Next-day trade minimum ($25)
- `DELTA_SEARCH_RANGE`: Delta search order [0.24, 0.23, 0.22, 0.21, 0.20]

## Usage

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure IBKR connection** in `utils/ibkr_client.py`

3. **Run the algorithm**:
   ```bash
   python main.py
   ```

## Algorithm Flow

1. **Market Hours Monitoring**: Continuous monitoring during market hours
2. **3:55 PM Daily Execution**: 
   - Calculate Heikin-Ashi values
   - Determine trade direction
   - Find suitable options
   - Execute trade if premium requirements met
3. **Next Day Additional Opportunities**: 
   - Monitor for pattern confirmations
   - Execute additional trades if conditions met
4. **Exit Monitoring**: 
   - Continuous monitoring of open positions
   - Exit based on price, time, and pattern conditions
5. **Logging**: Comprehensive trade logging throughout

## Risk Management

- **Position sizing**: Automatic adjustment based on performance
- **Premium requirements**: Tiered premium targets ensure profitability
- **Exit rules**: Multiple condition requirements prevent premature exits
- **Pattern confirmation**: Technical analysis confirmation for entries/exits

## Broker Integration

- **Primary broker**: Interactive Brokers (IBKR)
- **API**: ib_insync library for Python
- **Data sources**: Historical and real-time market data via IBKR

## Monitoring and Logging

- **Real-time monitoring**: All open positions tracked continuously
- **Comprehensive logging**: All trades logged with complete details
- **Performance tracking**: Win rate and P/L tracking for quantity adjustments
- **Resumable**: Algorithm can restart and resume monitoring existing positions