"""Step 2, price read: trend and realized volatility."""
import numpy as np


def hurst(series, P):
    """Hurst exponent: how the size of a move grows with the time gap.

    Above 0.5 moves tend to continue (trending); below 0.5 they tend to undo
    themselves (mean-reverting); 0.5 is a random walk.
    """
    x = np.asarray(series.dropna().tail(P["HURST_WINDOW"]), dtype=float)
    lags = np.arange(2, P["HURST_MAX_LAG"] + 1)
    if len(x) < 5 * P["HURST_MAX_LAG"]:
        return np.nan
    tau = np.array([np.std(x[lag:] - x[:-lag]) for lag in lags])
    if (tau <= 0).any():
        return np.nan
    return np.polyfit(np.log(lags), np.log(tau), 1)[0]


def hurst_label(h, P):
    if np.isnan(h):
        return "–"
    return "Trending" if h > P["HURST_TREND"] else "Reverting" if h < P["HURST_REVERT"] else "Random"


def _range_pos(c):
    """Where the last price sits in the range: 1 = at the high, 0 = at the low."""
    width = c.max() - c.min()
    return (c.iloc[-1] - c.min()) / width if width > 0 else np.nan


def read(df, P):
    c = df["Close"]
    ret = c.pct_change()
    n = P["TREND_WINDOW"]
    last = c.iloc[-1]
    fast, slow = c.rolling(P["FAST_MA"]).mean().iloc[-1], c.rolling(P["SLOW_MA"]).mean().iloc[-1]
    if last > slow and fast > slow:
        trend = "▲ Up"
    elif last < slow and fast < slow:
        trend = "▼ Down"
    else:
        trend = "◆ Mixed"
    move = last / c.iloc[-1 - n] - 1 if len(c) > n else np.nan
    dvol = ret.tail(n).std()
    m = P["SLOW_TREND_WINDOW"]
    slow = last / c.iloc[-1 - m] - 1 if len(c) > m else np.nan
    svol = ret.tail(m).std()
    # last day's move and opening gap, in units of a normal daily move (measured before that day)
    normal = ret.iloc[:-1].tail(P["SHOCK_VOL_WINDOW"]).std()
    shock = ret.iloc[-1] / normal if normal > 0 else np.nan
    gap = (df["Open"].iloc[-1] / c.iloc[-2] - 1) / normal if normal > 0 and len(c) > 1 else np.nan
    return {
        "Shock": shock,
        "Gap": gap,
        "Close": last,
        "Trend": trend,
        # the N-day move divided by a normal N-day move: 2.0 = twice the usual distance
        "Trend strength": move / (dvol * np.sqrt(n)) if dvol > 0 else np.nan,
        "Move %": move * 100,
        "Slow strength": slow / (svol * np.sqrt(m)) if svol > 0 else np.nan,
        "High pos": _range_pos(c.tail(P["HIGH_WINDOW"])) if len(c) >= P["HIGH_WINDOW"] else np.nan,
        "Skewness": ret.tail(P["SKEWNESS_WINDOW"]).skew(),
        "Hurst": hurst(np.log(c), P),
        "EWMA vol": ret.ewm(halflife=P["VOL_EWMA_HALFLIFE"]).std().iloc[-1] * np.sqrt(252) * 100,
        "Realized vol": ret.tail(P["RV_WINDOW"]).std() * np.sqrt(252) * 100,
    }
