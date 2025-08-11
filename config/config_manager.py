# config/config_manager.py
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

class ConfigManager:
    def __init__(self, config_file="config/trading_config.json"):
        self.config_file = config_file
        self.ensure_directory_exists()
        self.ensure_config_exists()
        self.config = self.load_config()
    
    def ensure_directory_exists(self):
        """Create config directory if it doesn't exist"""
        Path(self.config_file).parent.mkdir(parents=True, exist_ok=True)
    
    def ensure_config_exists(self):
        """Create config file if it doesn't exist"""
        if not os.path.exists(self.config_file):
            print(f"📋 Config file not found. Please create {self.config_file}")
            print("📋 You can copy the template from config/trading_config_template.json")
            raise FileNotFoundError(f"Configuration file {self.config_file} not found")
    
    def load_config(self):
        """Load configuration from file"""
        try:
            with open(self.config_file, 'r') as f:
                config = json.load(f)
            print(f"✅ Loaded configuration from {self.config_file}")
            return config
                
        except Exception as e:
            print(f"❌ Error loading config: {e}")
            raise
    
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
        """Get configuration value using dot notation"""
        try:
            keys = path.split('.')
            value = self.config
            for key in keys:
                value = value[key]
            return value
        except (KeyError, TypeError):
            if default is not None:
                return default
            print(f"❌ Configuration key '{path}' not found")
            return None
    
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
    
    def validate_config(self):
        """Validate that all required configuration keys exist"""
        required_keys = [
            'account_settings.account_value',
            'trade_quantity.default_quantity',
            'spread_settings.min_premium_tier_1',
            'trading_times.trade_execution_start',
            'delta_settings.delta_search_range'
        ]
        
        missing_keys = []
        for key in required_keys:
            if self.get(key) is None:
                missing_keys.append(key)
        
        if missing_keys:
            print(f"❌ Missing required configuration keys: {missing_keys}")
            return False
        
        print("✅ Configuration validation passed")
        return True
    
    def get_current_trade_quantity(self):
        """Get the current trade quantity from config"""
        return self.config.get('trade_settings', {}).get('main_trade_qty', 30)

    def update_trade_quantity(self, new_quantity):
        """Update the current trade quantity"""
        if 'trade_settings' not in self.config:
            self.config['trade_settings'] = {}
        self.config['trade_settings']['main_trade_qty'] = new_quantity
        self.save_config()
        
    def get_trade_setting(self, setting_name, default_value=None):
        """Get any trade setting by name"""
        return self.config.get('trade_settings', {}).get(setting_name, default_value)

# Global config manager instance
config_manager = ConfigManager()