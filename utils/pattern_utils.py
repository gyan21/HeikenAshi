from datetime import datetime, timedelta
import asyncio
from ib_insync import Stock

def determine_candle_color(bar):
    """Determine if a candle is red or green"""
    if bar.close > bar.open:
        return "green"
    elif bar.close < bar.open:
        return "red"
    else:
        return "doji"  # Equal open and close

async def get_15min_pattern(ib, symbol, num_candles=3):
    """
    Get the last num_candles 15-minute candles and return their color pattern
    Returns: list of colors ["red", "green", "red"] etc.
    """
    try:
        contract = Stock(symbol, 'SMART', 'USD')
        await ib.qualifyContractsAsync(contract)
        
        # Get 15-minute bars
        bars = await ib.reqHistoricalDataAsync(
            contract,
            endDateTime='',
            durationStr='2 D',  # Get enough data
            barSizeSetting='15 mins',
            whatToShow='TRADES',
            useRTH=True,
            formatDate=1
        )
        
        if not bars or len(bars) < num_candles:
            print(f"Insufficient 15-minute bars: {len(bars) if bars else 0}")
            return []
        
        # Get the last num_candles and determine their colors
        recent_bars = bars[-num_candles:]
        pattern = [determine_candle_color(bar) for bar in recent_bars]
        
        return pattern
    
    except Exception as e:
        print(f"Error getting 15-minute pattern: {e}")
        return []

async def check_exit_pattern(ib, symbol, trade_type):
    """
    Check if the exit pattern is met for the given trade type
    
    Bull exit: GGR (Green-Green-Red)
    Bear exit: RRG (Red-Red-Green)
    """
    pattern = await get_15min_pattern(ib, symbol, 3)
    
    if not pattern or len(pattern) < 3:
        return False
    
    if trade_type.lower() == "bull":
        # Bull exit pattern: Green-Green-Red
        return pattern == ["green", "green", "red"]
    elif trade_type.lower() == "bear":
        # Bear exit pattern: Red-Red-Green
        return pattern == ["red", "red", "green"]
    
    return False

async def check_additional_entry_pattern(ib, symbol, trade_direction, include_previous_day=True):
    """
    Check if the additional entry pattern is met for next-day trades
    
    Bull trades: wait for RRG (Red-Red-Green) pattern
    Bear trades: wait for GGR (Green-Green-Red) pattern
    
    If include_previous_day is True, consider the last 15-minute candle from previous day
    """
    try:
        if include_previous_day:
            # Get more data to include previous day's last candle
            pattern = await get_15min_pattern(ib, symbol, 3)
        else:
            # Only current day candles
            pattern = await get_15min_pattern(ib, symbol, 2)
        
        if not pattern:
            return False
        
        if trade_direction.lower() == "bull":
            # Bull additional entry: RRG (Red-Red-Green)
            if len(pattern) >= 3:
                return pattern[-3:] == ["red", "red", "green"]
            elif len(pattern) == 2:
                return pattern == ["red", "green"]  # Partial pattern
        elif trade_direction.lower() == "bear":
            # Bear additional entry: GGR (Green-Green-Red)
            if len(pattern) >= 3:
                return pattern[-3:] == ["green", "green", "red"]
            elif len(pattern) == 2:
                return pattern == ["green", "red"]  # Partial pattern
        
        return False
    
    except Exception as e:
        print(f"Error checking additional entry pattern: {e}")
        return False

async def get_previous_day_data(ib, symbol):
    """Get previous day's high, low, and close prices"""
    try:
        contract = Stock(symbol, 'SMART', 'USD')
        await ib.qualifyContractsAsync(contract)
        
        bars = await ib.reqHistoricalDataAsync(
            contract,
            endDateTime='',
            durationStr='3 D',  # Get enough data
            barSizeSetting='1 day',
            whatToShow='TRADES',
            useRTH=True,
            formatDate=1
        )
        
        if not bars or len(bars) < 2:
            print("Insufficient daily bars for previous day data")
            return None
        
        previous_day = bars[-2]  # Second to last is previous day
        return {
            'high': previous_day.high,
            'low': previous_day.low,
            'close': previous_day.close
        }
    
    except Exception as e:
        print(f"Error getting previous day data: {e}")
        return None
