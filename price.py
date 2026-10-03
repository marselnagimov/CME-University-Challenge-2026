"""Step 2, price read: trend and realized volatility."""
import numpy as np


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
    return {
        "Close": last,
        "Trend": trend,
        # the N-day move divided by a normal N-day move: 2.0 = twice the usual distance
        "Trend strength": move / (dvol * np.sqrt(n)) if dvol > 0 else np.nan,
        "Move %": move * 100,
        "Realized vol": ret.tail(P["RV_WINDOW"]).std() * np.sqrt(252) * 100,
    }
