# utils/excel_logger.py
import pandas as pd
import os
from datetime import datetime
from pathlib import Path

class ExcelTradeLogger:
    def __init__(self, file_path="logs/trade_log.xlsx"):
        self.file_path = file_path
        self.ensure_directory_exists()
        self.initialize_excel_file()
    
    def ensure_directory_exists(self):
        """Create logs directory if it doesn't exist"""
        Path(self.file_path).parent.mkdir(parents=True, exist_ok=True)
    
    def initialize_excel_file(self):
        """Initialize Excel file with proper headers if it doesn't exist"""
        if not os.path.exists(self.file_path):
            # Create initial DataFrame with all required columns
            df = pd.DataFrame(columns=[
                'Date', 'Time', 'Trade_ID', 'Trade_Type', 'Symbol', 'Direction',
                'Expiry', 'Sell_Strike', 'Buy_Strike', 'Option_Type', 'Spread_Width',
                'Quantity', 'Entry_Premium', 'Min_Premium_Required', 'Entry_Price',
                'Current_Status', 'Days_Held', 'Entry_Date', 'Entry_Time',
                'Exit_Date', 'Exit_Time', 'Exit_Premium', 'Exit_Price', 'Exit_Reason',
                'P_L_Dollar', 'P_L_Percent', 'Daily_Close_Price', 'Daily_HA_Close',
                'Price_Difference', 'Sell_Delta', 'IV_Entry', 'IV_Exit',
                'Market_Conditions', 'Trigger_1_Time', 'Trigger_2_Time',
                'Pattern_Confirmed', 'Max_Loss', 'Max_Profit', 'ROI',
                'Trade_Notes', 'Stop_Loss_Monitored'
            ])
            df.to_excel(self.file_path, index=False, engine='openpyxl')
            print(f"✅ Created new trade log: {self.file_path}")
    
    def log_trade_entry(self, trade_info):
        """Log a new trade entry"""
        try:
            # Read existing data
            df = pd.read_excel(self.file_path, engine='openpyxl')
            
            # Prepare new trade entry
            entry_data = {
                'Date': datetime.now().strftime('%Y-%m-%d'),
                'Time': datetime.now().strftime('%H:%M:%S'),
                'Trade_ID': trade_info.get('main_order_id'),
                'Trade_Type': trade_info.get('trade_type', 'Main'),
                'Symbol': trade_info.get('symbol', 'SPY'),
                'Direction': trade_info.get('trade_direction'),
                'Expiry': trade_info.get('spread', '').split()[-1] if 'spread' in trade_info else '',
                'Sell_Strike': trade_info.get('sell_strike'),
                'Buy_Strike': trade_info.get('buy_strike'),
                'Option_Type': trade_info.get('option_type'),
                'Spread_Width': trade_info.get('buy_strike', 0) - trade_info.get('sell_strike', 0) if trade_info.get('trade_direction') == 'bull' else trade_info.get('sell_strike', 0) - trade_info.get('buy_strike', 0),
                'Quantity': trade_info.get('quantity'),
                'Entry_Premium': trade_info.get('target_premium', 0) / 100,  # Convert to dollars
                'Min_Premium_Required': trade_info.get('min_premium_required', 0),
                'Entry_Price': trade_info.get('target_premium', 0) / 100,
                'Current_Status': trade_info.get('status', 'Open'),
                'Days_Held': 0,
                'Entry_Date': datetime.now().strftime('%Y-%m-%d'),
                'Entry_Time': datetime.now().strftime('%H:%M:%S'),
                'Exit_Date': '',
                'Exit_Time': '',
                'Exit_Premium': '',
                'Exit_Price': '',
                'Exit_Reason': '',
                'P_L_Dollar': '',
                'P_L_Percent': '',
                'Daily_Close_Price': trade_info.get('dailyClosePrice'),
                'Daily_HA_Close': trade_info.get('dailyCloseHA'),
                'Price_Difference': trade_info.get('dailyClosePrice', 0) - trade_info.get('dailyCloseHA', 0),
                'Sell_Delta': trade_info.get('sell_delta'),
                'IV_Entry': '',
                'IV_Exit': '',
                'Market_Conditions': self.get_market_conditions(),
                'Trigger_1_Time': '',
                'Trigger_2_Time': '',
                'Pattern_Confirmed': '',
                'Max_Loss': abs(trade_info.get('buy_strike', 0) - trade_info.get('sell_strike', 0)) * 100,  # Max loss in dollars
                'Max_Profit': trade_info.get('target_premium', 0),  # Premium collected
                'ROI': '',
                'Trade_Notes': f"H-A Strategy: {trade_info.get('trade_direction')} direction",
                'Stop_Loss_Monitored': trade_info.get('monitor_stop_loss', True)
            }
            
            # Add new row
            new_row = pd.DataFrame([entry_data])
            df = pd.concat([df, new_row], ignore_index=True)
            
            # Save to Excel
            df.to_excel(self.file_path, index=False, engine='openpyxl')
            print(f"✅ Trade entry logged to Excel: {trade_info.get('main_order_id')}")
            
        except Exception as e:
            print(f"❌ Error logging trade entry: {e}")
    
    def log_trade_exit(self, trade_info, exit_price, exit_reason):
        """Log trade exit and calculate P&L"""
        try:
            # Read existing data
            df = pd.read_excel(self.file_path, engine='openpyxl')
            
            # Find the trade to update
            trade_id = trade_info.get('main_order_id')
            mask = df['Trade_ID'] == trade_id
            
            if not mask.any():
                print(f"❌ Trade {trade_id} not found in Excel log")
                return
            
            # Calculate P&L
            entry_premium = df.loc[mask, 'Entry_Premium'].iloc[0]
            exit_premium = exit_price / 100 if exit_price else 0
            quantity = df.loc[mask, 'Quantity'].iloc[0]
            
            # P&L calculation (for credit spreads)
            if 'stop loss' in exit_reason.lower():
                # Loss scenario - we pay to close
                pnl_per_contract = entry_premium - exit_premium
                pnl_total = pnl_per_contract * quantity * 100  # Total dollar P&L
            else:
                # Profit scenario - we keep the credit
                pnl_per_contract = entry_premium
                pnl_total = pnl_per_contract * quantity * 100
            
            pnl_percent = (pnl_total / (df.loc[mask, 'Max_Loss'].iloc[0] * quantity)) * 100
            
            # Calculate days held
            entry_date = pd.to_datetime(df.loc[mask, 'Entry_Date'].iloc[0])
            days_held = (datetime.now() - entry_date).days
            
            # Update the row
            df.loc[mask, 'Exit_Date'] = datetime.now().strftime('%Y-%m-%d')
            df.loc[mask, 'Exit_Time'] = datetime.now().strftime('%H:%M:%S')
            df.loc[mask, 'Exit_Premium'] = exit_premium
            df.loc[mask, 'Exit_Price'] = exit_price
            df.loc[mask, 'Exit_Reason'] = exit_reason
            df.loc[mask, 'Current_Status'] = 'Closed'
            df.loc[mask, 'Days_Held'] = days_held
            df.loc[mask, 'P_L_Dollar'] = round(pnl_total, 2)
            df.loc[mask, 'P_L_Percent'] = round(pnl_percent, 2)
            df.loc[mask, 'ROI'] = round((pnl_total / (entry_premium * quantity * 100)) * 100, 2)
            
            # Save to Excel
            df.to_excel(self.file_path, index=False, engine='openpyxl')
            print(f"✅ Trade exit logged: {trade_id}, P&L: ${pnl_total:.2f}")
            
        except Exception as e:
            print(f"❌ Error logging trade exit: {e}")
    
    def update_trade_triggers(self, trade_id, trigger_1_time=None, trigger_2_time=None, pattern_confirmed=None):
        """Update trigger information for a trade"""
        try:
            df = pd.read_excel(self.file_path, engine='openpyxl')
            mask = df['Trade_ID'] == trade_id
            
            if not mask.any():
                return
            
            if trigger_1_time:
                df.loc[mask, 'Trigger_1_Time'] = trigger_1_time.strftime('%Y-%m-%d %H:%M:%S')
            if trigger_2_time:
                df.loc[mask, 'Trigger_2_Time'] = trigger_2_time.strftime('%Y-%m-%d %H:%M:%S')
            if pattern_confirmed is not None:
                df.loc[mask, 'Pattern_Confirmed'] = pattern_confirmed
            
            df.to_excel(self.file_path, index=False, engine='openpyxl')
            
        except Exception as e:
            print(f"❌ Error updating triggers: {e}")
    
    def get_market_conditions(self):
        """Get current market conditions for context"""
        current_time = datetime.now().time()
        if current_time < datetime.strptime('10:00', '%H:%M').time():
            return "Market Open"
        elif current_time < datetime.strptime('15:00', '%H:%M').time():
            return "Mid Day"
        else:
            return "Market Close"
    
    def get_trade_summary(self):
        """Get summary statistics"""
        try:
            df = pd.read_excel(self.file_path, engine='openpyxl')
            
            total_trades = len(df)
            open_trades = len(df[df['Current_Status'] == 'Open'])
            closed_trades = len(df[df['Current_Status'] == 'Closed'])
            
            if closed_trades > 0:
                total_pnl = df[df['Current_Status'] == 'Closed']['P_L_Dollar'].sum()
                win_rate = len(df[(df['Current_Status'] == 'Closed') & (df['P_L_Dollar'] > 0)]) / closed_trades * 100
                avg_pnl = df[df['Current_Status'] == 'Closed']['P_L_Dollar'].mean()
            else:
                total_pnl = 0
                win_rate = 0
                avg_pnl = 0
            
            return {
                'total_trades': total_trades,
                'open_trades': open_trades,
                'closed_trades': closed_trades,
                'total_pnl': total_pnl,
                'win_rate': win_rate,
                'avg_pnl': avg_pnl
            }
            
        except Exception as e:
            print(f"❌ Error getting summary: {e}")
            return {}

# Global logger instance
excel_logger = ExcelTradeLogger()

def save_trade_to_log(trade_info):
    """Save trade to Excel log"""
    excel_logger.log_trade_entry(trade_info)

def log_trade_exit(trade_info, exit_price, exit_reason):
    """Log trade exit to Excel"""
    excel_logger.log_trade_exit(trade_info, exit_price, exit_reason)

def update_trade_triggers(trade_id, trigger_1_time=None, trigger_2_time=None, pattern_confirmed=None):
    """Update trigger information"""
    excel_logger.update_trade_triggers(trade_id, trigger_1_time, trigger_2_time, pattern_confirmed)