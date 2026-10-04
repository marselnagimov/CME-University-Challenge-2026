"""Steps 4 and 5, size and report: turn the ranked signals into a target portfolio and an order sheet.

Rules, all tunable at the top of run.py:
  1. Keep held positions the exit check says to hold; drop the ones it says to close.
  2. Fill the remaining slots from the top of the signal ranking, skipping markets that
     are the same bet as one already chosen.
  3. Give every position equal risk, scaled so the whole portfolio's normal daily swing
     equals the risk budget (a % of the current balance, so size grows with profits).
  4. Scale everything down if estimated margin would exceed the cap.
  5. Orders are the difference between the target and what is held. A held position is only
     increased when it is in profit and agreement is still strong; it can always be trimmed.
"""
import numpy as np
import pandas as pd

import signals


def build(ranked, held, book, table, bars, markets, P):
    balance = book["balance"]
    budget = balance * P["DAILY_RISK_PCT"] / 100
    final_day = pd.Timestamp.today().normalize() >= pd.Timestamp(P["COMPETITION_END"])
    corr = pd.DataFrame({c: bars[c]["Close"].pct_change() for c in table.index}).tail(P["CORR_WINDOW"]).corr()

    current, closing, stops, addable = {}, {}, {}, set()
    for _, r in held.iterrows():
        if "Side" not in r or pd.isna(r.get("Side")):
            continue
        signed = (1 if r["Side"] == "Long" else -1) * r["Contracts"]
        current[r["Market"]] = current.get(r["Market"], 0) + signed
        stops[r["Market"]] = r["Stop"]
        if final_day:
            closing[r["Market"]] = "final day: be flat 15 minutes before the close"
        elif r["Action"].startswith("CLOSE"):
            closing[r["Market"]] = r["Action"][7:]
        elif "adding is allowed" in r["Action"]:
            addable.add(r["Market"])

    # 1-3. choose the positions and give each equal risk, scaled to the portfolio budget.
    # A market whose single contract is too big for its share is skipped and the next one tried.
    held_now = {c: int(np.sign(q)) for c, q in current.items() if c not in closing}
    too_big = set()
    while True:
        picks, why = dict(held_now), {c: "held" for c in held_now}
        if not final_day:
            for code, r in ranked.iterrows():
                if len(picks) >= P["MAX_POSITIONS"]:
                    break
                d = int(r["Direction"])
                if (code in picks or code in closing or code in too_big or d == 0
                        or r["Score"] < P["MIN_SCORE_TO_ENTER"]):
                    continue
                if any(corr.loc[code, o] * d * s > P["SAME_BET_CORR"] for o, s in picks.items()):
                    continue
                picks[code], why[code] = d, f"new: {r['Agree']} of {r['Voting']} signals agree"
        codes = list(picks)
        s = np.array([picks[c] for c in codes], dtype=float)
        C = corr.loc[codes, codes].values if codes else np.zeros((0, 0))
        move = np.array([table.loc[c, "Daily $ move"] for c in codes])
        unit = budget / np.sqrt(s @ C @ s) if codes else 0.0
        target = np.floor(unit / move) if codes else np.array([])
        zero = {c for c, t in zip(codes, target) if t == 0 and c not in held_now}
        if not zero:
            break
        too_big |= zero

    # 4. margin cap
    per = np.array([markets[c].get("margin") or table.loc[c, "Close"] * markets[c]["point_value"]
                    * markets[c].get("margin_pct", P["MARGIN_FALLBACK_PCT"]) / 100 for c in codes])
    cap = balance * P["MARGIN_USE_MAX_PCT"] / 100
    scaled = bool(codes) and (target * per).sum() > cap
    if scaled:
        target = np.floor(target * cap / (target * per).sum())

    # 5. orders
    rows = []
    for i, c in enumerate(codes):
        t = int(target[i]) * picks[c]
        h = current.get(c, 0)
        order = t - h
        if h and abs(order) < P["REBALANCE_MIN_PCT"] / 100 * abs(t):
            order, t = 0, h                     # too small a change to bother with
        if h and order * picks[c] > 0 and c not in addable:
            order, t = 0, h                     # only add to positions that are winning with strong agreement
        last, pv = table.loc[c, "Close"], markets[c]["point_value"]
        stop = stops.get(c, last - picks[c] * P["STOP_DAILY_MOVES"] * move[i] / pv)
        rows.append({"Market": c, "Name": table.loc[c, "Name"], "Side": "Long" if picks[c] > 0 else "Short",
                     "Held": h, "Target": t, "Order": order, "Stop": stop, "Daily risk": abs(t) * move[i],
                     "Margin": abs(t) * per[i], "Margin known": bool(markets[c].get("margin")),
                     "Alerts": signals.alerts(table.loc[c], P),
                     "Why": why[c] if order == 0 or why[c] != "held" else
                            ("add: balance or volatility changed" if order * picks[c] > 0 else "trim: balance or volatility changed")})
    for c, reason in closing.items():
        h = current[c]
        rows.append({"Market": c, "Name": table.loc[c, "Name"] if c in table.index else "",
                     "Side": "Long" if h > 0 else "Short", "Held": h, "Target": 0, "Order": -h, "Stop": np.nan,
                     "Daily risk": 0.0, "Margin": 0.0, "Margin known": True,
                     "Alerts": signals.alerts(table.loc[c], P) if c in table.index else [], "Why": "close: " + reason})
    sheet = pd.DataFrame(rows)

    w = np.array([r["Target"] * table.loc[r["Market"], "Daily $ move"] for r in rows if r["Target"]])
    kept = [r["Market"] for r in rows if r["Target"]]
    risk = float(np.sqrt(w @ corr.loc[kept, kept].values @ w)) if kept else 0.0
    volume = int(sheet["Order"].abs().sum()) if len(sheet) else 0
    return sheet, {
        "budget": budget, "risk": risk, "margin": float(sheet["Margin"].sum()) if len(sheet) else 0.0,
        "margin_cap": cap, "scaled": scaled, "final_day": final_day,
        "lockout_days": balance * P["DAILY_LOSS_LOCKOUT_PCT"] / 100 / risk if risk else np.nan,
        "too_big": sorted(too_big),
        "filler": max(0, P["MIN_CONTRACTS_PER_DAY"] - book["traded_today"] - volume),
        "commission": volume * P["COMMISSION_PER_SIDE"],
    }
