"""Downloads the free data from FRED. Run once:  python scripts/download_spots.py

Spots: Federal Reserve H.10 rates, last fixing of each month, in units of currency per 1 USD.
Rates: OECD 3-month interbank rates (FRED series IR3TIB01...), % per year. Used only to compare
       with version 1 of the project.
"""
import pandas as pd

URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id="
START = "1998-12-01"
SPOTS = {"AUD": ("DEXUSAL", True), "CAD": ("DEXCAUS", False), "CHF": ("DEXSZUS", False),
         "EUR": ("DEXUSEU", True), "GBP": ("DEXUSUK", True), "JPY": ("DEXJPUS", False),
         "NOK": ("DEXNOUS", False), "NZD": ("DEXUSNZ", True), "SEK": ("DEXSDUS", False)}
RATES = {"AUD": "AU", "CAD": "CA", "CHF": "CH", "EUR": "EZ", "GBP": "GB",
         "JPY": "JP", "NOK": "NO", "NZD": "NZ", "SEK": "SE", "USD": "US"}


def fred(series_id):
    df = pd.read_csv(URL + series_id, index_col=0, parse_dates=True, na_values=".")
    return df.iloc[:, 0].dropna()


spots = {c: (1 / fred(s) if inverted else fred(s)) for c, (s, inverted) in SPOTS.items()}
spots = pd.DataFrame(spots).resample("ME").last().loc[START:].round(6)
spots.index.name = "date"
spots.to_csv("data/fx_spot_fred.csv")

rates = pd.DataFrame({c: fred(f"IR3TIB01{code}M156N") for c, code in RATES.items()})
rates = rates.resample("ME").last().loc[START:].round(4)
rates.index.name = "date"
rates.to_csv("data/oecd_rates_3m.csv")
print(spots.tail(), rates.tail())
