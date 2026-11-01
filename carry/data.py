"""Load the market data and turn it into monthly returns."""
from pathlib import Path

import pandas as pd

DATA = Path(__file__).resolve().parent.parent / "data"
CURRENCIES = ["AUD", "CAD", "CHF", "EUR", "GBP", "JPY", "NOK", "NZD", "SEK", "USD"]


def load_spots(folder=DATA):
    """Month-end spots, in units of currency per 1 USD. USD itself = 1."""
    spots = pd.read_csv(Path(folder) / "fx_spot.csv", index_col="date", parse_dates=True)
    spots["USD"] = 1.0
    return spots[CURRENCIES]


def load_rates(folder=DATA):
    """3-month interbank rates, % per year, one column per currency."""
    rates = pd.read_csv(Path(folder) / "short_rates.csv", index_col="date", parse_dates=True)
    return rates[CURRENCIES].ffill(limit=1)   # a single missing month takes the previous value


def load_data(folder=DATA):
    """Spots and rates on the months where all 10 currencies have data.

    With the OECD series this is April 2002 (first JPY 3-month rate) to
    January 2026 (last EUR and GBP values published).
    """
    spots, rates = load_spots(folder), load_rates(folder)
    dates = spots.dropna().index.intersection(rates.dropna().index)
    dates = pd.date_range(dates[0], dates[-1], freq="ME")    # no hole allowed in between
    return spots.loc[dates], rates.loc[dates]


def monthly_returns(spots, rates):
    """Split the return of 'long 1 USD of currency k, funded in USD' into two parts.

    spot part  : the currency's move against the USD over the month
                 (spots are units per USD, so the currency gains when the spot falls)
    carry part : the rate differential i_k - i_USD earned over the month,
                 fixed at the start of the month (what a 1M forward locks in)

    Row t holds the return earned from the end of month t-1 to the end of month t.
    """
    spot_ret = spots.shift(1) / spots - 1
    carry = (rates.sub(rates["USD"], axis=0) / 100 / 12).shift(1)
    return spot_ret.iloc[1:], carry.iloc[1:]
