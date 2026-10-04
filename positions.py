"""Your open positions: a small command-line log, plus the checks the report runs on it.

You place every trade yourself in CQG, then record it here:

    python positions.py add ES long 10 7776.50          # opened or added to a position
    python positions.py add CL short 5 91.26 "Dec 26"   # optional contract month
    python positions.py close ES 7801.25                # closed all of it at this price
    python positions.py close ES 7801.25 4              # closed 4 contracts
    python positions.py list

Open positions live in positions.csv, every execution goes to trades.csv (used for the
daily 10-contract check and commissions), and closed trades with their P&L go to journal.csv.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent
POSITIONS, JOURNAL, TRADES = ROOT / "positions.csv", ROOT / "journal.csv", ROOT / "trades.csv"
COLS = ["market", "contract", "side", "contracts", "entry_price", "entry_date"]
COMMISSION_PER_SIDE = 2.50


def load():
    if not POSITIONS.exists():
        return pd.DataFrame(columns=COLS)
    return pd.read_csv(POSITIONS, dtype={"market": str, "contract": str}).fillna({"contract": ""})


def load_journal():
    return pd.read_csv(JOURNAL) if JOURNAL.exists() else pd.DataFrame()


def load_trades():
    return pd.read_csv(TRADES) if TRADES.exists() else pd.DataFrame()


def _log_trade(market, action, contracts, price):
    """One row per execution: the record of volume and commission."""
    row = pd.DataFrame([{"date": today(), "market": market, "action": action, "contracts": contracts,
                         "price": price, "commission": COMMISSION_PER_SIDE * contracts}])
    pd.concat([load_trades(), row]).to_csv(TRADES, index=False)


def today():
    return pd.Timestamp.today().strftime("%Y-%m-%d")


def add(market, side, contracts, price, contract=""):
    side = side.lower()
    if side not in ("long", "short"):
        sys.exit("side must be long or short")
    p = load()
    same = (p["market"] == market) & (p["contract"] == contract)
    if same.any():
        i = p.index[same][0]
        if p.loc[i, "side"] != side:
            sys.exit(f"You already hold {market} {p.loc[i, 'side']}. Use 'close' to reduce it first.")
        total = p.loc[i, "contracts"] + contracts
        p.loc[i, "entry_price"] = (p.loc[i, "entry_price"] * p.loc[i, "contracts"] + price * contracts) / total
        p.loc[i, "contracts"] = total
    else:
        p.loc[len(p)] = [market, contract, side, contracts, price, today()]
    p.to_csv(POSITIONS, index=False)
    _log_trade(market, "buy" if side == "long" else "sell", contracts, price)
    print(f"Recorded: {side} {contracts} {market} at {price}")


def close(market, price, contracts=None, point_value=None):
    p = load()
    hit = p.index[p["market"] == market]
    if not len(hit):
        sys.exit(f"No open position in {market}")
    i = hit[0]
    r = p.loc[i]
    n = int(contracts or r["contracts"])
    if n > r["contracts"]:
        sys.exit(f"You only hold {r['contracts']} {market}")
    sign = 1 if r["side"] == "long" else -1
    pnl = (price - r["entry_price"]) * sign * n * point_value
    row = pd.DataFrame([{"market": market, "contract": r["contract"], "side": r["side"], "contracts": n,
                         "entry_price": r["entry_price"], "entry_date": r["entry_date"], "exit_price": price,
                         "exit_date": today(), "pnl": round(pnl, 2)}])
    pd.concat([load_journal(), row]).to_csv(JOURNAL, index=False)
    _log_trade(market, "sell" if sign > 0 else "buy", n, price)
    if n == r["contracts"]:
        p = p.drop(i)
    else:
        p.loc[i, "contracts"] = r["contracts"] - n
    p.to_csv(POSITIONS, index=False)
    print(f"Closed {n} {market} at {price}: P&L ${pnl:,.0f} before commission")


def balance(table, markets, P):
    """Starting balance plus recorded results and open profit or loss."""
    p, j, tr = load(), load_journal(), load_trades()
    total = P["START_BALANCE"] + (j["pnl"].sum() if len(j) else 0.0) - (tr["commission"].sum() if len(tr) else 0.0)
    for _, r in p.iterrows():
        if r["market"] in table.index:
            sign = 1 if r["side"] == "long" else -1
            total += ((table.loc[r["market"], "Close"] - r["entry_price"]) * sign * r["contracts"]
                      * markets[r["market"]]["point_value"])
    return total


def evaluate(table, ranked, bars, markets, P):
    """Check every open position. Returns (table for the report, portfolio summary)."""
    p, j, tr = load(), load_journal(), load_trades()
    now = pd.Timestamp.today().normalize()
    realized = (j["pnl"].sum() if len(j) else 0.0) - (tr["commission"].sum() if len(tr) else 0.0)
    traded = int(tr.loc[tr["date"] == today(), "contracts"].sum()) if len(tr) else 0
    rows, risk, open_pnl = [], {}, 0.0
    for _, r in p.iterrows():
        code = r["market"]
        if code not in table.index:
            rows.append({"Market": code, "Action": "No data for this market"})
            continue
        t, s, close_ = table.loc[code], ranked.loc[code], bars[code]["Close"]
        sign = 1 if r["side"] == "long" else -1
        last, pv = t["Close"], markets[code]["point_value"]
        pnl = (last - r["entry_price"]) * sign * r["contracts"] * pv
        open_pnl += pnl
        # trailing stop: a set number of normal daily moves back from the best close since entry
        since = close_[close_.index >= pd.Timestamp(r["entry_date"])]
        best = max([r["entry_price"], *since]) if sign > 0 else min([r["entry_price"], *since])
        stop = best - sign * P["STOP_DAILY_MOVES"] * t["Daily $ move"] / pv
        notes = []
        if r["contract"]:
            try:
                days = (pd.to_datetime(r["contract"], format="%b %y") - now).days
                if days <= P["ROLL_WARN_DAYS"]:
                    when = "has started" if days <= 0 else f"starts in {days} days"
                    notes.append(f"contract month {when}: check expiry and first notice")
            except ValueError:
                pass
        shock = t.get("Shock", 0) or 0
        if abs(shock) >= P["SHOCK_MIN"]:
            notes.append(f"last day moved {abs(shock):.1f} normal days {'for' if shock * sign > 0 else 'against'} you")
        call = f"{'Long' if s['Direction'] > 0 else 'Short' if s['Direction'] < 0 else 'None'} {s['Agree']} of {s['Voting']}"
        if (last - stop) * sign <= 0:
            action = "CLOSE: trailing stop hit"
        elif s["Direction"] == -sign:
            action = "CLOSE: signals now point the other way"
        elif s["Direction"] == 0 or s["Score"] <= P["EXIT_MIN_SCORE"]:
            action = "CLOSE: signals no longer agree"
        elif s["Score"] >= P["ADD_MIN_SCORE"] and pnl > 0:
            action = "HOLD (adding is allowed)"
        else:
            action = "HOLD"
        risk[code] = risk.get(code, 0) + sign * r["contracts"] * t["Daily $ move"]
        rows.append({"Market": code, "Contract": r["contract"], "Side": r["side"].title(),
                     "Contracts": r["contracts"], "Entry": r["entry_price"], "Last": last, "P&L": pnl,
                     "Stop": stop, "Signals now": call, "Action": action, "Notes": "; ".join(notes)})

    codes = list(risk)
    w = np.array([risk[c] for c in codes])
    corr = pd.DataFrame({c: bars[c]["Close"].pct_change() for c in codes}).tail(P["CORR_WINDOW"]).corr().values
    daily_risk = float(np.sqrt(w @ corr @ w)) if codes else 0.0
    balance = P["START_BALANCE"] + realized + open_pnl
    return pd.DataFrame(rows), {
        "balance": balance, "daily_risk": daily_risk,
        "lockout_days": (balance * P["DAILY_LOSS_LOCKOUT_PCT"] / 100 / daily_risk) if daily_risk else np.nan,
        "traded_today": traded, "days_left": int(np.busday_count(now.date(), pd.Timestamp(P["COMPETITION_END"]).date())) + 1,
    }


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a or a[0] == "list":
        p = load()
        print(p.to_string(index=False) if len(p) else "No open positions.")
    elif a[0] == "add" and len(a) >= 5:
        add(a[1].upper(), a[2], int(a[3]), float(a[4]), a[5] if len(a) > 5 else "")
    elif a[0] == "close" and len(a) >= 3:
        import data
        m = data.load_markets()
        if a[1].upper() not in m:
            sys.exit(f"{a[1]} is not in config.yaml")
        close(a[1].upper(), float(a[2]), int(a[3]) if len(a) > 3 else None, m[a[1].upper()]["point_value"])
    else:
        print(__doc__)
