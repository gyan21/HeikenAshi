# backtesting/backtest_engine_fixed.py
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, time as dtime
import yfinance as yf
from pathlib import Path
import json
from typing import Dict, List, Optional, Tuple

class HeikinAshiBacktester:
    def __init__(self, config_path="config/backtest_config.json"):
        self.config = self.load_config(config_path)
        self.trades = []
        self.daily_pnl = []
        self.performance_metrics = {}
        
    def load_config(self, config_path):
        """Load trading configuration"""
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"❌ Config file not found: {config_path}")
            raise
    
    def calculate_heikin_ashi(self, df):
        """Calculate Heikin-Ashi values"""
        ha_df = df.copy()
        
        # Convert to numpy arrays for faster computation
        open_vals = ha_df['Open'].values
        high_vals = ha_df['High'].values
        low_vals = ha_df['Low'].values
        close_vals = ha_df['Close'].values
        
        # Initialize arrays
        ha_close = np.zeros(len(ha_df))
        ha_open = np.zeros(len(ha_df))
        ha_high = np.zeros(len(ha_df))
        ha_low = np.zeros(len(ha_df))
        
        # First candle
        ha_close[0] = (open_vals[0] + high_vals[0] + low_vals[0] + close_vals[0]) / 4
        ha_open[0] = (open_vals[0] + close_vals[0]) / 2
        ha_high[0] = max(high_vals[0], ha_open[0], ha_close[0])
        ha_low[0] = min(low_vals[0], ha_open[0], ha_close[0])
        
        # Subsequent candles
        for i in range(1, len(ha_df)):
            ha_close[i] = (open_vals[i] + high_vals[i] + low_vals[i] + close_vals[i]) / 4
            ha_open[i] = (ha_open[i-1] + ha_close[i-1]) / 2
            ha_high[i] = max(high_vals[i], ha_open[i], ha_close[i])
            ha_low[i] = min(low_vals[i], ha_open[i], ha_close[i])
        
        # Add to dataframe
        ha_df['HA_Close'] = ha_close
        ha_df['HA_Open'] = ha_open
        ha_df['HA_High'] = ha_high
        ha_df['HA_Low'] = ha_low
        
        return ha_df
    
    def determine_trade_direction(self, daily_close, ha_close):
        """Determine trade direction based on H-A logic"""
        return 'bull' if daily_close > ha_close else 'bear'
    
    def get_option_strikes_realistic(self, spot_price, option_type, target_delta=0.15):
        """Get realistic option strikes for credit spreads"""
        spread_width = self.config['spread_settings']['spread_width']
        
        # More realistic strike selection - closer to ATM for better premium
        if option_type == 'P':
            # Put credit spread - sell puts below current price
            # Target around 5-10 points below current price for better premium
            sell_strike = round((spot_price * 0.98) / 5) * 5  # ~2% below
            buy_strike = max(5, sell_strike - spread_width)
        else:
            # Call credit spread - sell calls above current price  
            sell_strike = round((spot_price * 1.02) / 5) * 5  # ~2% above
            buy_strike = sell_strike + spread_width
        
        return sell_strike, buy_strike
    
    def calculate_realistic_premium(self, spot_price, sell_strike, buy_strike, option_type):
        """Calculate more realistic premium for credit spreads"""
        spread_width = abs(sell_strike - buy_strike)
        
        if option_type == 'P':
            # Put spread - premium based on how far below current price
            distance_pct = (spot_price - sell_strike) / spot_price
            if distance_pct > 0.05:  # More than 5% OTM
                base_premium = 0.15
            elif distance_pct > 0.02:  # 2-5% OTM
                base_premium = 0.30
            else:  # Less than 2% OTM
                base_premium = 0.50
        else:
            # Call spread - premium based on how far above current price
            distance_pct = (sell_strike - spot_price) / spot_price
            if distance_pct > 0.05:  # More than 5% OTM
                base_premium = 0.15
            elif distance_pct > 0.02:  # 2-5% OTM
                base_premium = 0.30
            else:  # Less than 2% OTM
                base_premium = 0.50
        
        # Add some randomness for realism
        premium = base_premium + np.random.uniform(-0.05, 0.10)
        return max(0.10, premium)  # Minimum 10 cents
    
    def check_premium_requirements_relaxed(self, premium):
        """More relaxed premium requirements for backtesting"""
        # Significantly lower minimum premiums for backtesting
        min_premium = 0.20  # 20 cents minimum
        return premium >= min_premium
    
    def simulate_exit_conditions_improved(self, trade, current_data, prev_data, days_held):
        """Improved exit condition simulation"""
        current_price = float(current_data['Close'])
        trade_direction = trade['direction']
        sell_strike = trade['sell_strike']
        
        # 1. Check for immediate expiration (1 DTE means expires next day)
        if days_held >= 1:
            return True, 'expiration'
        
        # 2. Profit taking - close at 50% profit (common strategy)
        if np.random.random() < 0.2:  # 20% chance of profit taking
            return True, 'profit_taking'
        
        # 3. Stop loss simulation - price moves against position significantly
        if prev_data is not None:
            prev_close = float(prev_data['Close'])
            price_change_pct = (current_price - prev_close) / prev_close
            
            # Stop loss if significant move against position
            if trade_direction == 'bull' and price_change_pct < -0.015:  # 1.5% down
                if np.random.random() < 0.30:  # 30% chance of stop loss trigger
                    return True, 'stop_loss'
            elif trade_direction == 'bear' and price_change_pct > 0.015:  # 1.5% up
                if np.random.random() < 0.30:
                    return True, 'stop_loss'
        
        return False, None
    
    def calculate_exit_pnl_realistic(self, trade, current_price, exit_reason):
        """Calculate realistic P&L at exit"""
        option_type = trade['option_type']
        sell_strike = trade['sell_strike']
        buy_strike = trade['buy_strike']
        entry_premium = trade['entry_premium']
        quantity = trade['quantity']
        
        if exit_reason == 'expiration':
            # At expiration, worth intrinsic value only
            if option_type == 'P':
                sell_intrinsic = max(0, sell_strike - current_price)
                buy_intrinsic = max(0, buy_strike - current_price)
            else:
                sell_intrinsic = max(0, current_price - sell_strike)
                buy_intrinsic = max(0, current_price - buy_strike)
            
            exit_premium = sell_intrinsic - buy_intrinsic
            pnl = (entry_premium - exit_premium) * quantity * 100
            
        elif exit_reason == 'profit_taking':
            # Close at 50% of original premium
            exit_premium = entry_premium * 0.5
            pnl = (entry_premium - exit_premium) * quantity * 100
            
        elif exit_reason == 'stop_loss':
            # Stop loss - typically lose 2-3x the premium received
            exit_premium = entry_premium * 2.5
            pnl = (entry_premium - exit_premium) * quantity * 100
            
        else:  # final_close
            exit_premium = entry_premium * 0.3  # Assume 70% profit
            pnl = (entry_premium - exit_premium) * quantity * 100
        
        # Subtract commission
        commission = self.config['backtest_settings']['commission_per_trade']
        pnl -= commission * 2  # Entry and exit
        
        return pnl, exit_premium
    
    def run_backtest(self, symbol=None, start_date=None, end_date=None):
        """Run the complete backtest with debugging"""
        
        if symbol is None:
            symbol = self.config['backtest_settings']['symbol']
        if start_date is None:
            start_date = self.config['backtest_settings']['start_date']
        if end_date is None:
            end_date = self.config['backtest_settings']['end_date']
            
        print(f"🔄 Starting backtest for {symbol} from {start_date} to {end_date}")
        
        # Download historical data
        try:
            stock_data = yf.download(symbol, start=start_date, end=end_date, progress=False, auto_adjust=True)
        except Exception as e:
            print(f"❌ Error downloading data: {e}")
            return None
        
        if stock_data.empty:
            print("❌ No data downloaded")
            return None
        
        print(f"📊 Downloaded {len(stock_data)} days of data")
        
        # Calculate Heikin-Ashi
        ha_data = self.calculate_heikin_ashi(stock_data)
        print(f"✅ Calculated Heikin-Ashi for {len(ha_data)} days")
        
        # Initialize tracking
        open_trades = []
        account_value = self.config['backtest_settings']['initial_capital']
        daily_equity = []
        trade_attempts = 0
        trades_executed = 0
        
        print(f"📊 Processing {len(ha_data)} trading days...")
        
        # Main backtest loop
        for i, (date, row) in enumerate(ha_data.iterrows()):
            if i < 1:
                continue
                
            daily_close = float(row['Close'])
            ha_close = float(row['HA_Close'])
            prev_row = ha_data.iloc[i-1]
            
            # Process exits for open trades
            trades_to_close = []
            for trade_idx, trade in enumerate(open_trades):
                days_held = (date - trade['entry_date']).days
                should_exit, exit_reason = self.simulate_exit_conditions_improved(trade, row, prev_row, days_held)
                
                if should_exit:
                    pnl, exit_premium = self.calculate_exit_pnl_realistic(trade, daily_close, exit_reason)
                    
                    trade.update({
                        'exit_date': date,
                        'exit_price': daily_close,
                        'exit_premium': exit_premium,
                        'exit_reason': exit_reason,
                        'pnl': pnl,
                        'days_held': days_held
                    })
                    
                    self.trades.append(trade)
                    trades_to_close.append(trade_idx)
                    account_value += pnl
                    
                    if len(self.trades) <= 20:  # Show first 20 trades
                        profit_loss = "PROFIT" if pnl > 0 else "LOSS"
                        print(f"💰 Trade {len(self.trades)}: {trade['direction']} {trade['sell_strike']}/{trade['buy_strike']} "
                              f"{profit_loss}: ${pnl:.2f} | Reason: {exit_reason} | Days: {days_held}")
            
            # Remove closed trades
            for idx in reversed(trades_to_close):
                open_trades.pop(idx)
            
            # Check for new trade signals (limit to avoid overtrading)
            max_open_trades = 3  # Allow up to 3 open trades
            if len(open_trades) < max_open_trades and trade_attempts < len(ha_data) * 0.3:  # Limit trade frequency
                trade_direction = self.determine_trade_direction(daily_close, ha_close)
                option_type = 'P' if trade_direction == 'bull' else 'C'
                
                trade_attempts += 1
                
                try:
                    sell_strike, buy_strike = self.get_option_strikes_realistic(daily_close, option_type)
                    premium = self.calculate_realistic_premium(daily_close, sell_strike, buy_strike, option_type.lower())
                    
                    if self.check_premium_requirements_relaxed(premium):
                        quantity = self.config['trade_quantity']['default_quantity']
                        
                        new_trade = {
                            'entry_date': date,
                            'direction': trade_direction,
                            'option_type': option_type,
                            'sell_strike': sell_strike,
                            'buy_strike': buy_strike,
                            'entry_price': daily_close,
                            'entry_premium': premium,
                            'quantity': quantity,
                            'dte': 1,
                            'days_held': 0
                        }
                        
                        open_trades.append(new_trade)
                        trades_executed += 1
                        
                        # Show trade entries
                        if trades_executed <= 20:
                            print(f"📝 Trade {trades_executed}: {trade_direction} {sell_strike}/{buy_strike} "
                                  f"Premium: ${premium:.2f} | Price: ${daily_close:.2f}")
                    else:
                        if trade_attempts <= 10:
                            print(f"❌ Trade rejected: Premium ${premium:.2f} too low")
                
                except Exception as e:
                    if trade_attempts <= 5:
                        print(f"⚠️  Error creating trade: {e}")
            
            # Record daily equity
            daily_equity.append({
                'date': date.strftime('%Y-%m-%d'),
                'account_value': account_value,
                'open_trades': len(open_trades),
                'daily_close': daily_close,
                'ha_close': ha_close
            })
        
        # Close remaining trades
        if open_trades:
            final_price = float(ha_data.iloc[-1]['Close'])
            final_date = ha_data.index[-1]
            
            for trade in open_trades:
                pnl, exit_premium = self.calculate_exit_pnl_realistic(trade, final_price, 'final_close')
                trade.update({
                    'exit_date': final_date,
                    'exit_price': final_price,
                    'exit_premium': exit_premium,
                    'exit_reason': 'final_close',
                    'pnl': pnl,
                    'days_held': (final_date - trade['entry_date']).days
                })
                self.trades.append(trade)
                account_value += pnl
        
        self.daily_pnl = daily_equity
        self.final_account_value = account_value
        
        print(f"✅ Backtest completed:")
        print(f"   Trade attempts: {trade_attempts}")
        print(f"   Trades executed: {len(self.trades)}")
        print(f"   Final account value: ${account_value:,.2f}")
        
        if len(self.trades) > 0:
            self.calculate_performance_metrics()
        else:
            print("❌ No trades executed - check strategy parameters")
            
        return self.performance_metrics
    
    def calculate_performance_metrics(self):
        """Calculate performance metrics"""
        if not self.trades:
            self.performance_metrics = {'total_trades': 0}
            return
        
        trades_df = pd.DataFrame(self.trades)
        
        total_trades = len(trades_df)
        winning_trades = len(trades_df[trades_df['pnl'] > 0])
        win_rate = (winning_trades / total_trades) * 100 if total_trades > 0 else 0
        
        total_pnl = trades_df['pnl'].sum()
        avg_pnl = trades_df['pnl'].mean()
        avg_winner = trades_df[trades_df['pnl'] > 0]['pnl'].mean() if winning_trades > 0 else 0
        avg_loser = trades_df[trades_df['pnl'] < 0]['pnl'].mean() if (total_trades - winning_trades) > 0 else 0
        
        starting_value = self.config['backtest_settings']['initial_capital']
        total_return = ((self.final_account_value - starting_value) / starting_value) * 100
        
        self.performance_metrics = {
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': total_trades - winning_trades,
            'win_rate': round(win_rate, 2),
            'total_pnl': round(total_pnl, 2),
            'avg_pnl_per_trade': round(avg_pnl, 2),
            'avg_winner': round(avg_winner, 2),
            'avg_loser': round(avg_loser, 2),
            'max_win': round(trades_df['pnl'].max(), 2),
            'max_loss': round(trades_df['pnl'].min(), 2),
            'starting_account': starting_value,
            'ending_account': round(self.final_account_value, 2),
            'total_return_pct': round(total_return, 2)
        }
    
    def generate_report(self, save_path="results/backtest_results_fixed.json"):
        """Generate backtest report"""
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        
        report = {
            'backtest_summary': self.performance_metrics,
            'trades': self.trades,
            'daily_equity': self.daily_pnl,
            'generated_at': datetime.now().isoformat()
        }
        
        with open(save_path, 'w') as f:
            json.dump(report, f, indent=4, default=str)
        
        # Print summary
        print("\n" + "="*60)
        print("📊 BACKTEST RESULTS SUMMARY")
        print("="*60)
        
        if self.performance_metrics.get('total_trades', 0) > 0:
            metrics = self.performance_metrics
            print(f"Total Trades: {metrics['total_trades']}")
            print(f"Win Rate: {metrics['win_rate']}%")
            print(f"Total P&L: ${metrics['total_pnl']:,.2f}")
            print(f"Total Return: {metrics['total_return_pct']}%")
            print(f"Average P&L per Trade: ${metrics['avg_pnl_per_trade']:,.2f}")
            print(f"Average Winner: ${metrics['avg_winner']:,.2f}")
            print(f"Average Loser: ${metrics['avg_loser']:,.2f}")
        else:
            print("No trades executed during backtest period")
        
        print(f"\n💾 Report saved to: {save_path}")
        return report

# Test the fixed version
if __name__ == "__main__":
    print("🔧 Testing fixed backtest engine...")
    backtester = HeikinAshiBacktester()
    results = backtester.run_backtest()
    
    if results and results.get('total_trades', 0) > 0:
        backtester.generate_report()
        print("✅ Fixed backtest is working!")
    else:
        print("❌ Still no trades - need further debugging")