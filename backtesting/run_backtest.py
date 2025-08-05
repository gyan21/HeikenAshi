# backtesting/run_backtest.py
from backtest_engine import HeikinAshiBacktester
import sys
import os

def main():
    """Run the Heikin-Ashi credit spread backtest"""
    
    print("🚀 Starting Heikin-Ashi Credit Spread Backtest")
    print("=" * 50)
    
    try:
        # Create backtester
        backtester = HeikinAshiBacktester()
        
        # Run backtest
        print("📈 Running backtest...")
        results = backtester.run_backtest()
        
        if results:
            # Generate report
            report = backtester.generate_report()
            print("✅ Backtest completed successfully!")
        else:
            print("❌ Backtest failed")
            
    except FileNotFoundError as e:
        print(f"❌ Configuration error: {e}")
        print("Please run: python create_backtest_config.py")
    except Exception as e:
        print(f"❌ Error running backtest: {e}")

if __name__ == "__main__":
    main()