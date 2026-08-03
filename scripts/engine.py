"""
Analytics engine for the Sensex Tracker.

Pure functions only -- no network calls -- so the logic can be unit-tested
offline and reused by both the live updater and the demo/self-test.

All "decision" logic is rule-based (moving averages, RSI, return thresholds,
news keyword scan). No AI / LLM calls are made anywhere in this project.
"""
from __future__ import annotations
import math
import datetime as dt
from statistics import mean

# ---- Tunables (edit these to change behaviour) ------------------------------

RSI_PERIOD = 14
SMA_FAST = 50
SMA_SLOW = 200
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30

# Concentration limits (rebalancing flags)
MAX_STOCK_PCT = 10.0     # one stock above this % of portfolio -> flag
MAX_SECTOR_PCT = 30.0    # one sector above this % of portfolio -> flag

# The user's medium-term sell rule: book only if a holding has returned
# more than this % within this many months (they said ">15% in 6 months"),
# or if the company/sector has an issue (surfaced via the news keyword scan).
SELL_REVIEW_GAIN_PCT = 15.0
SELL_REVIEW_WINDOW_MONTHS = 6

# Words in a headline that suggest a company / sector problem worth reading.
# Words in a headline that suggest good news (checked only if not negative).
POSITIVE_NEWS_KEYWORDS = [
    "beats", "beat estimates", "exceeds estimates", "profit rises", "profit jumps",
    "profit surges", "profit up", "profit doubles", "net profit rises", "record profit",
    "record revenue", "record high", "all-time high", "52-week high", "surge", "surges",
    "soars", "jumps", "jump in", "rallies", "rally", "gains", "wins order", "bags order",
    "order win", "wins contract", "upgrade", "upgraded", "raises target", "target raised",
    "buy rating", "outperform", "bonus issue", "dividend declared", "special dividend",
    "expansion", "acquires", "strong results", "strong sales", "sales rise", "revenue up",
    "upside", "turnaround", "highest ever", "doubles",
]

NEGATIVE_NEWS_KEYWORDS = [
    "fraud", "probe", "raid", "scam", "default", "downgrade", "cut to",
    "resign", "resigns", "resignation", "penalty", "fine", "lawsuit", "sue",
    "ban", "banned", "recall", "loss", "losses", "plunge", "plunges", "slump",
    "crash", "sell-off", "selloff", "layoff", "lay off", "shut", "halt",
    "investigat", "sebi", "insolvency", "nclt", "writedown", "write-down",
    "impairment", "guidance cut", "misses", "miss estimates", "warning",
    "delisting", "auditor", "qualified opinion", "stake sale", "pledge",
]


# ---- Indicator maths --------------------------------------------------------

def sma(values, period):
    """Simple moving average of the last `period` values; None if too short."""
    if len(values) < period:
        return None
    return mean(values[-period:])


def rsi(values, period=RSI_PERIOD):
    """Wilder's RSI over a list of closing prices. None if too short."""
    if len(values) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(values)):
        delta = values[i] - values[i - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))
    # Wilder's smoothing
    avg_gain = mean(gains[:period])
    avg_loss = mean(losses[:period])
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def pct_return_over(values, lookback):
    """% return over the last `lookback` bars. None if too short/zero base."""
    if len(values) <= lookback:
        return None
    base = values[-1 - lookback]
    if base == 0:
        return None
    return (values[-1] / base - 1.0) * 100.0


def cross_state(closes):
    """
    Detect a recent golden/death cross of the fast vs slow SMA.
    Returns 'golden', 'death', or None.
    """
    if len(closes) < SMA_SLOW + 5:
        return None
    def fast(i): return mean(closes[i - SMA_FAST + 1: i + 1])
    def slow(i): return mean(closes[i - SMA_SLOW + 1: i + 1])
    last = len(closes) - 1
    # look back up to 10 sessions for a crossover
    for j in range(last, last - 10, -1):
        prev = j - 1
        if prev < SMA_SLOW:
            break
        pf, ps = fast(prev), slow(prev)
        cf, cs = fast(j), slow(j)
        if pf <= ps and cf > cs:
            return "golden"
        if pf >= ps and cf < cs:
            return "death"
    return None


# ---- Per-holding analysis ---------------------------------------------------

def months_held(buy_date, today=None):
    """Months since buy_date ('YYYY-MM-DD'); None if missing/invalid."""
    if not buy_date:
        return None
    try:
        d = dt.date.fromisoformat(str(buy_date).strip())
    except ValueError:
        return None
    today = today or dt.date.today()
    return (today.year - d.year) * 12 + (today.month - d.month) - (1 if today.day < d.day else 0)


def analyse_holding(h, closes, news_items, corp=None, today=None):
    """
    h: dict with ticker, name, qty, avg_cost, price (last), prev_close,
       and optionally buy_date / lots.
    closes: list of historical closes (oldest -> newest), may be empty
    news_items: list of dicts {title, link, published, negative(bool), event}
    corp: optional dict from corporate.fetch_corporate
    Returns an enriched dict with metrics + signals.
    """
    corp = corp or {}
    price = h["price"]
    avg_cost = h["avg_cost"]
    qty = h["qty"]

    invested = qty * avg_cost
    current = qty * price
    pnl = current - invested
    pnl_pct = None if avg_cost == 0 else (price / avg_cost - 1.0) * 100.0

    prev = h.get("prev_close")
    day_pct = None
    if prev not in (None, 0):
        day_pct = (price / prev - 1.0) * 100.0

    s_fast = sma(closes, SMA_FAST) if closes else None
    s_slow = sma(closes, SMA_SLOW) if closes else None
    r = rsi(closes) if closes else None
    ret_6m = pct_return_over(closes, 126) if closes else None   # ~126 trading days
    cross = cross_state(closes) if closes else None

    trend = None
    if s_slow:
        trend = "up" if price >= s_slow else "down"

    has_negative_news = any(n.get("negative") for n in news_items)
    has_event_news = any(n.get("event") for n in news_items)
    held = months_held(h.get("buy_date"), today)

    # ---- Rule-based signals -------------------------------------------------
    signals = []

    # 1. Medium-term booking review (user's ">15% within 6 months" rule).
    #    With a buy_date we enforce the window; without one we flag the gain
    #    and ask for the date so the window can be checked.
    if pnl_pct is not None and pnl_pct >= SELL_REVIEW_GAIN_PCT:
        if held is not None and held <= SELL_REVIEW_WINDOW_MONTHS:
            signals.append({
                "type": "sell_review", "level": "act",
                "text": (f"+{pnl_pct:.0f}% in {held} mo — meets your ≥15%-in-6-months rule; "
                         f"review for medium-term exit"),
            })
        elif held is None:
            signals.append({
                "type": "sell_review", "level": "act",
                "text": (f"+{pnl_pct:.0f}% vs cost — hits your 15% threshold; add a buy date "
                         f"to check the 6-month window"),
            })
        # held > window: long-term compounder, no exit flag — matches the
        # user's "long term" default. Still visible via P/L column.

    # 2. Company / sector issue (user's "company has issues" rule)
    if has_negative_news:
        signals.append({
            "type": "issue_watch",
            "level": "warn",
            "text": "Possible company/scope issue in recent news — read before deciding",
        })

    # 2b. Corporate-action awareness
    if corp.get("next_earnings"):
        signals.append({"type": "earnings_soon", "level": "info",
                        "text": f"Results due {corp['next_earnings']}"})
    if has_event_news:
        tags = sorted({n["event"] for n in news_items if n.get("event")})
        signals.append({"type": "corp_event", "level": "info",
                        "text": "Announcement: " + ", ".join(tags[:3])})

    # 2b2. Discipline: review dates + thesis (from discipline.csv, if provided)
    disc = h.get("discipline") or {}
    if h.get("qty", 0) > 0 and h.get("ticker") != "CASH":
        rd = disc.get("review_date", "")
        if rd:
            try:
                rdate = dt.date.fromisoformat(rd)
                days = (rdate - (today or dt.date.today())).days
                if days < 0:
                    signals.append({"type": "review_due", "level": "act",
                                    "text": f"Review overdue since {rdate.strftime('%d %b')}"})
                elif days <= 7:
                    signals.append({"type": "review_due", "level": "info",
                                    "text": f"Review due {rdate.strftime('%d %b')}"})
            except ValueError:
                pass
        elif disc.get("thesis"):
            signals.append({"type": "no_review_date", "level": "info",
                            "text": "Set a review date for this thesis"})
        if not disc.get("thesis"):
            signals.append({"type": "no_thesis", "level": "info",
                            "text": "No written thesis — add one in ✎ Discipline"})
        if disc.get("kill_condition"):
            # surface the kill condition — the only thing that should force action
            signals.append({"type": "kill_watch", "level": "info",
                            "text": f"Kill: {disc['kill_condition'][:60]}"})

    # 2c. Personal price targets / stop-loss
    tgt = h.get("target_price")
    stop = h.get("stop_loss")
    if tgt and price >= tgt:
        signals.append({"type": "target_hit", "level": "act",
                        "text": f"Hit your target ₹{tgt:g}"})
    if stop and price <= stop:
        signals.append({"type": "stop_hit", "level": "warn",
                        "text": f"Below your stop-loss ₹{stop:g}"})

    # 2d. Fundamentals awareness (backs the "company/scope issue" rule)
    wk_high = corp.get("wk_high")
    wk_low = corp.get("wk_low")
    if wk_high and price >= 0.98 * wk_high:
        signals.append({"type": "near_high", "level": "info", "text": "Near 52-week high"})
    if wk_low and price <= 1.02 * wk_low:
        signals.append({"type": "near_low", "level": "info", "text": "Near 52-week low"})
    if corp.get("de") is not None and corp["de"] >= 1.5:
        signals.append({"type": "high_debt", "level": "warn",
                        "text": f"High debt/equity ({corp['de']:.1f})"})
    if corp.get("roe") is not None and corp["roe"] < 0:
        signals.append({"type": "neg_roe", "level": "warn", "text": "Negative ROE"})

    # 3. Trend / technical context (informational for a long-term holder)
    if cross == "golden":
        signals.append({"type": "golden_cross", "level": "good",
                         "text": "Golden cross (50DMA crossed above 200DMA)"})
    if cross == "death":
        signals.append({"type": "death_cross", "level": "warn",
                         "text": "Death cross (50DMA crossed below 200DMA)"})
    if r is not None and r >= RSI_OVERBOUGHT:
        signals.append({"type": "overbought", "level": "warn",
                        "text": f"RSI {r:.0f} — overbought (short-term)"})
    if r is not None and r <= RSI_OVERSOLD:
        signals.append({"type": "oversold", "level": "good",
                        "text": f"RSI {r:.0f} — oversold (possible add-on zone)"})
    if trend == "down" and s_slow:
        signals.append({"type": "below_200dma", "level": "info",
                        "text": "Trading below 200DMA — long-term trend weak"})

    tax_status = None
    if held is not None and pnl_pct is not None:
        tax_status = "LTCG" if held >= 12 else "STCG"

    # ---- transparent 0-100 health score (formula, not opinion) --------------
    health = 50
    if trend == "up":
        health += 10
    elif trend == "down":
        health -= 10
    if r is not None and RSI_OVERSOLD < r < RSI_OVERBOUGHT:
        health += 5
    roe = corp.get("roe")
    if roe is not None:
        health += 10 if roe >= 15 else (-15 if roe < 0 else 0)
    de = corp.get("de")
    if de is not None:
        health += 10 if de < 1.0 else (-10 if de >= 1.5 else 0)
    pe = corp.get("pe")
    if pe is not None:
        health += 5 if 0 < pe <= 40 else (-5 if pe > 60 else 0)
    if has_negative_news:
        health -= 15
    if corp.get("profit_yoy") is not None:
        health += 5 if corp["profit_yoy"] > 0 else -5
    if cross == "golden":
        health += 5
    if cross == "death":
        health -= 5
    health = max(0, min(100, health))

    return {
        **h,
        "months_held": held,
        "tax_status": tax_status,
        "health": health,
        "corp": corp,
        "invested": round(invested, 2),
        "current": round(current, 2),
        "pnl": round(pnl, 2),
        "pnl_pct": None if pnl_pct is None else round(pnl_pct, 2),
        "day_pct": None if day_pct is None else round(day_pct, 2),
        "sma_fast": None if s_fast is None else round(s_fast, 2),
        "sma_slow": None if s_slow is None else round(s_slow, 2),
        "rsi": None if r is None else round(r, 1),
        "ret_6m": None if ret_6m is None else round(ret_6m, 1),
        "trend": trend,
        "cross": cross,
        "news": news_items,
        "signals": signals,
    }


def portfolio_summary(rows):
    """Aggregate totals + movers from a list of analysed holdings."""
    priced = [r for r in rows if r.get("has_price")]
    invested = sum(r["invested"] for r in priced)
    current = sum(r["current"] for r in priced)
    pnl = current - invested
    pnl_pct = (pnl / invested * 100.0) if invested else 0.0
    day_pnl = sum(r["qty"] * (r["price"] - r["prev_close"])
                  for r in priced if r.get("prev_close"))
    day_base = sum(r["qty"] * r["prev_close"] for r in priced if r.get("prev_close"))
    day_pct = (day_pnl / day_base * 100.0) if day_base else 0.0

    movers = [r for r in priced if r.get("day_pct") is not None]
    movers_sorted = sorted(movers, key=lambda r: r["day_pct"], reverse=True)
    gainers = movers_sorted[:5]
    losers = list(reversed(movers_sorted[-5:])) if len(movers_sorted) >= 1 else []

    sell_review = [r for r in priced if any(s["type"] == "sell_review" for s in r["signals"])]
    issues = [r for r in priced if any(s["type"] == "issue_watch" for s in r["signals"])]

    # concentration / rebalancing flags
    concentration = []
    for r in priced:
        pct = (r["current"] / current * 100.0) if current else 0.0
        r["pct_of_portfolio"] = round(pct, 1)
        if pct > MAX_STOCK_PCT:
            concentration.append({"kind": "stock", "name": r["ticker"],
                                  "pct": round(pct, 1), "limit": MAX_STOCK_PCT})
    sector_val = {}
    for r in priced:
        sector_val[r.get("sector", "Others")] = sector_val.get(r.get("sector", "Others"), 0.0) + r["current"]
    for sec, v in sorted(sector_val.items(), key=lambda kv: -kv[1]):
        pct = v / current * 100.0 if current else 0.0
        if pct > MAX_SECTOR_PCT:
            concentration.append({"kind": "sector", "name": sec,
                                  "pct": round(pct, 1), "limit": MAX_SECTOR_PCT})

    return {
        "invested": round(invested, 2),
        "current": round(current, 2),
        "pnl": round(pnl, 2),
        "pnl_pct": round(pnl_pct, 2),
        "day_pnl": round(day_pnl, 2),
        "day_pct": round(day_pct, 2),
        "n_holdings": len(rows),
        "n_priced": len(priced),
        "gainers": gainers,
        "losers": losers,
        "sell_review": sell_review,
        "issues": issues,
        "concentration": concentration,
    }
