# CME University Trading Challenge: morning pipeline

Analysis and record-keeping only. Every order is placed by hand in CQG; nothing here connects to it.

## Setup (once)

    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt

## Every morning

    cd ~/Desktop/GitHub/CME-University-Challenge-2026
    source .venv/bin/activate
    python run.py

This downloads prices, option chains and contract months, analyzes every market,
writes `report.html` and opens it. Downloads are reused for 6 hours, so a rerun
after changing a parameter takes seconds.

All tunable parameters are at the top of `run.py`.

## Reading the report

1. **Today's order sheet**: what to buy or sell to reach the target portfolio, with stops
2. **Upcoming events**: scheduled releases in the next few days
3. **Open positions**: hold or close for each position you have recorded
4. **Signal agreement**: every market ranked by how many signals point the same way
5. **Every market at a glance**, then the volatility, skew, gamma, curve, spread and price charts

Place the orders by hand in CQG, set a stop order at the level shown, then record each fill below.

## Recording trades

After each trade in CQG, record it:

    python positions.py add ES long 10 7776.50          # opened, or added to, a position
    python positions.py add CL short 5 91.26 "Dec 26"   # contract month is optional
    python positions.py close ES 7801.25                # closed all of it at this price
    python positions.py close ES 7801.25 4              # closed 4 contracts
    python positions.py list                            # show open positions

- `positions.csv`: what is open now
- `trades.csv`: every execution (daily 10-contract check and commissions)
- `journal.csv`: closed trades and their profit or loss

## Saving to GitHub

    git add -A
    git commit -m "Describe the change"
    git push

## Forcing fresh data

    rm -rf data/prices data/options     # then run python run.py

## Competition rules to remember

- Trade at least 10 contracts every trading day, or pay $1,000 for that day
- Losing 20% of the balance in one day locks the account for the day
- $1,000 per contract held to expiry, or still open 15 minutes before the close on October 30
- Commission is $2.50 per contract per side
- Algorithmic trading is not permitted

## Files

- `run.py`: parameters and the main script
- `config.yaml`: market table (symbols, point values, ETF option proxies, contract months)
- `data.py`: downloads and caches prices, contract months and option chains
- `price.py`: trend, Hurst exponent and realized volatility
- `options.py`: implied vol, skew, gamma levels, put/call ratio
- `curve.py`: carry, calendar spreads, butterflies, cross-market spreads
- `positioning.py`: speculator positioning and open interest from the CFTC's weekly report
- `events.py`: scheduled releases shown as warnings
- `signals.py`: collects every signal and ranks markets by agreement
- `positions.py`: records open positions and closed trades, and checks exits
- `sizing.py`: builds the target portfolio and the order sheet
- `report.py`: tables and charts
