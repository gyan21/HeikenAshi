from ib_insync import Option
import asyncio
from config.settings import DELTA_SEARCH_RANGE

async def find_option_by_delta_range(ib, symbol, expiry, option_type, target_deltas=None, spread_width=10):
    """
    Find options with delta close to the target values and ensure a valid spread width.

    Args:
        ib: IBKR connection
        symbol: Stock symbol (e.g., 'SPY')
        expiry: Option expiry date
        option_type: 'C' for Call, 'P' for Put
        target_deltas: List of delta values to search in order (default: DELTA_SEARCH_RANGE)
        spread_width: Minimum spread width between short and long legs.

    Returns:
        dict with 'short_option', 'long_option', and 'delta' keys, or None if not found.
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

        # Find the chain for the given expiry
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

            best_short_option = None
            best_long_option = None
            best_delta = None
            min_delta_diff = float('inf')

            # Get current price
            current_price = ib.reqMktData(stock, '', False, False).last
            await asyncio.sleep(1)  # Wait for market data

            # Filter strikes based on option type
            relevant_strikes = []
            if option_type == 'C':
                relevant_strikes = [strike for strike in chain.strikes if strike >= current_price][:10]
            elif option_type == 'P':
                relevant_strikes = [strike for strike in chain.strikes if strike <= current_price][-10:]

            # Check relevant strikes
            for strike in relevant_strikes:
                try:
                    short_option = Option(symbol, expiry, strike, option_type, 'SMART')
                    await ib.qualifyContractsAsync(short_option)

                    # Get market data to calculate delta
                    data = ib.reqMktData(short_option, '', False, False)
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
                                best_short_option = short_option
                    
                                # Find long leg for the spread
                                long_strike = strike + spread_width if option_type == 'C' else strike - spread_width

                                # Ensure long_strike is valid
                                while long_strike not in chain.strikes:
                                    if option_type == 'C':
                                        long_strike += 1  # Move 1 strike up for call options
                                    elif option_type == 'P':
                                        long_strike -= 1  # Move 1 strike down for put options

                                # Create long option contract
                                long_option = Option(symbol, expiry, long_strike, option_type, 'SMART')
                                await ib.qualifyContractsAsync(long_option)
                                
                                best_long_option = long_option
                                best_delta = abs_delta

                                # Stop searching once desired delta is found
                                if delta_diff == 0:
                                    print(f"Exact match found for {option_type} option: short strike {strike}, long strike {long_strike}, delta {best_delta:.3f}")
                                    return {
                                        'short_option': best_short_option,
                                        'long_option': best_long_option,
                                        'delta': best_delta
                                    }

                    ib.cancelMktData(short_option)

                except Exception as e:
                    print(f"Error processing strike {strike}: {e}")
                    continue

            # If we found an option with this delta, return it
            if best_short_option is not None and best_long_option is not None:
                print(f"Found {option_type} option: short strike {best_short_option.strike}, long strike {best_long_option.strike}, delta {best_delta:.3f}")
                return {
                    'short_option': best_short_option,
                    'long_option': best_long_option,
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
