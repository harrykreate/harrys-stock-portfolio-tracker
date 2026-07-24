"""Offline sanity tests for the analytics engine. Run: python3 scripts/test_engine.py"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine

def approx(a, b, tol=1e-6): return abs(a - b) <= tol

# SMA
assert engine.sma([1,2,3,4,5], 5) == 3
assert engine.sma([1,2,3], 5) is None

# RSI: strictly rising series -> RSI 100
assert engine.rsi(list(range(1, 40))) == 100.0
# RSI mid-range for an oscillating series is between 0 and 100
r = engine.rsi([10,11,10,11,10,11,10,11,10,11,10,11,10,11,10,11])
assert 0 < r < 100

# % return
assert approx(engine.pct_return_over([100, 110], 1), 10.0)

# Sell-review rule fires at >=15% gain
h = {"ticker":"X","name":"X","qty":10,"avg_cost":100.0,"price":120.0,"prev_close":118.0,"has_price":True}
out = engine.analyse_holding(h, [], [])
assert any(s["type"] == "sell_review" for s in out["signals"]), "15% rule should fire at +20%"
assert approx(out["pnl_pct"], 20.0)

# Below 15% gain does NOT fire sell-review
h2 = {**h, "price": 108.0}
out2 = engine.analyse_holding(h2, [], [])
assert not any(s["type"] == "sell_review" for s in out2["signals"]), "should not fire at +8%"

# Negative news triggers issue_watch
out3 = engine.analyse_holding(h2, [], [{"title":"Company faces SEBI probe","negative":True}])
assert any(s["type"] == "issue_watch" for s in out3["signals"])

# avg_cost 0 must not crash (KITEX case)
h4 = {**h, "avg_cost": 0.0, "price": 147.0}
out4 = engine.analyse_holding(h4, [], [])
assert out4["pnl_pct"] is None

# ---- Date-aware 15%-in-6-months rule ----
import datetime as dt
today = dt.date(2026, 7, 24)

# +20% bought 3 months ago -> fires with "in N mo" wording
h5 = {**h, "buy_date": "2026-04-20"}
out5 = engine.analyse_holding(h5, [], [], today=today)
sigs5 = [s for s in out5["signals"] if s["type"] == "sell_review"]
assert sigs5 and "6-months rule" in sigs5[0]["text"], sigs5

# +20% bought 2 years ago -> long-term holding, rule must NOT fire
h6 = {**h, "buy_date": "2024-05-01"}
out6 = engine.analyse_holding(h6, [], [], today=today)
assert not any(s["type"] == "sell_review" for s in out6["signals"]), "held >6mo should not flag"

# +20% with no buy date -> fires but asks for the date
h7 = {**h, "buy_date": ""}
out7 = engine.analyse_holding(h7, [], [], today=today)
sigs7 = [s for s in out7["signals"] if s["type"] == "sell_review"]
assert sigs7 and "buy date" in sigs7[0]["text"]

# months_held edge: same month, day not yet reached
assert engine.months_held("2026-01-30", dt.date(2026, 7, 24)) == 5
assert engine.months_held("2026-01-20", dt.date(2026, 7, 24)) == 6
assert engine.months_held("", today) is None
assert engine.months_held("garbage", today) is None

# corp: upcoming earnings adds an info signal
out8 = engine.analyse_holding(h6, [], [], corp={"next_earnings": "30 Jul 2026"}, today=today)
assert any(s["type"] == "earnings_soon" for s in out8["signals"])

# event-tagged news adds a corp_event signal
out9 = engine.analyse_holding(h6, [], [{"title": "Board to consider bonus issue",
                                        "negative": False, "event": "bonus issue"}], today=today)
assert any(s["type"] == "corp_event" for s in out9["signals"])

print("All engine tests passed.")
