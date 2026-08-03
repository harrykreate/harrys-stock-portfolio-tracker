"""
Decision-support analytics that need no paid data and no model calls.

Everything here is arithmetic over three things we already have: the lot
ledger (holdings.csv + sells.csv), the weekly price panel, and the ratios
corporate.py pulls from the free Yahoo feed.

  exit_report()     did selling actually help? per closed lot and in total
  never_sold()      the portfolio if no sale had ever happened
  alpha_vs_index()  per position, return minus the index over the same window
  value_screen()    a mechanical cheapness screen over holdings + watchlist
  averaging_down()  every time a position was added to below its own average
  cash_position()   parked capital, from CASH rows in holdings.csv
"""
import datetime as dt

BENCH = "^NSEI"

# a mechanical "is it cheap and sound" screen, tuned to the tangible-asset /
# bank / PSU pattern rather than to growth names
SCREEN = [
    ("pe", "P/E under 20", lambda v: v is not None and 0 < v < 20),
    ("pb", "P/B under 3", lambda v: v is not None and 0 < v < 3),
    ("roe", "ROE above 12%", lambda v: v is not None and v > 12),
    ("de", "Debt/equity under 1", lambda v: v is not None and v < 1),
    ("div_yield", "Yield above 1%", lambda v: v is not None and v > 1),
]


def _last(series):
    """Last non-empty value of an aligned price series."""
    if not series:
        return None
    for v in reversed(series):
        if v is not None:
            return v
    return None


def _at(dates, series, when):
    """Value on the first date at or after `when` (None if out of range)."""
    if not series or not dates or not when:
        return None
    for i, d in enumerate(dates):
        if d >= when:
            for j in range(i, len(series)):
                if series[j] is not None:
                    return series[j]
            return None
    return None


def latest_prices(prices, weekly):
    """Current price per ticker — live where we have it, last weekly close for
    positions that were fully exited and are no longer tracked."""
    out = {}
    for t, p in (prices or {}).items():
        if p.get("has_price") and p.get("price"):
            out[t] = p["price"]
    for t, s in ((weekly or {}).get("series") or {}).items():
        if t not in out:
            v = _last(s)
            if v:
                out[t] = v
    return out


def exit_report(sells, latest, today=None):
    """
    For every closed lot: what it sold for, what it would fetch now, and the
    dozen-word verdict. Positive `impact` means the sale cost money — the
    shares went up after you let them go.
    """
    today = today or dt.date.today()
    rows, left, saved, unknown = [], 0.0, 0.0, 0
    for s in sells or []:
        now = latest.get(s["ticker"])
        if not now or not s.get("sell_price"):
            unknown += 1
            continue
        qty = s.get("qty") or 0
        impact = (now - s["sell_price"]) * qty
        since = (now / s["sell_price"] - 1) * 100.0
        days = None
        try:
            days = (today - dt.date.fromisoformat(s["sell_date"])).days
        except Exception:
            pass
        rows.append({
            "ticker": s["ticker"], "name": s.get("name", s["ticker"]), "qty": qty,
            "sell_price": s["sell_price"], "sell_date": s.get("sell_date", ""),
            "now": round(now, 2), "since": round(since, 1),
            "impact": round(impact), "days": days,
            "gain": round((s["sell_price"] - s.get("buy_price", 0)) * qty),
            "verdict": "cost you" if impact > 0 else ("saved you" if impact < 0 else "neutral"),
        })
        if impact > 0:
            left += impact
        else:
            saved += -impact
    rows.sort(key=lambda r: -r["impact"])
    good = sum(1 for r in rows if r["impact"] <= 0)
    return {
        "rows": rows,
        "left_on_table": round(left),
        "saved": round(saved),
        "net": round(saved - left),
        "n": len(rows), "good": good, "unpriced": unknown,
        "good_rate": round(good / len(rows) * 100) if rows else None,
        "worst": rows[0] if rows else None,
        "best": rows[-1] if rows else None,
    }


def _qty_curve(holdings, sells, ignore_sells=False):
    """qty(t) helpers: current quantity, and the dated buy/sell events."""
    qty_now, buys, sold = {}, {}, {}
    for h in holdings:
        qty_now[h["ticker"]] = qty_now.get(h["ticker"], 0) + (h.get("qty") or 0)
        for lot in (h.get("lots") or []):
            if lot.get("buy_date"):
                buys.setdefault(h["ticker"], []).append((lot["buy_date"], lot.get("qty") or 0))
    for s in sells:
        if s.get("sell_date") and not ignore_sells:
            sold.setdefault(s["ticker"], []).append((s["sell_date"], s.get("qty") or 0))
        if ignore_sells and s.get("qty"):
            # never-sold world: those shares are still on the books today
            qty_now[s["ticker"]] = qty_now.get(s["ticker"], 0) + s["qty"]
        if s.get("buy_date"):
            buys.setdefault(s["ticker"], []).append((s["buy_date"], s.get("qty") or 0))
    return qty_now, buys, sold


def _value_series(weekly, qty_now, buys, sold, floor_date=""):
    dates = weekly.get("dates") or []
    series = weekly.get("series") or {}
    tickers = set(qty_now) | set(buys) | set(sold)
    missing = sorted(t for t in tickers if not series.get(t) and qty_now.get(t))
    values = []
    for i, d in enumerate(dates):
        total = 0.0
        for t in tickers:
            px = series.get(t)
            if not px:
                continue
            q = qty_now.get(t, 0)
            q += sum(n for sd, n in sold.get(t, []) if sd > d)
            q -= sum(n for bd, n in buys.get(t, []) if bd > d)
            if q <= 0:
                continue
            p = px[i]
            if p is None:
                p = next((px[j] for j in range(i - 1, -1, -1) if px[j] is not None), None)
            if p:
                total += q * p
        values.append(round(total))
    first = next((i for i, v in enumerate(values) if v > 0), 0)
    if floor_date:
        first = max(first, next((i for i, d in enumerate(dates) if d >= floor_date), first))
    return {"dates": dates[first:], "values": values[first:], "missing": missing,
            "from": dates[first] if dates[first:] else ""}


def actual_history(weekly, holdings, sells, floor_date=""):
    """Portfolio value week by week, share counts rebuilt from the ledger."""
    q, b, s = _qty_curve(holdings, sells, ignore_sells=False)
    return _value_series(weekly, q, b, s, floor_date)


def never_sold(weekly, holdings, sells, floor_date=""):
    """The same portfolio in a world where no sale ever happened."""
    q, b, s = _qty_curve(holdings, sells, ignore_sells=True)
    return _value_series(weekly, q, b, s, floor_date)


def alpha_vs_index(rows, weekly, bench=BENCH):
    """
    Per position: your return since you bought, the index over the identical
    window, and the gap. Answers 'is this earning its place or just floating'.
    """
    dates = (weekly or {}).get("dates") or []
    series = (weekly or {}).get("series") or {}
    idx = series.get(bench)
    if not idx or not dates:
        return {}
    idx_now = _last(idx)
    out = {}
    for r in rows:
        bd, cost, price = r.get("buy_date"), r.get("avg_cost"), r.get("price")
        if not (bd and cost and price and r.get("has_price")):
            continue
        idx_then = _at(dates, idx, bd)
        if not idx_then or not idx_now:
            continue
        mine = (price / cost - 1) * 100.0
        index = (idx_now / idx_then - 1) * 100.0
        out[r["ticker"]] = {"mine": round(mine, 1), "index": round(index, 1),
                            "alpha": round(mine - index, 1)}
    return out


def value_screen(rows, watch):
    """Mechanical cheapness screen. Not advice — five checks, counted."""
    out = []
    for r in list(rows) + list(watch):
        c = r.get("corp") or {}
        checks, passed = [], 0
        for key, label, test in SCREEN:
            ok = test(c.get(key))
            checks.append({"label": label, "ok": bool(ok),
                           "value": c.get(key)})
            passed += 1 if ok else 0
        known = sum(1 for k, _, _ in SCREEN if c.get(k) is not None)
        out.append({
            "ticker": r["ticker"], "name": r["name"],
            "held": bool(r.get("qty")), "price": r.get("price"),
            "pe": c.get("pe"), "pb": c.get("pb"), "roe": c.get("roe"),
            "de": c.get("de"), "div_yield": c.get("div_yield"),
            "score": passed, "known": known, "checks": checks,
            "sector": r.get("sector", "Others"),
        })
    out.sort(key=lambda x: (-x["score"], x["pe"] if x["pe"] is not None else 1e9))
    return out


def averaging_down(holdings, sells):
    """
    Every lot bought below the running average cost of that position — the
    'it's cheaper now' reflex. For closed positions we can say how it ended.
    """
    lots = {}
    for h in holdings:
        for lot in (h.get("lots") or []):
            if lot.get("buy_date") and lot.get("buy_price"):
                lots.setdefault(h["ticker"], []).append(
                    {"d": lot["buy_date"], "p": lot["buy_price"], "q": lot.get("qty") or 0,
                     "name": h["name"], "open": True})
    for s in sells or []:
        if s.get("buy_date") and s.get("buy_price"):
            lots.setdefault(s["ticker"], []).append(
                {"d": s["buy_date"], "p": s["buy_price"], "q": s.get("qty") or 0,
                 "name": s.get("name", s["ticker"]), "open": False,
                 "exit": s.get("sell_price"), "exit_date": s.get("sell_date")})
    events = []
    for tk, ls in lots.items():
        ls.sort(key=lambda x: x["d"])
        run_q = run_c = 0.0
        for lot in ls:
            avg = (run_c / run_q) if run_q else None
            if avg and lot["p"] < avg * 0.98 and lot["q"]:
                ev = {"ticker": tk, "name": lot["name"], "date": lot["d"],
                      "price": lot["p"], "qty": lot["q"], "prev_avg": round(avg, 2),
                      "below": round((lot["p"] / avg - 1) * 100, 1), "open": lot["open"]}
                if not lot["open"] and lot.get("exit"):
                    ev["exit"] = lot["exit"]
                    ev["outcome"] = round((lot["exit"] - lot["p"]) * lot["q"])
                    ev["exit_date"] = lot.get("exit_date", "")
                events.append(ev)
            run_c += lot["p"] * lot["q"]
            run_q += lot["q"]
    events.sort(key=lambda e: e["date"], reverse=True)
    closed = [e for e in events if not e["open"] and "outcome" in e]
    return {
        "events": events,
        "n": len(events),
        "worked": sum(1 for e in closed if e["outcome"] > 0),
        "closed": len(closed),
        "net": round(sum(e["outcome"] for e in closed)),
    }


def cash_position(holdings, portfolio_value):
    """Parked capital: any holdings row whose symbol is CASH."""
    amount = sum((h.get("qty") or 0) for h in holdings
                 if (h.get("yahoo_symbol") or "").upper() == "CASH")
    total = (portfolio_value or 0)
    return {"amount": round(amount),
            "pct": round(amount / total * 100, 1) if total else 0.0,
            "tracked": amount > 0}
