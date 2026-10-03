"""Morning analysis: download everything, read every market, write report.html.

Run:  python run.py
"""
# =====================================================================
# PARAMETERS: change these numbers, nothing below needs editing
# =====================================================================

# --- Data ---
PRICE_HISTORY = "2y"       # how much daily price history to download
CONTRACT_HISTORY = "6mo"   # history for each individual contract month
CACHE_HOURS = 6            # reuse downloads newer than this (0 = always re-download)
PAUSE_SECONDS = 0.2        # wait between downloads so Yahoo doesn't block you

# --- Trend ---
TREND_WINDOW = 20          # days used for the trend-strength score
FAST_MA = 20               # fast moving average (days)
SLOW_MA = 50               # slow moving average (days)

# --- Volatility ---
RV_WINDOW = 20             # days used for realized (actual) volatility

# --- Options (implied vol, skew, gamma) ---
OPTION_TARGET_DAYS = 30    # use the expiry closest to this many days away
OPTION_MIN_DAYS = 7        # ignore expiries closer than this
RISK_FREE_RATE = 0.04      # annual interest rate used in option pricing
SKEW_DELTA = 0.25          # skew = IV of this-delta put minus this-delta call
MIN_STRIKES = 6            # need at least this many usable strikes
MIN_OPTION_OI = 10000      # ignore option chains with less total open interest than this (too thin to trust)
GAMMA_RANGE_PCT = 8        # look for gamma levels within +/- this % of the price
GAMMA_LEVELS = 3           # how many top gamma strikes to list

# --- Curve and spreads ---
CURVE_CONTRACTS = 4        # contract months per market
CURVE_SEARCH_MONTHS = 15   # how far ahead to look for contract months
STALE_DAYS = 1             # a contract with no bar in this many days is treated as expired
MIN_LEG_VOLUME = 100       # skip spreads where any leg trades fewer contracts a day than this
SPREAD_WINDOW = 60         # days of history a spread is compared against
MIN_SPREAD_DAYS = 30       # need at least this much history to score a spread
SPREADS_SHOWN = 25         # most-stretched spreads shown in the chart
RATIO_PAIRS = [            # pairs of markets compared as a price ratio
    ("ES", "NQ"), ("ES", "RTY"), ("ZN", "ZB"), ("GC", "SI"), ("GC", "HG"),
    ("ZS", "ZC"), ("ZW", "ZC"), ("ZW", "KE"), ("LE", "HE"), ("CL", "NG"),
]
PACKAGES = {               # multi-leg spreads: contracts of each market (+ long, - short)
    "Crack 3:2:1": {"RB": 2, "HO": 1, "CL": -3},
    "Soy crush":   {"ZM": 11, "ZL": 9, "ZS": -10},
}

# --- Competition rules (2026 rules PDF, page 9-10). Used by sizing and order checks ---
START_BALANCE = 1_000_000       # beginning account balance
MIN_CONTRACTS_PER_DAY = 10      # team volume required every trading day
MISSED_VOLUME_PENALTY = 1000    # charged for each day under the minimum
COMMISSION_PER_SIDE = 2.50      # per contract, charged on entry and again on exit
DAILY_LOSS_LOCKOUT_PCT = 20     # lose this % of balance in a day and the account locks
OPEN_CONTRACT_PENALTY = 1000    # per contract held to expiry or still open at the end
COMPETITION_END = "2026-10-30"  # be flat 15 minutes before the market closes
EXCHANGE_SPREADS = ["CL", "NG", "GC", "ZC", "ZS", "LE", "ES", "6E"]  # calendars tradable as one order

# --- Report ---
CHART_DAYS = 120           # trading days shown in the price charts
CORR_WINDOW = 60           # days used for the correlation map
OPEN_BROWSER = True        # open report.html when done

# =====================================================================
P = {k: v for k, v in dict(globals()).items() if k.isupper()}

import webbrowser

import pandas as pd

import curve
import data
import options
import price
import report


def main():
    markets = data.load_markets()
    rows, gamma, curves, spreads, bars = {}, {}, {}, [], {}

    print(f"Reading {len(markets)} markets (first run of the day takes a few minutes)...")
    for code, m in markets.items():
        df = data.history(m["yahoo"], PRICE_HISTORY, P)
        if df.empty:
            print(f"  {code}: no price data")
            continue
        bars[code] = df
        row = {"Name": m["name"], **price.read(df, P)}

        # Options read, from the ETF proxy's option chain
        if m.get("proxy"):
            chain = data.option_chain(m["proxy"], P)
            spot = data.history(m["proxy"], "1mo", P)
            res = options.read(chain, spot["Close"].iloc[-1], P) if len(chain) and len(spot) else None
            if res:
                gamma[code] = res.pop("gamma")
                row.update(res)
            else:
                print(f"  {code}: options on {m['proxy']} missing or too thin, skipped")

        # Curve read, from the individual contract months
        contracts = data.contracts(code, m, P, row["Close"])
        res = curve.read(code, contracts, P)
        if res:
            curves[code] = res.pop("points")
            spreads += res.pop("spreads")
            row.update(res)

        vol = row.get("Implied vol", float("nan"))
        vol = row["Realized vol"] if pd.isna(vol) else vol
        row["Daily $ move"] = row["Close"] * m["point_value"] * vol / 100 / 252 ** 0.5
        rows[code] = row

    table = pd.DataFrame.from_dict(rows, orient="index")
    table.index.name = "Market"
    spreads += curve.intermarket(bars, markets, P)
    spreads = pd.DataFrame(spreads)
    options.log_history(table, data.DATA / "iv_history.csv")

    n = len(table)
    print(f"\nCoverage: prices {n}/{len(markets)}, "
          f"options {table.get('Implied vol', pd.Series(dtype=float)).notna().sum()}/{n}, "
          f"curves {len(curves)}/{n}, spreads scored {len(spreads)}")
    out = report.build(table, bars, gamma, curves, spreads, markets, P, data.ROOT / "report.html")
    print(f"Wrote {out}")
    if OPEN_BROWSER:
        webbrowser.open(out.as_uri())


if __name__ == "__main__":
    main()
