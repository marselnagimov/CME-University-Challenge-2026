"""Step 3, decide: collect every directional signal and rank markets by how many agree.

Each signal votes long (+1), short (-1) or neutral (0) for each market, or abstains
(blank) when it has no data or does not apply to that kind of market. Markets are
ranked by votes for the majority direction minus votes against it.
"""
import numpy as np
import pandas as pd

NAMES = ["Trend", "52w high", "Carry", "Rel basis", "Skewness", "Cross-asset", "FX lead",
         "Vol premium", "Implied skew", "Skew shift", "Spec level", "Spec change", "OI growth", "Hurst", "Shock"]


def _sign(v, threshold):
    """+1 above the threshold, -1 below its negative, 0 between, None if missing."""
    if v is None or pd.isna(v):
        return None
    return 1 if v > threshold else -1 if v < -threshold else 0


def _flip(v):
    return None if v is None else -v


def _ranked(values, P, high_is_long=True):
    """Compare markets with each other: the top slice votes one way, the bottom slice the other."""
    v = values.dropna()
    if len(v) < 6:
        return {}
    lo, hi = v.quantile(P["RANK_FRACTION"]), v.quantile(1 - P["RANK_FRACTION"])
    sign = 1 if high_is_long else -1
    return {c: sign if x >= hi else -sign if x <= lo else 0 for c, x in v.items()}


def skew_changes(table, path, P):
    """Today's skew minus its average over earlier snapshots, per market."""
    if not path.exists() or "Skew" not in table:
        return {}
    hist = pd.read_csv(path)
    hist = hist[hist["Date"] < pd.Timestamp.today().strftime("%Y-%m-%d")]
    out = {}
    for code, g in hist.dropna(subset=["Skew"]).groupby("Market"):
        if len(g) >= P["SKEW_MIN_SNAPSHOTS"] and code in table.index:
            out[code] = table.loc[code, "Skew"] - g["Skew"].tail(5).mean()
    return out


def alerts(r, P):
    """Plain-language flags for an extreme last-day move or opening gap."""
    out = []
    if abs(r.get("Shock", 0) or 0) >= P["SHOCK_MIN"]:
        out.append(f"last day {'rose' if r['Shock'] > 0 else 'fell'} {abs(r['Shock']):.1f} normal days' worth")
    if abs(r.get("Gap", 0) or 0) >= P["SHOCK_MIN"]:
        out.append(f"opened with a {abs(r['Gap']):.1f}-day gap {'up' if r['Gap'] > 0 else 'down'}")
    return out


def build(table, bars, P, iv_history_path, budget):
    t = table
    for col in ("Carry %/yr", "Rel basis", "Implied vol", "Skew", "Spec pressure", "Spec change", "OI growth"):
        if col not in t:
            t[col] = np.nan
    commodity = t["Group"] == "commodity"
    T = P["SIGNAL_TREND_MIN"]

    # --- signals that compare markets with each other ---
    # carry: what a long earns if prices stand still, per unit of risk. Contango is negative carry
    carry = _ranked(-t["Carry %/yr"] / t["Sizing vol"], P)
    # relative basis (commodities): a front end more backwardated than the back is bullish
    rel_basis = _ranked(t.loc[commodity, "Rel basis"], P)
    # skewness (commodities): the most negatively skewed outperform, the most positive underperform
    skewness = _ranked(t.loc[commodity, "Skewness"], P, high_is_long=False)
    # speculative pressure: markets where speculators are most net long outperform
    spec_level = _ranked(t["Spec pressure"], P)

    # --- signals shared by a whole group ---
    def slow(code):
        return _sign(t.loc[code, "Slow strength"], T) if code in t.index else None
    stocks, bonds = slow(P["CROSS_EQUITY"]), slow(P["CROSS_BOND"])
    fx = [t.loc[c, "Trend strength"] for c in P["COMMODITY_CURRENCIES"] if c in t.index]
    fx_lead = _sign(np.mean(fx), T) if fx else None
    changes = skew_changes(t, iv_history_path, P)

    rows = []
    for code, r in t.iterrows():
        g = r["Group"]
        # trend: fast signal for volatile markets, slow signal for calm ones
        speed = "Trend strength" if r["Sizing vol"] > P["TREND_SPEED_VOL"] else "Slow strength"
        trend = _sign(r[speed], T)
        pos, h = r.get("High pos"), r.get("Hurst")
        gap = r["Implied vol"] - r["Realized vol"]
        v = {
            "Trend": trend,
            # near the one-year high votes long, near the one-year low votes short
            "52w high": None if pd.isna(pos) else 1 if pos >= 1 - P["HIGH_EDGE"] else -1 if pos <= P["HIGH_EDGE"] else 0,
            "Carry": carry.get(code),
            "Rel basis": rel_basis.get(code),
            "Skewness": skewness.get(code),
            # rising bonds favour stocks; rising stocks weigh on bonds
            "Cross-asset": bonds if g == "equity" else _flip(stocks) if g == "bond" else None,
            # commodity currencies lead commodity prices
            "FX lead": fx_lead if g == "commodity" else None,
            # stock indexes: options pricing much more movement than has occurred is bullish
            "Vol premium": _sign(gap, P["VOL_PREMIUM_MIN"]) if g == "equity" else None,
            # commodities: calls dearer than puts (negative skew number) is bullish
            "Implied skew": _flip(_sign(r["Skew"], P["IMPLIED_SKEW_MIN"])) if g == "commodity" else None,
            # skew rising = more demand for downside protection (short); falling = long
            "Skew shift": _flip(_sign(changes.get(code), P["SKEW_CHANGE_MIN"])),
            "Spec level": spec_level.get(code),
            # fade what speculators did last week: their short-term flows tend to reverse
            "Spec change": _flip(_sign(r["Spec change"], P["COT_CHANGE_MIN"])),
            # commodities: growing open interest is bullish, shrinking is bearish
            "OI growth": _sign(r["OI growth"], P["OI_GROWTH_MIN"]) if g == "commodity" else None,
            # a trending market backs the trend vote; a mean-reverting one votes against it
            "Hurst": None if pd.isna(h) or trend is None else
                     trend if h > P["HURST_TREND"] else -trend if h < P["HURST_REVERT"] else 0,
        }
        mode = P["SHOCK_VOTE"]
        if mode in ("fade", "follow", "hurst"):
            # an extreme last-day move: vote with it ("follow") or against it ("fade").
            # "hurst" follows it in a trending market, fades it in a mean-reverting one,
            # and abstains where Hurst cannot tell the market from random
            hit = _sign(r["Shock"], P["SHOCK_MIN"])
            if mode == "hurst":
                mode = (None if pd.isna(h) else "follow" if h > P["HURST_TREND"]
                        else "fade" if h < P["HURST_REVERT"] else None)
            v["Shock"] = None if mode is None else hit if mode == "follow" else _flip(hit)
        cast = [x for x in v.values() if x is not None]
        direction = int(np.sign(sum(cast)))
        agree = sum(x == direction for x in cast) if direction else 0
        against = sum(x == -direction for x in cast) if direction else 0
        notes = [f"IV {gap:.0f} over RV"] if gap > P["IV_GAP_FLAG"] else []
        notes += alerts(r, P)
        rows.append({"Market": code, "Name": r["Name"], "Direction": direction, "Agree": agree,
                     "Against": against, "Voting": len(cast), "Score": agree - against,
                     "Strength": r[speed], **v, "Notes": notes, "Contracts": budget / r["Daily $ move"]})
    s = pd.DataFrame(rows).set_index("Market")
    s["_abs"] = s["Strength"].abs()
    s = s.sort_values(["Score", "_abs"], ascending=False).drop(columns="_abs")

    # Flag markets that are the same bet as a higher-ranked one
    corr = pd.DataFrame({c: bars[c]["Close"].pct_change() for c in s.index}).tail(P["CORR_WINDOW"]).corr()
    seen = []
    for code in s.index:
        d = s.loc[code, "Direction"]
        if not d:
            continue
        twin = next((o for o in seen if corr.loc[code, o] * d * s.loc[o, "Direction"] > P["SAME_BET_CORR"]), None)
        if twin:
            s.loc[code, "Notes"].append(f"same bet as {twin}")
        seen.append(code)
    return s
