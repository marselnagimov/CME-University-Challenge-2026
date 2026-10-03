"""Step 1: gather daily prices for every market in config.yaml.

Run:  python data.py
Saves one CSV per market in data/ and prints a summary table.
"""
from pathlib import Path

import pandas as pd
import yaml
import yfinance as yf

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"


def load_config():
    with open(ROOT / "config.yaml") as f:
        return yaml.safe_load(f)


def download(symbol, period):
    """Daily open/high/low/close/volume for one Yahoo symbol."""
    df = yf.Ticker(symbol).history(period=period, interval="1d", auto_adjust=False)
    if df.empty:
        return df
    df = df[["Open", "High", "Low", "Close", "Volume"]].dropna(subset=["Close"])
    df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
    df.index.name = "Date"
    return df


def fetch_all(cfg):
    """Download every market, save to data/, return {code: DataFrame}."""
    DATA_DIR.mkdir(exist_ok=True)
    bars = {}
    for code, m in cfg["markets"].items():
        try:
            df = download(m["yahoo"], cfg["history"])
        except Exception as e:  # network or symbol problem: report and move on
            print(f"  {code}: FAILED ({e})")
            continue
        if df.empty:
            print(f"  {code}: no data returned for {m['yahoo']}")
            continue
        df.to_csv(DATA_DIR / f"{code}.csv")
        bars[code] = df
    return bars


def load_saved(cfg):
    """Read previously saved CSVs (used by later steps)."""
    bars = {}
    for code in cfg["markets"]:
        path = DATA_DIR / f"{code}.csv"
        if path.exists():
            bars[code] = pd.read_csv(path, index_col="Date", parse_dates=True)
    return bars


def summary(cfg, bars):
    rows = []
    for code, df in bars.items():
        close = df["Close"]
        last = close.iloc[-1]
        day = close.pct_change().iloc[-1] * 100
        month = (last / close.iloc[-21] - 1) * 100 if len(close) > 21 else float("nan")
        rows.append({
            "Market": code,
            "Name": cfg["markets"][code]["name"],
            "Last date": df.index[-1].date(),
            "Close": round(last, 4),
            "1d %": round(day, 2),
            "20d %": round(month, 2),
            "Days": len(df),
        })
    return pd.DataFrame(rows).set_index("Market")


if __name__ == "__main__":
    cfg = load_config()
    print("Downloading prices...")
    bars = fetch_all(cfg)
    print()
    print(summary(cfg, bars).to_string())
    print(f"\nSaved {len(bars)} of {len(cfg['markets'])} markets to {DATA_DIR}/")
