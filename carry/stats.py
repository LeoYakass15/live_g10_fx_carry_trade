"""Performance statistics and crash analysis."""
import numpy as np
import pandas as pd

# Crash episodes: (first month, last month)
CRASHES = {
    "GFC 2008": ("2008-08", "2008-12"),
    "SNB Jan 2015": ("2015-01", "2015-01"),
    "Covid 2020": ("2020-02", "2020-03"),
}


def wealth(returns):
    """Value of 1 invested."""
    return (1 + returns).cumprod()


def drawdown(returns):
    w = wealth(returns)
    return w / w.cummax() - 1


def perf_stats(returns):
    years = len(returns) / 12
    return {
        "return_%": 100 * (wealth(returns).iloc[-1] ** (1 / years) - 1),
        "vol_%": 100 * returns.std() * np.sqrt(12),
        "sharpe": returns.mean() / returns.std() * np.sqrt(12),
        "skew": returns.skew(),
        "max_dd_%": 100 * drawdown(returns).min(),
        "worst_month_%": 100 * returns.min(),
        "positive_months_%": 100 * (returns > 0).mean(),
    }


def perf_table(strategies):
    return pd.DataFrame({name: perf_stats(r) for name, r in strategies.items()}).T


def annual_returns(strategies):
    """Calendar-year returns in %."""
    return pd.DataFrame({name: 100 * ((1 + r).groupby(r.index.year).prod() - 1)
                         for name, r in strategies.items()})


def crash_table(pnl, contrib):
    """Loss in each crash, split into spot and carry, plus the worst position."""
    rows = {}
    for name, (start, end) in CRASHES.items():
        p = pnl.loc[start:end]
        c = contrib.loc[start:end].sum()
        rows[name] = {
            "total_%": 100 * ((1 + p["total"]).prod() - 1),
            "spot_%": 100 * p["spot"].sum(),
            "carry_%": 100 * p["carry"].sum(),
            "worst_position": c.idxmin(),
            "worst_position_%": 100 * c.min(),
        }
    return pd.DataFrame(rows).T


def time_in_book(weights):
    """% of months each currency was long, short or out."""
    return pd.DataFrame({
        "long_%": 100 * (weights > 0).mean(),
        "short_%": 100 * (weights < 0).mean(),
        "out_%": 100 * (weights == 0).mean(),
    }).sort_values("long_%", ascending=False)
