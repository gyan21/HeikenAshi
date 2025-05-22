import pandas as pd
import numpy as np
from datetime import datetime, timedelta, time as dtime
from ib_insync import IB, Stock, util

# ---- IBKR DATA FETCH ----

def fetch_price_data_ibkr(symbol='SPY', minute_days=7, daily_years=1):
    ib = IB()
    ib.connect('127.0.0.1', 7497, clientId=1)
    contract = Stock(symbol, 'SMART', 'USD')

    # Minute data (last 7 days, IBKR limit)
    end_dt = ''
    duration = f'{minute_days} D'
    bars = ib.reqHistoricalData(
        contract,
        endDateTime=end_dt,
        durationStr=duration,
        barSizeSetting='1 min',
        whatToShow='TRADES',
        useRTH=False,
        formatDate=1
    )
    minute_df = util.df(bars)
    minute_df.rename(columns=str.lower, inplace=True)
    minute_df['date'] = pd.to_datetime(minute_df['date']).dt.date if 'date' in minute_df.columns else pd.to_datetime(minute_df['datetime']).dt.date

    # Daily data (last 1 year)
    bars_daily = ib.reqHistoricalData(
        contract,
        endDateTime='',
        durationStr=f'{daily_years} Y',
        barSizeSetting='1 day',
        whatToShow='TRADES',
        useRTH=False,
        formatDate=1
    )
    daily_df = util.df(bars_daily)
    daily_df.rename(columns=str.lower, inplace=True)
    daily_df['date'] = pd.to_datetime(daily_df['date']).dt.date if 'date' in daily_df.columns else pd.to_datetime(daily_df['datetime']).dt.date

    ib.disconnect()
    return minute_df, daily_df

# ---- HEIKIN ASHI HELPER ----

def compute_heikin_ashi(df):
    ha_df = df.copy().reset_index(drop=True)
    ha_df['ha_close'] = (ha_df['open'] + ha_df['high'] + ha_df['low'] + ha_df['close']) / 4
    ha_df['ha_open'] = ha_df['open']
    for i in range(1, len(ha_df)):
        ha_df.loc[i, 'ha_open'] = (ha_df.loc[i-1, 'ha_open'] + ha_df.loc[i-1, 'ha_close']) / 2
    ha_df['ha_high'] = ha_df[['high', 'ha_open', 'ha_close']].max(axis=1)
    ha_df['ha_low'] = ha_df[['low', 'ha_open', 'ha_close']].min(axis=1)
    return ha_df

# ---- SIMULATION HELPERS ----

def simulate_option_data(underlying_price, strike, option_type):
    """
    Simulate option delta and price for demo purposes.
    """
    # Simulate delta in [0.20, 0.30] for puts, [-0.30, -0.20] for calls
    if option_type == 'P':
        delta = np.round(np.random.uniform(0.20, 0.30), 3)
    else:
        delta = -np.round(np.random.uniform(0.20, 0.30), 3)
    # Simulate price: ATM option price + some randomness
    price = max(abs(underlying_price - strike), 0) + np.random.uniform(0.8, 1.5)
    return delta, price

def simulate_next_day_spread_price(entry_price):
    """
    Simulate next day spread price for demo purposes.
    """
    # Randomly decrease the spread price, but not below 0.01
    return max(entry_price - np.random.uniform(0, 0.5), 0.01)

def get_trade_type(daily_close, ha_close):
    """
    Determine trade type: 'bull' if daily_close > ha_close, else 'bear'.
    """
    return 'bull' if daily_close > ha_close else 'bear'

def get_spread_direction(trade_type):
    """
    Return 1 for bull (put spread), -1 for bear (call spread).
    """
    return 1 if trade_type == 'bull' else -1

# ---- MAIN ANALYSIS FUNCTION ----

def analyze_and_generate_report(minute_df, daily_df, ha_df, output_excel='analysis_report.xlsx'):
    results = []
    last_30_days = sorted(daily_df['date'].unique())[-30:]

    for day in last_30_days:
        day_minutes = minute_df[minute_df['date'] == day]
        daily_close = daily_df.loc[daily_df['date'] == day, 'close'].values[0]
        ha_close = ha_df.loc[ha_df['date'] == day, 'ha_close'].values[0]
        trade_type = get_trade_type(daily_close, ha_close)
        spread_direction = get_spread_direction(trade_type)

        for minute in range(15*60+45, 16*60):  # 15:45 to 16:00
            dt = datetime.combine(day, dtime(minute//60, minute%60))
            row = day_minutes[day_minutes['date'] == day_minutes['date'].iloc[0]]
            row = row[row['datetime'].dt.time == dt.time()] if 'datetime' in row.columns else row
            if row.empty:
                continue
            underlying_price = row['close'].values[0]

            # Simulate option selection
            sell_strike = round(underlying_price)
            buy_strike = sell_strike - 5 * spread_direction
            option_type = 'P' if trade_type == 'bull' else 'C'

            # Simulate sell option (delta 0.20-0.30)
            delta, sell_price = simulate_option_data(underlying_price, sell_strike, option_type)
            # Simulate buy option (same type, 5 points away)
            _, buy_price = simulate_option_data(underlying_price, buy_strike, option_type)
            spread_entry_price = abs(sell_price - buy_price)

            # Simulate next day
            next_day = day + timedelta(days=1)
            next_day_row = minute_df[(minute_df['date'] == next_day)]
            next_day_row = next_day_row[next_day_row['datetime'].dt.time == dt.time()] if 'datetime' in next_day_row.columns else next_day_row
            if not next_day_row.empty:
                next_underlying = next_day_row['close'].values[0]
            else:
                next_underlying = underlying_price  # fallback

            spread_exit_price = simulate_next_day_spread_price(spread_entry_price)

            # Exit logic
            exit_reason = ''
            profit = spread_entry_price - spread_exit_price
            if spread_exit_price <= 0.05:
                exit_reason = 'Spread <= 0.05'
            elif (trade_type == 'bull' and next_underlying <= sell_strike) or (trade_type == 'bear' and next_underlying >= sell_strike):
                exit_reason = 'SPY crossed sell strike'
            else:
                exit_reason = 'Hold'

            results.append({
                'date': day,
                'minute': dt.time(),
                'daily_close': daily_close,
                'ha_close': ha_close,
                'close_minus_ha': daily_close - ha_close,
                'trade_type': trade_type,
                'sell_strike': sell_strike,
                'buy_strike': buy_strike,
                'delta': delta,
                'spread_entry_price': spread_entry_price,
                'spread_exit_price': spread_exit_price,
                'next_day_underlying': next_underlying,
                'exit_reason': exit_reason,
                'profit': profit
            })

    df = pd.DataFrame(results)
    df.to_excel(output_excel, index=False)
    print(f"Analysis report saved to {output_excel}")

# ---- FETCH AND PREPARE DATA ----

print("Fetching SPY data from IBKR...")
minute_df, daily_df = fetch_price_data_ibkr('SPY', minute_days=7, daily_years=1)

# Ensure datetime columns
if 'datetime' not in minute_df.columns:
    minute_df['datetime'] = pd.to_datetime(minute_df['date'])
else:
    minute_df['datetime'] = pd.to_datetime(minute_df['datetime'])
minute_df['date'] = pd.to_datetime(minute_df['date']).dt.date
daily_df['date'] = pd.to_datetime(daily_df['date']).dt.date

# ---- COMPUTE HEIKIN ASHI ----

ha_df = compute_heikin_ashi(daily_df)
ha_df = ha_df[['date', 'ha_close']]

# ---- RUN ANALYSIS ----

analyze_and_generate_report(
    minute_df=minute_df,
    daily_df=daily_df,
    ha_df=ha_df,
    output_excel='analysis_report.xlsx'
)

print("Done! Check analysis_report.xlsx for your results.")