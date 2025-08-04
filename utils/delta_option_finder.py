from cmath import nan
import math
from ib_insync import Option
import asyncio
from config.settings import DELTA_SEARCH_RANGE

async def find_option_by_delta_range(ib, symbol, expiry, option_type, stockPrice, target_deltas=None, spread_width=10):
    """
    Search for put/call options with delta closest to target_deltas (0.24, 0.23, ..., 0.20).
    Returns first valid short/long leg pair found.
    """
    if target_deltas is None:
        target_deltas = [0.24, 0.23, 0.22, 0.21, 0.20]

    try:
        from ib_insync import Stock
        stock = Stock(symbol, 'SMART', 'USD')
        await ib.qualifyContractsAsync(stock)

        chains = await ib.reqSecDefOptParamsAsync(
            stock.symbol, '', stock.secType, stock.conId
        )

        if not chains:
            print(f"No option chains found for {symbol}")
            return None

        chain = next((c for c in chains if expiry in c.expirations), None)
        if not chain:
            print(f"Expiry {expiry} not found in option chains")
            return None

        # Get current price robustly
        data = ib.reqMktData(stock, '', True, False)
        await asyncio.sleep(5)
        current_price = data.last
        ib.cancelMktData(stock)
        if current_price is None or math.isnan(current_price):
            print("Could not get current stock price, using fallback")
            current_price = stockPrice

        # Strike selection
        if option_type == 'C':
            relevant_strikes = [strike for strike in chain.strikes if strike >= current_price][:10]
        else:
            relevant_strikes = [strike for strike in chain.strikes if strike <= current_price][-10:]

        # Delta search loop
        for target_delta in target_deltas:
            print(f"Searching for {option_type} options with delta near {target_delta}")
            for strike in relevant_strikes:
                try:
                    short_option = Option(symbol, expiry, strike, option_type, 'SMART')
                    await ib.qualifyContractsAsync(short_option)
                    data = ib.reqMktData(short_option, '', False, False)
                    await asyncio.sleep(1)
                    model_greeks = getattr(data, 'modelGreeks', None)
                    if model_greeks and model_greeks.delta is not None:
                        abs_delta = abs(model_greeks.delta)
                        delta_diff = abs(abs_delta - target_delta)
                        # Accept first found within reasonable tolerance (e.g., 0.01)
                        if delta_diff < 0.01 or abs_delta == target_delta:
                            # Find long leg
                            long_strike = strike + spread_width if option_type == 'C' else strike - spread_width
                            # Ensure long_strike is valid
                            while long_strike not in chain.strikes:
                                if option_type == 'C':
                                    long_strike += 1
                                else:
                                    long_strike -= 1
                            long_option = Option(symbol, expiry, long_strike, option_type, 'SMART')
                            await ib.qualifyContractsAsync(long_option)
                            ib.cancelMktData(short_option)
                            print(f"Found {option_type} spread: short {strike}, long {long_strike}, delta {abs_delta:.3f}")
                            return {
                                'short_option': short_option,
                                'long_option': long_option,
                                'delta': abs_delta
                            }
                    ib.cancelMktData(short_option)
                except Exception as e:
                    print(f"Error processing strike {strike}: {e}")
                    continue
        print(f"No suitable {option_type} options found with any target delta")
        return None
    except Exception as e:
        print(f"Error finding option by delta: {e}")
        return None

async def find_both_options_for_spread(ib, symbol, expiry, stockPrice):
    """
    Find both Call and Put options with deltas close to target values.
    Searches independently for each option type.

    Returns:
        dict with 'call' and 'put' keys, each containing option and delta info
    """
    results = {}

    # Find Call option
    call_result = await find_option_by_delta_range(ib, symbol, expiry, 'C', stockPrice)
    if call_result:
        results['call'] = call_result
    else:
        results['call'] = None

    # Find Put option
    put_result = await find_option_by_delta_range(ib, symbol, expiry, 'P', stockPrice)
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
