"""
Discipline layer — the accountability instrument from Harry's spec, merged
into the tracker. Pure rules, no AI, no network.

Covers: process-adherence score, family-floor status, journal statistics,
review-date tracking, violation summary.
"""
from __future__ import annotations
import os
import csv
import datetime as dt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STAGES = ["PROVE", "MONETIZE", "SYSTEMATIZE", "SCALE"]
JOURNAL_WINDOW_WEEKS = 12          # cadence window for the adherence score
VIOLATION_WINDOW_DAYS = 365
FRICTION_FULL_PCT = 0.5            # friction/portfolio <= this -> full marks
FRICTION_ZERO_PCT = 2.0            # >= this -> zero marks


def _read(path):
    p = os.path.join(ROOT, path)
    if not os.path.exists(p):
        return []
    with open(p, newline="") as f:
        return [r for r in csv.DictReader(f)]


def load_discipline():
    """{ticker: {stage, thesis, proof_metric, kill_condition, review_date, horizon_quarters}}"""
    out = {}
    for r in _read("discipline.csv"):
        t = (r.get("ticker") or "").strip()
        if not t:
            continue
        out[t] = {
            "stage": (r.get("stage") or "").strip().upper(),
            "thesis": (r.get("thesis") or "").strip(),
            "proof_metric": (r.get("proof_metric") or "").strip(),
            "kill_condition": (r.get("kill_condition") or "").strip(),
            "review_date": (r.get("review_date") or "").strip(),
            "horizon_quarters": (r.get("horizon_quarters") or "").strip(),
        }
    return out


def load_journal():
    rows = []
    for r in _read("journal.csv"):
        if (r.get("date") or "").strip():
            rows.append({"date": r["date"].strip(), "ticker": (r.get("ticker") or "").strip(),
                         "action": (r.get("action") or "note").strip(), "note": (r.get("note") or "").strip()})
    rows.sort(key=lambda x: x["date"], reverse=True)
    return rows


def load_violations():
    rows = []
    for r in _read("violations.csv"):
        if (r.get("date") or "").strip():
            rows.append({"date": r["date"].strip(), "type": (r.get("type") or "").strip(),
                         "ticker": (r.get("ticker") or "").strip(),
                         "justification": (r.get("justification") or "").strip()})
    rows.sort(key=lambda x: x["date"], reverse=True)
    return rows


def load_floor():
    out = {}
    for r in _read("floor.csv"):
        k = (r.get("key") or "").strip()
        if k:
            out[k] = (r.get("value") or "").strip()
    return out


def floor_status(floor, invested, today=None):
    """Family floor check. Returns {items:[{label,ok,detail}], breached:bool}."""
    today = today or dt.date.today()
    items = []

    def num(k):
        try:
            return float(floor.get(k, ""))
        except ValueError:
            return None

    tgt, cur = num("emergency_fund_target"), num("emergency_fund_current")
    if tgt:
        if cur is None:
            items.append({"label": "Emergency fund", "ok": None,
                          "detail": f"target ₹{tgt:,.0f} — not yet attested (fill in floor settings)"})
        else:
            ok = cur >= tgt
            items.append({"label": "Emergency fund", "ok": ok,
                          "detail": f"₹{cur:,.0f} of ₹{tgt:,.0f} target"})

    for key, label in (("term_insurance_renewal", "Term insurance"),
                       ("health_insurance_renewal", "Health insurance")):
        v = floor.get(key, "")
        if not v:
            items.append({"label": label, "ok": None, "detail": "renewal date not attested"})
        else:
            try:
                d = dt.date.fromisoformat(v)
                ok = d >= today
                items.append({"label": label, "ok": ok,
                              "detail": f"valid till {d.strftime('%d %b %Y')}" if ok else f"LAPSED {d.strftime('%d %b %Y')}"})
            except ValueError:
                items.append({"label": label, "ok": None, "detail": f"invalid date '{v}'"})

    ceil = num("investable_ceiling")
    if ceil:
        ok = invested <= ceil
        items.append({"label": "Investable ceiling", "ok": ok,
                      "detail": f"₹{invested:,.0f} invested of ₹{ceil:,.0f} ceiling"})

    breached = any(i["ok"] is False for i in items)
    unattested = sum(1 for i in items if i["ok"] is None)
    return {"items": items, "breached": breached, "unattested": unattested}


def journal_stats(journal, today=None):
    """Weeks with >=1 entry in the last JOURNAL_WINDOW_WEEKS."""
    today = today or dt.date.today()
    weeks = set()
    for j in journal:
        try:
            d = dt.date.fromisoformat(j["date"])
        except ValueError:
            continue
        if (today - d).days <= JOURNAL_WINDOW_WEEKS * 7:
            weeks.add(d.isocalendar()[:2])
    return {"weeks_covered": len(weeks), "window": JOURNAL_WINDOW_WEEKS,
            "entries_total": len(journal)}


def adherence_score(rows, disc, journal, violations, friction_year, portfolio_value,
                    today=None):
    """
    Composite 0-100. Weights: thesis 30, review dates 20, journal cadence 25,
    violations 15, friction 10. Returns {score, parts:[...]}.
    """
    today = today or dt.date.today()
    active = [r for r in rows if r.get("qty", 0) > 0]
    n = len(active) or 1

    with_thesis = sum(1 for r in active if disc.get(r["ticker"], {}).get("thesis"))
    thesis_frac = with_thesis / n

    ok_review = 0
    for r in active:
        rd = disc.get(r["ticker"], {}).get("review_date", "")
        try:
            if rd and dt.date.fromisoformat(rd) >= today:
                ok_review += 1
        except ValueError:
            pass
    review_frac = ok_review / n

    js = journal_stats(journal, today)
    journal_frac = min(1.0, js["weeks_covered"] / js["window"])

    recent_v = 0
    for v in violations:
        try:
            if (today - dt.date.fromisoformat(v["date"])).days <= VIOLATION_WINDOW_DAYS:
                recent_v += 1
        except ValueError:
            pass
    viol_frac = max(0.0, 1.0 - recent_v / 10.0)

    fr_pct = (friction_year / portfolio_value * 100.0) if portfolio_value else 0.0
    if fr_pct <= FRICTION_FULL_PCT:
        friction_frac = 1.0
    elif fr_pct >= FRICTION_ZERO_PCT:
        friction_frac = 0.0
    else:
        friction_frac = 1.0 - (fr_pct - FRICTION_FULL_PCT) / (FRICTION_ZERO_PCT - FRICTION_FULL_PCT)

    parts = [
        {"name": "Theses written", "frac": round(thesis_frac, 2), "weight": 30,
         "detail": f"{with_thesis}/{n} positions have a written thesis"},
        {"name": "Review dates current", "frac": round(review_frac, 2), "weight": 20,
         "detail": f"{ok_review}/{n} have a future review date"},
        {"name": "Journal cadence", "frac": round(journal_frac, 2), "weight": 25,
         "detail": f"{js['weeks_covered']}/{js['window']} recent weeks journalled"},
        {"name": "Violations", "frac": round(viol_frac, 2), "weight": 15,
         "detail": f"{recent_v} in the last 12 months"},
        {"name": "Friction", "frac": round(friction_frac, 2), "weight": 10,
         "detail": f"{fr_pct:.2f}% of portfolio this year"},
    ]
    score = round(sum(p["frac"] * p["weight"] for p in parts))
    return {"score": score, "parts": parts}
