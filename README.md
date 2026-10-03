# CME University Trading Challenge: morning pipeline

## Setup (once)
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt

## Every morning
    source .venv/bin/activate
    python run.py        # downloads, analyzes, writes report.html and opens it

All tunable parameters are at the top of run.py.

## Files
- run.py: parameters and the main script
- config.yaml: market table (symbols, point values, ETF option proxies, contract months)
- data.py: downloads and caches prices, contract months and option chains
- price.py: trend and realized volatility
- options.py: implied vol, skew, gamma levels, put/call ratio
- curve.py: carry, calendar spreads, butterflies, cross-market spreads
- report.py: tables and charts
