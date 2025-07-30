#!/usr/bin/env python3
"""
Test script to verify the updated Heikin-Ashi Credit Spread Trading Algorithm
This script tests the main components without connecting to IBKR.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_imports():
    """Test that all new modules can be imported successfully."""
    print("Testing imports...")
    
    try:
        # Test config imports
        from config.settings import (
            DEFAULT_TRADE_QUANTITY, SPREAD_WIDTH, MIN_PREMIUM_TIER_1,
            DELTA_SEARCH_RANGE, TRADE_EXECUTION_START
        )
        print("✅ Config imports successful")
        
        # Test utility imports
        from utils.quantity_manager import get_current_trade_quantity, calculate_win_rate_last_10_trades
        from utils.pattern_utils import determine_candle_color
        from utils.delta_option_finder import find_option_by_delta_range
        from utils.trade_executor import determine_trade_direction, should_execute_daily_trade
        from utils.trade_monitor import should_monitor_trades
        from utils.additional_trades import should_scan_additional_opportunities
        from utils.logger import save_trade_to_log, get_trade_summary
        print("✅ Utility imports successful")
        
        return True
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def test_configuration():
    """Test configuration values."""
    print("\nTesting configuration...")
    
    try:
        from config.settings import (
            DEFAULT_TRADE_QUANTITY, SPREAD_WIDTH, MIN_PREMIUM_TIER_1,
            MIN_PREMIUM_TIER_2, MIN_PREMIUM_NEXT_DAY, DELTA_SEARCH_RANGE
        )
        
        print(f"Default trade quantity: {DEFAULT_TRADE_QUANTITY}")
        print(f"Spread width: {SPREAD_WIDTH}")
        print(f"Premium tier 1: ${MIN_PREMIUM_TIER_1}")
        print(f"Premium tier 2: ${MIN_PREMIUM_TIER_2}")
        print(f"Next day premium: ${MIN_PREMIUM_NEXT_DAY}")
        print(f"Delta search range: {DELTA_SEARCH_RANGE}")
        
        # Validate values
        assert DEFAULT_TRADE_QUANTITY == 30, "Default quantity should be 30"
        assert SPREAD_WIDTH == 10, "Spread width should be 10"
        assert MIN_PREMIUM_TIER_1 == 55, "Tier 1 premium should be $55"
        assert MIN_PREMIUM_TIER_2 == 45, "Tier 2 premium should be $45"
        assert MIN_PREMIUM_NEXT_DAY == 25, "Next day premium should be $25"
        assert DELTA_SEARCH_RANGE == [0.24, 0.23, 0.22, 0.21, 0.20], "Delta range incorrect"
        
        print("✅ Configuration values are correct")
        return True
        
    except Exception as e:
        print(f"❌ Configuration test error: {e}")
        return False

def test_quantity_manager():
    """Test trade quantity management functions."""
    print("\nTesting quantity manager...")
    
    try:
        from utils.quantity_manager import (
            load_trade_quantity, calculate_win_rate_last_10_trades
        )
        
        # Test loading default quantity
        quantity = load_trade_quantity()
        print(f"Current trade quantity: {quantity}")
        
        # Test win rate calculation (should handle missing file gracefully)
        win_rate, trade_count = calculate_win_rate_last_10_trades()
        print(f"Win rate: {win_rate:.1f}%, Trade count: {trade_count}")
        
        print("✅ Quantity manager tests passed")
        return True
        
    except Exception as e:
        print(f"❌ Quantity manager test error: {e}")
        return False

def test_pattern_utils():
    """Test pattern detection utilities."""
    print("\nTesting pattern utilities...")
    
    try:
        from utils.pattern_utils import determine_candle_color
        
        # Create mock bar objects
        class MockBar:
            def __init__(self, open_price, close_price):
                self.open = open_price
                self.close = close_price
        
        # Test candle color determination
        green_bar = MockBar(100, 105)  # Close > Open = Green
        red_bar = MockBar(105, 100)    # Close < Open = Red
        doji_bar = MockBar(100, 100)   # Close = Open = Doji
        
        assert determine_candle_color(green_bar) == "green"
        assert determine_candle_color(red_bar) == "red"
        assert determine_candle_color(doji_bar) == "doji"
        
        print("✅ Pattern utilities tests passed")
        return True
        
    except Exception as e:
        print(f"❌ Pattern utilities test error: {e}")
        return False

def test_trade_direction_logic():
    """Test trade direction determination."""
    print("\nTesting trade direction logic...")
    
    try:
        import asyncio
        from utils.trade_executor import determine_trade_direction
        
        async def test_directions():
            # Test bull case
            bull_direction = await determine_trade_direction(100, 95)  # price > HA
            assert bull_direction == 'bull', "Should be bull when price > HA"
            
            # Test bear case  
            bear_direction = await determine_trade_direction(95, 100)  # price < HA
            assert bear_direction == 'bear', "Should be bear when price < HA"
            
            print("Bull case: dailyClosePrice (100) > dailyCloseHA (95) = bull")
            print("Bear case: dailyClosePrice (95) < dailyCloseHA (100) = bear")
            
        asyncio.run(test_directions())
        print("✅ Trade direction logic tests passed")
        return True
        
    except Exception as e:
        print(f"❌ Trade direction test error: {e}")
        return False

def test_logger():
    """Test logging functionality."""
    print("\nTesting logger...")
    
    try:
        from utils.logger import save_trade_to_log, get_trade_summary, enhance_trade_info
        
        # Test trade info enhancement
        test_trade = {
            'date': '2024-01-15 15:55:00',
            'sell_strike': 620,
            'buy_strike': 630,
            'option_type': 'C',
            'quantity': 30,
            'dailyClosePrice': 625,
            'dailyCloseHA': 620,
            'status': 'Open'
        }
        
        enhanced = enhance_trade_info(test_trade)
        
        # Verify enhancements
        assert 'spread' in enhanced, "Spread should be added"
        assert 'price_difference' in enhanced, "Price difference should be calculated"
        assert enhanced['spread'] == 'C620/C630', "Spread format should be correct"
        assert enhanced['price_difference'] == 5.0, "Price difference should be 5.0"
        
        print(f"Enhanced spread format: {enhanced['spread']}")
        print(f"Price difference: {enhanced['price_difference']}")
        
        # Test trade summary (should handle empty file)
        summary = get_trade_summary()
        print(f"Trade summary: {summary}")
        
        print("✅ Logger tests passed")
        return True
        
    except Exception as e:
        print(f"❌ Logger test error: {e}")
        return False

def main():
    """Run all tests."""
    print("=" * 60)
    print("HEIKIN-ASHI TRADING ALGORITHM - COMPONENT TESTS")
    print("=" * 60)
    
    tests = [
        test_imports,
        test_configuration,
        test_quantity_manager,
        test_pattern_utils,
        test_trade_direction_logic,
        test_logger
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"❌ Test {test.__name__} failed with error: {e}")
    
    print("\n" + "=" * 60)
    print(f"TEST RESULTS: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! The algorithm is ready to use.")
    else:
        print("⚠️ Some tests failed. Please check the errors above.")
    print("=" * 60)

if __name__ == "__main__":
    main()
