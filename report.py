"""Step 5 (preview): one page of tables and charts for every market."""
from datetime import datetime

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import events
import price
import signals

BLUE, ORANGE, AQUA, RED = "#2a78d6", "#eb6834", "#1baf7a", "#e34948"
INK, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#e6e5e0", "#fcfcfb"
FONT = "system-ui, -apple-system, Segoe UI, Helvetica, Arial, sans-serif"
DASH = "–"


def style(fig, height, title, top=70):
    fig.update_layout(
        title=dict(text=title, font=dict(size=17, color=INK), x=0, xanchor="left"),
        height=height, paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        font=dict(family=FONT, size=12, color=MUTED),
        margin=dict(l=70, r=40, t=top, b=40), hoverlabel=dict(font_family=FONT),
        legend=dict(orientation="h", y=1.0, yanchor="bottom", x=1, xanchor="right", font=dict(color=INK)))
    fig.update_xaxes(gridcolor=GRID, linecolor=GRID, zeroline=False)
    fig.update_yaxes(gridcolor=GRID, linecolor=GRID, zerolinecolor=MUTED)
    return fig


def num(v):
    return f"{v:,.2f}" if abs(v) >= 10 else f"{v:,.4g}"


def fmt(col, pattern):
    return col.map(lambda v: DASH if pd.isna(v) else pattern.format(v))


def events_html(calendar):
    if not calendar:
        return "<p class='note'>No scheduled events in the look-ahead window.</p>"
    items = "".join(f"<li><b>{when}</b>: {text}"
                    + ("" if not markets else " · affects " + ("every market" if markets == "ALL" else ", ".join(markets)))
                    + "</li>" for when, text, markets in calendar)
    return f"<ul class='events'>{items}</ul>"


def orders_html(sheet, plan, book, P, calendar):
    """The order sheet: what to buy or sell today to reach the target portfolio."""
    lock = "" if pd.isna(plan["lockout_days"]) else (
        f" The {P['DAILY_LOSS_LOCKOUT_PCT']}% lockout is <b>{plan['lockout_days']:.1f}</b> normal days' loss away.")
    line = (f"<p class='book'>Balance <b>${book['balance']:,.0f}</b> · risk budget <b>${plan['budget']:,.0f}</b> a day "
            f"({P['DAILY_RISK_PCT']}%) · target portfolio risk <b>${plan['risk']:,.0f}</b>.{lock} "
            f"Estimated margin <b>${plan['margin']:,.0f}</b> of a ${plan['margin_cap']:,.0f} cap"
            f"{' (sizes were cut to fit)' if plan['scaled'] else ''} · commission ${plan['commission']:,.2f}</p>")
    if plan["final_day"]:
        line = "<p class='book'><b>Final day: close every position at least 15 minutes before the market closes.</b></p>" + line
    if plan["filler"]:
        line += (f"<p class='book'><b>Volume:</b> these orders leave you {plan['filler']} contracts short of today's "
                 f"minimum of {P['MIN_CONTRACTS_PER_DAY']}. Make it up with a small round trip, such as buying and "
                 "selling a micro contract.</p>")
    if plan["too_big"]:
        line += (f"<p class='book'>Skipped because one contract exceeds its share of the risk budget: "
                 f"{', '.join(plan['too_big'])}. A micro contract may fit.</p>")
    if not len(sheet):
        return line + ("<p class='note'>No market has enough agreement to open a position "
                       f"(needs a score of {P['MIN_SCORE_TO_ENTER']}).</p>")
    o = pd.DataFrame({
        "Market": sheet["Market"], "Name": sheet["Name"], "Side": sheet["Side"],
        "Order": ["<b>" + ("Buy " if v > 0 else "Sell ") + f"{abs(int(v)):,}</b>" if v else "No change" for v in sheet["Order"]],
        "Held": sheet["Held"].map("{:+,d}".format), "Target": sheet["Target"].map("{:+,d}".format),
        "Stop": sheet["Stop"].map(lambda v: DASH if pd.isna(v) else num(v)),
        "Daily risk": sheet["Daily risk"].map("${:,.0f}".format),
        "Margin": [f"${m:,.0f}" + ("" if k else " (est.)") for m, k in zip(sheet["Margin"], sheet["Margin known"])],
        "Why": sheet["Why"],
        "Alerts and events": ["; ".join(a + events.for_market(calendar, c))
                              for a, c in zip(sheet["Alerts"], sheet["Market"])]})
    return line + "<div class='scroll'>" + o.to_html(index=False, border=0, classes="summary orders", escape=False) + "</div>"


def positions_html(held, book, P):
    """Open positions with an action for each, plus the portfolio risk line."""
    if not len(held):
        return ("<p class='note'>No open positions recorded. After a trade in CQG, record it with "
                "<code>python positions.py add ES long 10 7776.50</code></p>")
    h = held.copy()
    for col, pattern in (("Entry", None), ("Last", None), ("Stop", None)):
        h[col] = h[col].map(lambda v: DASH if pd.isna(v) else num(v))
    h["P&L"] = fmt(h["P&L"], "${:+,.0f}")
    h["Action"] = "<b>" + h["Action"] + "</b>"
    risk = book["daily_risk"]
    lock = "" if pd.isna(book["lockout_days"]) else (
        f" The {P['DAILY_LOSS_LOCKOUT_PCT']}% lockout is {book['lockout_days']:.1f} normal days' loss away.")
    line = (f"<p class='book'>Estimated balance <b>${book['balance']:,.0f}</b> · portfolio daily risk "
            f"<b>${risk:,.0f}</b> ({risk / book['balance'] * 100:.1f}% of balance).{lock} "
            f"Contracts recorded today: <b>{book['traded_today']} of {P['MIN_CONTRACTS_PER_DAY']}</b> · "
            f"trading days left: <b>{book['days_left']}</b></p>")
    return line + "<div class='scroll'>" + h.fillna("").to_html(
        index=False, border=0, classes="summary held", escape=False) + "</div>"


def agreement_html(s):
    """The ranked signal table: one row per market, one column per signal."""
    sym = {1: "▲", -1: "▼", 0: "–"}
    names = [n for n in signals.NAMES if n in s.columns]
    head = "".join(f"<th>{h}</th>" for h in ["#", "Market", "Name", "Call", "Agreement"] + names
                   + ["Strength", "Contracts", "Notes"])
    body = ""
    for i, (code, r) in enumerate(s.iterrows(), 1):
        d = r["Direction"]
        call = "▲ Long" if d > 0 else "▼ Short" if d < 0 else "– None"
        agree = f"{r['Agree']} of {r['Voting']}" + (f" ({r['Against']} against)" if r["Against"] else "")
        cells = "".join(f"<td class='v'>{'' if pd.isna(r[n]) or r[n] is None else sym[int(r[n])]}</td>"
                        for n in names)
        body += (f"<tr><td>{i}</td><td>{code}</td><td>{r['Name']}</td><td class='l'><b>{call}</b></td>"
                 f"<td class='l'>{agree if d else DASH}</td>{cells}<td>{r['Strength']:+.2f}</td>"
                 f"<td>{r['Contracts']:,.0f}</td><td class='l'>{'; '.join(r['Notes'])}</td></tr>")
    return f"<table class='summary agree'><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def overview_html(t, P):
    o = pd.DataFrame(index=t.index)
    o["Name"] = t["Name"]
    o["Close"] = t["Close"].map(num)
    o["Trend"] = t["Trend"]
    o["Last day"] = [DASH if pd.isna(v) else f"{v:+.1f}" + (" !" if abs(v) >= P["SHOCK_MIN"] else "") for v in t["Shock"]]
    o["Trend strength"] = fmt(t["Trend strength"], "{:+.2f}")
    o["Hurst"] = fmt(t["Hurst"], "{:.2f}")
    o["Behaviour"] = [price.hurst_label(h, P) for h in t["Hurst"]]
    o["Realized vol"] = fmt(t["Realized vol"], "{:.0f}%")
    o["Implied vol"] = fmt(t["Implied vol"], "{:.0f}%")
    o["IV − RV"] = fmt(t["Implied vol"] - t["Realized vol"], "{:+.0f}")
    o["Skew"] = fmt(t["Skew"], "{:+.1f}")
    o["Put/call"] = fmt(t["Put/call"], "{:.2f}")
    o["Option OI"] = fmt(t["Option OI"], "{:,.0f}")
    o["Daily $ move"] = fmt(t["Daily $ move"], "${:,.0f}")
    o["Spec pressure"] = fmt(t["Spec pressure"], "{:+.2f}")
    o["Spec change"] = fmt(t["Spec change"], "{:+.1f}")
    o["OI growth"] = fmt(t["OI growth"], "{:+.0f}%")
    o["Carry %/yr"] = fmt(t["Carry %/yr"], "{:+.1f}%")
    o["Calendar z"] = fmt(t["Calendar z"], "{:+.1f}")
    o["Gamma levels"] = [
        " / ".join(num(r * c) for r in sorted(rel)) if isinstance(rel, list) and rel else DASH
        for rel, c in zip(t["Gamma rel"], t["Close"])]
    return o.reset_index().to_html(index=False, border=0, classes="summary")


def hbar(values, labels, title, text, hover, diverging=True, suffix=""):
    colors = [BLUE if v >= 0 else RED for v in values] if diverging else BLUE
    fig = go.Figure(go.Bar(
        x=values, y=labels, orientation="h", width=0.6,
        marker=dict(color=colors, cornerradius=4), text=text, textposition="outside",
        textfont=dict(color=INK), cliponaxis=False, hovertemplate=hover + "<extra></extra>"))
    style(fig, 110 + 30 * len(values), title)
    fig.update_xaxes(ticksuffix=suffix)
    fig.update_yaxes(automargin=True)
    return fig


def vol_chart(t):
    v = t.dropna(subset=["Implied vol"]).copy()
    v["gap"] = v["Implied vol"] - v["Realized vol"]
    v = v.sort_values("gap")
    fig = go.Figure()
    for name, col, color in (("Implied (expected)", "Implied vol", BLUE), ("Realized (actual)", "Realized vol", ORANGE)):
        fig.add_trace(go.Bar(x=v[col], y=v.index, orientation="h", name=name,
                             marker=dict(color=color, cornerradius=3),
                             hovertemplate="%{y} " + name.lower() + ": %{x:.1f}%<extra></extra>"))
    style(fig, 120 + 34 * len(v), "Expected vs actual volatility")
    fig.update_layout(barmode="group", bargap=0.3, bargroupgap=0.1)
    fig.update_xaxes(ticksuffix="%")
    return fig


def grid(n, cols):
    return -(-n // cols), cols


def gamma_chart(gamma, t):
    codes = [c for c in gamma if len(gamma[c]) and gamma[c]["gex"].max() > 0]
    if not codes:
        return None
    rows, cols = grid(len(codes), 4)
    fig = make_subplots(rows=rows, cols=cols, subplot_titles=codes,
                        vertical_spacing=min(0.12, 0.5 / rows), horizontal_spacing=0.05)
    for i, code in enumerate(codes):
        g, close = gamma[code], t.loc[code, "Close"]
        r, c = i // cols + 1, i % cols + 1
        fig.add_trace(go.Bar(x=g["rel"] * close, y=g["gex"] / g["gex"].max() * 100, showlegend=False,
                             marker=dict(color=BLUE), hovertemplate="%{x:,.4~g}: %{y:.0f}<extra></extra>"),
                      row=r, col=c)
        fig.add_vline(x=close, line=dict(color=INK, width=1, dash="dot"), row=r, col=c)
        fig.update_yaxes(showticklabels=False, row=r, col=c)
    style(fig, 190 * rows + 90, "Gamma by price level (dotted line = current price)")
    fig.update_annotations(font=dict(size=13, color=INK))
    return fig


def curve_chart(curves):
    codes = list(curves)
    if not codes:
        return None
    rows, cols = grid(len(codes), 4)
    fig = make_subplots(rows=rows, cols=cols, subplot_titles=codes,
                        vertical_spacing=min(0.12, 0.5 / rows), horizontal_spacing=0.06)
    for i, code in enumerate(codes):
        labels, prices = zip(*curves[code])
        fig.add_trace(go.Scatter(x=labels, y=prices, mode="lines+markers", showlegend=False,
                                 line=dict(color=BLUE, width=2), marker=dict(size=8),
                                 hovertemplate="%{x}: %{y:,.4~f}<extra></extra>"),
                      row=i // cols + 1, col=i % cols + 1)
    style(fig, 190 * rows + 90, "Futures curve: price by contract month")
    fig.update_annotations(font=dict(size=13, color=INK))
    fig.update_xaxes(type="category", tickfont=dict(size=10))
    return fig


def price_chart(bars, markets, P):
    codes = list(bars)
    rows, cols = grid(len(codes), 4)
    fig = make_subplots(rows=rows, cols=cols, vertical_spacing=min(0.1, 0.4 / rows), horizontal_spacing=0.05,
                        subplot_titles=[f"{c} · {markets[c]['name']}" for c in codes])
    series = [("Price", None, BLUE, 2), (f"{P['FAST_MA']}-day average", P["FAST_MA"], ORANGE, 1.3),
              (f"{P['SLOW_MA']}-day average", P["SLOW_MA"], AQUA, 1.3)]
    for i, code in enumerate(codes):
        close = bars[code]["Close"]
        for name, window, color, width in series:
            y = (close if window is None else close.rolling(window).mean()).tail(P["CHART_DAYS"])
            fig.add_trace(go.Scatter(x=y.index, y=y, name=name, legendgroup=name, showlegend=(i == 0),
                                     mode="lines", line=dict(color=color, width=width),
                                     hovertemplate="%{y:,.4~f}"), row=i // cols + 1, col=i % cols + 1)
    style(fig, 200 * rows + 130, "Price and trend", top=120)
    fig.update_layout(hovermode="x unified", legend=dict(y=1.02))
    fig.update_annotations(font=dict(size=12, color=INK))
    fig.update_xaxes(tickfont=dict(size=10), nticks=4)
    return fig


def corr_chart(bars, P):
    corr = pd.DataFrame({c: df["Close"].pct_change() for c, df in bars.items()}).tail(P["CORR_WINDOW"]).corr()
    fig = go.Figure(go.Heatmap(
        z=corr.values, x=corr.columns, y=corr.index, zmin=-1, zmax=1,
        colorscale=[[0, RED], [0.5, "#ecebe7"], [1, BLUE]], xgap=1, ygap=1,
        hovertemplate="%{y} vs %{x}: %{z:.2f}<extra></extra>", colorbar=dict(title="Correlation", thickness=12)))
    style(fig, 760, f"Which markets move together ({P['CORR_WINDOW']}-day correlation of daily moves)")
    fig.update_yaxes(autorange="reversed")
    return fig


PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Morning report</title><style>
body{{margin:0;background:{surface};color:{ink};font-family:{font}}}
main{{max-width:1450px;margin:0 auto;padding:24px 16px 60px}}
h1{{font-size:26px;margin:0 0 4px}} h2{{font-size:17px;font-weight:500;margin:0 0 10px}}
.sub{{color:{muted};margin:0 0 24px}} section{{margin:0 0 40px}}
.note{{color:{muted};font-size:14px;max-width:80ch;margin:6px 0 0}} .scroll{{overflow-x:auto}} ul.events{{margin:0;padding-left:20px;font-size:14px;line-height:1.7}} .book{{font-size:14px;margin:0 0 10px}}
table.orders td:nth-child(-n+4),table.orders th:nth-child(-n+4),table.orders td:nth-last-child(-n+2),table.orders th:nth-last-child(-n+2){{text-align:left}}
table.held td:nth-child(n+9),table.held th:nth-child(n+9),table.held td:nth-child(3),table.held th:nth-child(3){{text-align:left}}
table.summary{{border-collapse:collapse;width:100%;font-size:13px;font-variant-numeric:tabular-nums;white-space:nowrap}}
table.summary th{{text-align:right;color:{muted};font-weight:600;padding:7px 9px;border-bottom:1px solid {grid}}}
table.summary td{{text-align:right;padding:7px 9px;border-bottom:1px solid {grid}}}
table.summary th:nth-child(-n+2),table.summary td:nth-child(-n+2){{text-align:left}}
table.agree th:nth-child(-n+5),table.agree td:nth-child(-n+5),table.agree td.l,table.agree th:last-child{{text-align:left}}
table.agree td.v,table.agree th:nth-child(n+6):nth-child(-n+19){{text-align:center}}
table.agree th{{white-space:normal;vertical-align:bottom;max-width:64px}}
</style></head><body><main>
<h1>Morning report</h1><p class="sub">Prices through {asof} · generated {now} · {coverage}</p>
{body}</main></body></html>"""


def build(calendar, sheet, plan, held, book, ranked, table, bars, gamma, curves, spreads, markets, P, path):
    t = table.copy()
    for col in ("Implied vol", "Skew", "Put/call", "Carry %/yr", "Calendar z", "Gamma rel", "Option OI",
                "Spec pressure", "Spec change", "OI growth"):
        if col not in t:
            t[col] = np.nan
    d = int(P["SKEW_DELTA"] * 100)
    parts = [(
        "<h2>Today's order sheet</h2>" + orders_html(sheet, plan, book, P, calendar),
        f"Positions you hold are kept unless the exit check says close. Empty slots (up to {P['MAX_POSITIONS']}) are "
        f"filled from the top of the signal ranking, needing a score of {P['MIN_SCORE_TO_ENTER']} and skipping "
        "anything that is the same bet as a position already chosen. Every position gets equal risk, scaled so the "
        "whole portfolio's normal daily swing equals the risk budget. Sizing uses the highest of implied, realized "
        "and recent-weighted volatility. Margin marked (est.) is a guess: check CQG before placing the order. "
        "A held position is only added to when it is in profit and agreement is still strong. "
        "Held and Target are signed: + is long, − is short."), (
        "<h2>Upcoming events</h2>" + events_html(calendar),
        f"Scheduled releases in the next {P['EVENT_LOOKAHEAD_DAYS']} days. Prices can jump on these, and a stop will "
        "not protect you from a gap, so consider holding less into an event that affects a position."), (
        "<h2>Open positions</h2>" + positions_html(held, book, P),
        f"CLOSE appears when the trailing stop is hit ({P['STOP_DAILY_MOVES']} normal daily moves back from the best "
        "close since entry), when the signals flip, or when they stop agreeing. Prices are the front-month "
        "close, so a position in a later month is approximate. Balance is the starting balance plus recorded "
        "results; CQG is the true figure. The script only advises: every order is yours to place."), (
        "<h2>Signal agreement: where the signals point the same way</h2><div class='scroll'>"
        + agreement_html(ranked) + "</div>",
        "Each signal votes ▲ long, ▼ short or – neutral. A blank cell means the signal has no data or does not "
        "apply to that kind of market. Markets are ranked by votes for the call minus votes against it. "
        f"<b>Trend</b>: the {P['TREND_WINDOW']}-day move for markets more volatile than {P['TREND_SPEED_VOL']}% a year, "
        f"the {P['SLOW_TREND_WINDOW']}-day move for calmer ones. <b>52w high</b>: price near its one-year high or low. "
        "<b>Carry</b>: what a long earns if prices stand still, compared across all markets. "
        "<b>Rel basis</b> (commodities): whether the front of the curve is more backwardated than the back. "
        "<b>Skewness</b> (commodities): lopsided past returns; the most negative vote long. "
        "<b>Cross-asset</b>: rising bonds favour stocks, rising stocks weigh on bonds. "
        "<b>FX lead</b> (commodities): the trend in the Australian and Canadian dollars. "
        "<b>Vol premium</b> (stock indexes): implied vol well above realized votes long. "
        "<b>Implied skew</b> (commodities): calls dearer than puts votes long. "
        f"<b>Skew shift</b>: change in skew, voting after {P['SKEW_MIN_SNAPSHOTS']} earlier daily runs. "
        "<b>Spec level</b>: markets where speculators are most net long vote long. "
        "<b>Spec change</b>: fades speculators' buying or selling over the last reported week. "
        "<b>OI growth</b> (commodities): rising open interest votes long. "
        "<b>Hurst</b>: backs the trend vote in a trending market, opposes it in a mean-reverting one. "
        + ("" if P["SHOCK_VOTE"] == "off" else f"<b>Shock</b>: a last-day move beyond {P['SHOCK_MIN']} normal daily moves; the vote "
           + {"fade": "goes against the move. ", "follow": "goes with the move. ",
              "hurst": "goes with the move in a market Hurst labels trending, against it in one labelled "
                       "reverting, and is blank where Hurst reads as random. "}.get(P["SHOCK_VOTE"], "")) +
        "Notes flag any market whose last day or opening gap was that extreme. "
        f"Contracts is how many give a normal daily swing of {P['DAILY_RISK_PCT']}% of your balance in that market "
        "alone, before any margin check. Positioning data is weekly and three days old when published."), (
        "<h2>Every market at a glance</h2><div class='scroll'>" + overview_html(t, P) + "</div>",
        f"Trend strength is the {P['TREND_WINDOW']}-day move divided by a normal {P['TREND_WINDOW']}-day move "
        "(2.0 = twice the usual distance; the sign is the direction). Last day is the most recent day's move in "
        f"normal daily moves, marked ! beyond {P['SHOCK_MIN']}. Hurst above 0.5 means moves have tended "
        "to continue, below 0.5 that they have tended to reverse, and near 0.5 is indistinguishable from random. Implied vol is what the options market expects; "
        "realized vol is what actually happened. Skew above zero means protection against a drop costs more than "
        "protection against a rally. Spec pressure runs from -1 (speculators all short) to +1 (all long); Spec change "
        "is their net buying over the last reported week as % of open interest; OI growth is the change in open "
        f"interest over {P['OI_GROWTH_WEEKS']} weeks. Carry is the yearly price gap between the first two contract months. "
        "Calendar z is how unusual that gap is. Gamma levels are prices where option positions are concentrated. "
        f"Option OI is how many option contracts are open: low numbers mean the options read is less reliable. "
        f"A dash means no data, or data too thin to trust.")]

    if t["Implied vol"].notna().any():
        parts.append((vol_chart(t),
                      "Blue longer than orange: the options market expects bigger moves than the market has been "
                      "making, often because an event is coming. Orange longer: options are pricing calm after a "
                      "rough patch."))
        s = t["Skew"].dropna().sort_values()
        if len(s):
            parts.append((hbar(s.values, s.index, f"Skew: {d}-delta put vol minus {d}-delta call vol",
                               [f"{v:+.1f}" for v in s], "%{y}: %{x:+.2f} vol points"),
                          "Right of zero: traders are paying up for downside protection. Left of zero: they are "
                          "paying up for upside. This is the price of a risk reversal."))
        g = gamma_chart(gamma, t)
        if g:
            parts.append((g, "Tall bars are prices where the most option gamma sits. Price often stalls near them "
                             "and can speed up once it breaks through. Levels come from the ETF's options, "
                             "rescaled to the futures price."))

    c = curve_chart(curves)
    if c:
        parts.append((c, "Sloping up (contango): later months cost more. Sloping down (backwardation): the market "
                         "is paying a premium for delivery now, usually a sign of tight supply. For stock index, "
                         "bond and currency futures the slope mostly reflects interest rates."))
    if len(spreads):
        s = spreads.dropna(subset=["Z"])
        s = s.reindex(s["Z"].abs().sort_values(ascending=False).index).head(P["SPREADS_SHOWN"]).iloc[::-1]
        if len(s):
            parts.append((hbar(s["Z"].values, s["Spread"] + "  (" + s["Type"] + ")",
                               f"Most stretched spreads (z-score against the last {P['SPREAD_WINDOW']} days)",
                               [f"{z:+.1f}  ·  H {h:.2f}" if not np.isnan(h) else f"{z:+.1f}"
                                for z, h in zip(s["Z"], s["Hurst"])], "%{y}: %{x:+.2f}"),
                          "Each bar is a spread's distance from its own recent average, in normal deviations. "
                          "Beyond +2 or -2 is unusual. H is the spread's Hurst exponent: well below 0.5 it has tended to snap "
                          "back, which is what a mean-reversion trade needs. Plain 'Calendar' spreads can be traded as one order in the "
                          "challenge; anything marked 'legged', plus ratios and packages, must be entered leg by "
                          "leg and is charged full margin on each leg."))

    parts.append((price_chart(bars, markets, P),
                  "Price above both averages, with the fast one above the slow one, is an uptrend. "
                  "The reverse is a downtrend. Lines tangled together mean no clear trend."))
    parts.append((corr_chart(bars, P),
                  "Blue: the two markets rise and fall together, so holding both the same way is one bet made twice. "
                  "Red: they move opposite. Pale: unrelated."))

    body, first = "", True
    for item, note in parts:
        if isinstance(item, go.Figure):
            item = item.to_html(full_html=False, include_plotlyjs=first,
                                config={"displayModeBar": False, "responsive": True})
            first = False
        body += f"<section>{item}<p class='note'>{note}</p></section>"
    coverage = (f"{len(t)} markets, options data for {t['Implied vol'].notna().sum()}, "
                f"curves for {len(curves)}")
    path.write_text(PAGE.format(
        surface=SURFACE, ink=INK, muted=MUTED, grid=GRID, font=FONT, coverage=coverage,
        asof=max(df.index[-1] for df in bars.values()).date(),
        now=datetime.now().strftime("%Y-%m-%d %H:%M"), body=body), encoding="utf-8")
    return path
