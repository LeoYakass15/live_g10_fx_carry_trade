"""
Live paper trading of the G10 carry book (rule 3 of the backtest: carry, 3 long / 3 short, crisis filter).

Every week I take a Bloomberg photo of the FRD screen at the Friday close (Pricing Date = Friday) of the 9 pairs (EURUSD, GBPUSD, AUDUSD,
NZDUSD, USDCAD, USDJPY, USDCHF, USDNOK, USDSEK) and add 9 lines to data/bloomberg/live/frd_fridays.csv:
    date, pair, spot, pts_1m_bid, pts_1m_ask        (spot and points as Bloomberg shows them)

A "month" runs from the last Friday of one month to the last Friday of the next. On the last
Friday, the carry of each currency is read from the 1M forward points of that photo, and the
new book is traded at the photo prices.

    python live.py positions   -> after the last Friday of a month: the new book
    python live.py week        -> every weekend: P&L of the week, chart, block for LIVE.md
    python live.py chart       -> the empty cone, before the first live week
"""
import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import backtest as bt

CAPITAL = 1_000_000                     # paper capital in USD
FRD = "data/bloomberg/live/frd_fridays.csv"
POSITIONS = "results/positions_live.csv"
PNL = "results/live_pnl.csv"
PAIR = {c: (c + "USD" if c in bt.QUOTED_IN_USD else "USD" + c) for c in bt.CCY}


def last_friday(date):
    d = pd.Timestamp(date) + pd.offsets.MonthEnd(0)
    return d - pd.Timedelta(days=(d.weekday() - 4) % 7)


def load_frd():
    """One row per Friday: spot (units per USD) and 1M forward (units per USD) of the 9 currencies."""
    raw = pd.read_csv(FRD, parse_dates=["date"])
    raw["ccy"] = raw.pair.str.replace("USD", "")
    raw["pts"] = (raw.pts_1m_bid + raw.pts_1m_ask) / 2 * raw.ccy.map(bt.PIP)
    usd_quote = raw.ccy.isin(bt.QUOTED_IN_USD)
    raw["s"] = np.where(usd_quote, 1 / raw.spot, raw.spot)
    raw["f"] = np.where(usd_quote, 1 / (raw.spot + raw.pts), raw.spot + raw.pts)
    spot = raw.pivot(index="date", columns="ccy", values="s")[bt.CCY]
    fwd = raw.pivot(index="date", columns="ccy", values="f")[bt.CCY]
    return spot.sort_index(), fwd.sort_index()


def month_end_spots(spot):
    """FRED month-ends for the history, then the last-Friday photos of the live months."""
    hist = bt.load_spots()
    fridays = spot[[d == last_friday(d) for d in spot.index]]
    fridays.index = fridays.index + pd.offsets.MonthEnd(0)
    return pd.concat([hist.loc[:fridays.index[0] - pd.Timedelta(days=1)] if len(fridays) else hist, fridays])


def new_positions():
    spot, fwd = load_frd()
    d = spot.index[-1]
    if d != last_friday(d):
        print(f"{d:%d %b %Y} is not the last Friday of the month: no rebalance."); return
    carry = fwd.loc[d] / spot.loc[d] - 1
    monthly = month_end_spots(spot)
    size = bt.crisis_size(monthly.shift(1) / monthly - 1).shift(-1).iloc[-1]   # known at d, for the month to come
    size = 1.0 if np.isnan(size) else size
    weight = bt.weights_from_score(carry.to_frame().T).iloc[0] * size

    table = pd.DataFrame({"trade_date": d.date(), "ccy": bt.CCY, "carry_per_year": (carry * 12).round(4).values,
                          "weight": weight.round(4).values, "spot": spot.loc[d].round(6).values,
                          "forward": fwd.loc[d].round(6).values})
    old = pd.read_csv(POSITIONS) if pd.io.common.file_exists(POSITIONS) else pd.DataFrame()
    if len(old):
        old = old[old.trade_date != str(d.date())]
    pd.concat([old, table]).to_csv(POSITIONS, index=False)

    print(f"### Positions traded at the Bloomberg photo of Friday {d:%d %B %Y}\n")
    print(f"Crisis filter: {'ON, book halved' if size < 1 else 'off, full size'}.\n")
    print("| Rank | Currency | Carry vs USD (% per year) | Position |\n|---|---|---|---|")
    ranked = pd.concat([carry * 12, pd.Series({"USD": 0.0})]).sort_values(ascending=False)
    for i, (c, x) in enumerate(ranked.items(), 1):
        w = weight.get(c, 0.0)
        side = "**Long**" if w > 0 or (c == "USD" and i <= bt.N_LEGS) else ("**Short**" if w < 0 or (c == "USD" and i > len(ranked) - bt.N_LEGS) else "-")
        print(f"| {i} | {c} | {x:+.2%} | {side} |")


def weekly_report():
    pos = pd.read_csv(POSITIONS, parse_dates=["trade_date"])
    spot, _ = load_frd()
    rows = []
    # start the book at the first trade date
    nav = CAPITAL
    w0 = pos[pos.trade_date == pos.trade_date.min()].set_index("ccy")["weight"].reindex(bt.CCY).fillna(0)
    notional = w0 * nav
    opening = notional.abs().sum() * bt.COST                       # first trade: open the whole book
    dates = spot.index[spot.index >= pos.trade_date.min()]
    for prev, d in zip(dates[:-1], dates[1:]):
        book = pos[pos.trade_date <= prev]
        book = book[book.trade_date == book.trade_date.max()].set_index("ccy")
        move = spot.loc[prev] / spot.loc[d] - 1
        accrual = book["carry_per_year"].reindex(bt.CCY) / 365 * (d - prev).days
        detail = notional * (move + accrual)
        cost, opening = opening, 0.0                               # the opening cost goes into week 1
        if d in set(pos.trade_date):                               # monthly roll and rebalance
            new = pos[pos.trade_date == d].set_index("ccy")["weight"].reindex(bt.CCY).fillna(0) * (nav + detail.sum())
            cost += (new.abs().sum() + min((new - notional).abs().sum(), new.abs().sum())) * bt.COST
        pnl = detail.sum() - cost
        rows.append({"date": d, "pnl_usd": pnl, "pnl_pct": pnl / nav, "carry_usd": (notional * accrual).sum(),
                     "spot_usd": (notional * move).sum(), "costs_usd": cost, "nav": nav + pnl})
        last_detail, last_notional, last_move = detail, notional.copy(), move
        nav += pnl
        notional = new if d in set(pos.trade_date) else notional * (1 + move)
    if not rows:
        print("No live week yet."); live_chart(pd.DataFrame({"cumulative": []})); return
    hist = pd.DataFrame(rows)
    hist["cumulative"] = hist.nav / CAPITAL - 1
    hist.to_csv(PNL, index=False, float_format="%.4f")
    last = rows[-1]
    dd = (hist.nav / hist.nav.cummax() - 1).iloc[-1]
    print(f"### Week {len(rows)}, ending Friday {last['date']:%d %B %Y}\n")
    print("| Currency | Position | Notional (USD) | Move vs USD | P&L (USD) |\n|---|---|---|---|---|")
    for c in last_notional[last_notional != 0].sort_values(ascending=False).index:
        n = last_notional[c]
        print(f"| {c} | {'Long' if n > 0 else 'Short'} | {n:+,.0f} | {last_move[c]:+.2%} | {last_detail[c]:+,.0f} |")
    print(f"\nCarry {last['carry_usd']:+,.0f} USD, spot {last['spot_usd']:+,.0f} USD, costs {-last['costs_usd']:,.0f} USD.")
    print(f"**Week: {last['pnl_pct']:+.2%} ({last['pnl_usd']:+,.0f} USD). Since launch: "
          f"{hist.cumulative.iloc[-1]:+.2%}. NAV {last['nav']:,.0f} USD. Drawdown {dd:.1%}.**")
    live_chart(hist)


def live_chart(hist):
    """Live P&L against what the backtest expects (mean, 1 and 2 standard deviations)."""
    bt_pnl = pd.read_csv("results/monthly_pnl.csv", index_col=0)["pnl"]
    mu, sigma = bt_pnl.mean() * 12 / 52, bt_pnl.std() * np.sqrt(12) / np.sqrt(52)
    weeks = np.arange(0, max(52, len(hist)) + 1)
    live = np.r_[0, hist.cumulative.values] if len(hist) else np.array([0.0])
    plt.figure(figsize=(8, 4))
    for k, a in [(2, 0.12), (1, 0.25)]:
        plt.fill_between(weeks, mu * weeks - k * sigma * np.sqrt(weeks), mu * weeks + k * sigma * np.sqrt(weeks),
                         color="tab:blue", alpha=a, lw=0)
    plt.plot(weeks, mu * weeks, color="tab:blue", ls="--", label="Backtest expectation (1 and 2 std)")
    plt.plot(np.arange(len(live)), live, color="black", lw=2, marker="o", label="Live")
    plt.axhline(0, color="grey", lw=0.8)
    plt.xlabel("Weeks since launch"); plt.ylabel("Cumulative return"); plt.legend(loc="upper left")
    plt.title("Live vs backtest"); plt.tight_layout(); plt.savefig("results/5_live_vs_backtest.png", dpi=120)
    plt.close()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "chart":
        live_chart(pd.DataFrame({"cumulative": []}))
    elif len(sys.argv) > 1 and sys.argv[1] == "positions":
        new_positions()
    else:
        weekly_report()
