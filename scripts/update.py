"""
Sensex Tracker — daily updater.

Live mode (default):   fetch prices (Yahoo Finance) + news (Google News RSS),
                       compute indicators/signals, write docs/index.html + data.json.
Demo mode (--demo):    no network; synthesise price history from the seed prices
                       so the full pipeline + dashboard can be validated offline.

No AI / LLM calls anywhere.
"""
from __future__ import annotations
import os
import sys
import csv
import json
import math
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine
import render as renderer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOLDINGS = os.path.join(ROOT, "holdings.csv")
WATCHLIST = os.path.join(ROOT, "watchlist.csv")
DOCS = os.path.join(ROOT, "docs")
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


def load_watchlist():
    """Read watchlist.csv — stocks tracked but not owned. Empty list if missing."""
    if not os.path.exists(WATCHLIST):
        return []
    out = []
    with open(WATCHLIST, newline="") as f:
        for row in csv.DictReader(f):
            if not (row.get("ticker") or "").strip():
                continue
            try:
                tp = float(row.get("target_price"))
            except (TypeError, ValueError):
                tp = None
            out.append({
                "ticker": row["ticker"].strip(),
                "name": (row.get("name") or row["ticker"]).strip(),
                "yahoo_symbol": (row.get("yahoo_symbol") or "").strip(),
                "target_price": tp,
                "notes": (row.get("notes") or "").strip(),
            })
    return out


def load_holdings():
    """
    Read holdings.csv. Multiple rows with the same ticker are separate
    purchase lots: they are aggregated (qty summed, cost qty-weighted) and the
    earliest lot's buy_date is kept for the 6-month rule (conservative).
    """
    def fnum(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None
    lots = []
    with open(HOLDINGS, newline="") as f:
        for row in csv.DictReader(f):
            lots.append({
                "ticker": row["ticker"].strip(),
                "name": row["name"].strip(),
                "yahoo_symbol": row["yahoo_symbol"].strip(),
                "qty": float(row["qty"]),
                "buy_price": float(row["buy_price"]),
                "buy_date": (row.get("buy_date") or "").strip(),
                "seed_price": float(row.get("seed_price") or 0),
                "sector": (row.get("sector") or "Others").strip() or "Others",
                "target_price": fnum(row.get("target_price")),
                "stop_loss": fnum(row.get("stop_loss")),
                "notes": (row.get("notes") or "").strip(),
            })
    merged = {}
    for l in lots:
        m = merged.setdefault(l["ticker"], {
            "ticker": l["ticker"], "name": l["name"], "yahoo_symbol": l["yahoo_symbol"],
            "qty": 0.0, "cost_total": 0.0, "buy_date": l["buy_date"],
            "seed_price": l["seed_price"], "sector": l["sector"],
            "target_price": l["target_price"], "stop_loss": l["stop_loss"],
            "notes": l["notes"], "lots": [],
        })
        m["qty"] += l["qty"]
        m["cost_total"] += l["qty"] * l["buy_price"]
        m["lots"].append({"qty": l["qty"], "buy_price": l["buy_price"], "buy_date": l["buy_date"]})
        if l["buy_date"] and (not m["buy_date"] or l["buy_date"] < m["buy_date"]):
            m["buy_date"] = l["buy_date"]
        if l["seed_price"]:
            m["seed_price"] = l["seed_price"]
        for k in ("target_price", "stop_loss"):
            if l[k] is not None:
                m[k] = l[k]
        if l["notes"]:
            m["notes"] = l["notes"]
    out = []
    for m in merged.values():
        m["avg_cost"] = (m["cost_total"] / m["qty"]) if m["qty"] else 0.0
        del m["cost_total"]
        out.append(m)
    return out


# ---------------------------------------------------------------- live fetch
def fetch_prices(holdings):
    """
    Return ({ticker: {'price','prev_close','closes','has_price'}}, history, px)
    where history = {'dates': [...], 'values': [...]} is the total portfolio
    value over the past year (holdings only; no-feed symbols counted flat), and
    px = {'dates': [...], 'series': {ticker: [close|None, ...]}} is every
    symbol's daily close on one shared date axis — raw material for the
    per-stock charts. We already download this; keeping it costs one dict.
    """
    import yfinance as yf
    import pandas as pd
    syms = [h["yahoo_symbol"] for h in holdings]
    data = yf.download(syms, period="1y", interval="1d",
                       group_by="ticker", threads=True, progress=False, auto_adjust=True)
    px = {"dates": [d.strftime("%Y-%m-%d") for d in data.index], "series": {}}
    result = {}
    series_parts, flat_value = [], 0.0
    for h in holdings:
        s = h["yahoo_symbol"]
        if s.upper() == "CASH" or not s:
            # cash / parked capital is a first-class position at price 1.0
            result[h["ticker"]] = {"price": 1.0, "prev_close": 1.0, "closes": [], "has_price": True}
            if h.get("qty"):
                flat_value += h["qty"]
            continue
        try:
            close_s = data[s]["Close"].dropna()
            closes = [float(x) for x in close_s.tolist()]
        except Exception:
            close_s, closes = None, []
        if closes and closes[-1] > 0:
            result[h["ticker"]] = {
                "price": closes[-1],
                "prev_close": closes[-2] if len(closes) > 1 else None,
                "closes": closes,
                "has_price": True,
            }
            px["series"][h["ticker"]] = _align(close_s, data.index)
            if h.get("qty"):
                series_parts.append(close_s * h["qty"])
        else:
            result[h["ticker"]] = {
                "price": h["seed_price"], "prev_close": None,
                "closes": [], "has_price": False,
            }
            if h.get("qty"):
                flat_value += h["qty"] * h["seed_price"]
    history = {"dates": [], "values": []}
    if series_parts:
        total = pd.concat(series_parts, axis=1).ffill().sum(axis=1) + flat_value
        total = total.dropna()
        history = {
            "dates": [d.strftime("%Y-%m-%d") for d in total.index],
            "values": [round(float(v)) for v in total.tolist()],
        }
    return result, history, px


def _align(series, index):
    """A price series reindexed onto a shared date axis, rounded, None for gaps."""
    import math
    out = []
    for v in series.reindex(index).tolist():
        out.append(None if (v is None or (isinstance(v, float) and math.isnan(v))) else round(float(v), 2))
    return out


def fetch_long(holdings, start, extra_syms=()):
    """
    Weekly closes from `start` for every symbol we track — holdings, watchlist,
    and (via extra_syms) tickers fully exited but still in sells.csv, which the
    5-year portfolio reconstruction needs. One batch call.
    """
    import yfinance as yf
    syms = sorted({h["yahoo_symbol"] for h in holdings
                   if h.get("yahoo_symbol") and h["yahoo_symbol"].upper() != "CASH"}
                  | set(extra_syms))
    if not syms:
        return {"dates": [], "series": {}}
    try:
        data = yf.download(syms, start=start, interval="1wk", group_by="ticker",
                           threads=True, progress=False, auto_adjust=True)
    except Exception:
        return {"dates": [], "series": {}}
    if data is None or len(data) == 0:
        return {"dates": [], "series": {}}
    out = {"dates": [d.strftime("%Y-%m-%d") for d in data.index], "series": {}}
    by_sym = {}
    for h in holdings:
        by_sym.setdefault(h.get("yahoo_symbol"), h["ticker"])
    for s in extra_syms:
        by_sym.setdefault(s, s.split(".")[0])
    for s in syms:
        try:
            col = data[s]["Close"].dropna()
        except Exception:
            continue
        if len(col):
            out["series"][by_sym[s]] = _align(col, data.index)
    # the in-progress week has no close yet — drop trailing all-empty bars
    while out["dates"] and all(v[-1] is None for v in out["series"].values()):
        out["dates"].pop()
        for v in out["series"].values():
            v.pop()
    return out


SNAPSHOTS = os.path.join(ROOT, "docs", "snapshots.json")


def holdings_start(holdings):
    """Earliest buy date across current holdings — where the lot ledger becomes
    complete. Before this, only sold positions are traceable."""
    dates = [lot.get("buy_date") for h in holdings for lot in (h.get("lots") or [])
             if lot.get("buy_date")]
    dates += [h.get("buy_date") for h in holdings if h.get("buy_date")]
    dates = [d for d in dates if d and len(d) == 10]
    return min(dates) if dates else ""


def long_start(holdings):
    """
    Start of the long price history: five years back, or six months before the
    oldest position if that is older. Floored at 2008. As real buy dates
    replace the vintage placeholders this reaches back further on its own.
    """
    t = dt.date.today()
    five = f"{t.year - 5:04d}-{t.month:02d}-01"
    earliest = holdings_start(holdings) or five
    y, m = int(earliest[:4]), int(earliest[5:7]) - 6
    if m <= 0:
        y, m = y - 1, m + 12
    return max("2008-01-01", min(five, f"{y:04d}-{m:02d}-01"))


def update_snapshots(summary, sectors):
    """Append/replace today's snapshot of REAL portfolio state. Returns all snaps."""
    snaps = []
    if os.path.exists(SNAPSHOTS):
        try:
            snaps = json.load(open(SNAPSHOTS))
        except Exception:
            snaps = []
    today = dt.date.today().isoformat()
    entry = {"date": today, "value": summary["current"], "invested": summary["invested"],
             "sectors": {s["name"]: s["value"] for s in sectors}}
    snaps = [s for s in snaps if s.get("date") != today] + [entry]
    snaps.sort(key=lambda s: s["date"])
    os.makedirs(os.path.dirname(SNAPSHOTS), exist_ok=True)
    json.dump(snaps, open(SNAPSHOTS, "w"), separators=(",", ":"))
    return snaps


def splice_history(history, snaps):
    """
    True history: recorded snapshots where they exist, reconstructed (current
    holdings × past prices) before the first snapshot. Marks the boundary.
    """
    if not snaps:
        return history, None
    snap_map = {s["date"]: s["value"] for s in snaps}
    first_snap = snaps[0]["date"]
    dates, values = list(history.get("dates", [])), list(history.get("values", []))
    # replace reconstructed values with recorded ones where we have them
    for i, d in enumerate(dates):
        if d in snap_map:
            values[i] = snap_map[d]
    # append snapshot dates the price history didn't include (weekends won't occur)
    known = set(dates)
    for s in snaps:
        if s["date"] not in known:
            dates.append(s["date"])
            values.append(s["value"])
    order = sorted(range(len(dates)), key=lambda i: dates[i])
    return ({"dates": [dates[i] for i in order], "values": [values[i] for i in order]},
            first_snap)


def fetch_benchmark(dates):
    """Nifty-50 (^NSEI) closes aligned onto `dates` (list of 'YYYY-MM-DD'). []=fail."""
    if not dates:
        return []
    try:
        import yfinance as yf
        d = yf.download("^NSEI", period="1y", interval="1d", progress=False, auto_adjust=True)
        close = d["Close"].dropna()
        m = {ts.strftime("%Y-%m-%d"): float(v) for ts, v in close.items()}
    except Exception:
        return []
    out, last = [], None
    for day in dates:
        if day in m:
            last = m[day]
        out.append(last)
    # backfill leading None
    first = next((x for x in out if x is not None), None)
    return [x if x is not None else first for x in out] if first else []


def indexed_series(hist_values, bench_values):
    """Index portfolio & benchmark to 100 at the first point for a fair overlay."""
    if not hist_values or not bench_values or len(bench_values) != len(hist_values):
        return None
    p0, b0 = hist_values[0], bench_values[0]
    if not p0 or not b0:
        return None
    return {
        "portfolio": [round(v / p0 * 100, 2) for v in hist_values],
        "nifty": [round(v / b0 * 100, 2) for v in bench_values],
    }


def sector_allocation(rows):
    """Current value grouped by sector, largest first."""
    agg = {}
    for r in rows:
        if not r.get("has_price"):
            continue
        agg[r.get("sector", "Others")] = agg.get(r.get("sector", "Others"), 0.0) + r["current"]
    total = sum(agg.values()) or 1.0
    items = sorted(agg.items(), key=lambda kv: kv[1], reverse=True)
    return [{"name": k, "value": round(v), "pct": round(v / total * 100, 1)} for k, v in items]


def dividend_months(rows, n=12):
    """
    Dividends *received* (₹ amount × qty held) grouped into the last n months.
    Uses each row's corp['dividends'] entries ('%d %b %Y' dates).
    Returns {'labels': [...], 'values': [...]}.
    """
    today = dt.date.today()
    keys = []
    y, m = today.year, today.month
    for _ in range(n):
        keys.append((y, m))
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    keys.reverse()
    sums = {k: 0.0 for k in keys}
    for r in rows:
        for d in (r.get("corp") or {}).get("dividends", []):
            try:
                when = dt.datetime.strptime(d["date"], "%d %b %Y").date()
            except Exception:
                continue
            k = (when.year, when.month)
            if k in sums:
                sums[k] += d["amount"] * r.get("qty", 0)
    return {
        "labels": [dt.date(y, m, 1).strftime("%b %y") for (y, m) in keys],
        "values": [round(sums[k]) for k in keys],
    }


def fetch_all_news(holdings):
    import news as newsmod
    out = {}
    for h in holdings:
        try:
            out[h["ticker"]] = newsmod.fetch_news(h["name"], h["ticker"])
        except Exception:
            out[h["ticker"]] = []
    return out


# ---------------------------------------------------------------- demo synth
def synth_history(prices, holdings):
    """Synthetic portfolio-value series from the per-holding synthetic closes."""
    n = max((len(p["closes"]) for p in prices.values()), default=0)
    if not n:
        return {"dates": [], "values": []}
    values = []
    for t in range(n):
        total = 0.0
        for h in holdings:
            p = prices[h["ticker"]]
            closes = p["closes"]
            qty = h.get("qty", 0)
            if closes:
                idx = min(t, len(closes) - 1)
                total += qty * closes[idx]
            else:
                total += qty * p["price"]
        values.append(round(total))
    end = dt.date.today()
    dates = []
    d = end
    while len(dates) < n:
        if d.weekday() < 5:
            dates.append(d.strftime("%Y-%m-%d"))
        d -= dt.timedelta(days=1)
    dates.reverse()
    return {"dates": dates, "values": values}


def synth_px(prices, dates):
    """Offline stand-in for the daily/weekly price panels."""
    daily = {"dates": dates, "series": {}}
    for t, p in prices.items():
        c = p.get("closes") or []
        if c:
            daily["series"][t] = [round(float(x), 2) for x in c[-len(dates):]]
    weekly = {"dates": dates[::5], "series": {t: v[::5] for t, v in daily["series"].items()}}
    return daily, weekly


def synth_benchmark(history):
    """Synthetic Nifty series: gentler climb than the portfolio, for offline test."""
    n = len(history.get("values", []))
    if not n:
        return []
    import math
    base = 24000.0
    return [round(base * (1 + 0.14 * (t / (n - 1)) + 0.01 * math.sin(t / 12.0)), 2)
            for t in range(n)]


def load_sells():
    """Optional realized-sells log for tax. Empty list if file missing/empty."""
    path = os.path.join(ROOT, "sells.csv")
    if not os.path.exists(path):
        return []
    out = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            if not (row.get("ticker") or "").strip():
                continue
            try:
                out.append({
                    "ticker": row["ticker"].strip(),
                    "name": (row.get("name") or row["ticker"]).strip(),
                    "qty": float(row["qty"]),
                    "buy_price": float(row["buy_price"]),
                    "buy_date": (row.get("buy_date") or "").strip(),
                    "sell_price": float(row["sell_price"]),
                    "sell_date": (row.get("sell_date") or "").strip(),
                })
            except (TypeError, ValueError, KeyError):
                continue
    return out


def synth_prices(holdings):
    """Deterministic synthetic 1y history anchored to seed price, for offline test."""
    result = {}
    for i, h in enumerate(holdings):
        end = h["seed_price"] or 1.0
        # deterministic pseudo-trend so different stocks get different signals
        drift = math.sin(i) * 0.4 + 0.05
        n = 260
        closes = []
        for t in range(n):
            # start below/above end depending on drift, add gentle waves
            base = end * (1 - drift)
            frac = t / (n - 1)
            wave = math.sin(t / 9.0 + i) * end * 0.02
            price = base + (end - base) * frac + wave
            closes.append(max(price, 0.01))
        closes[-1] = end
        result[h["ticker"]] = {
            "price": end,
            "prev_close": closes[-2],
            "closes": closes,
            "has_price": end > 0,
        }
    return result


def demo_news(holdings):
    """A couple of illustrative headlines so the 'issue' path is visible offline."""
    sample = {
        "DRREDDY": [{"title": "Dr Reddy's shares slump after US FDA issues observations",
                     "link": "https://news.google.com/", "published": "22 Jul 2026",
                     "negative": True, "event": None}],
        "GOLDBEES": [{"title": "Gold ETFs see outflows as prices cool from record highs",
                      "link": "https://news.google.com/", "published": "23 Jul 2026",
                      "negative": False, "event": None}],
        "TATASTEEL": [{"title": "Tata Steel Q1 results: profit beats estimates on higher volumes",
                       "link": "https://news.google.com/", "published": "24 Jul 2026",
                       "negative": False, "positive": True, "event": "q1 results"}],
        "BEL": [{"title": "Bharat Electronics board to consider bonus issue on Aug 4",
                 "link": "https://news.google.com/", "published": "23 Jul 2026",
                 "negative": False, "event": "bonus issue"}],
        "RELIANCE": [{"title": "Reliance Industries Q1 results on July 29; retail arm in focus",
                      "link": "https://news.google.com/", "published": "23 Jul 2026",
                      "negative": False, "event": "results"}],
    }
    return {h["ticker"]: sample.get(h["ticker"], []) for h in holdings}


# ---------------------------------------------------------------- build
def build(demo=False):
    import corporate as corpmod
    holdings = load_holdings()
    watch = load_watchlist()
    all_syms = holdings + [{**w, "qty": 0, "avg_cost": 0.0, "seed_price": 0.0} for w in watch
                           if w["ticker"] not in {h["ticker"] for h in holdings}]
    if demo:
        # illustrative buy dates so the tax/returns preview isn't empty (preview only)
        base = dt.date.today()
        offs = [14, 4, 11]  # months ago: LTCG, STCG, approaching-LTCG
        for i, h in enumerate(holdings):
            if not h.get("buy_date"):
                mo = offs[i % 3]
                y, m = base.year, base.month - mo
                while m <= 0:
                    y -= 1; m += 12
                d = dt.date(y, m, min(base.day, 28)).isoformat()
                h["buy_date"] = d
                for lot in h.get("lots", []):
                    lot["buy_date"] = d
        demo_watch_seed = {"RELIANCE": 2874.0, "HDFCBANK": 1642.0, "INFY": 1519.0}
        for srec in all_syms:
            if srec["qty"] == 0 and srec["ticker"] in demo_watch_seed:
                srec["seed_price"] = demo_watch_seed[srec["ticker"]]
        prices = synth_prices(all_syms)
        history = synth_history(prices, holdings)
        px_daily, px_weekly = synth_px(prices, history["dates"])
        bench = synth_benchmark(history)
        news = demo_news(all_syms)
        corp = corpmod.demo_corporate(all_syms)
    else:
        prices, history, px_daily = fetch_prices(all_syms)
        known = {h["ticker"] for h in all_syms}
        exited = sorted({s["ticker"] + ".NS" for s in load_sells()
                         if s["ticker"] not in known} | {"^NSEI"})
        px_weekly = fetch_long(all_syms, long_start(holdings), exited)
        bench = fetch_benchmark(history["dates"])
        news = fetch_all_news(all_syms)
        corp = corpmod.fetch_all_corporate(all_syms)

    import discipline as discmod
    disc_map = discmod.load_discipline()
    journal = discmod.load_journal()
    violations = discmod.load_violations()
    floor_cfg = discmod.load_floor()
    if demo and not any(v.get("thesis") for v in disc_map.values()):
        # illustrative discipline data so the preview shows the feature working
        nxt = (dt.date.today() + dt.timedelta(days=45)).isoformat()
        over = (dt.date.today() - dt.timedelta(days=12)).isoformat()
        disc_map["TATASTEEL"] = {"stage": "SYSTEMATIZE",
            "thesis": "India steel demand compounding with infra capex; TSL cost curve improving post-UK restructuring",
            "proof_metric": "EBITDA/tonne > ₹12,000 for 2 consecutive quarters",
            "kill_condition": "EBITDA/tonne below ₹8,000 for 2 quarters, or China dumping resumes",
            "review_date": nxt, "horizon_quarters": "8"}
        disc_map["FEDERALBNK"] = {"stage": "SCALE",
            "thesis": "Best-in-class mid bank; NIM expansion + branch productivity story intact",
            "proof_metric": "ROA ≥ 1.3% sustained", "kill_condition": "GNPA > 3% or CEO exit",
            "review_date": over, "horizon_quarters": "12"}
        disc_map["SUZLON"] = {"stage": "PROVE",
            "thesis": "Wind capex cycle turning; order book conversion is the test",
            "proof_metric": "2 quarters of positive FCF", "kill_condition": "Order book flat QoQ twice",
            "review_date": nxt, "horizon_quarters": "6"}
        journal = [
            {"date": dt.date.today().isoformat(), "ticker": "TATASTEEL", "action": "note",
             "note": "Q1 results: EBITDA/tonne ₹12,400 — proof metric holding. No structural change."},
            {"date": (dt.date.today() - dt.timedelta(days=7)).isoformat(), "ticker": "", "action": "note",
             "note": "Weekly sweep: no structural change across portfolio. Metals capex commentary positive."},
        ]
        violations = [{"date": (dt.date.today() - dt.timedelta(days=40)).isoformat(),
                       "type": "sell_before_review", "ticker": "KWIL",
                       "justification": "Exited before review date on liquidity concerns — accepted the violation."}]
        floor_cfg = {"emergency_fund_target": "600000", "emergency_fund_current": "650000",
                     "term_insurance_renewal": (dt.date.today() + dt.timedelta(days=200)).isoformat(),
                     "health_insurance_renewal": (dt.date.today() - dt.timedelta(days=5)).isoformat(),
                     "investable_ceiling": "12000000"}

    rows = []
    for h in holdings:
        p = prices[h["ticker"]]
        rec = {**h, "price": p["price"], "prev_close": p["prev_close"], "has_price": p["has_price"],
               "discipline": disc_map.get(h["ticker"], {})}
        rows.append(engine.analyse_holding(rec, p["closes"], news.get(h["ticker"], []),
                                           corp=corp.get(h["ticker"])))

    watch_rows = []
    for w in watch:
        p = prices.get(w["ticker"], {"price": 0, "prev_close": None, "closes": [], "has_price": False})
        rec = {**w, "qty": 0, "avg_cost": 0.0, "buy_date": "",
               "price": p["price"], "prev_close": p["prev_close"], "has_price": p["has_price"]}
        watch_rows.append(engine.analyse_holding(rec, p["closes"], news.get(w["ticker"], []),
                                                 corp=corp.get(w["ticker"])))

    # order table by current value desc
    rows.sort(key=lambda r: r["current"], reverse=True)
    summary = engine.portfolio_summary(rows)
    generated = dt.datetime.now(IST).strftime("%d %b %Y, %I:%M %p IST")

    # ---- v5: snapshots (portfolio memory), risk, backtest, projections ------
    import risk as riskmod
    sectors = sector_allocation(rows)
    snaps = update_snapshots(summary, sectors)
    history, first_snap = splice_history(history, snaps)
    bench_aligned = bench if (bench and len(bench) == len(history["values"])) else \
        (bench + [bench[-1]] * (len(history["values"]) - len(bench)) if bench else [])

    price_map = {}
    value_map = {}
    for h in holdings:
        p = prices[h["ticker"]]
        if p["closes"]:
            price_map[h["ticker"]] = p["closes"]
        value_map[h["ticker"]] = h["qty"] * p["price"]

    risk_model = {
        "metrics": riskmod.risk_metrics(history["dates"], history["values"], bench_aligned),
        "correlation": riskmod.correlations(price_map, value_map),
        "backtest": riskmod.backtest_rule(price_map, value_map,
                                          gain_pct=engine.SELL_REVIEW_GAIN_PCT,
                                          window_days=126),
        "montecarlo": riskmod.monte_carlo(history["values"], years=3),
        "first_snapshot": first_snap,
        "n_snapshots": len(snaps),
    }

    import tax as taxmod
    sells = load_sells()
    if demo and not sells:
        sells = [
            {"ticker": "IRCTC", "name": "IRCTC", "qty": 100, "buy_price": 620, "buy_date": "2023-02-10",
             "sell_price": 940, "sell_date": "2025-03-15"},
            {"ticker": "ZOMATO", "name": "Zomato", "qty": 500, "buy_price": 138, "buy_date": "2025-01-05",
             "sell_price": 205, "sell_date": "2025-06-20"},
        ]
    tax_model = taxmod.build_tax(rows, sells)

    floor = discmod.floor_status(floor_cfg, summary["current"])
    adherence = discmod.adherence_score(
        rows, disc_map, journal, violations,
        friction_year=tax_model["realised_totals"].get("friction", 0),
        portfolio_value=summary["current"])

    import insight
    floor_date = holdings_start(holdings)
    history5y = insight.actual_history(px_weekly, holdings, sells, floor_date)
    nosell = insight.never_sold(px_weekly, holdings, sells, floor_date)
    latest = insight.latest_prices(prices, px_weekly)
    exits = insight.exit_report(sells, latest)
    alpha = insight.alpha_vs_index(rows, px_weekly)
    screen = insight.value_screen(rows, watch_rows)
    avgdown = insight.averaging_down(holdings, sells)
    cash = insight.cash_position(holdings, summary.get("current"))
    for r in rows:
        r["alpha"] = alpha.get(r["ticker"])
    if history5y["missing"]:
        print(f"  5y reconstruction: no price feed for {len(history5y['missing'])} "
              f"ticker(s): {', '.join(history5y['missing'][:8])}")
    print(f"  exits: {exits['good']}/{exits['n']} sales still look right "
          f"(₹{exits['left_on_table']:,.0f} left on the table, ₹{exits['saved']:,.0f} saved); "
          f"averaging-down events: {avgdown['n']}")

    model = {"summary": summary, "rows": rows, "watch": watch_rows,
             "history": history, "history5y": history5y, "nosell": nosell,
             "exits": exits, "screen": screen, "avgdown": avgdown, "cash": cash,
             "benchmark": indexed_series(history["values"], bench_aligned),
             "sectors": sectors, "div_months": dividend_months(rows),
             "tax": tax_model, "risk": risk_model,
             "discipline": {"floor": floor, "adherence": adherence,
                            "journal": journal[:30], "violations": violations[:30],
                            "journal_stats": discmod.journal_stats(journal),
                            "map": disc_map},
             "meta": {"generated": generated, "demo": demo}}

    os.makedirs(DOCS, exist_ok=True)
    # Price panels live in their own file: the dashboard lazy-loads it the first
    # time a chart is opened, so the main page stays small.
    with open(os.path.join(DOCS, "prices.json"), "w") as f:
        json.dump({"daily": px_daily, "weekly": px_weekly,
                   "generated": generated}, f, separators=(",", ":"), default=str)
    with open(os.path.join(DOCS, "data.json"), "w") as f:
        json.dump(model, f, indent=2, default=str)
    with open(os.path.join(DOCS, "index.html"), "w") as f:
        f.write(renderer.render(model))
    print(f"Built dashboard: {summary['n_priced']}/{summary['n_holdings']} priced, "
          f"P/L {summary['pnl']:.0f} ({summary['pnl_pct']:.2f}%), "
          f"{len(summary['sell_review'])} booking reviews, {len(summary['issues'])} issue flags. demo={demo}")
    return model


if __name__ == "__main__":
    build(demo="--demo" in sys.argv)
