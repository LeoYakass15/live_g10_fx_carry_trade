"""G10 carry trade backtest. Run: python run_analysis.py

Writes the charts and tables to results/.
"""
import os

import pandas as pd

from carry import plots
from carry.data import load_data, monthly_returns
from carry.stats import annual_returns, crash_table, perf_table, time_in_book
from carry.strategy import (backtest, carry_weights, contributions, dollar_weights,
                            pair_weights, vol_target)

N = 3              # number of currencies long and short
COST_BP = 2        # bid/ask paid on the whole book at each monthly roll
TARGET_VOL = 0.08  # for the vol-targeted version
OUT = "results"

pd.set_option("display.width", 160)
pd.set_option("display.max_columns", 20)
pd.set_option("display.precision", 2)
os.makedirs(OUT, exist_ok=True)

# Data
spots, rates = load_data()
spot_ret, carry = monthly_returns(spots, rates)
print(f"Data: {spot_ret.index[0]:%Y-%m} to {spot_ret.index[-1]:%Y-%m}, {len(spot_ret)} months")

# 1. Carry book and two benchmarks
w = carry_weights(rates, N)
pnl = backtest(w, spot_ret, carry, COST_BP)
audjpy = backtest(pair_weights(rates, "AUD", "JPY"), spot_ret, carry, COST_BP)
dollar = backtest(dollar_weights(rates), spot_ret, carry, COST_BP)

strategies = {
    "Carry G10 (3 long / 3 short)": pnl["total"],
    "AUD/JPY carry": audjpy["total"],
    "Long G9 vs USD (no signal)": dollar["total"],
}
perf = perf_table(strategies)
print("\n== Performance ==")
print(perf)
perf.to_csv(f"{OUT}/performance.csv")
annual_returns(strategies).to_csv(f"{OUT}/annual_returns.csv")

# 2. Where the return comes from (% per year)
split = 1200 * pnl.mean()
print("\n== Return split, % per year ==")
print(split.round(2))
split.to_csv(f"{OUT}/return_split.csv", header=["pct_per_year"])

# 3. Crashes
contrib = contributions(w, spot_ret, carry)
crashes = crash_table(pnl, contrib)
print("\n== Crash episodes (%) ==")
print(crashes)
crashes.to_csv(f"{OUT}/crash_episodes.csv")

worst = 100 * pnl["total"].nsmallest(10)
print("\n== 10 worst months (%) ==")
print(worst.round(2))
worst.to_csv(f"{OUT}/worst_months.csv", header=["return_pct"])

book = time_in_book(w)
print("\n== % of months in the book ==")
print(book.round(0))
book.to_csv(f"{OUT}/time_in_book.csv")

# 4. Vol targeting (needs 12 months of history, so compare on the same months)
scaled, leverage = vol_target(pnl["total"], TARGET_VOL)
vt = perf_table({"Carry G10": pnl["total"].loc[scaled.index], "Carry G10, vol-targeted": scaled})
print("\n== Vol targeting (same period) ==")
print(vt)
vt.to_csv(f"{OUT}/vol_target.csv")
pnl.join(scaled.rename("total_vol_targeted")).to_csv(f"{OUT}/monthly_pnl.csv")

# 5. Charts
plots.plot_rates(rates, f"{OUT}/01_short_rates.png")
plots.plot_positions(w, f"{OUT}/02_positions.png")
plots.plot_cumulative(strategies, f"{OUT}/03_cumulative_returns.png")
plots.plot_carry_vs_spot(pnl, f"{OUT}/04_carry_vs_spot.png")
plots.plot_drawdowns(strategies, f"{OUT}/05_drawdowns.png")
plots.plot_distribution(pnl["total"], f"{OUT}/06_return_distribution.png")
plots.plot_crash_contributions(contrib, f"{OUT}/07_crash_contributions.png")
plots.plot_vol_target(pnl["total"], scaled, leverage, f"{OUT}/08_vol_target.png")
print(f"\nCharts and tables saved in {OUT}/")
