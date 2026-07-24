"""
Risk analytics + Monte Carlo + rule backtest — pure math, no AI, no network.

Everything works from price/value series already fetched by update.py.
"""
from __future__ import annotations
import math
import random

RISK_FREE = 6.5          # % p.a. (approx Indian 10y G-sec) for the risk-adjusted score
TRADING_DAYS = 252


def daily_returns(values):
    return [(values[i] / values[i - 1] - 1.0) for i in range(1, len(values))
            if values[i - 1]]


def max_drawdown(dates, values):
    """Worst peak-to-trough fall. Returns dict or None."""
    if len(values) < 2:
        return None
    peak, peak_i = values[0], 0
    worst = {"dd": 0.0, "peak_date": dates[0], "trough_date": dates[0], "recovered": None}
    trough_i = 0
    for i, v in enumerate(values):
        if v > peak:
            peak, peak_i = v, i
        dd = (v / peak - 1.0) if peak else 0.0
        if dd < worst["dd"]:
            worst = {"dd": dd, "peak_date": dates[peak_i], "trough_date": dates[i], "recovered": None}
            trough_i = i
    # recovery: first date after trough where value regains the peak
    peak_val = None
    for i in range(len(values)):
        if dates[i] == worst["peak_date"]:
            peak_val = values[i]
            break
    if peak_val:
        for i in range(trough_i, len(values)):
            if values[i] >= peak_val:
                worst["recovered"] = dates[i]
                break
    worst["dd_pct"] = round(worst["dd"] * 100, 1)
    return worst


def volatility_pct(values):
    r = daily_returns(values)
    if len(r) < 20:
        return None
    mean = sum(r) / len(r)
    var = sum((x - mean) ** 2 for x in r) / (len(r) - 1)
    return round(math.sqrt(var) * math.sqrt(TRADING_DAYS) * 100, 1)


def annualised_return_pct(values):
    if len(values) < 2 or not values[0]:
        return None
    total = values[-1] / values[0]
    years = len(values) / TRADING_DAYS
    if years <= 0 or total <= 0:
        return None
    return round((total ** (1 / years) - 1) * 100, 1)


def beta_vs(values, bench_values):
    if not bench_values or len(bench_values) != len(values):
        return None
    rp, rb = daily_returns(values), daily_returns(bench_values)
    if len(rp) != len(rb) or len(rp) < 20:
        return None
    mp, mb = sum(rp) / len(rp), sum(rb) / len(rb)
    cov = sum((a - mp) * (b - mb) for a, b in zip(rp, rb)) / (len(rp) - 1)
    varb = sum((b - mb) ** 2 for b in rb) / (len(rb) - 1)
    return round(cov / varb, 2) if varb else None


def risk_metrics(dates, values, bench_values):
    ann = annualised_return_pct(values)
    vol = volatility_pct(values)
    sharpe = None
    if ann is not None and vol:
        sharpe = round((ann - RISK_FREE) / vol, 2)
    return {
        "drawdown": max_drawdown(dates, values),
        "volatility": vol,
        "ann_return": ann,
        "beta": beta_vs(values, bench_values),
        "sharpe": sharpe,
    }


# ---------------------------------------------------------------- correlation
def _corr(a, b):
    n = min(len(a), len(b))
    if n < 30:
        return None
    a, b = a[-n:], b[-n:]
    ma, mb = sum(a) / n, sum(b) / n
    sa = math.sqrt(sum((x - ma) ** 2 for x in a))
    sb = math.sqrt(sum((x - mb) ** 2 for x in b))
    if not sa or not sb:
        return None
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (sa * sb)


def correlations(price_map, value_map, top_n=10, min_value_pct=1.0):
    """
    price_map: {ticker: closes list}; value_map: {ticker: current value}.
    Only holdings above min_value_pct of portfolio considered (noise control).
    Returns {pairs: [...], avg_corr, diversification_score}.
    """
    total = sum(value_map.values()) or 1.0
    tickers = [t for t, closes in price_map.items()
               if len(closes) >= 60 and value_map.get(t, 0) / total * 100 >= min_value_pct]
    rets = {t: daily_returns(price_map[t]) for t in tickers}
    pairs, corr_sum, corr_cnt = [], 0.0, 0
    for i in range(len(tickers)):
        for j in range(i + 1, len(tickers)):
            c = _corr(rets[tickers[i]], rets[tickers[j]])
            if c is None:
                continue
            corr_sum += c
            corr_cnt += 1
            pairs.append((tickers[i], tickers[j], c))
    pairs.sort(key=lambda x: -abs(x[2]))
    avg = (corr_sum / corr_cnt) if corr_cnt else None
    return {
        "pairs": [{"a": a, "b": b, "corr": round(c, 2)} for a, b, c in pairs[:top_n]],
        "avg_corr": round(avg, 2) if avg is not None else None,
        # 100 = perfectly diversified (avg corr <= 0), 0 = everything moves together
        "diversification": max(0, min(100, round((1 - avg) * 100))) if avg is not None else None,
        "n_considered": len(tickers),
    }


# ---------------------------------------------------------------- backtest
def backtest_rule(price_map, value_map, gain_pct=15.0, window_days=126, top_n=15):
    """
    Test 'sell if +gain% within window' vs buy-and-hold on each stock's series
    (entry at series start; cash after selling). A simplification — labelled so.
    """
    rows = []
    for t, closes in price_map.items():
        if len(closes) < 60 or not closes[0]:
            continue
        entry = closes[0]
        hold_ret = closes[-1] / entry - 1.0
        rule_ret, triggered, sold_day = hold_ret, False, None
        for i in range(1, min(window_days + 1, len(closes))):
            if closes[i] / entry - 1.0 >= gain_pct / 100.0:
                rule_ret = closes[i] / entry - 1.0
                triggered, sold_day = True, i
                break
        rows.append({"ticker": t, "value": value_map.get(t, 0),
                     "hold": round(hold_ret * 100, 1), "rule": round(rule_ret * 100, 1),
                     "triggered": triggered, "sold_day": sold_day})
    rows.sort(key=lambda r: -r["value"])
    total_v = sum(r["value"] for r in rows) or 1.0
    w_hold = sum(r["hold"] * r["value"] for r in rows) / total_v
    w_rule = sum(r["rule"] * r["value"] for r in rows) / total_v
    return {
        "rows": rows[:top_n],
        "weighted_hold": round(w_hold, 1),
        "weighted_rule": round(w_rule, 1),
        "n": len(rows),
        "n_triggered": sum(1 for r in rows if r["triggered"]),
        "gain_pct": gain_pct, "window_days": window_days,
    }


# ---------------------------------------------------------------- Monte Carlo
def monte_carlo(values, years=3, sims=1000, seed=42, weekly=True):
    """
    Bootstrap future paths from historical daily returns.
    Returns {labels(months), p10, p50, p90} sampled weekly to keep payload small.
    """
    r = daily_returns(values)
    if len(r) < 60:
        return None
    rng = random.Random(seed)
    horizon = int(years * TRADING_DAYS)
    step = 5 if weekly else 1
    n_points = horizon // step
    start = values[-1]
    # simulate
    paths_at = [[] for _ in range(n_points)]
    for _ in range(sims):
        v = start
        k = 0
        for d in range(1, horizon + 1):
            v *= (1 + rng.choice(r))
            if d % step == 0:
                paths_at[k].append(v)
                k += 1
    def pct(vals, p):
        s = sorted(vals)
        return s[min(len(s) - 1, int(p / 100 * len(s)))]
    labels = [round(((i + 1) * step) / TRADING_DAYS * 12, 1) for i in range(n_points)]
    return {
        "start": round(start),
        "months": labels,
        "p10": [round(pct(v, 10)) for v in paths_at],
        "p50": [round(pct(v, 50)) for v in paths_at],
        "p90": [round(pct(v, 90)) for v in paths_at],
        "years": years, "sims": sims,
    }
