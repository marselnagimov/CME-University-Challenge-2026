"""Step 2, positioning read: what speculators hold, from the CFTC's weekly report.

"Speculators" are the report's non-commercial traders. The report comes out on
Friday afternoon and shows positions as of the Tuesday before.
"""
import numpy as np
import pandas as pd

COLS = ["Spec pressure", "Spec change", "OI growth", "COT date"]


def read(cot, P):
    """One row per market: speculative pressure, its weekly change, and open-interest growth."""
    rows = {}
    for market, g in cot.groupby("market"):
        g = g.sort_values("date")
        last = g.iloc[-1]
        net = g["spec_long"] - g["spec_short"]
        gross = last["spec_long"] + last["spec_short"]
        back = P["OI_GROWTH_WEEKS"]
        rows[market] = {
            # +1 = speculators all long, -1 = all short
            "Spec pressure": (last["spec_long"] - last["spec_short"]) / gross if gross > 0 else np.nan,
            # change in speculators' net position over the last week, as % of open interest
            "Spec change": (net.iloc[-1] - net.iloc[-2]) / last["oi"] * 100 if len(g) > 1 and last["oi"] > 0 else np.nan,
            "OI growth": (last["oi"] / g["oi"].iloc[-1 - back] - 1) * 100 if len(g) > back else np.nan,
            "COT date": last["date"].strftime("%b %d"),
        }
    return pd.DataFrame.from_dict(rows, orient="index", columns=COLS)
