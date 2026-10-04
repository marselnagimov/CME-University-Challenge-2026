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

# --- Hurst exponent (does the market trend or snap back?) ---
HURST_WINDOW = 750         # days of history used
HURST_MAX_LAG = 30         # longest gap (days) compared; shorter = more short-term behaviour
HURST_TREND = 0.55         # above this is labelled trending (a pure random walk scores 0.34-0.59 nine times in ten)
HURST_REVERT = 0.45        # below this is labelled mean-reverting

# --- Signal agreement (the ranked list in the report) ---
SIGNAL_TREND_MIN = 0.5     # a trend-strength reading must be beyond +/- this to count as a vote
SLOW_TREND_WINDOW = 250    # days for the slow (12-month) trend signal
TREND_SPEED_VOL = 17       # markets more volatile than this (% a year) use the fast trend; calmer ones the slow trend
HIGH_WINDOW = 250          # days for the 52-week high signal
HIGH_EDGE = 0.2            # price in the top (or bottom) fifth of its 52-week range votes long (or short); 0.1 = top tenth
RANK_FRACTION = 0.4        # ranked signals: this share of markets at the top votes one way, the same share at the bottom the other
SKEWNESS_WINDOW = 250      # days of returns used for the skewness signal
VOL_PREMIUM_MIN = 3        # stock indexes: implied vol this many points over realized votes long
IMPLIED_SKEW_MIN = 1       # commodities: skew beyond +/- this many vol points votes
SKEW_CHANGE_MIN = 1.0      # skew must have moved this many vol points to vote
SKEW_MIN_SNAPSHOTS = 3     # earlier daily runs needed before the skew-shift signal votes
COT_WEEKS = 26             # weeks of CFTC positioning history to download
COT_CHANGE_MIN = 1.5       # speculators' weekly net change, as % of open interest, needed to vote
OI_GROWTH_WEEKS = 13       # weeks over which open-interest growth is measured
OI_GROWTH_MIN = 10         # open interest must have grown or shrunk this % to vote
CROSS_EQUITY, CROSS_BOND = "ES", "ZN"    # the markets that stand for "stocks" and "bonds" in the cross-asset signal
COMMODITY_CURRENCIES = ["6A", "6C"]      # currencies whose trend votes on every commodity
IV_GAP_FLAG = 5            # note when implied vol exceeds realized by this many points
SAME_BET_CORR = 0.8        # note when a market moves this closely with a higher-ranked one

# --- Extreme one-day moves ---
SHOCK_VOL_WINDOW = 20      # days used to define a "normal" daily move
SHOCK_MIN = 2.0            # flag a last-day move (or opening gap) beyond +/- this many normal daily moves
SHOCK_VOTE = "hurst"       # "off" = flag only, "fade" = vote against the move, "follow" = vote with it,
                           # "hurst" = follow in trending markets, fade in mean-reverting ones, abstain otherwise

# --- Event calendar (shown as warnings; "ALL" means every market) ---
EVENT_LOOKAHEAD_DAYS = 5   # show events this many days ahead
EVENTS = [                 # one-off events: date, description, markets affected
    ("2026-10-09", "USDA supply and demand report, 12:00 ET", ["ZC", "ZS", "ZW", "KE", "ZL", "ZM"]),
    ("2026-10-14", "Consumer price index, 8:30 ET", ["ES", "NQ", "RTY", "YM", "ZT", "ZF", "ZN", "ZB", "UB", "GC", "6E", "6J"]),
    ("2026-10-15", "Producer price index, 8:30 ET", ["ZT", "ZF", "ZN", "ZB", "UB"]),
    ("2026-10-28", "Fed rate decision, 14:00 ET (confirm the date on federalreserve.gov)", "ALL"),
    ("2026-10-30", "Employment cost index, 8:30 ET. Contest ends 16:00 CT: be flat 15 minutes before", "ALL"),
]
WEEKLY_EVENTS = [          # recurring: weekday (0 = Monday), description, markets affected
    (2, "EIA crude oil inventories, 10:30 ET", ["CL", "RB", "HO"]),
    (3, "EIA natural gas storage, 10:30 ET", ["NG"]),
    (4, "CFTC positioning report, 15:30 ET (positioning signals update on the next run)", []),
]
MONTH_END_DAYS = 3         # in the last few trading days of the month, flag pension-fund rebalancing

# --- Sizing (the order sheet) ---
DAILY_RISK_PCT = 10        # the portfolio's normal daily swing, as % of current balance (lockout is at 20%)
MAX_POSITIONS = 3          # how many separate bets to hold at once
MIN_SCORE_TO_ENTER = 4     # agreement (votes for minus against) needed to open a new position
REBALANCE_MIN_PCT = 20     # ignore size changes smaller than this % of the target
VOL_EWMA_HALFLIFE = 10     # days; recent days count more in the volatility used for sizing
VOL_SAFETY_MULT = 1.0      # size as if volatility were this many times the estimate (1.5 = more cautious)
MARGIN_USE_MAX_PCT = 60    # never commit more than this % of the balance to margin
MARGIN_FALLBACK_PCT = 8    # margin guess (% of contract value) for a market with no margin or margin_pct in config.yaml

# --- Open positions and exits (positions.py records what you hold) ---
STOP_DAILY_MOVES = 2.5     # trailing stop: this many normal daily moves back from the best close since entry
EXIT_MIN_SCORE = 1         # say CLOSE when agreement (votes for minus against) falls to this or lower
ADD_MIN_SCORE = 4          # say adding is allowed when agreement is at least this and the trade is in profit
ROLL_WARN_DAYS = 10        # warn when a position's contract month starts within this many days

# --- Volatility ---
RV_WINDOW = 20             # days used for realized (actual) volatility

# --- Options (implied vol, skew, gamma) ---
OPTION_TARGET_DAYS = 30    # use the expiry closest to this many days away
OPTION_MIN_DAYS = 7        # ignore expiries closer than this
RISK_FREE_RATE = 0.04      # annual interest rate used in option pricing
SKEW_DELTA = 0.25          # skew = IV of this-delta put minus this-delta call
MIN_STRIKES = 6            # need at least this many usable strikes
MAX_ABS_SKEW = 10          # discard a skew reading beyond +/- this many vol points as bad data
MIN_OPTION_OI = 5000       # ignore option chains with less total open interest than this (too thin to trust)
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
import events
import options
import positioning
import positions
import price
import report
import signals
import sizing
import symbols


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

        # sizing volatility: the highest of implied, realized and recent-weighted, times the safety margin
        vol = pd.Series([row.get("Implied vol"), row["Realized vol"], row["EWMA vol"]], dtype=float).max()
        row["Sizing vol"], row["Group"] = vol * VOL_SAFETY_MULT, m.get("group", "commodity")
        row["Daily $ move"] = row["Close"] * m["point_value"] * vol * VOL_SAFETY_MULT / 100 / 252 ** 0.5
        rows[code] = row

    table = pd.DataFrame.from_dict(rows, orient="index")
    table.index.name = "Market"
    spreads += curve.intermarket(bars, markets, P)
    spreads = pd.DataFrame(spreads)
    cot = data.cot(markets, P)
    table = table.join(positioning.read(cot, P))
    missing = [c for c in table.index if pd.isna(table.loc[c, "Spec pressure"])]
    if missing:
        print(f"  No CFTC positioning for: {', '.join(missing)}")
    budget = positions.balance(table, markets, P) * DAILY_RISK_PCT / 100
    ranked = signals.build(table, bars, P, data.DATA / "iv_history.csv", budget)
    options.log_history(table, data.DATA / "iv_history.csv")
    held, book = positions.evaluate(table, ranked, bars, markets, P)
    sheet, plan = sizing.build(ranked, held, book, table, bars, markets, P)

    n = len(table)
    print(f"\nCoverage: prices {n}/{len(markets)}, "
          f"options {table.get('Implied vol', pd.Series(dtype=float)).notna().sum()}/{n}, "
          f"curves {len(curves)}/{n}, positioning {table['Spec pressure'].notna().sum()}/{n}, spreads scored {len(spreads)}")
    calendar = events.upcoming(table, P)
    out = report.build(calendar, sheet, plan, held, book, ranked, table, bars, gamma, curves, spreads, markets, P, data.ROOT / "report.html")
    top = ranked[ranked["Direction"] != 0].head(5)
    print("Top agreement: " + ", ".join(
        f"{symbols.root(c, markets)} {'long' if r['Direction'] > 0 else 'short'} {r['Agree']}/{r['Voting']}"
        for c, r in top.iterrows()))
    print("Order sheet:")
    for _, r in sheet.iterrows():
        o = int(r["Order"])
        print(f"  {symbols.front(r['Market'], markets, curves):<8} {('BUY ' if o > 0 else 'SELL') + ' ' + str(abs(o)) if o else 'no change':<10}"
              f" target {int(r['Target']):+d}  ({r['Why']})")
    for when, text, _ in calendar:
        print(f"  Event {when}: {text}")
    if plan["filler"]:
        print(f"  Volume: {plan['filler']} more contracts needed today to reach the minimum")
    print(f"Wrote {out}")
    if OPEN_BROWSER:
        webbrowser.open(out.as_uri())


if __name__ == "__main__":
    main()
