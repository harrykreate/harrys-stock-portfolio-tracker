"""
Corporate actions + fundamentals scraper (free, no AI).

Per holding, via yfinance:
  - recent dividends & stock splits (last 12 months)
  - next earnings date (if published)
  - latest quarterly revenue & net profit, with YoY change

Announcement-type events (bonus issues, record dates, results dates, board
meetings) are caught by the news scraper's keyword pass — see EVENT_KEYWORDS —
because there is no reliable free structured feed for NSE announcements.
"""
from __future__ import annotations
import datetime as dt

# Headline keywords that mark a corporate-action / event announcement.
EVENT_KEYWORDS = [
    "bonus issue", "bonus share", "stock split", "record date", "ex-date",
    "ex date", "dividend", "buyback", "rights issue", "q1 results", "q2 results",
    "q3 results", "q4 results", "quarterly results", "annual results",
    "board meeting", "agm", "earnings", "financial results", "demerger",
    "merger", "acquisition", "stake", "open offer", "ipo", "listing",
]


def classify_event(title: str):
    """Return the matched event keyword (for tagging) or None."""
    t = title.lower()
    for k in EVENT_KEYWORDS:
        if k in t:
            return k
    return None


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:
        return default


def fetch_corporate(symbol: str):
    """
    Fetch dividends/splits/earnings/fundamentals for one Yahoo symbol.
    Returns a dict; every field may be None/[] on failure — never raises.
    """
    import yfinance as yf
    t = yf.Ticker(symbol)
    out = {"dividends": [], "splits": [], "next_earnings": None,
           "q_revenue": None, "q_profit": None, "rev_yoy": None, "profit_yoy": None,
           "q_label": None,
           # fundamentals
           "pe": None, "pb": None, "roe": None, "de": None, "mcap": None,
           "wk_high": None, "wk_low": None, "div_yield": None}

    info = _safe(lambda: t.info) or {}

    def gi(*keys):
        for k in keys:
            v = info.get(k)
            if isinstance(v, (int, float)) and v == v:
                return float(v)
        return None

    out["pe"] = gi("trailingPE")
    out["pb"] = gi("priceToBook")
    roe = gi("returnOnEquity")
    out["roe"] = round(roe * 100, 1) if roe is not None else None      # to %
    de = gi("debtToEquity")
    out["de"] = round(de / 100, 2) if de is not None else None          # yf gives %, -> ratio
    out["mcap"] = gi("marketCap")
    out["wk_high"] = gi("fiftyTwoWeekHigh")
    out["wk_low"] = gi("fiftyTwoWeekLow")
    dy = gi("dividendYield")
    out["div_yield"] = round(dy, 2) if dy is not None else None

    cutoff = dt.datetime.now() - dt.timedelta(days=365)

    divs = _safe(lambda: t.dividends)
    if divs is not None and len(divs):
        for date, amt in divs.items():
            d = date.to_pydatetime().replace(tzinfo=None)
            if d >= cutoff:
                out["dividends"].append({"date": d.strftime("%d %b %Y"), "amount": round(float(amt), 2)})

    splits = _safe(lambda: t.splits)
    if splits is not None and len(splits):
        for date, ratio in splits.items():
            d = date.to_pydatetime().replace(tzinfo=None)
            if d >= cutoff:
                out["splits"].append({"date": d.strftime("%d %b %Y"), "ratio": float(ratio)})

    cal = _safe(lambda: t.calendar)
    if cal:
        ed = None
        if isinstance(cal, dict):
            ed = cal.get("Earnings Date")
            if isinstance(ed, (list, tuple)) and ed:
                ed = ed[0]
        if ed is not None:
            try:
                if hasattr(ed, "strftime"):
                    when = ed if isinstance(ed, dt.date) else ed.date()
                    if when >= dt.date.today():
                        out["next_earnings"] = when.strftime("%d %b %Y")
            except Exception:
                pass

    fin = _safe(lambda: t.quarterly_income_stmt)
    if fin is not None and hasattr(fin, "columns") and len(fin.columns) >= 1:
        try:
            cols = list(fin.columns)
            latest = cols[0]
            out["q_label"] = latest.strftime("%b %Y") if hasattr(latest, "strftime") else str(latest)

            def row(name, col):
                if name in fin.index:
                    v = fin.loc[name, col]
                    return None if v is None or (isinstance(v, float) and v != v) else float(v)
                return None

            rev = row("Total Revenue", latest)
            prof = row("Net Income", latest)
            out["q_revenue"] = rev
            out["q_profit"] = prof
            # YoY: same quarter last year = 4 columns back
            if len(cols) >= 5:
                prev = cols[4]
                rev_p, prof_p = row("Total Revenue", prev), row("Net Income", prev)
                if rev and rev_p:
                    out["rev_yoy"] = round((rev / rev_p - 1.0) * 100.0, 1)
                if prof and prof_p and prof_p != 0:
                    out["profit_yoy"] = round((prof / abs(prof_p) - (1.0 if prof_p > 0 else -1.0)) * 100.0, 1)
        except Exception:
            pass
    return out


def fetch_all_corporate(holdings, sleep_s=0.5):
    """Fetch corporate data for all holdings, politely spaced."""
    import time
    out = {}
    for h in holdings:
        out[h["ticker"]] = fetch_corporate(h["yahoo_symbol"])
        time.sleep(sleep_s)
    return out


# ---------------------------------------------------------------- demo data
def demo_corporate(holdings):
    """Deterministic sample corp data so the dashboard sections render offline."""
    sample = {
        "TCS": {"dividends": [{"date": "16 Jul 2026", "amount": 10.0}], "splits": [],
                "next_earnings": None, "q_revenue": 664790000000.0, "q_profit": 127600000000.0,
                "rev_yoy": 5.4, "profit_yoy": 4.2, "q_label": "Jun 2026"},
        "TATASTEEL": {"dividends": [{"date": "20 Jun 2026", "amount": 3.6}], "splits": [],
                      "next_earnings": "30 Jul 2026", "q_revenue": 559800000000.0,
                      "q_profit": 12400000000.0, "rev_yoy": 2.1, "profit_yoy": 28.0, "q_label": "Mar 2026"},
        "FEDERALBNK": {"dividends": [], "splits": [], "next_earnings": "28 Jul 2026",
                       "q_revenue": None, "q_profit": 10600000000.0, "rev_yoy": None,
                       "profit_yoy": 11.3, "q_label": "Jun 2026"},
        "M&M": {"dividends": [{"date": "05 Jul 2026", "amount": 21.1}], "splits": [],
                "next_earnings": "05 Aug 2026", "q_revenue": 310500000000.0,
                "q_profit": 32200000000.0, "rev_yoy": 14.7, "profit_yoy": 19.9, "q_label": "Jun 2026"},
        "SUZLON": {"dividends": [], "splits": [], "next_earnings": "25 Jul 2026",
                   "q_revenue": 35300000000.0, "q_profit": 8900000000.0,
                   "rev_yoy": 73.0, "profit_yoy": 240.0, "q_label": "Jun 2026"},
    }
    empty = {"dividends": [], "splits": [], "next_earnings": None, "q_revenue": None,
             "q_profit": None, "rev_yoy": None, "profit_yoy": None, "q_label": None}
    funda = {
        "TCS": dict(pe=27.4, pb=12.1, roe=51.2, de=0.05, mcap=8.3e12, wk_high=2540, wk_low=1990, div_yield=1.6),
        "TATASTEEL": dict(pe=18.9, pb=2.1, roe=9.8, de=1.35, mcap=2.3e12, wk_high=195, wk_low=122, div_yield=2.0),
        "DRREDDY": dict(pe=17.2, pb=3.0, roe=18.5, de=0.09, mcap=0.96e12, wk_high=1650, wk_low=1100, div_yield=0.7),
        "M&M": dict(pe=29.1, pb=4.8, roe=17.6, de=1.9, mcap=3.9e12, wk_high=3300, wk_low=2350, div_yield=0.6),
        "SUZLON": dict(pe=61.0, pb=13.2, roe=21.8, de=0.02, mcap=0.71e12, wk_high=58, wk_low=32, div_yield=0.0),
        "FEDERALBNK": dict(pe=12.1, pb=1.3, roe=13.9, de=None, mcap=0.87e12, wk_high=360, wk_low=170, div_yield=0.4),
        "HINDCOPPER": dict(pe=44.0, pb=6.1, roe=13.2, de=0.11, mcap=0.47e12, wk_high=580, wk_low=460, div_yield=0.5),
        "RELIANCE": dict(pe=25.6, pb=2.2, roe=8.9, de=0.44, mcap=19.4e12, wk_high=3020, wk_low=2400, div_yield=0.4),
        "HDFCBANK": dict(pe=19.8, pb=2.8, roe=16.9, de=None, mcap=12.5e12, wk_high=1790, wk_low=1360, div_yield=1.1),
        "INFY": dict(pe=24.1, pb=8.4, roe=31.5, de=0.09, mcap=6.3e12, wk_high=1730, wk_low=1350, div_yield=2.3),
    }
    out = {}
    for h in holdings:
        base = dict(sample.get(h["ticker"], dict(empty)))
        base.update({k: None for k in ("pe", "pb", "roe", "de", "mcap", "wk_high", "wk_low", "div_yield")})
        base.update(funda.get(h["ticker"], {}))
        out[h["ticker"]] = base
    return out
