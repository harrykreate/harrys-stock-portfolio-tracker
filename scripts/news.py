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

from engine import NEGATIVE_NEWS_KEYWORDS
from corporate import classify_event

GOOGLE_NEWS = "https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en"
MAX_ITEMS = 4


def _is_negative(title: str) -> bool:
    t = title.lower()
    return any(k in t for k in NEGATIVE_NEWS_KEYWORDS)


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
        pub_short = published
        try:
            if getattr(e, "published_parsed", None):
                pub_short = dt.datetime(*e.published_parsed[:6]).strftime("%d %b %Y")
        except Exception:
            pass
        items.append({
            "title": title,
            "link": getattr(e, "link", ""),
            "published": pub_short,
            "negative": _is_negative(title),
            "event": classify_event(title),
        })
    return items
