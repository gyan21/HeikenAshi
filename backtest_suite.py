"""
Backtest Suite for Option Spread Strategy

- Fetches minute and daily price data using yfinance
- Simulates option Greeks (delta, theta, IV) using Black-Scholes (py_vollib)
- Runs a backtest loop using your entry/exit logic (delta, IV, Heikin Ashi, time window, stop loss, theta diff)
- Outputs a DataFrame of trades and summary stats

Requirements:
    pip install yfinance py_vollib pandas numpy
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, time
from py_vollib.black_scholes.greeks.analytical import delta, theta
from py_vollib.black_scholes.implied_volatility import implied_volatility
from py_vollib.black_scholes import black_scholes

# --- 1. Fetch minute and daily price data ---

def fetch_price_data(symbol, minute_days=7, daily_years=1):
    # Minute data (last 7 days, adjust as needed)
    minute_df = yf.download(symbol, interval="1m", period=f"{minute_days}d")
    minute_df.reset_index(inplace=True)
    minute_df.rename(columns=str.lower, inplace=True)
    # Daily data (last 1 year, adjust as needed)
    daily_df = yf.download(symbol, interval="1d", period=f"{daily_years}y")
    daily_df.reset_index(inplace=True)
    daily_df.rename(columns=str.lower, inplace=True)
    return minute_df, daily_df

# --- 2. Compute Heikin Ashi ---

def compute_heikin_ashi(df):
    ha_df = df.copy().reset_index(drop=True)
    ha_df = ha_df.loc[:, ~ha_df.columns.duplicated()]
    ha_df['ha_close'] = (ha_df['open'] + ha_df['high'] + ha_df['low'] + ha_df['close']) / 4
    ha_df['ha_open'] = ha_df['open'].astype(float)
    for i in range(1, len(ha_df)):
        prev_ha_open = ha_df.loc[i-1, 'ha_open']
        prev_ha_close = ha_df.loc[i-1, 'ha_close']
        ha_df.loc[i, 'ha_open'] = (prev_ha_open + prev_ha_close) / 2
    return ha_df

# --- 3. Simulate Option Greeks ---

def simulate_greeks(row, strike, expiry, option_type='c', r=0.01, iv_assumed=0.25):
    """
    row: a row from minute_df or daily_df
    strike: option strike price
    expiry: datetime object for option expiry
    option_type: 'c' for call, 'p' for put
    r: risk-free rate
    iv_assumed: assumed IV for simulation
    """
    S = row['close']
    K = strike
    t = (expiry - row['Datetime']).total_seconds() / (365 * 24 * 60 * 60)
    if t <= 0:
        return None, None, None
    # Simulate an option price (for demo, use Black-Scholes with fixed IV)
    option_price = black_scholes(option_type, S, K, t, r, iv_assumed)
    # Calculate implied volatility (should return iv_assumed)
    iv = implied_volatility(option_price, S, K, t, r, option_type)
    # Calculate delta and theta
    d = delta(option_type, S, K, t, r, iv)
    th = theta(option_type, S, K, t, r, iv)
    return d, th, iv

# --- 4. Backtest Logic ---

def backtest_strategy(
    minute_df, 
    daily_df, 
    account_value=100000, 
    risk_per_trade=0.02, 
    max_scale=0.05,
    delta_target=0.20, 
    delta_tol=0.03,
    iv_threshold=0.25,
    stop_loss_guard_hour=10,
    spread_width=5,
    check_minutes=[48, 53, 57]
):
    trades = []
    ha_df = compute_heikin_ashi(daily_df)
    # Map date to HA close for fast lookup
    ha_close_map = {row['date']: row['ha_close'] for _, row in ha_df.iterrows()}

    # Loop through each day in minute data
    minute_df['date'] = minute_df['Datetime'].dt.date
    for day, day_df in minute_df.groupby('date'):
        # Only trade between 15:45 and 15:59
        for minute in check_minutes:
            dt = datetime.combine(day, time(15, minute))
            row = day_df[day_df['Datetime'] == dt]
            if row.empty:
                continue
            row = row.iloc[0]
            regular_close = row['close']
            ha_close = ha_close_map.get(day, regular_close)
            expiry = dt + timedelta(days=7)  # Example: next week's expiry

            # Simulate option chain for this minute (3 strikes: ATM, ATM-5, ATM+5)
            strikes = [round(regular_close - spread_width), round(regular_close), round(regular_close + spread_width)]
            option_chain = []
            for strike in strikes:
                for right in ['p', 'c']:
                    d, th, iv = simulate_greeks(row, strike, expiry, option_type=right, iv_assumed=0.28)
                    option_chain.append({
                        'strike': strike,
                        'right': right,
                        'delta': d,
                        'theta': th,
                        'iv': iv
                    })
            option_chain_df = pd.DataFrame(option_chain)

            # Entry logic
            if regular_close > ha_close:
                # Bull case: Sell PUT spread
                puts = option_chain_df[option_chain_df['right'] == 'p']
                puts['delta_diff'] = (puts['delta'] - (-delta_target)).abs()
                candidate = puts.loc[puts['delta_diff'].idxmin()]
                if abs(candidate['delta'] - (-delta_target)) <= delta_tol and candidate['iv'] > iv_threshold:
                    sell_strike = candidate['strike']
                    buy_strike = sell_strike - spread_width
                    # Simulate entry
                    entry_price = candidate['iv']  # Use IV as a proxy for premium
                    # Simulate exit: theta diff or stop loss after 10am
                    # For demo, exit at next day's open or if 1-min close < sell_strike after 10am
                    exit_row = day_df[(day_df['Datetime'] > dt) & (day_df['Datetime'].dt.hour >= stop_loss_guard_hour) & (day_df['close'] < sell_strike)]
                    if not exit_row.empty:
                        exit_time = exit_row.iloc[0]['Datetime']
                        exit_price = exit_row.iloc[0]['close']
                        reason = "1-min close below short strike"
                    else:
                        # Exit at next day's open
                        next_day = day + timedelta(days=1)
                        next_open_row = minute_df[(minute_df['date'] == next_day) & (minute_df['Datetime'].dt.hour == 9) & (minute_df['Datetime'].dt.minute == 30)]
                        if not next_open_row.empty:
                            exit_time = next_open_row.iloc[0]['Datetime']
                            exit_price = next_open_row.iloc[0]['open']
                            reason = "Next day open"
                        else:
                            exit_time = dt + timedelta(days=1)
                            exit_price = entry_price - 0.05  # Simulate
                            reason = "Simulated exit"
                    profit = exit_price - entry_price
                    trades.append({
                        'entry_time': dt,
                        'exit_time': exit_time,
                        'type': 'bull',
                        'sell_strike': sell_strike,
                        'buy_strike': buy_strike,
                        'entry_price': entry_price,
                        'exit_price': exit_price,
                        'profit': profit,
                        'reason': reason
                    })
            elif regular_close < ha_close:
                # Bear case: Sell CALL spread
                calls = option_chain_df[option_chain_df['right'] == 'c']
                calls['delta_diff'] = (calls['delta'] - delta_target).abs()
                candidate = calls.loc[calls['delta_diff'].idxmin()]
                if abs(candidate['delta'] - delta_target) <= delta_tol and candidate['iv'] > iv_threshold:
                    sell_strike = candidate['strike']
                    buy_strike = sell_strike + spread_width
                    entry_price = candidate['iv']
                    exit_row = day_df[(day_df['Datetime'] > dt) & (day_df['Datetime'].dt.hour >= stop_loss_guard_hour) & (day_df['close'] > sell_strike)]
                    if not exit_row.empty:
                        exit_time = exit_row.iloc[0]['Datetime']
                        exit_price = exit_row.iloc[0]['close']
                        reason = "1-min close above short strike"
                    else:
                        next_day = day + timedelta(days=1)
                        next_open_row = minute_df[(minute_df['date'] == next_day) & (minute_df['Datetime'].dt.hour == 9) & (minute_df['Datetime'].dt.minute == 30)]
                        if not next_open_row.empty:
                            exit_time = next_open_row.iloc[0]['Datetime']
                            exit_price = next_open_row.iloc[0]['open']
                            reason = "Next day open"
                        else:
                            exit_time = dt + timedelta(days=1)
                            exit_price = entry_price - 0.05
                            reason = "Simulated exit"
                    profit = entry_price - exit_price
                    trades.append({
                        'entry_time': dt,
                        'exit_time': exit_time,
                        'type': 'bear',
                        'sell_strike': sell_strike,
                        'buy_strike': buy_strike,
                        'entry_price': entry_price,
                        'exit_price': exit_price,
                        'profit': profit,
                        'reason': reason
                    })
    return pd.DataFrame(trades)

# --- 5. Run Backtest ---

if __name__ == "__main__":
    symbol = "SPY"
    minute_df, daily_df = fetch_price_data(symbol)
    trades_df = backtest_strategy(minute_df, daily_df)
    print(trades_df)
    print("\nSummary:")
    print(trades_df.groupby('type')['profit'].agg(['count', 'mean', 'sum']))
    trades_df.to_csv("backtest_results.csv", index=False)