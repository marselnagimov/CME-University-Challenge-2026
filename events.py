"""Scheduled events that can move markets: shown as warnings, never as votes."""
import numpy as np
import pandas as pd


def upcoming(table, P):
    """Events from today through the look-ahead window: list of (date label, text, markets)."""
    today = pd.Timestamp.today().normalize()
    end = today + pd.Timedelta(days=P["EVENT_LOOKAHEAD_DAYS"])
    found = []
    for date, text, markets in P["EVENTS"]:
        d = pd.Timestamp(date)
        if today <= d <= end:
            found.append((d, text, markets))
    for day in pd.date_range(today, end):
        for weekday, text, markets in P["WEEKLY_EVENTS"]:
            if day.weekday() == weekday:
                found.append((day, text, markets))

    # Month-end rebalancing: funds sell whichever of stocks and bonds has done better
    month_end = today + pd.offsets.BMonthEnd(0)
    left = int(np.busday_count(today.date(), month_end.date()))
    eq, bd = P["CROSS_EQUITY"], P["CROSS_BOND"]
    if 0 <= left < P["MONTH_END_DAYS"] and eq in table.index and bd in table.index:
        gap = table.loc[eq, "Move %"] - table.loc[bd, "Move %"]
        side = "stocks" if gap > 0 else "bonds"
        found.append((today, f"Month-end rebalancing: {side} have outperformed by {abs(gap):.1f} points this month, "
                             f"so funds are likely sellers of {side}", [eq, bd]))
    found.sort(key=lambda e: e[0])
    return [(d.strftime("%a %b %d"), text, markets) for d, text, markets in found]


def for_market(calendar, code):
    return [f"{when}: {text.split(',')[0]}" for when, text, markets in calendar if markets == "ALL" or code in markets]
