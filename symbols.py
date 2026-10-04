"""CQG symbols: what you type on the trading platform.

CQG writes a contract as root + month letter + two-digit year, e.g. EPZ26 for the
December 2026 E-mini S&P 500. Roots come from the `cqg` field in config.yaml.
"""
import re

import pandas as pd

MONTH_CODES = "FGHJKMNQUVXZ"   # Jan..Dec


def root(code, markets):
    return markets.get(code, {}).get("cqg", code)


def month_code(label):
    """'Dec 26' -> 'Z26'. Empty string if the label is not a contract month."""
    if not isinstance(label, str) or not label.strip():
        return ""
    try:
        d = pd.to_datetime(label, format="%b %y")
    except (ValueError, TypeError):
        return ""
    return f"{MONTH_CODES[d.month - 1]}{d.year % 100:02d}"


def contract(code, markets, label):
    """Full CQG contract symbol, e.g. ('ES', 'Dec 26') -> 'EPZ26'."""
    return root(code, markets) + month_code(label)


def front(code, markets, curves):
    """The contract the front-month price series is following, as a CQG symbol."""
    points = curves.get(code)
    return contract(code, markets, points[0][0]) if points else root(code, markets)


def calendar(code, markets, first_label, reverse):
    """Exchange-traded calendar spread, following the rules' example CLES1V20.
    S1 buys the front month and sells the next; W1 is the reverse."""
    return f"{root(code, markets)}{'W1' if reverse else 'S1'}{month_code(first_label)}"


def relabel(text, markets):
    """Swap any market codes appearing as whole words in a piece of text for CQG roots."""
    if not isinstance(text, str):
        return text
    codes = sorted(markets, key=len, reverse=True)
    pattern = r"(?<![A-Za-z0-9])(" + "|".join(re.escape(c) for c in codes) + r")(?![A-Za-z0-9])"
    return re.sub(pattern, lambda m: root(m.group(1), markets), text)


def resolve(symbol, markets):
    """Accept a market code (ES), a CQG root (EP) or a CQG contract (EPZ26).
    Returns (market code, contract label such as 'Dec 26' or '')."""
    s = symbol.upper()
    by_root = {m.get("cqg", c): c for c, m in markets.items()}
    if s in markets:
        return s, ""
    if s in by_root:
        return by_root[s], ""
    m = re.fullmatch(r"(.+)([FGHJKMNQUVXZ])(\d{2})", s)
    if m and (m.group(1) in by_root or m.group(1) in markets):
        code = by_root.get(m.group(1), m.group(1))
        label = pd.Timestamp(2000 + int(m.group(3)), MONTH_CODES.index(m.group(2)) + 1, 1).strftime("%b %y")
        return code, label
    return None, ""
