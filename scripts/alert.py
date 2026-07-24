"""
Proactive alerts — reads the built dashboard model (docs/data.json) and sends a
digest of *newly* firing alerts to Telegram and/or email. Rule-based, no AI.

Runs after update.py in the GitHub Actions workflow. Credentials come from repo
secrets via environment variables; with none set it is a harmless no-op.

  Telegram:  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
  Email:     SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, ALERT_TO
             (SMTP_USER is also used as the From address)

Dedup: docs/alert_state.json remembers keys already sent so you aren't pinged
about the same thing every run. News keys include the headline; the ≥15% /
target / results keys re-fire at most once per month.
"""
from __future__ import annotations
import os
import sys
import json
import time
import hashlib
import datetime as dt
import urllib.request
import urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "docs", "data.json")
STATE = os.path.join(ROOT, "docs", "alert_state.json")
RSI_BUY = 30           # watchlist "buy zone" when RSI at/below this


def _ym():
    return dt.date.today().strftime("%Y-%m")


def collect_alerts(model):
    """Return list of {key, emoji, ticker, text}. `key` drives dedup."""
    out = []
    ym = _ym()
    today = dt.date.today()

    def add(key, emoji, ticker, text):
        out.append({"key": key, "emoji": emoji, "ticker": ticker, "text": text})

    for r in model.get("rows", []):
        tk = r["ticker"]
        for sg in r.get("signals", []):
            t = sg["type"]
            if t == "sell_review":
                add(f"book:{tk}:{ym}", "⭐", tk, f"{tk}: {sg['text']}")
            elif t == "issue_watch":
                add(f"issue:{tk}:{ym}", "⚠️", tk, f"{tk}: possible company/sector issue — check news")
            elif t == "target_hit":
                add(f"target:{tk}:{ym}", "🎯", tk, f"{tk}: {sg['text']} (now ₹{r['price']:.2f})")
            elif t == "stop_hit":
                add(f"stop:{tk}", "🛑", tk, f"{tk}: {sg['text']} (now ₹{r['price']:.2f})")
            elif t == "review_due" and sg.get("level") == "act":
                add(f"review:{tk}:{ym}", "🧭", tk, f"{tk}: scheduled thesis review is overdue")
        # results tomorrow / today
        ne = (r.get("corp") or {}).get("next_earnings")
        if ne:
            try:
                d = dt.datetime.strptime(ne, "%d %b %Y").date()
                if 0 <= (d - today).days <= 1:
                    add(f"results:{tk}:{d}", "🏛️", tk, f"{tk}: results on {ne}")
            except ValueError:
                pass
        # fresh negative headline (keyed by title so each distinct one alerts once)
        for n in r.get("news", []):
            if n.get("negative"):
                h = hashlib.md5(n["title"].encode()).hexdigest()[:8]
                add(f"news:{tk}:{h}", "📰", tk, f"{tk}: {n['title']}")

    # family floor breach — shown once a month until fixed
    fl = (model.get("discipline") or {}).get("floor") or {}
    if fl.get("breached"):
        bad = ", ".join(i["label"] for i in fl.get("items", []) if i.get("ok") is False)
        add(f"floor:{ym}", "🚨", "FLOOR", f"Family floor breached: {bad} — fix before new positions")

    # watchlist buy-zone: oversold RSI or price at/below your target
    for w in model.get("watch", []):
        tk = w["ticker"]
        if w.get("rsi") is not None and w["rsi"] <= RSI_BUY:
            add(f"buyzone:{tk}:{ym}", "🟢", tk,
                f"{tk} (watchlist): RSI {w['rsi']:.0f} — in buy zone (₹{w['price']:.2f})")
        tp = w.get("target_price")
        if tp and w.get("price") and w["price"] <= tp:
            add(f"wtarget:{tk}:{ym}", "🟢", tk,
                f"{tk} (watchlist): at/below your target ₹{tp:g} (now ₹{w['price']:.2f})")
    return out


def send_telegram(text):
    tok = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not tok or not chat:
        return False
    url = f"https://api.telegram.org/bot{tok}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": chat, "text": text,
        "parse_mode": "HTML", "disable_web_page_preview": "true"}).encode()
    try:
        urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=20).read()
        return True
    except Exception as e:
        print("Telegram send failed:", e)
        return False


def send_email(text):
    host = os.environ.get("SMTP_HOST")
    user = os.environ.get("SMTP_USER")
    pw = os.environ.get("SMTP_PASS")
    to = os.environ.get("ALERT_TO") or user
    if not (host and user and pw and to):
        return False
    import smtplib
    from email.mime.text import MIMEText
    msg = MIMEText(text)
    msg["Subject"] = "Sensex Tracker alerts"
    msg["From"] = user
    msg["To"] = to
    try:
        port = int(os.environ.get("SMTP_PORT", "587"))
        with smtplib.SMTP(host, port, timeout=20) as s:
            s.starttls()
            s.login(user, pw)
            s.sendmail(user, [to], msg.as_string())
        return True
    except Exception as e:
        print("Email send failed:", e)
        return False


def weekly_digest(model, state):
    """Monday-morning summary. Returns text or None if not due."""
    today = dt.date.today()
    week_key = f"{today.isocalendar()[0]}-W{today.isocalendar()[1]}"
    if today.weekday() != 0 or state.get("last_digest") == week_key:
        return None
    s = model.get("summary", {})
    lines = [f"🗞️ <b>Weekly digest</b> — {today.strftime('%d %b %Y')}",
             f"Portfolio: ₹{s.get('current',0):,.0f} ({s.get('pnl_pct',0):+.1f}% overall)"]
    # week-on-week change from snapshots
    snap_path = os.path.join(ROOT, "docs", "snapshots.json")
    if os.path.exists(snap_path):
        try:
            snaps = json.load(open(snap_path))
            week_ago = today - dt.timedelta(days=7)
            older = [x for x in snaps if x["date"] <= week_ago.isoformat()]
            if older and s.get("current"):
                base = older[-1]["value"]
                if base:
                    chg = (s["current"] / base - 1) * 100
                    lines.append(f"This week: {chg:+.2f}% (₹{s['current']-base:+,.0f})")
        except Exception:
            pass
    r = model.get("risk", {}).get("metrics") or {}
    if r.get("sharpe") is not None:
        lines.append(f"Risk-adjusted score {r['sharpe']} · beta {r.get('beta','—')} · vol {r.get('volatility','—')}%")
    if s.get("sell_review"):
        lines.append(f"⭐ {len(s['sell_review'])} holding(s) in booking-review")
    if s.get("issues"):
        lines.append(f"⚠️ {len(s['issues'])} with flagged news")
    upcoming = []
    for row in model.get("rows", []):
        ne = (row.get("corp") or {}).get("next_earnings")
        if ne:
            try:
                d = dt.datetime.strptime(ne, "%d %b %Y").date()
                if 0 <= (d - today).days <= 7:
                    upcoming.append(f"{row['ticker']} ({ne})")
            except ValueError:
                pass
    if upcoming:
        lines.append("🏛️ Results this week: " + ", ".join(upcoming[:8]))
    state["last_digest"] = week_key
    return "\n".join(lines)


def main(dry=False):
    if not os.path.exists(DATA):
        print("No data.json — run update.py first.")
        return
    model = json.load(open(DATA))
    alerts = collect_alerts(model)

    state = {"sent": []}
    if os.path.exists(STATE):
        try:
            state = json.load(open(STATE))
        except Exception:
            pass
    seen = set(state.get("sent", []))
    fresh = [a for a in alerts if a["key"] not in seen]
    digest = weekly_digest(model, state)

    if dry:
        print(f"{len(alerts)} firing, {len(fresh)} new:")
        for a in fresh:
            print("  ", a["emoji"], a["text"])
        if digest:
            print("--- weekly digest ---\n" + digest)
        return

    parts = []
    if digest:
        parts.append(digest)
    if fresh:
        parts.append(f"📈 <b>Sensex Tracker</b> — {len(fresh)} new alert(s)\n\n"
                     + "\n".join(f"{a['emoji']} {a['text']}" for a in fresh))
    if not parts:
        print("No new alerts.")
        return

    body = "\n\n".join(parts)
    sent_any = send_telegram(body) | send_email(
        body.replace("<b>", "").replace("</b>", ""))
    if sent_any:
        seen.update(a["key"] for a in fresh)
        state["sent"] = list(seen)[-800:]     # keep the most recent 800 keys
        json.dump(state, open(STATE, "w"), indent=0)
        print(f"Sent {len(fresh)} alert(s)" + (" + weekly digest." if digest else "."))
    else:
        print("No delivery channel configured (set Telegram or SMTP secrets). "
              f"{len(fresh)} alert(s) would have been sent.")


if __name__ == "__main__":
    main(dry="--dry" in sys.argv)
