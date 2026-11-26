# Rules of the live book (frozen on 27 November 2026)

These rules are written before the first live week. If I change one, the book becomes "v3"
and starts a new track record. I never rewrite the past.

1. **Universe**: the 10 G10 currencies: AUD, CAD, CHF, EUR, GBP, JPY, NOK, NZD, SEK and USD.
2. **Signal**: the 1-month carry of each currency against the USD, from the Bloomberg FRD screen: forward / spot - 1, using the middle of the bid and ask points. The USD has a carry of 0. Same code as the backtest (`backtest.weights_from_score`).
3. **Positions**: long the 3 highest carries, short the 3 lowest, one third of the capital each, through 1-month forwards. If the USD is among the 3 best or 3 worst, that third is simply held in USD (no trade).
4. **Crisis filter**: the book is cut in half when the average 6-month volatility of the 9 currencies against the USD is above its 90th percentile since 2004 (rule 3 of the backtest, `backtest.crisis_size`).
5. **Months**: a month runs from the last Friday of one month to the last Friday of the next.
6. **Rebalancing**: at the price of the photo of the last Friday of each month. No change during the month, whatever happens.
7. **Prices**: Bloomberg FRD, source BGN, one photo per pair, at the Friday close. The photo can be taken on Friday evening or on Saturday (the market is closed, the screen shows the Friday close); the field `Pricing Date` must show the Friday. If the market is closed on Friday (Christmas, New Year), I use Thursday's photo and keep the Friday date.
8. **Weekly P&L**: spot move of each currency against the USD, plus the carry earned day by day (carry per year × days / 365).
9. **Costs**: 2 bp on every USD traded. The whole book rolls every month, plus the switches.
10. **Capital**: 1,000,000 USD on paper. P&L in USD and in % of capital.
11. **Weekly report**: committed before Monday 09:00 Paris time. Every week is reported, good or bad. A missed Friday is written as missed, and its move is added to the next week.
