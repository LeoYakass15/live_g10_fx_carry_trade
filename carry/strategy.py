"""Carry trade portfolios and the monthly backtest."""
import numpy as np
import pandas as pd


def carry_weights(rates, n=3):
    """Each month: long the n highest yielders, short the n lowest, equal weights.

    Weights are +1/n and -1/n, so the book is dollar neutral (they sum to zero).
    """
    rank = rates.rank(axis=1, ascending=False, method="first")   # 1 = highest rate
    w = rates * 0.0
    w[rank <= n] = 1 / n
    w[rank > len(rates.columns) - n] = -1 / n
    return w


def pair_weights(rates, long_ccy, short_ccy):
    """One pair held all the time, e.g. long AUD / short JPY."""
    w = rates * 0.0
    w[long_ccy] = 1.0
    w[short_ccy] = -1.0
    return w


def dollar_weights(rates):
    """Long the 9 other currencies against the USD, no carry signal."""
    w = rates * 0.0 + 1 / 9
    w["USD"] = -1.0
    return w


def backtest(weights, spot_ret, carry, cost_bp=2):
    """Monthly P&L of a book of 1-month forwards.

    Weights chosen at the end of month t-1 are held during month t (no look-ahead).
    Each month the forwards expire and the whole book is rolled: cost = cost_bp x gross notional.
    """
    w = weights.shift(1).loc[spot_ret.index]
    pnl = pd.DataFrame({
        "spot": (w * spot_ret).sum(axis=1),
        "carry": (w * carry).sum(axis=1),
        "cost": -w.abs().sum(axis=1) * cost_bp / 10_000,
    })
    pnl["total"] = pnl["spot"] + pnl["carry"] + pnl["cost"]
    return pnl


def vol_target(returns, target=0.08, window=12, max_leverage=2):
    """Scale the position so that the last 12 months' volatility matches the target."""
    realised_vol = returns.rolling(window).std() * np.sqrt(12)
    leverage = (target / realised_vol).clip(upper=max_leverage).shift(1)   # known at t-1
    return (returns * leverage).dropna(), leverage.dropna()


def contributions(weights, spot_ret, carry):
    """P&L of each currency position, month by month."""
    w = weights.shift(1).loc[spot_ret.index]
    return w * (spot_ret + carry)
