"""Visual morning report: turns the saved prices into one page of charts.

Run:  python charts.py
Downloads fresh prices, writes report.html and opens it in your browser.
"""
import webbrowser
from datetime import datetime

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import data

LOOKBACK = 120          # trading days shown in the price charts
BLUE, ORANGE, AQUA, RED = "#2a78d6", "#eb6834", "#1baf7a", "#e34948"
INK, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#e6e5e0", "#fcfcfb"
FONT = "system-ui, -apple-system, Segoe UI, Helvetica, Arial, sans-serif"


def metrics(cfg, bars):
    """One row per market: the numbers behind every chart."""
    rows = []
    for code, df in bars.items():
        c = df["Close"]
        ret = c.pct_change()
        ma20, ma50 = c.rolling(20).mean().iloc[-1], c.rolling(50).mean().iloc[-1]
        last = c.iloc[-1]
        if last > ma50 and ma20 > ma50:
            trend = "▲ Up"
        elif last < ma50 and ma20 < ma50:
            trend = "▼ Down"
        else:
            trend = "◆ Mixed"
        vol = ret.tail(20).std() * np.sqrt(252) * 100
        pv = cfg["markets"][code]["point_value"]
        rows.append({
            "Market": code,
            "Name": cfg["markets"][code]["name"],
            "Close": last,
            "1d %": ret.iloc[-1] * 100,
            "20d %": (last / c.iloc[-21] - 1) * 100,
            "Trend": trend,
            "Volatility %": vol,
            "Typical daily $ move": last * pv * vol / 100 / np.sqrt(252),
        })
    return pd.DataFrame(rows).set_index("Market")


def style(fig, height, title):
    fig.update_layout(
        title=dict(text=title, font=dict(size=17, color=INK), x=0, xanchor="left"),
        height=height, paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        font=dict(family=FONT, size=12, color=MUTED),
        margin=dict(l=60, r=30, t=70, b=40), hoverlabel=dict(font_family=FONT),
    )
    fig.update_xaxes(gridcolor=GRID, linecolor=GRID, zeroline=False)
    fig.update_yaxes(gridcolor=GRID, linecolor=GRID, zerolinecolor=MUTED)
    return fig


def price_panels(cfg, bars):
    """Small multiples: price with 20- and 50-day averages, one panel per market."""
    codes = list(bars)
    cols = 3
    rows = -(-len(codes) // cols)
    fig = make_subplots(
        rows=rows, cols=cols, vertical_spacing=0.09, horizontal_spacing=0.06,
        subplot_titles=[f"{c} · {cfg['markets'][c]['name']}" for c in codes])
    series = [("Price", None, BLUE, 2), ("20-day average", 20, ORANGE, 1.5),
              ("50-day average", 50, AQUA, 1.5)]
    for i, code in enumerate(codes):
        close = bars[code]["Close"]
        for name, window, color, width in series:
            y = (close if window is None else close.rolling(window).mean()).tail(LOOKBACK)
            fig.add_trace(go.Scatter(
                x=y.index, y=y, name=name, legendgroup=name, showlegend=(i == 0),
                mode="lines", line=dict(color=color, width=width),
                hovertemplate="%{y:,.4~f}"), row=i // cols + 1, col=i % cols + 1)
    style(fig, 250 * rows + 130, "Price and trend, last 6 months")
    fig.update_layout(margin=dict(t=120))
    fig.update_layout(hovermode="x unified",
                      legend=dict(orientation="h", y=1.06, yanchor="bottom", x=1, xanchor="right",
                                  font=dict(color=INK)))
    fig.update_annotations(font=dict(size=13, color=INK))
    return fig


def change_bars(m):
    s = m["20d %"].sort_values()
    fig = go.Figure(go.Bar(
        x=s.values, y=s.index, orientation="h", width=0.6,
        marker=dict(color=[BLUE if v >= 0 else RED for v in s.values], cornerradius=4),
        text=[f"{v:+.1f}%" for v in s.values], textposition="outside",
        textfont=dict(color=INK), cliponaxis=False,
        customdata=m.loc[s.index, "Name"], hovertemplate="%{customdata}: %{x:+.2f}%<extra></extra>"))
    style(fig, 60 + 36 * len(s) + 60, "Change over the last 20 trading days")
    fig.update_xaxes(ticksuffix="%")
    return fig


def vol_bars(m):
    s = m["Volatility %"].sort_values()
    fig = go.Figure(go.Bar(
        x=s.values, y=s.index, orientation="h", width=0.6,
        marker=dict(color=BLUE, cornerradius=4),
        text=[f"{v:.0f}%" for v in s.values], textposition="outside",
        textfont=dict(color=INK), cliponaxis=False,
        customdata=m.loc[s.index, "Name"], hovertemplate="%{customdata}: %{x:.1f}%<extra></extra>"))
    style(fig, 60 + 36 * len(s) + 60, "Volatility: how jumpy each market is (20-day, annualized)")
    fig.update_xaxes(ticksuffix="%")
    return fig


def corr_heatmap(bars):
    rets = pd.DataFrame({c: df["Close"].pct_change() for c, df in bars.items()}).tail(60)
    corr = rets.corr().round(2)
    fig = go.Figure(go.Heatmap(
        z=corr.values, x=corr.columns, y=corr.index, zmin=-1, zmax=1,
        colorscale=[[0, RED], [0.5, "#ecebe7"], [1, BLUE]], xgap=2, ygap=2,
        text=corr.values, texttemplate="%{text:.2f}", textfont=dict(size=11),
        hovertemplate="%{y} vs %{x}: %{z:.2f}<extra></extra>",
        colorbar=dict(title="Correlation", thickness=12)))
    style(fig, 520, "Which markets move together (60-day correlation of daily moves)")
    fig.update_yaxes(autorange="reversed")
    return fig


def table_html(m):
    t = m.copy()
    t["Close"] = t["Close"].map(lambda v: f"{v:,.2f}" if v >= 10 else f"{v:,.4g}")
    for col in ("1d %", "20d %"):
        t[col] = t[col].map("{:+.2f}%".format)
    t["Volatility %"] = t["Volatility %"].map("{:.0f}%".format)
    t["Typical daily $ move"] = t["Typical daily $ move"].map("${:,.0f}".format)
    return t.reset_index().to_html(index=False, border=0, classes="summary")


PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Morning report</title><style>
body{{margin:0;background:{surface};color:{ink};font-family:{font}}}
main{{max-width:1150px;margin:0 auto;padding:24px 16px 60px}}
h1{{font-size:26px;margin:0 0 4px}} .sub{{color:{muted};margin:0 0 24px}}
section{{margin:0 0 36px}} .note{{color:{muted};font-size:14px;max-width:75ch;margin:4px 0 0}}
.scroll{{overflow-x:auto}}
table.summary{{border-collapse:collapse;width:100%;font-size:14px;font-variant-numeric:tabular-nums}}
table.summary th{{text-align:right;color:{muted};font-weight:600;padding:8px 10px;border-bottom:1px solid {grid}}}
table.summary td{{text-align:right;padding:8px 10px;border-bottom:1px solid {grid}}}
table.summary th:nth-child(-n+2),table.summary td:nth-child(-n+2){{text-align:left}}
</style></head><body><main>
<h1>Morning report</h1><p class="sub">Prices through {asof} · generated {now}</p>
{body}</main></body></html>"""


def build(cfg, bars, path):
    m = metrics(cfg, bars)
    parts = [
        ("<div class='scroll'>" + table_html(m) + "</div>",
         "Trend is Up when the price and its 20-day average are both above the 50-day average, "
         "Down when both are below, Mixed otherwise. Typical daily $ move is what one contract "
         "gains or loses on a normal day."),
        (price_panels(cfg, bars),
         "Price above both averages, with the 20-day above the 50-day, is an uptrend. "
         "The reverse is a downtrend. Lines tangled together mean no clear trend."),
        (change_bars(m), "The strongest and weakest markets over the past month."),
        (vol_bars(m),
         "Higher volatility means bigger daily swings, so you trade fewer contracts there to risk the same dollars."),
        (corr_heatmap(bars),
         "Near +1: the two markets rise and fall together, so holding both the same way doubles one bet. "
         "Near -1: they move opposite. Near 0: unrelated."),
    ]
    body, first = "", True
    for item, note in parts:
        if isinstance(item, go.Figure):
            html = item.to_html(full_html=False, include_plotlyjs=first,
                                config={"displayModeBar": False, "responsive": True})
            first = False
        else:
            html = item
        body += f"<section>{html}<p class='note'>{note}</p></section>"
    asof = max(df.index[-1] for df in bars.values()).date()
    path.write_text(PAGE.format(
        surface=SURFACE, ink=INK, muted=MUTED, grid=GRID, font=FONT, asof=asof,
        now=datetime.now().strftime("%Y-%m-%d %H:%M"), body=body), encoding="utf-8")
    return path


if __name__ == "__main__":
    cfg = data.load_config()
    print("Downloading prices...")
    bars = data.fetch_all(cfg) or data.load_saved(cfg)
    if not bars:
        raise SystemExit("No price data. Check your internet connection and run again.")
    out = build(cfg, bars, data.ROOT / "report.html")
    print(f"Wrote {out}")
    webbrowser.open(out.as_uri())
