import pandas as pd
import numpy as np
from datetime import datetime, timedelta, time as dt_time
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import warnings
warnings.filterwarnings('ignore')

# IBKR data fetching
from ib_insync import IB, Stock, util

class CompleteHeikenAshiBacktester:
    def __init__(self, config_path="config/heikenashi_config.json"):
        self.config = self.load_config(config_path)
        self.trades = []
        self.daily_equity = []
        self.performance_metrics = {}
        
    def load_config(self, config_path):
        """Load trading configuration"""
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"❌ Config file not found: {config_path}")
            # Return default config
            return {
                "data_settings": {
                    "symbol": "SPY",
                    "exchange": "ARCA", 
                    "currency": "USD",
                    "days_to_fetch": 30,
                    "ibkr_host": "127.0.0.1",
                    "ibkr_port": 7497,
                    "client_id": 1
                },
                "backtest_settings": {
                    "initial_capital": 100000,
                    "commission_per_trade": 2.0
                },
                "trade_settings": {
                    "main_trade_qty": 30,
                    "main_trade_credit": 45,
                    "additional_trade_qty": 30,
                    "additional_trade_1_credit": 45,
                    "additional_trade_2_credit": 25,
                    "spread_points": 3,
                    "increment_qty": 10,
                    "win_rate_window": 10,
                    "win_rate_threshold": 0.7
                },
                "output_settings": {
                    "excel_file": "results/trade_log.xlsx",
                    "csv_15m": "data/spy_15m.csv",
                    "csv_5m": "data/spy_5m.csv"
                }
            }

    def fetch_ibkr_data(self, symbol, exchange, currency, bar_size, days, save_path):
        """Fetch real historical data from TWS/IBKR"""
        print(f"🔄 Fetching {bar_size} data for {symbol} (last {days} days)...")
        
        try:
            # Connect to TWS
            ib = IB()
            ib.connect(
                host=self.config['data_settings']['ibkr_host'],
                port=self.config['data_settings']['ibkr_port'],
                clientId=self.config['data_settings']['client_id']
            )
            print(f"✅ Connected to TWS")
            
            # Create contract
            contract = Stock(symbol, exchange, currency)
            
            # Request historical data
            bars = ib.reqHistoricalData(
                contract,
                endDateTime='',
                durationStr=f'{days} D',
                barSizeSetting=bar_size,
                whatToShow='TRADES',
                useRTH=True,  # Regular trading hours only
                formatDate=1
            )
            
            if not bars:
                print(f"❌ No data received for {symbol}")
                ib.disconnect()
                return None
            
            # Convert to DataFrame
            df = util.df(bars)
            
            # Rename columns to match our format
            df.rename(columns={
                'date': 'Datetime', 
                'open': 'Open', 
                'high': 'High', 
                'low': 'Low', 
                'close': 'Close', 
                'volume': 'Volume'
            }, inplace=True)
            
            # Ensure datetime column
            df['Datetime'] = pd.to_datetime(df['Datetime'])
            
            # Save to CSV
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(save_path, index=False)
            
            print(f"✅ Saved {len(df)} {bar_size} bars to {save_path}")
            print(f"   📅 Date range: {df['Datetime'].min()} to {df['Datetime'].max()}")
            
            ib.disconnect()
            return df
            
        except Exception as e:
            print(f"❌ Error fetching IBKR data: {e}")
            print("   💡 Make sure TWS/IB Gateway is running and connected")
            try:
                ib.disconnect()
            except:
                pass
            return None

    def load_csv_data(self, csv_path):
        """Load data from CSV file"""
        try:
            df = pd.read_csv(csv_path)
            df['Datetime'] = pd.to_datetime(df['Datetime'])
            return df
        except Exception as e:
            print(f"❌ Error loading CSV {csv_path}: {e}")
            return None

    def calculate_heiken_ashi(self, df):  # Fixed spelling
        """Calculate Heiken-Ashi values"""
        ha_df = df.copy()
        
        # Calculate HA values
        ha_close = (ha_df['Open'] + ha_df['High'] + ha_df['Low'] + ha_df['Close']) / 4
        ha_open = np.zeros(len(ha_df))
        ha_open[0] = (ha_df['Open'].iloc[0] + ha_df['Close'].iloc[0]) / 2
        
        for i in range(1, len(ha_df)):
            ha_open[i] = (ha_open[i-1] + ha_close.iloc[i-1]) / 2
        
        ha_high = np.maximum(ha_df['High'], np.maximum(ha_open, ha_close))
        ha_low = np.minimum(ha_df['Low'], np.minimum(ha_open, ha_close))
        
        ha_df['HA_Open'] = ha_open
        ha_df['HA_High'] = ha_high
        ha_df['HA_Low'] = ha_low
        ha_df['HA_Close'] = ha_close
        
        return ha_df

    def calculate_macd(self, df, fast=12, slow=26, signal=9):
        """Calculate MACD indicator"""
        ema_fast = df['Close'].ewm(span=fast, adjust=False).mean()
        ema_slow = df['Close'].ewm(span=slow, adjust=False).mean()
        macd = ema_fast - ema_slow
        macd_signal = macd.ewm(span=signal, adjust=False).mean()
        macd_diff = macd - macd_signal
        
        df['MACD'] = macd
        df['MACD_Signal'] = macd_signal
        df['MACD_Diff'] = macd_diff
        
        return df

    def find_candle_pattern(self, df, pattern_type):
        """Find Red-Red-Green or Green-Green-Red patterns"""
        colors = []
        for i in range(len(df)):
            color = "green" if df.iloc[i]['Close'] > df.iloc[i]['Open'] else "red"
            colors.append(color)
        
        pattern_indices = []
        
        if pattern_type == "bull":  # Look for Red-Red-Green
            target_pattern = ["red", "red", "green"]
        else:  # Look for Green-Green-Red
            target_pattern = ["green", "green", "red"]
        
        for i in range(len(colors) - 2):
            if colors[i:i+3] == target_pattern:
                pattern_indices.append(i+2)  # Return index of the final candle
        
        return pattern_indices

    def get_1550_candle(self, day_df):
        """Get the 15:50 candle from a day's data"""
        target_time = dt_time(15, 50)
        candle_1550 = day_df[day_df['Datetime'].dt.time == target_time]
        
        if candle_1550.empty:
            # If 15:50 not found, get the closest before 16:00
            before_close = day_df[day_df['Datetime'].dt.time <= dt_time(15, 55)]
            if not before_close.empty:
                return before_close.iloc[-1]
        else:
            return candle_1550.iloc[0]
        
        return None

    def get_1545_macd(self, day_df):
        """Get MACD at 15:45 candle"""
        target_time = dt_time(15, 45)
        candle_1545 = day_df[day_df['Datetime'].dt.time == target_time]
        
        if not candle_1545.empty:
            return candle_1545.iloc[0]['MACD_Diff']
        else:
            # Get closest available
            before_1545 = day_df[day_df['Datetime'].dt.time <= dt_time(15, 50)]
            if not before_1545.empty:
                return before_1545.iloc[-1]['MACD_Diff']
        
        return 0.0

    def fetch_all_data(self):
        """Fetch both 15min and 5min data from TWS"""
        symbol = self.config['data_settings']['symbol']
        exchange = self.config['data_settings']['exchange']
        currency = self.config['data_settings']['currency']
        days = self.config['data_settings']['days_to_fetch']
        
        # Fetch 15-minute data
        df_15m = self.fetch_ibkr_data(
            symbol=symbol,
            exchange=exchange, 
            currency=currency,
            bar_size="15 mins",
            days=days,
            save_path=self.config['output_settings']['csv_15m']
        )
        
        # Wait a moment and use different client ID for 5min data
        import time
        time.sleep(2)
        
        # Temporarily change client ID for second connection
        original_client_id = self.config['data_settings']['client_id']
        self.config['data_settings']['client_id'] = original_client_id + 1
        
        # Fetch 5-minute data
        df_5m = self.fetch_ibkr_data(
            symbol=symbol,
            exchange=exchange,
            currency=currency, 
            bar_size="5 mins",
            days=days,
            save_path=self.config['output_settings']['csv_5m']
        )
        
        # Restore original client ID
        self.config['data_settings']['client_id'] = original_client_id
        
        return df_15m, df_5m

    def calculate_heiken_ashi_daily(self, df_15m, df_5m):
        """
        Calculate Heiken-Ashi using:
        - Daily Open, High, Low from 15min data
        - Close price from 5min 15:50 candle
        """
        # Group 15min data by date to get daily OHLV
        df_15m['Date'] = df_15m['Datetime'].dt.date
        daily_ohlv = df_15m.groupby('Date').agg({
            'Open': 'first',    # Day's opening price
            'High': 'max',      # Day's highest price
            'Low': 'min',       # Day's lowest price
            'Close': 'last'     # This will be replaced with 5min 15:50 close
        }).reset_index()
        
        # Group 5min data by date and get 15:50 close price
        df_5m['Date'] = df_5m['Datetime'].dt.date
        df_5m['Time'] = df_5m['Datetime'].dt.time
        
        # Get 15:50 candle close price for each day
        target_time = dt_time(15, 50)
        closes_1550 = []
        
        for date in daily_ohlv['Date']:
            day_5m = df_5m[df_5m['Date'] == date]
            candle_1550 = day_5m[day_5m['Time'] == target_time]
            
            if not candle_1550.empty:
                closes_1550.append(candle_1550.iloc[0]['Close'])
            else:
                # Fallback to closest time before 16:00
                before_close = day_5m[day_5m['Time'] <= dt_time(15, 55)]
                if not before_close.empty:
                    closes_1550.append(before_close.iloc[-1]['Close'])
                else:
                    # Use daily close as fallback
                    closes_1550.append(daily_ohlv[daily_ohlv['Date'] == date]['Close'].iloc[0])
        
        # Replace daily close with 15:50 close from 5min data
        daily_ohlv['Close_1550'] = closes_1550
        
        # Calculate Heiken-Ashi using daily OHLC with 15:50 close
        ha_data = []
        
        for i, row in daily_ohlv.iterrows():
            day_open = row['Open']
            day_high = row['High'] 
            day_low = row['Low']
            close_1550 = row['Close_1550']  # This is from 5min 15:50 candle
            
            # HA Close = (O + H + L + C) / 4
            ha_close = (day_open + day_high + day_low + close_1550) / 4
            
            if i == 0:
                # First day: HA Open = (Open + Close) / 2
                ha_open = (day_open + close_1550) / 2
            else:
                # Subsequent days: HA Open = (Previous HA Open + Previous HA Close) / 2
                prev_ha = ha_data[i-1]
                ha_open = (prev_ha['HA_Open'] + prev_ha['HA_Close']) / 2
            
            # HA High = max(High, HA Open, HA Close)
            ha_high = max(day_high, ha_open, ha_close)
            
            # HA Low = min(Low, HA Open, HA Close)
            ha_low = min(day_low, ha_open, ha_close)
            
            ha_data.append({
                'Date': row['Date'],
                'Day_Open': day_open,
                'Day_High': day_high,
                'Day_Low': day_low,
                'Close_1550': close_1550,  # 5min 15:50 close
                'HA_Open': ha_open,
                'HA_High': ha_high,
                'HA_Low': ha_low,
                'HA_Close': ha_close
            })
        
        return pd.DataFrame(ha_data)

    def run_backtest(self):
        """Run the complete Heiken Ashi backtest"""
        print("🚀 Starting Heiken Ashi Strategy Backtest...")
        
        # Load or fetch 15min and 5min data
        csv_15m = self.config['output_settings']['csv_15m']
        csv_5m = self.config['output_settings']['csv_5m']
        
        df_15m = self.load_csv_data(csv_15m)
        df_5m = self.load_csv_data(csv_5m)
        
        # If no data exists, fetch from TWS
        if df_15m is None or df_5m is None:
            print("📡 No existing data found. Fetching from TWS...")
            df_15m, df_5m = self.fetch_all_data()
            
            if df_15m is None or df_5m is None:
                print("❌ Failed to fetch data from TWS")
                return None
        else:
            print(f"✅ Loaded existing data: {len(df_15m)} 15min bars, {len(df_5m)} 5min bars")
        
        # Calculate MACD on 15min data
        print("🔢 Calculating MACD indicators...")
        df_15m = self.calculate_macd(df_15m)
        
        # Calculate Heiken-Ashi using daily OHLC and 5min 15:50 close
        print("🔢 Calculating Heiken Ashi (Daily OHLC + 5min 15:50 close)...")
        ha_daily = self.calculate_heiken_ashi_daily(df_15m, df_5m)
        
        print(f"📅 Processing {len(ha_daily)} trading days...")
        
        # Initialize tracking variables
        account_value = self.config['backtest_settings']['initial_capital']
        trade_qty = self.config['trade_settings']['main_trade_qty']
        win_count = 0
        total_count = 0
        
        # Main backtest loop - process pairs of days
        for i in range(len(ha_daily) - 1):
            day1_data = ha_daily.iloc[i]
            day2_data = ha_daily.iloc[i + 1]
            
            day1_date = day1_data['Date']
            day2_date = day2_data['Date']
            
            day_close_1550 = day1_data['Close_1550']  # 5min 15:50 close on Day 1
            ha_close = day1_data['HA_Close']          # HA close calculated from daily OHLC
            
            # Get MACD from 15min data at 15:45 on Day 1
            day1_15m = df_15m[df_15m['Datetime'].dt.date == day1_date]
            macd_diff = self.get_1545_macd(day1_15m)
            
            # *** DETERMINE TRADE DIRECTION at 15:55 on Day 1 ***
            if day_close_1550 > ha_close:
                direction = "bull"
                price_main_trade = int(day_close_1550) - self.config['trade_settings']['spread_points']
                credit_main = self.config['trade_settings']['main_trade_credit']
            else:
                direction = "bear"
                price_main_trade = int(day_close_1550) + self.config['trade_settings']['spread_points']
                credit_main = self.config['trade_settings']['main_trade_credit']
            
            print(f"📅 {day1_date}: {direction.upper()} signal (Close:{day_close_1550:.2f} vs HA:{ha_close:.2f})")
            
            # *** LOOK FOR ADDITIONAL TRADES on Day 2 based on Day 1's direction ***
            additional_trades = []
            day2_15m = df_15m[df_15m['Datetime'].dt.date == day2_date].reset_index(drop=True)
            
            if len(day2_15m) > 0:
                if direction == "bull":
                    # Day 1 was BULL, look for Red-Red-Green pattern on Day 2
                    pattern_indices = self.find_candle_pattern(day2_15m, "bull")
                    print(f"   🔍 Looking for Red-Red-Green pattern on {day2_date}: Found {len(pattern_indices)} patterns")
                    
                if pattern_indices:
                    for idx in pattern_indices:
                        if direction == "bull":
                            green_candle = day2_15m.iloc[idx]
                            additional_strike = int(green_candle['Close']) - self.config['trade_settings']['spread_points']
                            pattern_time = green_candle['Datetime'].time()
                            
                            # Check gap condition first
                            prev_day_low = day1_data['Day_Low']
                            day2_open = day2_15m.iloc[0]['Open']
                            
                            if day2_open > prev_day_low:  # No gap down
                                # Only create ONE additional trade - execute 15 minutes after pattern
                                pattern_datetime = green_candle['Datetime']
                                trade_datetime = pattern_datetime + timedelta(minutes=15)
                                trade_time = trade_datetime.time()
                                
                                additional_trades.append({
                                    'type': 'additional_1',
                                    'strike': additional_strike,
                                    'credit': self.config['trade_settings']['additional_trade_1_credit'],
                                    'candle_time': trade_time,  # Execute 15 minutes after pattern
                                    'pattern_candle': 'green',
                                    'direction': direction,
                                    'trade_date': day2_date,
                                    'pattern_time': pattern_time  # For reference
                                })
                                
                                print(f"   🎯 Added bull trade at {trade_time} (15min after {pattern_time} RRG pattern)")
                        
                        elif direction == "bear":
                            red_candle = day2_15m.iloc[idx]
                            additional_strike = int(red_candle['Close']) + self.config['trade_settings']['spread_points']
                            pattern_time = red_candle['Datetime'].time()
                            
                            # Check gap condition first
                            prev_day_high = day1_data['Day_High']
                            day2_open = day2_15m.iloc[0]['Open']
                            
                            if day2_open < prev_day_high:  # No gap up
                                # Only create ONE additional trade - execute 15 minutes after pattern
                                pattern_datetime = red_candle['Datetime']
                                trade_datetime = pattern_datetime + timedelta(minutes=15)
                                trade_time = trade_datetime.time()
                                
                                additional_trades.append({
                                    'type': 'additional_1',
                                    'strike': additional_strike,
                                    'credit': self.config['trade_settings']['additional_trade_1_credit'],
                                    'candle_time': trade_time,  # Execute 15 minutes after pattern
                                    'pattern_candle': 'red',
                                    'direction': direction,
                                    'trade_date': day2_date,
                                    'pattern_time': pattern_time  # For reference
                                })
                                
                                print(f"   🎯 Added bear trade at {trade_time} (15min after {pattern_time} GGR pattern)")
                        
                        break  # Take first pattern only
                
                if additional_trades:
                    print(f"   🎯 Found {len(additional_trades)} additional {direction} trades on {day2_date}")
            
            # *** EVALUATE ALL TRADES at Day 2 close ***
            if len(day2_15m) > 0:
                day2_close = day2_15m.iloc[-1]['Close']
                
                # *** MAIN TRADE EVALUATION ***
                if direction == "bull":
                    profit_main = (credit_main * trade_qty) if day2_close > price_main_trade else ((day2_close - price_main_trade) * trade_qty)
                else:
                    profit_main = (credit_main * trade_qty) if day2_close < price_main_trade else ((price_main_trade - day2_close) * trade_qty)
                
                # Subtract commission
                profit_main -= (self.config['backtest_settings']['commission_per_trade'] * 2)
                win_main = profit_main > 0
                
                # Record main trade (opened on Day 1)
                self.trades.append({
                    'Trade_Date': day1_date,  # Main trade opens on Day 1
                    'Direction': direction,
                    'Type': 'main',
                    'Strike': price_main_trade,
                    'Open_Time': '15:55',
                    'Close_Time': 'next_day_close',
                    'Quantity': trade_qty,
                    'Credit': credit_main,
                    'Close_1550': round(day_close_1550, 2),
                    'HA_Close': round(ha_close, 2),
                    'Close_HA_Diff': round(day_close_1550 - ha_close, 2),
                    'MACD_Diff': round(macd_diff, 4),
                    'Day2_Close': round(day2_close, 2),
                    'Profit_Loss': round(profit_main, 2),
                    'Label': 'Profit' if win_main else 'Loss'
                })
                
                account_value += profit_main
                total_count += 1
                if win_main:
                    win_count += 1
                
                # *** ADDITIONAL TRADES EVALUATION ***
                for trade in additional_trades:
                    trade_direction = trade['direction']
                    
                    # Get Day 3 close for additional trades (they close next day after opening)
                    if i < len(ha_daily) - 2:  # Make sure we have Day 3 data
                        day3_date = ha_daily.iloc[i + 2]['Date']
                        day3_15m = df_15m[df_15m['Datetime'].dt.date == day3_date].reset_index(drop=True)
                        
                        if len(day3_15m) > 0:
                            day3_close = day3_15m.iloc[-1]['Close']
                            
                            if trade_direction == "bull":
                                profit_add = (trade['credit'] * trade_qty) if day3_close > trade['strike'] else ((day3_close - trade['strike']) * trade_qty)
                            else:
                                profit_add = (trade['credit'] * trade_qty) if day3_close < trade['strike'] else ((trade['strike'] - day3_close) * trade_qty)
                            

                            profit_add -= (self.config['backtest_settings']['commission_per_trade'] * 2)
                            win_add = profit_add > 0
                            
                            self.trades.append({
                                'Trade_Date': trade['trade_date'],  # Additional trades open on Day 2
                                'Direction': trade_direction,
                                'Type': trade['type'],
                                'Strike': trade['strike'],
                                'Open_Time': str(trade['candle_time']),
                                'Close_Time': 'next_day_close',
                                'Quantity': trade_qty,
                                'Credit': trade['credit'],
                                'Close_1550': round(day_close_1550, 2),  # Original Day 1 data for reference
                                'HA_Close': round(ha_close, 2),
                                'Close_HA_Diff': round(day_close_1550 - ha_close, 2),
                                'MACD_Diff': round(macd_diff, 4),
                                'Day2_Close': round(day3_close, 2),  # This is actually Day 3 close
                                'Profit_Loss': round(profit_add, 2),
                                'Label': 'Profit' if win_add else 'Loss',
                                'Pattern_Candle': trade['pattern_candle']
                            })
                            
                            account_value += profit_add
                            total_count += 1
                            if win_add:
                                win_count += 1
        
        # Check for quantity increment every 2 weeks
        if total_count >= self.config['trade_settings']['win_rate_window']:
            recent_trades = self.trades[-self.config['trade_settings']['win_rate_window']:]
            recent_win_rate = sum(1 for t in recent_trades if t['Label'] == 'Profit') / len(recent_trades)
            
            if recent_win_rate >= self.config['trade_settings']['win_rate_threshold']:
                trade_qty += self.config['trade_settings']['increment_qty']
                print(f"📈 Increased quantity to {trade_qty} (Win rate: {recent_win_rate:.1%})")
        
        # Record daily equity
        self.daily_equity.append({
            'Date': day1_date,
            'Account_Value': round(account_value, 2),
            'Daily_PnL': round(sum(t['Profit_Loss'] for t in self.trades if t['Trade_Date'] == day1_date), 2),
            'Cumulative_Trades': len(self.trades)
        })
    
        # Calculate final metrics
        self.calculate_performance_metrics(account_value)
        
        print(f"\n✅ Backtest completed!")
        print(f"   📈 Total trades: {len(self.trades)}")
        print(f"   🎯 Win rate: {(win_count/total_count)*100:.1f}%" if total_count > 0 else "   🎯 Win rate: 0%")
        print(f"   💰 Final account: ${account_value:,.2f}")
        print(f"   📊 Total return: {((account_value/self.config['backtest_settings']['initial_capital'])-1)*100:.1f}%")
        
        return self.performance_metrics

    def calculate_performance_metrics(self, final_account_value):
        """Calculate comprehensive performance metrics"""
        if not self.trades:
            return
        
        trades_df = pd.DataFrame(self.trades)
        
        total_trades = len(trades_df)
        winning_trades = len(trades_df[trades_df['Profit_Loss'] > 0])
        losing_trades = total_trades - winning_trades
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        
        total_pnl = trades_df['Profit_Loss'].sum()
        avg_pnl = trades_df['Profit_Loss'].mean()
        
        winners = trades_df[trades_df['Profit_Loss'] > 0]['Profit_Loss']
        losers = trades_df[trades_df['Profit_Loss'] <= 0]['Profit_Loss']
        
        avg_winner = winners.mean() if len(winners) > 0 else 0
        avg_loser = losers.mean() if len(losers) > 0 else 0
        
        max_win = trades_df['Profit_Loss'].max()
        max_loss = trades_df['Profit_Loss'].min()
        
        profit_factor = abs(winners.sum() / losers.sum()) if losers.sum() != 0 else float('inf')
        
        starting_capital = self.config['backtest_settings']['initial_capital']
        total_return = ((final_account_value - starting_capital) / starting_capital) * 100
        
        self.performance_metrics = {
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': round(win_rate, 2),
            'total_pnl': round(total_pnl, 2),
            'avg_pnl_per_trade': round(avg_pnl, 2),
            'avg_winner': round(avg_winner, 2),
            'avg_loser': round(avg_loser, 2),
            'max_win': round(max_win, 2),
            'max_loss': round(max_loss, 2),
            'profit_factor': round(profit_factor, 2) if profit_factor != float('inf') else 999,
            'starting_capital': starting_capital,
            'ending_capital': round(final_account_value, 2),
            'total_return_pct': round(total_return, 2)
        }

    def save_results(self):
        """Save results to Excel and JSON"""
        # Save trades to Excel
        excel_path = self.config['output_settings']['excel_file']
        Path(excel_path).parent.mkdir(parents=True, exist_ok=True)
        
        trades_df = pd.DataFrame(self.trades)
        equity_df = pd.DataFrame(self.daily_equity)
        
        with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
            trades_df.to_excel(writer, sheet_name='Trades', index=False)
            equity_df.to_excel(writer, sheet_name='Daily_Equity', index=False)
            
            # Summary sheet
            summary_data = [[k, v] for k, v in self.performance_metrics.items()]
            summary_df = pd.DataFrame(summary_data, columns=['Metric', 'Value'])
            summary_df.to_excel(writer, sheet_name='Summary', index=False)
        
        # Save JSON report
        json_path = excel_path.replace('.xlsx', '_report.json')
        report = {
            'performance_metrics': self.performance_metrics,
            'trades': self.trades,
            'daily_equity': self.daily_equity,
            'config': self.config,
            'generated_at': datetime.now().isoformat()
        }
        
        with open(json_path, 'w') as f:
            json.dump(report, f, indent=4, default=str)
        
        print(f"📁 Results saved:")
        print(f"   📊 Excel: {excel_path}")
        print(f"   📄 JSON: {json_path}")

    def print_summary_report(self):
        """Print detailed summary report"""
        print("\n" + "="*80)
        print("📊 HEIKEN ASHI STRATEGY BACKTEST RESULTS")
        print("="*80)
        
        if self.performance_metrics:
            m = self.performance_metrics
            print(f"📈 Total Trades: {m['total_trades']}")
            print(f"✅ Winning Trades: {m['winning_trades']}")
            print(f"❌ Losing Trades: {m['losing_trades']}")
            print(f"🎯 Win Rate: {m['win_rate']}%")
            print(f"💰 Total P&L: ${m['total_pnl']:,.2f}")
            print(f"📊 Total Return: {m['total_return_pct']:.2f}%")
            print(f"💵 Avg P&L per Trade: ${m['avg_pnl_per_trade']:,.2f}")
            print(f"✅ Avg Winner: ${m['avg_winner']:,.2f}")
            print(f"❌ Avg Loser: ${m['avg_loser']:,.2f}")
            print(f"📈 Max Win: ${m['max_win']:,.2f}")
            print(f"📉 Max Loss: ${m['max_loss']:,.2f}")
            print(f"⚖️  Profit Factor: {m['profit_factor']}")
            print(f"💳 Starting Capital: ${m['starting_capital']:,.2f}")
            print(f"💰 Ending Capital: ${m['ending_capital']:,.2f}")
        
        print("="*80)

# Example usage and testing
if __name__ == "__main__":
    # Create config directory and file if it doesn't exist
    config_dir = Path("config")
    config_dir.mkdir(exist_ok=True)
    
    config_file = config_dir / "heikenashi_config.json"
    if not config_file.exists():
        default_config = {
            "data_settings": {
                "symbol": "SPY",
                "exchange": "ARCA", 
                "currency": "USD",
                "days_to_fetch": 30,  # Configurable number of days
                "ibkr_host": "127.0.0.1",
                "ibkr_port": 7497,
                "client_id": 1
            },
            "backtest_settings": {
                "initial_capital": 100000,
                "commission_per_trade": 2.0
            },
            "trade_settings": {
                "main_trade_qty": 30,
                "main_trade_credit": 45,
                "additional_trade_qty": 30,
                "additional_trade_1_credit": 45,
                "additional_trade_2_credit": 25,
                "spread_points": 3,
                "increment_qty": 10,
                "win_rate_window": 10,
                "win_rate_threshold": 0.7
            },
            "output_settings": {
                "excel_file": "results/trade_log.xlsx",
                "csv_15m": "data/spy_15m.csv",
                "csv_5m": "data/spy_5m.csv"
            }
        }
        
        with open(config_file, 'w') as f:
            json.dump(default_config, f, indent=4)
        print(f"✅ Created default config: {config_file}")
    
    # Run the backtest
    backtester = CompleteHeikenAshiBacktester(config_file)
    
    # Run backtest (will fetch data from TWS automatically)
    results = backtester.run_backtest()
    
    if results:
        backtester.print_summary_report()
        backtester.save_results()
    else:
        print("❌ Backtest failed")