"""
Option utilities for the Heikin-Ashi trading algorithm.
Contains minimal helper functions for option chain operations.
"""

import datetime
from ib_insync import Stock

def get_next_option_expiry(for_additional_trades=False):
    """
    Calculate the next expiry date for options.
    For core Heikin-Ashi logic, exclude Friday expiry.
    For additional trades, use same-day expiry.
    """
    today = datetime.date.today()

    if for_additional_trades:
        # Same-day expiry for additional trades
        return today

    # Calculate next expiry excluding Friday
    next_expiry = today + datetime.timedelta(days=1)
    while next_expiry.weekday() == 4:  # Skip Friday
        next_expiry += datetime.timedelta(days=1)

    return next_expiry
