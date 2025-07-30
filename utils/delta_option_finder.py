from ib_insync import Option
import asyncio
from config.settings import DELTA_SEARCH_RANGE, SPREAD_WIDTH

async def find_option_by_delta_range(ib, symbol, expiry, option_type, target_deltas=None):
    """
    Find options with delta close to the target values in descending order.
    
    Args:
        ib: IBKR connection
        symbol: Stock symbol (e.g., 'SPY')
        expiry: Option expiry date
        option_type: 'C' for Call, 'P' for Put
        target_deltas: List of delta values to search in order (default: DELTA_SEARCH_RANGE)
    
    Returns:
        dict with 'option' and 'delta' keys, or None if not found
    """
    if target_deltas is None:
        target_deltas = DELTA_SEARCH_RANGE
    
    try:
        # Get all options for the expiry
        from ib_insync import Stock
        stock = Stock(symbol, 'SMART', 'USD')
        await ib.qualifyContractsAsync(stock)
        
        # Get option chain
        chains = await ib.reqSecDefOptParamsAsync(
            stock.symbol, '', stock.secType, stock.conId
        )
        
        if not chains:
            print(f"No option chains found for {symbol}")
            return None
        
        # Find the right expiry
        chain = None
        for c in chains:
            if expiry in c.expirations:
                chain = c
                break
        
        if not chain:
            print(f"Expiry {expiry} not found in option chains")
            return None
        
        # Search through delta values in order
        for target_delta in target_deltas:
            print(f"Searching for {option_type} options with delta near {target_delta}")
            
            best_option = None
            best_delta = None
            min_delta_diff = float('inf')
            
            # Check several strikes around the current price
            for strike in chain.strikes:
                try:
                    option = Option(symbol, expiry, strike, option_type, 'SMART')
                    await ib.qualifyContractsAsync(option)
                    
                    # Get market data to calculate delta
                    data = ib.reqMktData(option, '', False, False)
                    await asyncio.sleep(1)  # Wait for data
                    
                    model_greeks = getattr(data, 'modelGreeks', None)
                    if model_greeks:
                        delta = getattr(model_greeks, 'delta', None)
                        if delta is not None:
                            # For puts, delta is negative, so we take absolute value
                            abs_delta = abs(delta)
                            delta_diff = abs(abs_delta - target_delta)
                            
                            if delta_diff < min_delta_diff:
                                min_delta_diff = delta_diff
                                best_option = option
                                best_delta = abs_delta
                    
                    ib.cancelMktData(option)
                    
                except Exception as e:
                    print(f"Error processing strike {strike}: {e}")
                    continue
            
            # If we found an option with this delta, return it
            if best_option is not None:
                print(f"Found {option_type} option: strike {best_option.strike}, delta {best_delta:.3f}")
                return {
                    'option': best_option,
                    'delta': best_delta
                }
        
        print(f"No suitable {option_type} options found with any target delta")
        return None
        
    except Exception as e:
        print(f"Error finding option by delta: {e}")
        return None

async def find_both_options_for_spread(ib, symbol, expiry):
    """
    Find both Call and Put options with deltas close to target values.
    Searches independently for each option type.
    
    Returns:
        dict with 'call' and 'put' keys, each containing option and delta info
    """
    results = {}
    
    # Find Call option
    call_result = await find_option_by_delta_range(ib, symbol, expiry, 'C')
    if call_result:
        results['call'] = call_result
    else:
        results['call'] = None
    
    # Find Put option  
    put_result = await find_option_by_delta_range(ib, symbol, expiry, 'P')
    if put_result:
        results['put'] = put_result
    else:
        results['put'] = None
    
    return results

async def calculate_spread_premium(ib, sell_option, buy_option):
    """
    Calculate the premium that can be collected from a spread.
    
    Returns:
        Premium per contract that can be collected
    """
    try:
        # Get market data for both legs
        sell_data = ib.reqMktData(sell_option, '', False, False)
        buy_data = ib.reqMktData(buy_option, '', False, False)
        await asyncio.sleep(2)  # Wait for market data
        
        # Calculate mid prices
        sell_mid = (sell_data.bid + sell_data.ask) / 2 if sell_data.bid and sell_data.ask else 0
        buy_mid = (buy_data.bid + buy_data.ask) / 2 if buy_data.bid and buy_data.ask else 0
        
        ib.cancelMktData(sell_option)
        ib.cancelMktData(buy_option)
        
        # Premium is what we collect (sell - buy)
        premium = sell_mid - buy_mid
        return max(0, premium * 100)  # Convert to dollars per contract
        
    except Exception as e:
        print(f"Error calculating spread premium: {e}")
        return 0
