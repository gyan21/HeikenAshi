import pandas as pd
import numpy as np
from datetime import datetime, timedelta, time as dtime

# ---- LOAD AND PREPARE DATA ----

# Load daily data
daily_df = pd.read_csv(
    r'c:\Projects\Personal\Investment\tradeXSecondVer\Logs\SPY-LOG\30D\priceBars1daySPY.csv'
)
daily_df.rename(columns={
    'Time': 'date',
    'Open': 'open',
    'Close': 'close',
    'High': 'high',
    'Low': 'low',
    'Volume': 'volume'
}, inplace=True)
# Parse date
daily_df['date'] = pd.to_datetime(daily_df['date'].str[:8], format='%Y%m%d').dt.date

# Load minute data
minute_df = pd.read_csv(
    r'c:\Projects\Personal\Investment\tradeXSecondVer\Logs\SPY-LOG\30D\priceBars1minSPY.csv'
)
minute_df.rename(columns={
    'Time': 'datetime',
    'Open': 'open',
    'Close': 'close',
    'High': 'high',
    'Low': 'low',
    'Volume': 'volume'
}, inplace=True)
# Parse datetime and extract date
minute_df['datetime'] = pd.to_datetime(
    minute_df['datetime'].str.split().str[0] + ' ' + minute_df['datetime'].str.split().str[1],
    format='%Y%m%d %H:%M:%S'
)
minute_df['date'] = minute_df['datetime'].dt.date

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
    if option_type == 'P':
        delta = np.round(np.random.uniform(0.20, 0.30), 3)
    else:
        delta = -np.round(np.random.uniform(0.20, 0.30), 3)
    price = max(abs(underlying_price - strike), 0) + np.random.uniform(0.8, 1.5)
    return delta, price

def simulate_next_day_spread_price(entry_price):
    return max(entry_price - np.random.uniform(0, 0.5), 0.01)

def get_trade_type(daily_close, ha_close):
    return 'bull' if daily_close > ha_close else 'bear'

def get_spread_direction(trade_type):
    return 1 if trade_type == 'bull' else -1

# ---- MAIN ANALYSIS FUNCTION ----

def analyze_and_generate_report(minute_df, daily_df, ha_df, output_excel='analysis_report.xlsx'):
    results = []
    available_days = sorted(minute_df['date'].unique())

    for day in available_days:
        day_minutes = minute_df[minute_df['date'] == day]
        if day_minutes.empty:
            continue
        daily_row = daily_df[daily_df['date'] == day]
        if daily_row.empty:
            continue
        daily_close = daily_row['close'].values[0]
        ha_close = ha_df.loc[ha_df['date'] == day, 'ha_close'].values[0]
        trade_type = get_trade_type(daily_close, ha_close)
        spread_direction = get_spread_direction(trade_type)

        for minute in range(15*60+45, 16*60):  # 15:45 to 16:00
            dt = datetime.combine(day, dtime(minute//60, minute%60))
            candidates = day_minutes[day_minutes['datetime'] <= dt]
            if candidates.empty:
                continue
            row = candidates.iloc[-1]
            underlying_price = row['close']

            # ---- NEW: Try a range of strikes around the underlying price ----
            # For example, try strikes from (underlying-20) to (underlying+20) in steps of 1
            for strike_offset in range(-20, 21):
                sell_strike = round(underlying_price) + strike_offset
                buy_strike = sell_strike - 5 * spread_direction
                option_type = 'P' if trade_type == 'bull' else 'C'

                # Simulate sell option (delta 0.20-0.30)
                delta, sell_price = simulate_option_data(underlying_price, sell_strike, option_type)
                if 0.20 <= abs(delta) <= 0.30:
                    # Simulate buy option (same type, 5 points away)
                    _, buy_price = simulate_option_data(underlying_price, buy_strike, option_type)
                    spread_entry_price = abs(sell_price - buy_price)

                    # Simulate next day
                    next_day = day + timedelta(days=1)
                    next_day_minutes = minute_df[minute_df['date'] == next_day]
                    candidates_next = next_day_minutes[next_day_minutes['datetime'] <= dt]
                    if not candidates_next.empty:
                        next_underlying = candidates_next.iloc[-1]['close']
                    else:
                        next_underlying = underlying_price

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