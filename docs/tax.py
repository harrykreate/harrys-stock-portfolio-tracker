"""
Tax & returns module (India equity) — rule-based, no AI.

Rates are the post-Budget-2024 listed-equity rules and are kept as editable
constants. THIS IS NOT TAX ADVICE — verify current rates with a professional;
STT-paid listed shares only, no surcharge/cess modelled.
"""
from __future__ import annotations
import datetime as dt

# ---- editable rates ---------------------------------------------------------
STCG_RATE = 0.20            # Sec 111A, holding < 12 months
LTCG_RATE = 0.125          # Sec 112A, holding >= 12 months
LTCG_EXEMPTION = 125000     # ₹1.25 lakh aggregate LTCG exemption per year
LTCG_MONTHS = 12            # long-term threshold for listed equity
APPROACHING_WINDOW = 2      # months-before-LTCG to flag "hold a little longer"


# ---- friction (delivery equity, discount-broker defaults; editable) --------
BROKERAGE_PER_ORDER = 0.0     # ₹ flat (0 at discount brokers for delivery)
STT_PCT = 0.001               # 0.1% on both buy & sell (delivery)
EXCHANGE_PCT = 0.0000297      # NSE transaction charge
SEBI_PCT = 0.000001           # SEBI turnover fee
STAMP_PCT = 0.00015           # 0.015%, buy side only
GST_PCT = 0.18                # on brokerage + exchange + SEBI
DP_CHARGE_SELL = 15.34        # ₹ per scrip per sell day


def friction_cost(value, side):
    """Estimated transaction cost ₹ for one delivery trade of `value` (side: 'buy'|'sell')."""
    stt = value * STT_PCT
    exch = value * EXCHANGE_PCT
    sebi = value * SEBI_PCT
    stamp = value * STAMP_PCT if side == "buy" else 0.0
    dp = DP_CHARGE_SELL if side == "sell" else 0.0
    gst = (BROKERAGE_PER_ORDER + exch + sebi) * GST_PCT
    return round(BROKERAGE_PER_ORDER + stt + exch + sebi + stamp + dp + gst, 2)


def _parse(d):
    try:
        return dt.date.fromisoformat(str(d).strip())
    except (ValueError, TypeError):
        return None


def _months(d1, d2):
    return (d2.year - d1.year) * 12 + (d2.month - d1.month) - (1 if d2.day < d1.day else 0)


def xirr(cashflows, guess=0.15):
    """cashflows: list of (date, amount). Newton's method. None if it can't solve."""
    flows = [(d, a) for d, a in cashflows if d]
    if len(flows) < 2:
        return None
    if not (any(a < 0 for _, a in flows) and any(a > 0 for _, a in flows)):
        return None
    t0 = min(d for d, _ in flows)

    def npv(rate):
        return sum(a / (1 + rate) ** (((d - t0).days) / 365.0) for d, a in flows)

    def dnpv(rate):
        return sum(-((d - t0).days) / 365.0 * a / (1 + rate) ** (((d - t0).days) / 365.0 + 1)
                   for d, a in flows)

    rate = guess
    for _ in range(100):
        f = npv(rate)
        df = dnpv(rate)
        if abs(df) < 1e-9:
            break
        new = rate - f / df
        if new <= -0.9999:
            new = (rate - 0.9999) / 2
        if abs(new - rate) < 1e-7:
            return round(new * 100, 1)
        rate = new
    return round(rate * 100, 1) if -0.95 < rate < 10 else None


def build_tax(rows, sells, today=None):
    today = today or dt.date.today()

    # ---- unrealised gains split by holding period --------------------------
    ltcg_gain = stcg_gain = 0.0
    dated = 0
    approaching = []
    cashflows = []
    total_current = 0.0
    for r in rows:
        if not r.get("has_price"):
            continue
        gain = r["pnl"]
        total_current += r["current"]
        # portfolio XIRR cashflows from lots that have dates
        for lot in r.get("lots", []):
            d = _parse(lot.get("buy_date"))
            if d:
                cashflows.append((d, -lot["qty"] * lot["buy_price"]))
        bd = _parse(r.get("buy_date"))
        if bd:
            dated += 1
            m = _months(bd, today)
            if m >= LTCG_MONTHS:
                ltcg_gain += gain
            else:
                stcg_gain += gain
                if LTCG_MONTHS - m <= APPROACHING_WINDOW and gain > 0:
                    approaching.append({
                        "ticker": r["ticker"], "name": r["name"],
                        "months_to_go": LTCG_MONTHS - m, "gain": round(gain),
                    })
    if cashflows:
        cashflows.append((today, total_current))
    port_xirr = xirr(cashflows) if cashflows else None

    ltcg_taxable = max(0.0, ltcg_gain - LTCG_EXEMPTION)
    est_ltcg_tax = ltcg_taxable * LTCG_RATE
    est_stcg_tax = max(0.0, stcg_gain) * STCG_RATE

    # ---- realised gains from sells.csv -------------------------------------
    realised = []
    r_lt = r_st = r_tax = 0.0
    friction_total = 0.0
    for s in sells:
        gain = (s["sell_price"] - s["buy_price"]) * s["qty"]
        fr = friction_cost(s["qty"] * s["sell_price"], "sell") + \
             friction_cost(s["qty"] * s["buy_price"], "buy")
        friction_total += fr
        bd, sd = _parse(s.get("buy_date")), _parse(s.get("sell_date"))
        kind = "?"
        if bd and sd:
            kind = "LTCG" if _months(bd, sd) >= LTCG_MONTHS else "STCG"
        tax = 0.0
        if gain > 0:
            if kind == "LTCG":
                tax = gain * LTCG_RATE
                r_lt += gain
            elif kind == "STCG":
                tax = gain * STCG_RATE
                r_st += gain
        r_tax += tax
        pct = ((s["sell_price"] / s["buy_price"] - 1) * 100.0) if s["buy_price"] else None
        months = _months(bd, sd) if (bd and sd) else None
        realised.append({
            "ticker": s["ticker"], "name": s["name"], "qty": s["qty"],
            "buy_price": s["buy_price"], "sell_price": s["sell_price"],
            "buy_date": s.get("buy_date", ""),
            "gain": round(gain), "pct": None if pct is None else round(pct, 1),
            "months": months, "tax": round(tax), "kind": kind,
            "sell_date": s.get("sell_date", ""), "friction": round(fr),
        })

    # booked-P/L aggregates: running total, current-FY total, win rate
    realised.sort(key=lambda x: x.get("sell_date") or "")
    cum, booked_series = 0.0, []
    for x in realised:
        cum += x["gain"]
        if x.get("sell_date"):
            booked_series.append({"date": x["sell_date"], "cum": round(cum)})
    today_d = today
    fy_start = dt.date(today_d.year if today_d.month >= 4 else today_d.year - 1, 4, 1)
    fy_gain = fy_tax = 0.0
    for x in realised:
        sd2 = _parse(x.get("sell_date"))
        if sd2 and sd2 >= fy_start:
            fy_gain += x["gain"]
            fy_tax += x["tax"]
    wins = sum(1 for x in realised if x["gain"] > 0)
    booked = {
        "total": round(sum(x["gain"] for x in realised)),
        "fy": round(fy_gain), "fy_tax": round(fy_tax),
        "fy_label": f"FY {fy_start.year}-{str(fy_start.year+1)[2:]}",
        "n": len(realised), "wins": wins,
        "win_rate": round(wins / len(realised) * 100) if realised else None,
        "series": booked_series,
    }

    # ---- projected annual dividend income (trailing 12m × qty) -------------
    div_income = 0.0
    for r in rows:
        for d in (r.get("corp") or {}).get("dividends", []):
            div_income += d["amount"] * r.get("qty", 0)

    return {
        "unrealised": {
            "ltcg_gain": round(ltcg_gain), "stcg_gain": round(stcg_gain),
            "est_ltcg_tax": round(est_ltcg_tax), "est_stcg_tax": round(est_stcg_tax),
            "est_total_tax": round(est_ltcg_tax + est_stcg_tax),
            "dated": dated, "n": len([r for r in rows if r.get("has_price")]),
            "exemption": LTCG_EXEMPTION,
        },
        "approaching": sorted(approaching, key=lambda x: x["months_to_go"]),
        "realised": realised,
        "realised_totals": {"ltcg": round(r_lt), "stcg": round(r_st), "tax": round(r_tax),
                            "friction": round(friction_total)},
        "booked": booked,
        "xirr": port_xirr,
        "div_income": round(div_income),
        "rates": {"stcg": STCG_RATE, "ltcg": LTCG_RATE, "exemption": LTCG_EXEMPTION},
    }
