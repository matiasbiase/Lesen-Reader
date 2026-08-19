"""
News: verified feeds + article body extraction.

Every feed in here was tested by hand (returns 200 and carries items). DW's
per-topic feeds and the nachrichtenleicht ones I tried returned 404, so they're
left out rather than filling the app with dead sources.
"""
import logging
import re
import time
from dataclasses import dataclass

import feedparser
import httpx
import trafilatura

log = logging.getLogger("lesen.news")

UA = "lesen/1.0 (personal offline German reader)"


@dataclass
class Feed:
    id: str
    name: str
    url: str
    topic: str
    level: str  # "medio" | "dificil" — shown to the reader, so it stays in Spanish


FEEDS = [
    Feed("ts_top", "tagesschau · Titulares", "https://www.tagesschau.de/index~rss2.xml", "aktuell", "medio"),
    Feed("ts_inland", "tagesschau · Alemania", "https://www.tagesschau.de/inland/index~rss2.xml", "deutschland", "medio"),
    Feed("ts_ausland", "tagesschau · Mundo", "https://www.tagesschau.de/ausland/index~rss2.xml", "welt", "medio"),
    Feed("ts_wirtschaft", "tagesschau · Economía", "https://www.tagesschau.de/wirtschaft/index~rss2.xml", "wirtschaft", "medio"),
    Feed("ts_wissen", "tagesschau · Ciencia", "https://www.tagesschau.de/wissen/index~rss2.xml", "wissen", "medio"),
    Feed("dw", "Deutsche Welle", "https://rss.dw.com/rdf/rss-de-all", "aktuell", "medio"),
    Feed("t3n", "t3n · Digital y diseño", "https://t3n.de/rss.xml", "tech", "medio"),
    Feed("heise", "heise · Tecnología", "https://www.heise.de/rss/heise-atom.xml", "tech", "dificil"),
    Feed("zeit", "Die Zeit", "https://newsfeed.zeit.de/index", "aktuell", "dificil"),
]

TOPICS = {
    "deutschland": "Alemania y política",
    "welt": "Mundo",
    "wirtschaft": "Economía y trabajo",
    "wissen": "Ciencia y salud",
    "tech": "Tecnología, IA y diseño",
    "aktuell": "Titulares del día",
}

_cache: dict[str, tuple[float, list]] = {}
CACHE_TTL = 600  # 10 min


def _strip(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html or "")).strip()


def _summary(summary: str, title: str) -> str:
    """
    The summary, except when it's the headline all over again.

    Several feeds — tagesschau most of all — send the description with the
    headline inside it when the piece has no standfirst. Measured on 19 Aug
    against `wissen`: 12 of 40 articles came in like that. The list showed the
    same line twice, once in bold and once below in grey, as if the second one
    carried something new.

    ⚠️ The comparison ignores case and trailing punctuation, because the same
    text comes back with a comma or a full stop of difference. What it does NOT
    do is guess: if the summary merely starts the same and then goes on, it's
    kept whole — there were none of those, and trimming them would be inventing
    a rule for a case that doesn't exist.
    """
    if not summary:
        return ""
    same = lambda t: re.sub(r"[\s.,;:!?\u2026-]+$", "", t).casefold()
    return "" if same(summary) == same(title) else summary


def fetch_feed(feed: Feed) -> list[dict]:
    hit = _cache.get(feed.id)
    if hit and time.time() - hit[0] < CACHE_TTL:
        return hit[1]
    try:
        r = httpx.get(feed.url, headers={"User-Agent": UA}, timeout=15.0, follow_redirects=True)
        r.raise_for_status()
        parsed = feedparser.parse(r.content)
    except Exception as e:
        log.warning("feed %s failed: %s", feed.id, e)
        return []

    items = []
    for e in parsed.entries[:40]:
        items.append({
            "id": e.get("id") or e.get("link", ""),
            "title": _strip(e.get("title", "")),
            "summary": _summary(_strip(e.get("summary", "")),
                                _strip(e.get("title", "")))[:400],
            "link": e.get("link", ""),
            "published": e.get("published", "") or e.get("updated", ""),
            "source": feed.name,
            "source_id": feed.id,
            "topic": feed.topic,
            "level": feed.level,
        })
    _cache[feed.id] = (time.time(), items)
    return items


def score(item: dict, interests: list[str]) -> int:
    """
    Interest score: counts keywords in the headline and the summary.
    Deliberately simple — the reader gets to see why each article showed up.
    """
    if not interests:
        return 0
    hay = (item["title"] + " " + item["summary"]).lower()
    return sum(3 if k.lower() in item["title"].lower() else 1
               for k in interests if k.lower() in hay)


def headlines(topics: list[str], interests: list[str], limit: int = 40) -> list[dict]:
    feeds = [f for f in FEEDS if not topics or f.topic in topics]
    out: list[dict] = []
    seen = set()
    for f in feeds:
        for it in fetch_feed(f):
            key = it["link"]
            if not key or key in seen:
                continue
            seen.add(key)
            it["score"] = score(it, interests)
            it["matched"] = [k for k in interests
                             if k.lower() in (it["title"] + " " + it["summary"]).lower()]
            out.append(it)
    out.sort(key=lambda x: (-x["score"], x.get("published", "")), reverse=False)
    out.sort(key=lambda x: -x["score"])
    return out[:limit]


def extract(url: str) -> dict | None:
    """Fetches the article and pulls out the clean text, no menus or cookie banners."""
    try:
        r = httpx.get(url, headers={"User-Agent": UA}, timeout=20.0, follow_redirects=True)
        r.raise_for_status()
        text = trafilatura.extract(r.text, include_comments=False, include_tables=False,
                                   favor_precision=True, url=url)
        if not text or len(text) < 200:
            return None
        meta = trafilatura.extract_metadata(r.text)
        return {
            "url": url,
            "title": (meta.title if meta else "") or "",
            "text": text.strip(),
            "n_chars": len(text),
        }
    except Exception as e:
        log.warning("extract %s failed: %s", url, e)
        return None
