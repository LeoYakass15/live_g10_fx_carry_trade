"""Charts saved in results/."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from .stats import CRASHES, drawdown, wealth

COLORS = ["#2a78d6", "#eb6834", "#1baf7a"]   # blue, orange, green
CCY_COLORS = {"AUD": "#2a78d6", "NZD": "#1baf7a", "GBP": "#6250d6", "USD": "#8a8985",
              "CAD": "#e34948", "NOK": "#008300", "SEK": "#eda100", "EUR": "#e87ba4",
              "CHF": "#eb6834", "JPY": "black"}
plt.rcParams.update({"axes.grid": True, "grid.alpha": 0.3, "axes.axisbelow": True,
                     "axes.spines.top": False, "axes.spines.right": False})


def shade_crashes(ax):
    for start, end in CRASHES.values():
        ax.axvspan(pd.Timestamp(start), pd.Timestamp(end) + pd.offsets.MonthEnd(0),
                   color="red", alpha=0.12)


def save(fig, path):
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def plot_rates(rates, path):
    fig, ax = plt.subplots(figsize=(10, 4.8))
    for ccy in rates.columns:
        lw = 2.2 if ccy in ["AUD", "NZD", "JPY", "CHF"] else 1
        ax.plot(rates[ccy], color=CCY_COLORS[ccy], lw=lw, label=ccy)
    ax.axhline(0, color="grey", lw=0.8)
    ax.set_ylabel("3-month rate (% per year)")
    ax.set_title("G10 short rates: AUD and NZD on top, JPY and CHF at the bottom")
    ax.legend(ncol=5)
    save(fig, path)


def plot_positions(weights, path):
    """Long (blue), short (orange) or out (white), currency by month."""
    order = weights.mean().sort_values(ascending=False).index
    fig, ax = plt.subplots(figsize=(10, 3.8))
    cmap = matplotlib.colors.ListedColormap(["#eb6834", "#f4f3ef", "#2a78d6"])
    t = weights.index.year + weights.index.month / 12   # dates as decimal years
    ax.imshow(weights[order].T.values, aspect="auto", cmap=cmap, vmin=-0.5, vmax=0.5,
              interpolation="nearest", extent=[t[0] - 1 / 12, t[-1], len(order), 0])
    ax.set_yticks([i + 0.5 for i in range(len(order))], order)
    ax.grid(False)
    ax.set_title("Carry book: long the 3 highest yielders (blue), short the 3 lowest (orange)")
    save(fig, path)


def plot_cumulative(strategies, path):
    fig, ax = plt.subplots(figsize=(10, 4.8))
    for (name, r), c in zip(strategies.items(), COLORS):
        ax.plot(wealth(r), color=c, lw=2, label=name)
    shade_crashes(ax)
    ax.set_yscale("log")
    ax.set_ylabel("Value of 1 USD invested (log scale)")
    ax.set_title("G10 carry trade vs simple benchmarks (crashes shaded)")
    ax.legend(loc="upper left")
    save(fig, path)


def plot_carry_vs_spot(pnl, path):
    fig, ax = plt.subplots(figsize=(10, 4.8))
    ax.plot(100 * pnl["carry"].cumsum(), color=COLORS[2], lw=2, label="Carry (rate differential)")
    ax.plot(100 * pnl["spot"].cumsum(), color=COLORS[1], lw=2, label="Spot moves")
    ax.plot(100 * pnl["total"].cumsum(), color=COLORS[0], lw=2.4, label="Total (after costs)")
    ax.axhline(0, color="grey", lw=0.8)
    shade_crashes(ax)
    ax.set_ylabel("Cumulative return (%, simple sum)")
    ax.set_title("Where the money comes from: steady carry, spot losses in crashes")
    ax.legend(loc="upper left")
    save(fig, path)


def plot_drawdowns(strategies, path):
    fig, ax = plt.subplots(figsize=(10, 4))
    for (name, r), c in zip(strategies.items(), COLORS):
        ax.plot(100 * drawdown(r), color=c, lw=1.6, label=name)
    shade_crashes(ax)
    ax.set_ylabel("Drawdown (%)")
    ax.set_title("Up the stairs, down the elevator (crashes shaded: 2008, CHF 2015, Covid)")
    ax.legend(loc="lower left")
    save(fig, path)


def plot_distribution(returns, path):
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.hist(100 * returns, bins=40, color=COLORS[0], edgecolor="white")
    ax.axvline(100 * returns.mean(), color="black", ls="--", label=f"mean {100 * returns.mean():.2f}%")
    ax.annotate("Oct 2008", (100 * returns.min(), 1), xytext=(0, 20), textcoords="offset points",
                ha="center", arrowprops=dict(arrowstyle="-"))
    ax.set_xlabel("Monthly return (%)")
    ax.set_ylabel("Number of months")
    ax.set_title(f"Monthly returns of the carry book: skewness {returns.skew():.2f}")
    ax.legend()
    save(fig, path)


def plot_crash_contributions(contrib, path):
    fig, axes = plt.subplots(1, len(CRASHES), figsize=(11, 3.8))
    for ax, (name, (start, end)) in zip(axes, CRASHES.items()):
        c = 100 * contrib.loc[start:end].sum()
        c = c[c != 0].sort_values()
        ax.barh(c.index, c, color=["#e34948" if v < 0 else "#1baf7a" for v in c])
        ax.axvline(0, color="grey", lw=0.8)
        ax.set_title(name)
        ax.set_xlabel("P&L (% of notional)")
    fig.suptitle("P&L by position in each crash: the high yielders fall, the funding currencies jump")
    save(fig, path)


def plot_vol_target(raw, scaled, leverage, path):
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6), sharex=True, height_ratios=[2, 1])
    ax1.plot(wealth(raw.loc[scaled.index]), color="grey", label="Carry book")
    ax1.plot(wealth(scaled), color=COLORS[0], lw=2, label="Carry book, vol-targeted")
    ax1.set_yscale("log")
    ax1.set_ylabel("Value of 1 USD (log)")
    ax1.set_title("Cutting the position when volatility rises")
    ax1.legend(loc="lower right")
    ax2.plot(leverage, color="#6250d6")
    ax2.axhline(1, color="grey", lw=0.8)
    ax2.set_ylabel("Leverage")
    shade_crashes(ax1)
    shade_crashes(ax2)
    save(fig, path)
