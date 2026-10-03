"""Step 2, options read: implied vol, skew, gamma levels, put/call ratio.

Uses the Black-76 model on out-of-the-money options. The forward price comes from
put-call parity, so no dividend assumption is needed.
"""
from math import erf, exp, log, pi, sqrt

import numpy as np
import pandas as pd


def _N(x):
    return 0.5 * (1 + erf(x / sqrt(2)))


def _d1(F, K, T, s):
    return (log(F / K) + 0.5 * s * s * T) / (s * sqrt(T))


def black76(F, K, T, s, call):
    """Undiscounted option price on a forward."""
    d1 = _d1(F, K, T, s)
    d2 = d1 - s * sqrt(T)
    return F * _N(d1) - K * _N(d2) if call else K * _N(-d2) - F * _N(-d1)


def implied_vol(price, F, K, T, call):
    """Volatility that reproduces the option price (bisection). NaN if impossible."""
    intrinsic = max(F - K, 0) if call else max(K - F, 0)
    if not price > intrinsic or price >= (F if call else K):
        return np.nan
    lo, hi = 0.005, 5.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if black76(F, K, T, mid, call) > price:
            hi = mid
        else:
            lo = mid
    return mid if 0.006 < mid < 4.99 else np.nan


def read(chain, spot, P):
    """Return the options read for one market, or None if the chain is unusable."""
    T = chain["days"].iloc[0] / 365
    disc = exp(-P["RISK_FREE_RATE"] * T)

    # Forward price from put-call parity at the strike nearest the spot price
    both = chain.dropna(subset=["price_call", "price_put"])
    if both.empty:
        return None
    k0 = both.iloc[(both["strike"] - spot).abs().argmin()]
    F = k0["strike"] + (k0["price_call"] - k0["price_put"]) / disc
    if abs(F / spot - 1) > 0.05:
        F = spot / disc

    rows = []
    for _, r in chain.iterrows():
        K, call = r["strike"], r["strike"] >= F
        px = r["price_call"] if call else r["price_put"]
        if pd.isna(px) or px <= 0:
            continue
        iv = implied_vol(px / disc, F, K, T, call)
        if np.isnan(iv):
            continue
        d1 = _d1(F, K, T, iv)
        rows.append({
            "strike": K, "iv": iv, "call": call,
            "delta": _N(d1) if call else _N(d1) - 1,
            "gamma": exp(-d1 * d1 / 2) / sqrt(2 * pi) / (F * iv * sqrt(T)),
            "oi": (r["oi_call"] if not pd.isna(r["oi_call"]) else 0)
                  + (r["oi_put"] if not pd.isna(r["oi_put"]) else 0),
        })
    o = pd.DataFrame(rows)
    if len(o) < P["MIN_STRIKES"] or not o["strike"].min() < F < o["strike"].max():
        return None

    def iv_at_delta(side, target):
        s = side.sort_values("delta")
        if len(s) < 2 or not s["delta"].min() <= target <= s["delta"].max():
            return np.nan
        return np.interp(target, s["delta"], s["iv"])

    atm = np.interp(F, o["strike"], o["iv"])
    d = P["SKEW_DELTA"]
    skew = iv_at_delta(o[~o["call"]], -d) - iv_at_delta(o[o["call"]], d)

    near = o[(o["strike"] / F - 1).abs() <= P["GAMMA_RANGE_PCT"] / 100].copy()
    near["gex"] = near["gamma"] * near["oi"]
    near["rel"] = near["strike"] / F          # strike as a fraction of the price
    top = near.nlargest(P["GAMMA_LEVELS"], "gex")
    top = top[top["gex"] > 0]

    put_oi, call_oi = chain["oi_put"].sum(), chain["oi_call"].sum()
    if put_oi + call_oi < P["MIN_OPTION_OI"]:
        return None
    return {
        "Option OI": put_oi + call_oi,
        "Implied vol": atm * 100,
        "Skew": skew * 100,
        "Put/call": put_oi / call_oi if call_oi > 0 else np.nan,
        "Expiry": chain["expiry"].iloc[0],
        "Gamma rel": list(top["rel"]),
        "gamma": near[["rel", "gex"]],
    }


def log_history(table, path):
    """Append today's implied vol and skew so later runs can show how they change."""
    if "Implied vol" not in table:
        return
    snap = table[["Implied vol", "Skew"]].dropna(subset=["Implied vol"]).reset_index()
    snap.insert(0, "Date", pd.Timestamp.today().strftime("%Y-%m-%d"))
    if path.exists():
        snap = pd.concat([pd.read_csv(path), snap]).drop_duplicates(["Date", "Market"], keep="last")
    path.parent.mkdir(parents=True, exist_ok=True)
    snap.to_csv(path, index=False)
