"""Step 5 (preview): one page of tables and charts for every market."""
from datetime import datetime

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

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


def overview_html(t, bars):
    o = pd.DataFrame(index=t.index)
    o["Name"] = t["Name"]
    o["Close"] = t["Close"].map(num)
    o["Trend"] = t["Trend"]
    o["Trend strength"] = fmt(t["Trend strength"], "{:+.2f}")
    o["Realized vol"] = fmt(t["Realized vol"], "{:.0f}%")
    o["Implied vol"] = fmt(t["Implied vol"], "{:.0f}%")
    o["IV − RV"] = fmt(t["Implied vol"] - t["Realized vol"], "{:+.0f}")
    o["Skew"] = fmt(t["Skew"], "{:+.1f}")
    o["Put/call"] = fmt(t["Put/call"], "{:.2f}")
    o["Option OI"] = fmt(t["Option OI"], "{:,.0f}")
    o["Daily $ move"] = fmt(t["Daily $ move"], "${:,.0f}")
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
main{{max-width:1250px;margin:0 auto;padding:24px 16px 60px}}
h1{{font-size:26px;margin:0 0 4px}} h2{{font-size:17px;font-weight:500;margin:0 0 10px}}
.sub{{color:{muted};margin:0 0 24px}} section{{margin:0 0 40px}}
.note{{color:{muted};font-size:14px;max-width:80ch;margin:6px 0 0}} .scroll{{overflow-x:auto}}
table.summary{{border-collapse:collapse;width:100%;font-size:13px;font-variant-numeric:tabular-nums;white-space:nowrap}}
table.summary th{{text-align:right;color:{muted};font-weight:600;padding:7px 9px;border-bottom:1px solid {grid}}}
table.summary td{{text-align:right;padding:7px 9px;border-bottom:1px solid {grid}}}
table.summary th:nth-child(-n+2),table.summary td:nth-child(-n+2){{text-align:left}}
</style></head><body><main>
<h1>Morning report</h1><p class="sub">Prices through {asof} · generated {now} · {coverage}</p>
{body}</main></body></html>"""


def build(table, bars, gamma, curves, spreads, markets, P, path):
    t = table.copy()
    for col in ("Implied vol", "Skew", "Put/call", "Carry %/yr", "Calendar z", "Gamma rel", "Option OI"):
        if col not in t:
            t[col] = np.nan
    d = int(P["SKEW_DELTA"] * 100)
    parts = [(
        "<h2>Every market at a glance</h2><div class='scroll'>" + overview_html(t, bars) + "</div>",
        f"Trend strength is the {P['TREND_WINDOW']}-day move divided by a normal {P['TREND_WINDOW']}-day move "
        "(2.0 = twice the usual distance; the sign is the direction). Implied vol is what the options market expects; "
        "realized vol is what actually happened. Skew above zero means protection against a drop costs more than "
        "protection against a rally. Carry is the yearly price gap between the first two contract months. "
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
                               [f"{v:+.1f}" for v in s["Z"]], "%{y}: %{x:+.2f}"),
                          "Each bar is a spread's distance from its own recent average, in normal deviations. "
                          "Beyond +2 or -2 is unusual. Plain 'Calendar' spreads can be traded as one order in the "
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
