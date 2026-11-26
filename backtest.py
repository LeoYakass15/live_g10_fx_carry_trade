"""
G10 FX carry trade, version 2: the carry is read from real 1-month forward points (Bloomberg).

Rule: at each month-end, compute the carry of the 10 G10 currencies against the USD from their
1-month forward. Buy the 3 currencies that pay the most, sell the 3 that pay the least, equal
weights, through 1-month forwards. Hold one month, then rank again.

Run:  python backtest.py
Data: Bloomberg 1M forward points (month-end, Feb 2004 - Oct 2026, not published), FRED spots
      and OECD 3-month rates (free), Ken French US market factor (free).
"""
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.stats import norm, skew, kurtosis
import statsmodels.api as sm

# ---------------------------------------------------------------- settings
N_LEGS = 3               # 3 currencies long, 3 short
COST = 0.0002            # 2 bp per USD traded (bid/ask of a G10 forward); the whole book rolls every month
VOL_WINDOW = 12          # months of spot returns used for the volatility (rule 2 and rule 3)
CRISIS_PCT = 0.90        # rule 3: halve the book when FX volatility is above its 90th percentile so far
TEST_START = "2020-01-31"    # 2005-2019 to choose, 2020-2026 opened once at the end
CCY = ["AUD", "CAD", "CHF", "EUR", "GBP", "JPY", "NOK", "NZD", "SEK"]   # the USD is the 10th currency
QUOTED_IN_USD = ["EUR", "GBP", "AUD", "NZD"]  # Bloomberg quotes EURUSD, GBPUSD... the others as USDJPY, USDCHF...
PIP = {c: 0.01 if c == "JPY" else 0.0001 for c in CCY}


# ---------------------------------------------------------------- 1. data
def load_spots():
    """Month-end spots from FRED, in units of currency per 1 USD."""
    s = pd.read_csv("data/fx_spot_fred.csv", index_col=0, parse_dates=True)
    s.index = s.index + pd.offsets.MonthEnd(0)
    return s[CCY]


def load_points():
    """Bloomberg 1-month forward points at each month-end (Last Price, in pips)."""
    p = pd.read_csv("data/bloomberg/fwd_points_1m.csv", index_col=0, parse_dates=True)
    p.index = p.index + pd.offsets.MonthEnd(0)
    return p[CCY]


def forwards(spots, points):
    """1-month outright forward, in units of currency per USD.
    Bloomberg adds the points to the spot in its own quote (EURUSD or USDJPY), so I convert."""
    fwd = pd.DataFrame(index=points.index, columns=CCY, dtype=float)
    for c in CCY:
        s, pts = spots[c].reindex(points.index), points[c] * PIP[c]
        fwd[c] = 1 / (1 / s + pts) if c in QUOTED_IN_USD else s + pts
    return fwd


def carry_and_returns(spots, fwd):
    """carry : what a 1M forward locks in (long the currency, short USD), known at month-end t.
                 Positive when the currency's interest rate is above the USD rate.
       ret   : what the forward bought at t actually earns at t+1 = carry + spot move.
       Row t of ret = month t-1 -> t, using the forward of t-1."""
    carry = fwd / spots.reindex(fwd.index) - 1
    ret = (fwd.shift(1) / spots.reindex(fwd.index) - 1).iloc[1:]
    spot_part = (spots.shift(1) / spots - 1).reindex(ret.index)
    return carry, ret, spot_part


def load_oecd_carry(index):
    """Version 1 of the project: carry approximated by OECD 3-month rates (i_k - i_USD) / 12."""
    r = pd.read_csv("data/oecd_rates_3m.csv", index_col=0, parse_dates=True).ffill(limit=1)
    r.index = r.index + pd.offsets.MonthEnd(0)
    return (r[CCY].sub(r["USD"], axis=0) / 100 / 12).reindex(index)


def load_market():
    ff = pd.read_csv("data/ken_french/F-F_Research_Data_Factors.csv", skiprows=4, index_col=0)
    ff.index = ff.index.astype(str).str.strip()
    ff = ff[ff.index.str.fullmatch(r"\d{6}")].astype(float) / 100
    ff.index = pd.to_datetime(ff.index, format="%Y%m") + pd.offsets.MonthEnd(0)
    return ff["Mkt-RF"]


# ---------------------------------------------------------------- 2. strategy
def weights_from_score(score):
    """Rank the 10 currencies (the 9 + the USD with a score of 0), long the 3 best, short the 3 worst.
    The USD leg has no position: being 'long USD' just means the shorts are funded in USD."""
    full = score.copy()
    full["USD"] = 0.0
    rank = full.rank(axis=1, ascending=False)
    n = full.notna().sum(axis=1)
    w = (rank <= N_LEGS).astype(float) / N_LEGS - (rank > n.values[:, None] - N_LEGS).astype(float) / N_LEGS
    return w[CCY].where(score.notna(), 0.0)


def run(weights, ret, size=1.0):
    """Monthly P&L after costs. Weights decided at month-end t are held during month t+1."""
    w = weights.shift(1).reindex(ret.index).fillna(0).mul(size, axis=0)
    gross = (w * ret).sum(axis=1)
    traded = w.abs().sum(axis=1) + w.diff().abs().sum(axis=1).clip(upper=w.abs().sum(axis=1))
    pnl = gross - traded * COST                       # roll of the whole book + switches
    return pnl[w.abs().sum(axis=1) > 0], w


def fx_vol(spot_part, window=VOL_WINDOW):
    """Annualised volatility of each currency against the USD, known at month-end t."""
    return spot_part.rolling(window).std() * np.sqrt(12)


def crisis_size(spot_part):
    """Rule 3: 1 normally, 0.5 when the average G10 FX vol is above its 90th percentile
    measured on the past only (expanding window, at least 3 years of history)."""
    avg = fx_vol(spot_part, 6).mean(axis=1)
    threshold = avg.expanding(36).quantile(CRISIS_PCT)
    size = pd.Series(1.0, index=avg.index).where(~(avg > threshold), 0.5)
    return size.shift(1)                              # decided at t, applied in t+1


# ---------------------------------------------------------------- 3. statistics (same as my other backtests)
def stats(pnl):
    n = len(pnl)
    sr = pnl.mean() / pnl.std() * np.sqrt(12)
    nav = (1 + pnl).cumprod()
    return {"Return (ann.)": pnl.mean() * 12, "Vol (ann.)": pnl.std() * np.sqrt(12), "Sharpe": sr,
            "t-stat": sr * np.sqrt(n / 12), "Max drawdown": (nav / nav.cummax() - 1).min(),
            "Skew": skew(pnl), "Worst month": pnl.min(), "Months": n}


def deflated_sharpe(pnl, trial_sharpes):
    """Bailey and Lopez de Prado (2014). Probability that the true Sharpe is above zero,
    knowing we tried N versions (trial_sharpes = monthly Sharpes of every trial)."""
    n_trials = len(trial_sharpes)
    sr = pnl.mean() / pnl.std()
    euler = 0.5772
    sr0 = np.std(trial_sharpes, ddof=1) * ((1 - euler) * norm.ppf(1 - 1 / n_trials)
                                           + euler * norm.ppf(1 - 1 / (n_trials * np.e)))
    g3, g4 = skew(pnl), kurtosis(pnl, fisher=False)
    z = (sr - sr0) * np.sqrt(len(pnl) - 1) / np.sqrt(1 - g3 * sr + (g4 - 1) / 4 * sr ** 2)
    return norm.cdf(z), sr0 * np.sqrt(12)


# ---------------------------------------------------------------- 4. main
if __name__ == "__main__":
    spots, points = load_spots(), load_points()
    fwd = forwards(spots, points)
    carry, ret, spot_part = carry_and_returns(spots, fwd)
    vol = fx_vol(spot_part).reindex(carry.index)
    oecd = load_oecd_carry(carry.index)
    print(f"Data: {carry.index[0]:%b %Y} - {carry.index[-1]:%b %Y}, {len(ret)} monthly returns")
    print("Average carry per year (forward points):\n", (carry.mean() * 12).round(4).to_string())

    # the 3 rules, written in my plan before I ran anything
    rules = {
        "1. Carry (3 long / 3 short)": (weights_from_score(carry), 1.0),
        "2. Carry / volatility": (weights_from_score(carry / vol), 1.0),
        "3. Carry + crisis filter": (weights_from_score(carry), crisis_size(spot_part).reindex(ret.index).fillna(1)),
    }
    pnls = {name: run(w, ret, size)[0] for name, (w, size) in rules.items()}
    common = pd.concat(pnls, axis=1).dropna().index            # same months for every rule
    pnls = {k: v.loc[common] for k, v in pnls.items()}

    # version 1 (OECD rates) on the same months, for comparison: same rule, other carry measure
    w_v1 = weights_from_score(oecd)
    pnl_v1 = run(w_v1, ret)[0].reindex(common).dropna()

    # trials log: every version I have ever tried on this trade, chosen on 2005-2019 only.
    # The two lines of version 1 (Oct 2026) count too: I already looked at them.
    choose = common[common < TEST_START]
    trials = [{"version": "v1 (Oct 2026)", "rule": "Carry from OECD 3M rates, 3/3", "pnl": run(w_v1, ret)[0]},
              {"version": "v1 (Oct 2026)", "rule": "Same + 12-month vol targeting",
               "pnl": run(w_v1, ret, (0.10 / run(w_v1, ret)[0].rolling(12).std().shift(1) / np.sqrt(12))
                          .clip(upper=2).reindex(ret.index))[0]}]
    trials += [{"version": "v2 (Nov 2026)", "rule": k, "pnl": v} for k, v in pnls.items()]
    log = []
    for t in trials:
        p = t["pnl"].reindex(choose).dropna()
        s = stats(p)
        log.append({"version": t["version"], "rule": t["rule"], "sharpe_2004_2019": round(s["Sharpe"], 3),
                    "t_stat": round(s["t-stat"], 2), "monthly_sharpe": p.mean() / p.std()})
    log = pd.DataFrame(log)
    log.drop(columns="monthly_sharpe").to_csv("results/trials_log.csv", index=False)
    print("\nTrials (2005-2019):\n", log.drop(columns="monthly_sharpe").to_string(index=False))

    # choice on 2005-2019: the best v2 rule. Then the test period is opened once.
    best = max(pnls, key=lambda k: stats(pnls[k].loc[choose])["Sharpe"])
    pnl = pnls[best]
    dsr, lucky = deflated_sharpe(pnl.loc[choose], log["monthly_sharpe"])
    print(f"\nRule chosen on 2005-2019: {best}")

    table = pd.DataFrame({f"{best[:2]} 2005-2019 (choice)": stats(pnl.loc[choose]),
                          f"{best[:2]} 2020-2026 (test)": stats(pnl.loc[TEST_START:]),
                          f"{best[:2]} 2005-2026": stats(pnl)})
    for k, v in pnls.items():
        if k != best:
            table[f"{k[:2]} 2005-2026"] = pd.Series(stats(v))
    table["v1 OECD 2005-2026"] = pd.Series(stats(pnl_v1))
    print("\n", table.round(3).to_string())
    print(f"\nTrials: {len(log)} | Sharpe the best trial would show by luck: {lucky:.2f}"
          f" | Deflated Sharpe 2005-2019: {dsr:.3f}")
    table.round(4).to_csv("results/summary.csv")
    pd.Series({"rule": best, "n_trials": len(log), "lucky_sharpe": round(lucky, 3),
               "dsr_2004_2019": round(dsr, 4)}).to_csv("results/dsr.csv", header=False)

    # where the money comes from: carry part vs spot part of the chosen rule
    w = rules[best][0].shift(1).reindex(ret.index).fillna(0).mul(rules[best][1], axis=0).loc[common]
    carry_part = (w * carry.shift(1).reindex(common)).sum(axis=1)
    spot_pnl = pnl - carry_part
    split = pd.Series({"carry per year": carry_part.mean() * 12, "spot per year": spot_pnl.mean() * 12,
                       "costs per year": (pnl - (w * ret.loc[common]).sum(axis=1)).mean() * 12})
    print("\nWhere the return comes from:\n", split.round(4).to_string())
    split.round(4).to_csv("results/return_split.csv", header=False)
    pd.DataFrame({"pnl": pnl, "carry_part": carry_part, "spot_part": spot_pnl}).to_csv(
        "results/monthly_pnl.csv", float_format="%.6f")

    # forward points vs OECD rates: how far is the v1 approximation from what a forward really pays?
    gap = ((carry - oecd) * 12 * 1e4).dropna(how="all")       # bp per year
    gap_table = pd.DataFrame({"mean gap (bp/yr)": gap.mean(), "mean abs gap (bp/yr)": gap.abs().mean(),
                              "corr of monthly carry": [carry[c].corr(oecd[c]) for c in CCY]}).round(1)
    gap_table["corr of monthly carry"] = [round(carry[c].corr(oecd[c]), 2) for c in CCY]
    same_book = (weights_from_score(carry).loc[common] == w_v1.loc[common]).all(axis=1).mean()
    print("\nForward points vs OECD rates:\n", gap_table.to_string(),
          f"\nMonths where v1 and v2 pick exactly the same 6 currencies: {same_book:.0%}")
    gap_table.to_csv("results/points_vs_oecd.csv")

    # crashes
    episodes = {"Aug 2007 (quant crisis)": ("2007-08", "2007-08"), "Sep-Dec 2008 (Lehman)": ("2008-09", "2008-12"),
                "Jan 2015 (CHF floor removed)": ("2015-01", "2015-01"), "Mar 2020 (Covid)": ("2020-03", "2020-03"),
                "2022 (Fed hikes)": ("2022-01", "2022-12")}
    crashes = pd.DataFrame({k: {n: (1 + p.loc[a:b]).prod() - 1 for n, (a, b) in episodes.items()}
                            for k, p in pnls.items()})
    print("\nCrashes:\n", crashes.round(3).to_string())
    crashes.round(4).to_csv("results/crashes.csv")

    # is it just equity risk? regression on the US stock market
    mkt = load_market()
    both = pd.concat([pnl, mkt], axis=1, join="inner").dropna()
    reg = sm.OLS(both.iloc[:, 0], sm.add_constant(both.iloc[:, 1])).fit(cov_type="HAC", cov_kwds={"maxlags": 6})
    down = both[both.iloc[:, 1] < -0.05]
    regression = pd.Series({"alpha_per_year": reg.params.iloc[0] * 12, "alpha_t": reg.tvalues.iloc[0],
                            "beta_market": reg.params.iloc[1], "beta_t": reg.tvalues.iloc[1], "r2": reg.rsquared,
                            "months_market_below_-5%": len(down), "avg_carry_pnl_those_months": down.iloc[:, 0].mean()})
    print("\nRegression on the US market:\n", regression.round(3).to_string())
    regression.round(4).to_csv("results/regression.csv", header=False)

    # what the book holds today (last month-end in the data)
    last = carry.index[-1]
    today = pd.DataFrame({"carry_per_year": carry.loc[last] * 12, "vol": vol.loc[last],
                          "weight": rules[best][0].loc[last]}).sort_values("carry_per_year", ascending=False)
    print(f"\nPositions at {last:%d %b %Y}:\n", today.round(4).to_string())
    today.round(4).to_csv("results/positions_last_month.csv")

    # ------------------------------------------------------------ charts
    plt.figure(figsize=(10, 5))
    for k, p in pnls.items():
        (1 + p).cumprod().plot(label=k, lw=2 if k == best else 1.2)
    (1 + pnl_v1).cumprod().plot(label="v1: carry from OECD rates", color="grey", ls="--")
    plt.axvspan(pd.Timestamp(TEST_START), common[-1], color="grey", alpha=0.15, label="Test period")
    plt.legend(); plt.title("Growth of 1 USD, G10 carry after costs, 2005-2026"); plt.tight_layout()
    plt.savefig("results/1_equity_curve.png", dpi=120); plt.close()

    plt.figure(figsize=(10, 4))
    carry_part.cumsum().plot(label="Carry (known in advance)", color="tab:green", lw=2)
    spot_pnl.cumsum().plot(label="Spot moves (the risk)", color="tab:orange", lw=2)
    pnl.cumsum().plot(label="Total", color="black")
    plt.axhline(0, color="grey", lw=0.8); plt.legend(); plt.title(f"Where the return comes from ({best})")
    plt.tight_layout(); plt.savefig("results/2_carry_vs_spot.png", dpi=120); plt.close()

    fig, ax = plt.subplots(1, 2, figsize=(11, 4), sharey=False)
    for a, c in zip(ax, ["JPY", "AUD"]):
        (carry[c] * 12 * 100).plot(ax=a, label="1M forward points (v2)", lw=1.5)
        (oecd[c] * 12 * 100).plot(ax=a, label="OECD 3M rate gap (v1)", ls="--")
        a.set_title(f"Carry of {c} against USD, % per year"); a.axhline(0, color="grey", lw=0.8)
    ax[0].legend(); plt.tight_layout(); plt.savefig("results/3_points_vs_oecd.png", dpi=120); plt.close()

    plt.figure(figsize=(8, 4))
    s = log.set_index("rule")["sharpe_2004_2019"]
    s.plot.barh(color=["grey", "grey"] + ["tab:blue"] * (len(s) - 2))
    plt.axvline(lucky, color="red", ls="--", label=f"Best of {len(s)} by luck ({lucky:.2f})")
    plt.xlabel("Sharpe 2005-2019"); plt.legend(); plt.title("Every version I tried")
    plt.tight_layout(); plt.savefig("results/4_trials.png", dpi=120); plt.close()
