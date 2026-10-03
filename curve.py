"""Step 2, curve and spread read: carry, calendar spreads, butterflies, cross-market spreads.

Every spread gets a z-score: how many normal deviations it sits from its own recent
average. +2 means unusually high, -2 unusually low.
"""
import numpy as np
import pandas as pd


def zscore(s, P):
    s = s.dropna().tail(P["SPREAD_WINDOW"])
    if len(s) < P["MIN_SPREAD_DAYS"] or s.std() == 0:
        return np.nan
    return (s.iloc[-1] - s.mean()) / s.std()


def _row(name, kind, series, P):
    s = series.dropna()
    return {"Spread": name, "Type": kind, "Value": s.iloc[-1] if len(s) else np.nan,
            "Z": zscore(series, P), "Days": len(s.tail(P["SPREAD_WINDOW"]))}


def read(code, contracts, P):
    """Curve read for one market from its contract months, or None."""
    if len(contracts) < 2:
        return None
    labels = [c[0] for c in contracts]
    closes = pd.DataFrame({lab: df["Close"] for lab, _, df in contracts})
    last = [df["Close"].iloc[-1] for _, _, df in contracts]
    months = contracts[1][1] - contracts[0][1]
    out = {
        "points": list(zip(labels, last)),
        # annualized % gap between the 2nd and 1st contract: + contango, - backwardation
        "Carry %/yr": (last[1] / last[0] - 1) * 12 / months * 100,
        "spreads": [],
    }
    liquid = [df["Volume"].tail(20).mean() >= P["MIN_LEG_VOLUME"] for _, _, df in contracts]
    # spreads as a % of price, so they stay comparable when the price level changes
    cal = (closes[labels[0]] / closes[labels[1]] - 1) * 100
    kind = "Calendar" if code in P["EXCHANGE_SPREADS"] else "Calendar, legged"
    if all(liquid[:2]):
        out["spreads"].append(_row(f"{code} {labels[0]} – {labels[1]}", kind, cal, P))
        out["Calendar z"] = out["spreads"][-1]["Z"]
    if len(contracts) >= 3 and all(liquid[:3]):
        fly = (closes[labels[0]] - 2 * closes[labels[1]] + closes[labels[2]]) / closes[labels[1]] * 100
        out["spreads"].append(_row(f"{code} fly {labels[0]}/{labels[1]}/{labels[2]}", "Butterfly, legged", fly, P))
    return out


def intermarket(bars, markets, P):
    """Cross-market spreads from the front-month price series."""
    rows = []
    for a, b in P["RATIO_PAIRS"]:
        if a in bars and b in bars:
            rows.append(_row(f"{a} / {b}", "Ratio", bars[a]["Close"] / bars[b]["Close"], P))
    for name, legs in P["PACKAGES"].items():
        if all(c in bars for c in legs):
            value = sum(q * bars[c]["Close"] * markets[c]["point_value"] for c, q in legs.items())
            rows.append(_row(name, "Package ($)", value, P))
    return rows
