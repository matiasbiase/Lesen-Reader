"""
Noticias: feeds verificados + extracción del cuerpo del artículo.

Los feeds de acá están todos probados a mano (responden 200 y traen items).
Los de DW por tema y los de nachrichtenleicht que probé devolvían 404, así que
no los incluyo para no llenar la app de fuentes muertas.
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
    level: str  # "medio" | "dificil"


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


def _resumen(summary: str, title: str) -> str:
    """
    El resumen, salvo cuando es el título otra vez.

    Varios feeds —tagesschau el que más— mandan la descripción con el titular
    adentro cuando no tienen bajada. Medido el 19/08 sobre `wissen`: 12 de 40
    notas venían así. En la lista se veía el mismo renglón dos veces, uno en
    negrita y otro abajo en gris, como si fuera información nueva.

    ⚠️ Se compara sin distinguir mayúsculas y sin la puntuación del final,
    porque el mismo texto vuelve con una coma o un punto de diferencia. Lo que
    NO se hace es adivinar: si el resumen apenas empieza igual pero sigue, se
    deja entero —de esos no había ninguno, y recortarlo sería inventar una
    regla para un caso que no existe.
    """
    if not summary:
        return ""
    igual = lambda t: re.sub(r"[\s.,;:!?\u2026-]+$", "", t).casefold()
    return "" if igual(summary) == igual(title) else summary


def fetch_feed(feed: Feed) -> list[dict]:
    hit = _cache.get(feed.id)
    if hit and time.time() - hit[0] < CACHE_TTL:
        return hit[1]
    try:
        r = httpx.get(feed.url, headers={"User-Agent": UA}, timeout=15.0, follow_redirects=True)
        r.raise_for_status()
        parsed = feedparser.parse(r.content)
    except Exception as e:
        log.warning("feed %s falló: %s", feed.id, e)
        return []

    items = []
    for e in parsed.entries[:40]:
        items.append({
            "id": e.get("id") or e.get("link", ""),
            "title": _strip(e.get("title", "")),
            "summary": _resumen(_strip(e.get("summary", "")),
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
    Puntaje por intereses: cuenta palabras clave en título y resumen.
    Simple a propósito — el usuario ve por qué apareció cada nota.
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
    """Baja el artículo y saca el texto limpio, sin menú ni cookies."""
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
        log.warning("extract %s falló: %s", url, e)
        return None
