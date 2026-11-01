"""Download the free data from FRED and save it in data/. Run: python scripts/download_data.py

Spots: Federal Reserve H.10 daily rates, last fixing of each month,
       stored as units of currency per 1 USD.
Rates: OECD 3-month interbank rates (FRED series IR3TIB01...), % per year.
"""
import pandas as pd

URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id="
START = "1998-12-01"

# FRED spot series. True = quoted in USD per unit (like EUR/USD), so we invert it.
SPOTS = {"AUD": ("DEXUSAL", True), "CAD": ("DEXCAUS", False), "CHF": ("DEXSZUS", False),
         "EUR": ("DEXUSEU", True), "GBP": ("DEXUSUK", True), "JPY": ("DEXJPUS", False),
         "NOK": ("DEXNOUS", False), "NZD": ("DEXUSNZ", True), "SEK": ("DEXSDUS", False)}
RATES = {"AUD": "AU", "CAD": "CA", "CHF": "CH", "EUR": "EZ", "GBP": "GB",
         "JPY": "JP", "NOK": "NO", "NZD": "NZ", "SEK": "SE", "USD": "US"}


def fred(series_id):
    df = pd.read_csv(URL + series_id, index_col=0, parse_dates=True, na_values=".")
    return df.iloc[:, 0].dropna()


spots = {}
for ccy, (sid, invert) in SPOTS.items():
    s = fred(sid)
    spots[ccy] = 1 / s if invert else s
spots = pd.DataFrame(spots).resample("ME").last()
spots = spots[spots.index >= START].round(6)
spots.index.name = "date"
spots.to_csv("data/fx_spot.csv")
print("fx_spot.csv saved")

rates = {ccy: fred(f"IR3TIB01{code}M156N") for ccy, code in RATES.items()}
rates = pd.DataFrame(rates).resample("ME").last()   # dates moved to month end
rates = rates[rates.index >= START].round(4)
rates.index.name = "date"
rates.to_csv("data/short_rates.csv")
print("short_rates.csv saved")
