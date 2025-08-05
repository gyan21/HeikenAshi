# config/config_manager.py
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

class ConfigManager:
    def __init__(self, config_file="config/trading_config.json"):
        self.config_file = config_file
        self.ensure_directory_exists()
        self.config = self.load_config()
    
    def ensure_directory_exists(self):
        """Create config directory if it doesn't exist"""
        Path(self.config_file).parent.mkdir(parents=True, exist_ok=True)
    
    def get_default_config(self):
        """Return default configuration"""
        return {
            "account_settings": {
                "account_value": 100000,
                "risk_per_trade": 0.02,
                "max_trades_per_day": 2
            },
            "trade_quantity": {
                "default_quantity": 30,
                "min_quantity": 10,
                "max_quantity": 100,
                "adjustment_step": 10,  # Adjust by 10 contracts
                "target_win_rate": 0.70,
                "evaluation_period": 10,  # Minimum trades before adjustment
                "minimum_days_between_adjustments": 14,  # 2 weeks
                "last_adjustment_date": None,
                "trades_at_last_adjustment": 0  # Track trade count at last adjustment
            },
            "spread_settings": {
                "spread_width": 10,
                "min_premium_tier_1": 0.55,
                "min_premium_tier_2": 0.45,
                "min_premium_next_day_before_12": 0.50,
                "min_premium_next_day_after_12": 0.35
            },
            "delta_settings": {
                "delta_search_range": [0.24, 0.23, 0.22, 0.21, 0.20],
                "target_delta_tolerance": 0.01
            },
            "trading_times": {
                "trade_execution_start": "15:55",
                "trade_execution_end": "16:00",
                "fallback_execution_end": "16:00",
                "pattern_monitoring_start": "10:00",
                "additional_trade_window_start": "09:30",
                "additional_trade_window_end": "15:30"
            },
            "exit_patterns": {
                "bull_exit_pattern": ["green", "green", "red"],
                "bear_exit_pattern": ["red", "red", "green"],
                "pattern_timeframe": "15min"
            },
            "additional_trade_patterns": {
                "bull_additional_pattern": ["red", "red", "green"],
                "bear_additional_pattern": ["green", "green", "red"]
            },
            "additional_trade_limits": {
                "max_additional_if_profitable": 2,
                "max_additional_if_unprofitable": 1
            },
            "monitoring_settings": {
                "stop_loss_after_time": "10:00",
                "monitor_additional_trades": False,
                "price_check_interval": 60
            },
            "logging_settings": {
                "excel_log_path": "logs/trade_log.xlsx",
                "debug_mode": True,
                "log_level": "INFO"
            },
            "last_updated": datetime.now().isoformat(),
            "version": "1.0"
        }
    
    def load_config(self):
        """Load configuration from file or create default"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                print(f"✅ Loaded configuration from {self.config_file}")
                
                # Merge with defaults to ensure all keys exist
                default_config = self.get_default_config()
                merged_config = self.merge_configs(default_config, config)
                return merged_config
            else:
                print(f"📋 Creating default configuration at {self.config_file}")
                config = self.get_default_config()
                self.save_config(config)
                return config
                
        except Exception as e:
            print(f"❌ Error loading config: {e}, using defaults")
            return self.get_default_config()
    
    def merge_configs(self, default, loaded):
        """Recursively merge loaded config with defaults"""
        for key, value in default.items():
            if key not in loaded:
                loaded[key] = value
            elif isinstance(value, dict) and isinstance(loaded[key], dict):
                loaded[key] = self.merge_configs(value, loaded[key])
        return loaded
    
    def save_config(self, config=None):
        """Save configuration to file"""
        try:
            if config is None:
                config = self.config
            
            config["last_updated"] = datetime.now().isoformat()
            
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=4)
            print(f"✅ Configuration saved to {self.config_file}")
            
        except Exception as e:
            print(f"❌ Error saving config: {e}")
    
    def get(self, path, default=None):
        """Get configuration value using dot notation (e.g., 'trade_quantity.default_quantity')"""
        try:
            keys = path.split('.')
            value = self.config
            for key in keys:
                value = value[key]
            return value
        except (KeyError, TypeError):
            return default
    
    def set(self, path, value):
        """Set configuration value using dot notation"""
        try:
            keys = path.split('.')
            config = self.config
            for key in keys[:-1]:
                if key not in config:
                    config[key] = {}
                config = config[key]
            config[keys[-1]] = value
            self.save_config()
            return True
        except Exception as e:
            print(f"❌ Error setting config: {e}")
            return False
    
    def update_trade_quantity_based_on_performance(self):
        """
        Update trade quantity based on win rate, but only after:
        1. At least 10 trades have been completed since last adjustment, AND
        2. At least 2 weeks have passed since last adjustment
        """
        try:
            # Check if we should adjust based on time and trade count
            can_adjust, reason = self.can_adjust_quantity()
            
            if not can_adjust:
                print(f"📊 Cannot adjust quantity yet: {reason}")
                return self.get('trade_quantity.default_quantity')
            
            # Get trade statistics for evaluation
            stats = self.get_recent_trade_statistics_since_last_adjustment()
            
            if stats['total_trades'] < 10:
                print(f"📊 Insufficient trades ({stats['total_trades']}) since last adjustment")
                return self.get('trade_quantity.default_quantity')
            
            current_quantity = self.get('trade_quantity.default_quantity')
            target_win_rate = self.get('trade_quantity.target_win_rate')
            adjustment_step = self.get('trade_quantity.adjustment_step', 10)  # Default to 10
            min_quantity = self.get('trade_quantity.min_quantity')
            max_quantity = self.get('trade_quantity.max_quantity')
            
            win_rate = stats['win_rate'] / 100  # Convert to decimal
            
            print(f"📊 Performance Analysis (since last adjustment):")
            print(f"   Trades analyzed: {stats['total_trades']}")
            print(f"   Win rate: {win_rate:.1%}")
            print(f"   Target win rate: {target_win_rate:.1%}")
            print(f"   Current quantity: {current_quantity}")
            print(f"   Winning trades: {stats['winning_trades']}")
            print(f"   Losing trades: {stats['losing_trades']}")
            
            new_quantity = current_quantity
            adjustment_made = False
            
            if win_rate >= target_win_rate:
                # Increase quantity if performing well
                new_quantity = min(current_quantity + adjustment_step, max_quantity)
                if new_quantity > current_quantity:
                    print(f"🔼 Increasing trade quantity to {new_quantity} (good performance: {win_rate:.1%})")
                    adjustment_made = True
                else:
                    print(f"📈 Performance good but already at maximum quantity ({max_quantity})")
            else:
                # Decrease quantity if underperforming
                new_quantity = max(current_quantity - adjustment_step, min_quantity)
                if new_quantity < current_quantity:
                    print(f"🔽 Decreasing trade quantity to {new_quantity} (poor performance: {win_rate:.1%})")
                    adjustment_made = True
                else:
                    print(f"📉 Performance poor but already at minimum quantity ({min_quantity})")
            
            if adjustment_made or stats['total_trades'] >= 10:
                # Update configuration with new adjustment date
                today = datetime.now().strftime('%Y-%m-%d')
                self.set('trade_quantity.default_quantity', new_quantity)
                self.set('trade_quantity.last_adjustment_date', today)
                self.set('trade_quantity.trades_at_last_adjustment', self.get_total_trade_count())
                
                print(f"✅ Quantity adjustment completed. Next adjustment after 10+ trades and 2+ weeks.")
            
            return new_quantity
            
        except Exception as e:
            print(f"❌ Error updating trade quantity: {e}")
            return self.get('trade_quantity.default_quantity', 30)
    
    def can_adjust_quantity(self):
        """
        Check if quantity can be adjusted based on time and trade count criteria
        Returns: (can_adjust: bool, reason: str)
        """
        try:
            last_adjustment_date = self.get('trade_quantity.last_adjustment_date')
            trades_at_last_adjustment = self.get('trade_quantity.trades_at_last_adjustment', 0)
            
            # If never adjusted before, allow adjustment
            if not last_adjustment_date:
                return True, "First time adjustment"
            
            # Check time criteria (2 weeks)
            last_adjustment = datetime.strptime(last_adjustment_date, '%Y-%m-%d')
            today = datetime.now()
            days_since_adjustment = (today - last_adjustment).days
            
            if days_since_adjustment < 14:
                return False, f"Only {days_since_adjustment} days since last adjustment (need 14 days)"
            
            # Check trade count criteria (10 trades)
            current_trade_count = self.get_total_trade_count()
            trades_since_adjustment = current_trade_count - trades_at_last_adjustment
            
            if trades_since_adjustment < 10:
                return False, f"Only {trades_since_adjustment} trades since last adjustment (need 10 trades)"
            
            return True, f"Ready for adjustment: {days_since_adjustment} days and {trades_since_adjustment} trades since last adjustment"
            
        except Exception as e:
            print(f"❌ Error checking adjustment criteria: {e}")
            return False, "Error checking criteria"
    
    def get_total_trade_count(self):
        """Get total number of closed main trades"""
        try:
            import pandas as pd
            from utils.excel_logger import excel_logger
            
            if not os.path.exists(excel_logger.file_path):
                return 0
            
            df = pd.read_excel(excel_logger.file_path, engine='openpyxl')
            
            # Count all closed main trades
            closed_main_trades = df[
                (df['Current_Status'] == 'Closed') & 
                (df['Trade_Type'] == 'Main')
            ]
            
            return len(closed_main_trades)
            
        except Exception as e:
            print(f"❌ Error getting total trade count: {e}")
            return 0
    
    def get_recent_trade_statistics_since_last_adjustment(self):
        """Get statistics for trades since last quantity adjustment"""
        try:
            import pandas as pd
            from utils.excel_logger import excel_logger
            
            if not os.path.exists(excel_logger.file_path):
                return {'total_trades': 0, 'win_rate': 0, 'avg_pnl': 0}
            
            df = pd.read_excel(excel_logger.file_path, engine='openpyxl')
            
            # Get trades since last adjustment
            trades_at_last_adjustment = self.get('trade_quantity.trades_at_last_adjustment', 0)
            
            # Filter closed main trades (not additional trades)
            all_closed_trades = df[
                (df['Current_Status'] == 'Closed') & 
                (df['Trade_Type'] == 'Main')
            ].sort_values('Date')  # Sort by date to get chronological order
            
            # Get trades since last adjustment (skip the first N trades)
            recent_trades = all_closed_trades.iloc[trades_at_last_adjustment:]
            
            if len(recent_trades) == 0:
                return {'total_trades': 0, 'win_rate': 0, 'avg_pnl': 0}
            
            total_trades = len(recent_trades)
            winning_trades = len(recent_trades[recent_trades['P_L_Dollar'] > 0])
            win_rate = (winning_trades / total_trades) * 100
            avg_pnl = recent_trades['P_L_Dollar'].mean()
            
            return {
                'total_trades': total_trades,
                'win_rate': win_rate,
                'avg_pnl': avg_pnl,
                'winning_trades': winning_trades,
                'losing_trades': total_trades - winning_trades
            }
            
        except Exception as e:
            print(f"❌ Error getting trade statistics since last adjustment: {e}")
            return {'total_trades': 0, 'win_rate': 0, 'avg_pnl': 0}
    
    def get_current_trade_quantity(self):
        """Get current trade quantity (with performance adjustment)"""
        return self.update_trade_quantity_based_on_performance()
    
    def reset_to_defaults(self):
        """Reset configuration to defaults"""
        self.config = self.get_default_config()
        self.save_config()
        print("✅ Configuration reset to defaults")
    
    def get_quantity_status(self):
        """Get detailed status of quantity adjustment system"""
        try:
            can_adjust, reason = self.can_adjust_quantity()
            stats = self.get_recent_trade_statistics_since_last_adjustment()
            
            last_adjustment = self.get('trade_quantity.last_adjustment_date')
            if last_adjustment:
                last_adj_date = datetime.strptime(last_adjustment, '%Y-%m-%d')
                days_since = (datetime.now() - last_adj_date).days
            else:
                days_since = "Never"
            
            trades_at_last = self.get('trade_quantity.trades_at_last_adjustment', 0)
            current_total = self.get_total_trade_count()
            trades_since = current_total - trades_at_last
            
            return {
                'current_quantity': self.get('trade_quantity.default_quantity'),
                'can_adjust': can_adjust,
                'reason': reason,
                'days_since_last_adjustment': days_since,
                'trades_since_last_adjustment': trades_since,
                'trades_needed': max(0, 10 - trades_since),
                'days_needed': max(0, 14 - (days_since if isinstance(days_since, int) else 0)),
                'recent_win_rate': stats.get('win_rate', 0),
                'recent_trades_count': stats.get('total_trades', 0),
                'target_win_rate': self.get('trade_quantity.target_win_rate') * 100
            }
            
        except Exception as e:
            print(f"❌ Error getting quantity status: {e}")
            return {}

# Global config manager instance
config_manager = ConfigManager()