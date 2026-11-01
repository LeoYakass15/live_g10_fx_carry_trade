"""Unit tests (pytest). Run with: python -m pytest -q"""
import numpy as np
import pandas as pd

from carry.data import monthly_returns
from carry.stats import drawdown, perf_stats
from carry.strategy import backtest, carry_weights, pair_weights, vol_target

DATES = pd.date_range("2020-01-31", periods=4, freq="ME")
CCYS = ["AUD", "CAD", "CHF", "EUR", "GBP", "JPY", "NOK", "NZD", "SEK", "USD"]


def flat_rates():
    # AUD 5%, NZD 4.5%, ... JPY -0.1%, constant over time
    levels = [5.0, 2.0, -0.5, 0.0, 1.0, -0.1, 1.5, 4.5, 0.5, 3.0]
    return pd.DataFrame([levels] * len(DATES), index=DATES, columns=CCYS)


def test_weights_pick_highest_and_lowest_yielders():
    w = carry_weights(flat_rates(), 3).iloc[0]
    assert set(w[w > 0].index) == {"AUD", "NZD", "USD"}
    assert set(w[w < 0].index) == {"CHF", "JPY", "EUR"}
    assert np.isclose(w.sum(), 0) and np.isclose(w.abs().sum(), 2)


def test_constant_spots_earn_the_rate_differential():
    rates = flat_rates()
    spots = pd.DataFrame(1.0, index=DATES, columns=CCYS)
    spot_ret, carry = monthly_returns(spots, rates)
    pnl = backtest(pair_weights(rates, "AUD", "JPY"), spot_ret, carry, cost_bp=0)
    # long AUD 5%, short JPY -0.1%: 5.1% a year, 0.425% a month
    assert np.allclose(pnl["total"], 0.051 / 12)
    assert np.allclose(pnl["spot"], 0)


def test_spot_return_sign():
    # USD/JPY falls from 100 to 80: the yen gains 25% against the dollar
    spots = pd.DataFrame(1.0, index=DATES[:2], columns=CCYS)
    spots.loc[DATES[1], "JPY"] = 80.0
    spots.loc[DATES[0], "JPY"] = 100.0
    spot_ret, _ = monthly_returns(spots, flat_rates().iloc[:2])
    assert np.isclose(spot_ret["JPY"].iloc[0], 0.25)


def test_no_look_ahead():
    # weights decided at the end of month t-1 are used for month t
    rates = flat_rates()
    spots = pd.DataFrame(1.0, index=DATES, columns=CCYS)
    spot_ret, carry = monthly_returns(spots, rates)
    w = carry_weights(rates)
    w.iloc[-1] = 0.0                       # a change at the last date has no effect
    assert np.allclose(backtest(w, spot_ret, carry)["total"].iloc[:-1],
                       backtest(carry_weights(rates), spot_ret, carry)["total"].iloc[:-1])


def test_roll_cost():
    rates = flat_rates()
    spots = pd.DataFrame(1.0, index=DATES, columns=CCYS)
    spot_ret, carry = monthly_returns(spots, rates)
    pnl = backtest(carry_weights(rates), spot_ret, carry, cost_bp=2)
    assert np.allclose(pnl["cost"], -2 * 2 / 10_000)   # gross notional 2 x 2 bp


def test_drawdown_and_stats():
    r = pd.Series([0.1, -0.5, 0.2], index=pd.date_range("2020-01-31", periods=3, freq="ME"))
    assert np.isclose(drawdown(r).min(), -0.5)
    assert np.isclose(perf_stats(r)["worst_month_%"], -50)


def test_vol_target_scale():
    rng = np.random.default_rng(0)
    r = pd.Series(rng.normal(0, 0.04, 240), index=pd.date_range("2000-01-31", periods=240, freq="ME"))
    scaled, scale = vol_target(r, target=0.08, max_leverage=5)
    assert abs(scaled.std() * np.sqrt(12) - 0.08) < 0.02
    assert scale.max() <= 5
