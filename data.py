"""Step 1, gather: downloads and caches everything from Yahoo Finance."""
import logging
import time
from pathlib import Path

import pandas as pd
import yaml
import yfinance as yf

ROOT = Path(__file__).parent
DATA = ROOT / "data"
logging.getLogger("yfinance").setLevel(logging.CRITICAL)   # hide Yahoo's "not found" chatter
MONTH_CODES = "FGHJKMNQUVXZ"   # Jan..Dec futures month letters


def load_markets():
    with open(ROOT / "config.yaml") as f:
        return yaml.safe_load(f)["markets"]


def _fresh(path, hours):
    return path.exists() and time.time() - path.stat().st_mtime < hours * 3600


def history(symbol, period, P):
    """Daily bars for one Yahoo symbol. Empty DataFrame if Yahoo has nothing."""
    path = DATA / "prices" / f"{symbol.replace('=', '_')}.csv"
    miss = path.with_suffix(".missing")
    if _fresh(miss, P["CACHE_HOURS"]):
        return pd.DataFrame()          # Yahoo had nothing earlier today; don't ask again
    if _fresh(path, P["CACHE_HOURS"]):
        return pd.read_csv(path, index_col="Date", parse_dates=True)
    try:
        df = yf.Ticker(symbol).history(period=period, interval="1d", auto_adjust=False)
    except Exception:
        df = None
    time.sleep(P["PAUSE_SECONDS"])
    path.parent.mkdir(parents=True, exist_ok=True)
    if df is None or df.empty or "Close" not in df:
        miss.touch()
        return pd.DataFrame()
    df = df[["Open", "High", "Low", "Close", "Volume"]].dropna(subset=["Close"])
    df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
    df.index.name = "Date"
    df = df[~df.index.duplicated(keep="last")]
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path)
    return df


def contracts(code, m, P, front_close=None):
    """The next few live contract months: list of (label, months_ahead, DataFrame)."""
    if not m.get("months"):
        return []
    today = pd.Timestamp.today().normalize()
    found, misses = [], 0
    for i in range(P["CURVE_SEARCH_MONTHS"]):
        month, year = (today.month - 1 + i) % 12, today.year + (today.month - 1 + i) // 12
        if MONTH_CODES[month] not in m["months"]:
            continue
        symbol = f"{m.get('root', code)}{MONTH_CODES[month]}{year % 100:02d}.{m['exchange']}"
        df = history(symbol, P["CONTRACT_HISTORY"], P)
        if df.empty:
            misses += 1
            if found and misses >= 2:      # past the last month Yahoo lists
                break
            continue
        misses = 0
        found.append((pd.Timestamp(year, month + 1, 1).strftime("%b %y"), i, df))
        if len(found) == P["CURVE_CONTRACTS"] + 2:
            break
    if not found:
        return []
    latest = max(df.index[-1] for _, _, df in found)
    live = [c for c in found if (latest - c[2].index[-1]).days <= P["STALE_DAYS"]]
    # Skip a thin delivery-month contract: begin where the front-month series is
    for j, c in enumerate(live):
        if front_close and abs(c[2]["Close"].iloc[-1] / front_close - 1) < 0.002:
            live = live[j:]
            break
    return live[:P["CURVE_CONTRACTS"]]


def option_chain(proxy, P):
    """One expiry of the proxy ETF's option chain: strike, prices, open interest."""
    path = DATA / "options" / f"{proxy}.csv"
    if _fresh(path, P["CACHE_HOURS"]):
        return pd.read_csv(path)
    try:
        t = yf.Ticker(proxy)
        today = pd.Timestamp.today().normalize()
        days = {e: (pd.Timestamp(e) - today).days for e in t.options}
        ok = [e for e in days if days[e] >= P["OPTION_MIN_DAYS"]]
        if not ok:
            return pd.DataFrame()
        expiry = min(ok, key=lambda e: abs(days[e] - P["OPTION_TARGET_DAYS"]))
        ch = t.option_chain(expiry)
    except Exception:
        return pd.DataFrame()
    finally:
        time.sleep(P["PAUSE_SECONDS"])

    def side(d):
        # mid price when there is a live two-sided quote, otherwise the last trade
        mid = (d["bid"] + d["ask"]) / 2
        px = mid.where((d["bid"] > 0) & (d["ask"] > 0), d["lastPrice"])
        return pd.DataFrame({"strike": d["strike"], "price": px, "oi": d["openInterest"].fillna(0)})

    df = side(ch.calls).merge(side(ch.puts), on="strike", how="outer",
                              suffixes=("_call", "_put")).sort_values("strike")
    df["expiry"], df["days"] = expiry, days[expiry]
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    return df
