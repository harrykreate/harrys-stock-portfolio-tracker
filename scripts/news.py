"""
Free news fetching via Google News RSS (no API key, no AI).

For each holding we query Google News for the company name + "share/stock"
scoped to India, keep the few most recent headlines, and flag any whose title
contains a negative keyword (used by the engine's "company issue" rule).
"""
from __future__ import annotations
import urllib.parse
import datetime as dt

try:
    import feedparser
except Exception:  # pragma: no cover
    feedparser = None

from engine import NEGATIVE_NEWS_KEYWORDS, POSITIVE_NEWS_KEYWORDS, _kw_hit
from corporate import classify_event

GOOGLE_NEWS = "https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en"
MAX_ITEMS = 4          # shown on cards / used by the signal rules
ARCHIVE_ITEMS = 40     # kept per run for the rolling news bank
ARCHIVE_DAYS = 120     # how far back the bank keeps headlines


def _is_negative(title: str) -> bool:
    return _kw_hit(title, NEGATIVE_NEWS_KEYWORDS)


def _is_positive(title: str) -> bool:
    return _kw_hit(title, POSITIVE_NEWS_KEYWORDS)


def fetch_news(name: str, ticker: str, max_items: int = MAX_ITEMS):
    """Return a list of {title, link, published, negative}. Empty on failure."""
    if feedparser is None:
        return []
    query = f'"{name}" (share OR stock OR results OR NSE)'
    url = GOOGLE_NEWS.format(q=urllib.parse.quote(query))
    try:
        feed = feedparser.parse(url)
    except Exception:
        return []
    items = []
    for e in feed.entries[:max_items]:
        title = getattr(e, "title", "").strip()
        if not title:
            continue
        published = getattr(e, "published", "") or ""
        # normalise date to YYYY-MM-DD if parseable
        pub_short, iso = published, ""
        try:
            if getattr(e, "published_parsed", None):
                d = dt.datetime(*e.published_parsed[:6])
                pub_short = d.strftime("%d %b %Y")
                iso = d.strftime("%Y-%m-%d")
        except Exception:
            pass
        neg = _is_negative(title)
        items.append({
            "title": title,
            "link": getattr(e, "link", ""),
            "published": pub_short,
            "date": iso,
            "source": (title.rsplit(" - ", 1)[-1] if " - " in title else ""),
            "negative": neg,
            "positive": (not neg) and _is_positive(title),
            "event": classify_event(title),
        })
    return items


def merge_archive(old, fresh, today=None, days=ARCHIVE_DAYS, cap=160):
    """
    Fold this run's headlines into the rolling bank: dedupe on title, drop
    anything older than `days`, newest first. Google News only serves a recent
    window, so the bank is how the platform accumulates depth over time —
    it is thin on day one and fills out with every scrape.
    """
    today = today or dt.date.today()
    cutoff = (today - dt.timedelta(days=days)).strftime("%Y-%m-%d")
    seen, out = set(), []
    for item in list(fresh or []) + list(old or []):
        key = (item.get("title") or "").strip().lower()
        if not key or key in seen:
            continue
        d = (item.get("date") or "")
        if d and d < cutoff:
            continue
        seen.add(key)
        out.append(item)
    out.sort(key=lambda x: x.get("date") or "", reverse=True)
    return out[:cap]
