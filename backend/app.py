"""
The lesen server.

Tapping a word deliberately goes down two separate routes:
  /api/word    -> fast (spaCy + Wiktionary). This is what you see instantly.
  /api/context -> slow (Ollama, ~4s). Arrives after, and fills in the card.

The split exists because the local LLM is far too slow to block a tap on.
"""
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import dictionary
import german
import llm
import news
import store

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("lesen")

WEB = Path(__file__).resolve().parent.parent / "web"

app = FastAPI(title="lesen")

# ── NO CORS, AND THAT IS THE FIX ─────────────────────────────────────────────
#
# There used to be a `CORSMiddleware(allow_origins=["*"])` here, telling the
# browser "any page in the world may make requests to me". Since this server has
# no login, that meant **any site you opened in another tab could read your
# words and your saved articles** by asking localhost:8777 for them, for as long
# as lesen was running.
#
# 👉 And it enabled nothing: this same server serves the web app, and `app.js`
# always asks for `/api/...` relatively, so the requests are same-origin and the
# browser never consults CORS at all. It was open with nobody using it.
#
# ⚠️ If the frontend is ever served from somewhere else this comes back — but
# with the origins spelled out, never with `*`.


@app.on_event("startup")
def _startup():
    store.init()
    german.nlp()  # cargar spaCy ya, para que el primer artículo no espere
    log.info("spaCy listo · Ollama %s", "OK" if llm.available() else "NO DISPONIBLE")


# ---------- news ----------

@app.get("/api/topics")
def topics():
    return {
        "topics": [{"id": k, "name": v} for k, v in news.TOPICS.items()],
        "feeds": [{"id": f.id, "name": f.name, "topic": f.topic, "level": f.level}
                  for f in news.FEEDS],
    }


@app.get("/api/headlines")
def headlines(topics: str = "", interests: str = "", tenses: str = ""):
    t = [x for x in topics.split(",") if x]
    i = [x.strip() for x in interests.split(",") if x.strip()]
    want = [x for x in tenses.split(",") if x]
    if not t or not i:
        cfg = store.get_setting("prefs", {}) or {}
        t = t or cfg.get("topics", [])
        i = i or cfg.get("interests", [])

    items = news.headlines(t, i)

    # Tense profile over headline + standfirst. It's a sample, not the whole
    # article, but it's enough to find the pieces that step outside the usual
    # present/Perfekt.
    profiles = german.tense_profiles([f"{x['title']}. {x['summary']}" for x in items])
    for it, p in zip(items, profiles):
        it["tenses"] = p
        it["rare"] = german.rare_tenses(p)

    if want:
        items = [x for x in items if any(w in x["tenses"] for w in want)]
    return {"items": items, "tense_names": german.TENSES}


class UrlIn(BaseModel):
    url: str


@app.post("/api/article")
def article(inp: UrlIn):
    # If it's already saved, it's read from the database: instant, and still
    # there even after the newspaper takes it down.
    cached = store.get_article(inp.url)
    if cached and cached.get("text"):
        art = {"url": inp.url, "title": cached["title"], "text": cached["text"],
               "n_chars": len(cached["text"])}
        store.mark_read(inp.url)
    else:
        art = news.extract(inp.url)
        if not art:
            return {"error": "No pude extraer el texto de esa página."}
    an = german.analyze(art["text"])
    return {**art, **an, "statuses": store.statuses(),
            "tenses": german.tense_profile(art["text"]),
            "saved": bool(cached)}


class TextIn(BaseModel):
    text: str
    title: str = "Texto pegado"


@app.post("/api/analyze")
def analyze(inp: TextIn):
    """For pasting your own text: a work email, a letter from the Amt."""
    an = german.analyze(inp.text)
    return {"url": "", "title": inp.title, "text": inp.text,
            "n_chars": len(inp.text), **an, "statuses": store.statuses()}


# ---------- tapping a word ----------

class WordIn(BaseModel):
    word: str
    lemma: str
    sentence: str = ""
    pos: str = ""
    separable: dict | None = None


@app.post("/api/word")
def word(inp: WordIn):
    """The fast path: dictionary, no LLM. Answers on the spot."""
    entry = dictionary.lookup(inp.lemma)
    if not entry and inp.lemma != inp.word:
        entry = dictionary.lookup(inp.word)
    # Separable detection is confirmed against the dictionary before it's shown:
    # spaCy and the prefix split both produce false positives ('einigen',
    # 'hochliegen'), and teaching the reader a rule that doesn't exist is worse
    # than teaching nothing.
    sep_ok = dictionary.confirm_separable(inp.separable) if inp.separable else False

    # If it was a false positive the rebuilt lemma is no good for lookup either
    # ('hochliegen' isn't anywhere): fall back to the real stem.
    lemma = inp.lemma
    if inp.separable and not sep_ok:
        stem = inp.separable.get("stem", "")
        if not entry and stem:
            entry = dictionary.lookup(stem)
            if entry:
                lemma = stem

    saved = store.get_word(lemma)
    return {"lemma": lemma, "word": inp.word, "entry": entry,
            "separable_ok": sep_ok, "saved": saved}


@app.post("/api/context")
def context(inp: WordIn):
    """The slow path: the LLM picks the sense that applies and writes an example."""
    if not llm.available():
        return {"error": "Ollama no responde. Levantalo con: ollama serve"}
    entry = dictionary.lookup(inp.lemma)
    if entry and entry["senses"]:
        out = llm.pick_sense(inp.word, inp.sentence, inp.lemma, entry["senses"])
        if out:
            sense = next((s for s in entry["senses"] if s["n"] == out["sense"]), None)
            # The generated example is validated before it's shown: with
            # separable verbs the model writes things like «hängt vom Wetter
            # abhängen», and a malformed example is worse than none.
            ej_de, ej_es = out.get("ejemplo_de", ""), out.get("ejemplo_es", "")
            ok = german.check_example(ej_de, inp.lemma) if ej_de else False
            if not ok:
                log.info("ejemplo descartado para %s: %r", inp.lemma, ej_de)
                ej_de = ej_es = ""
            return {"mode": "sense", "sense_n": out["sense"],
                    "sense_de": sense["de"] if sense else "",
                    "es": out["es"], "porque": out["porque"],
                    "ejemplo_de": ej_de, "ejemplo_es": ej_es,
                    "ejemplo_ok": ok,
                    # Real dictionary examples for the chosen sense: correct by
                    # definition.
                    "ejemplos_dict": sense["examples"] if sense else []}
    out = llm.explain_free(inp.word, inp.sentence, inp.lemma)
    if not out:
        return {"error": "El modelo no devolvió nada."}
    if out.get("ejemplo_de") and not german.check_example(out["ejemplo_de"], inp.lemma):
        out["ejemplo_de"] = out["ejemplo_es"] = ""
    return {"mode": "libre", **out}


class SentIn(BaseModel):
    sentence: str


@app.post("/api/translate")
def translate(inp: SentIn):
    return {"es": llm.translate_sentence(inp.sentence)}


# ---------- vocabulary ----------

class SaveIn(BaseModel):
    lemma: str
    form: str = ""
    pos: str = ""
    article: str = ""
    es: str = ""
    sense_n: str = ""
    sense_de: str = ""
    separable: dict | None = None
    sentence: str = ""
    src_title: str = ""
    src_url: str = ""
    example_de: str = ""
    example_es: str = ""
    status: str = "aprendiendo"


@app.post("/api/vocab")
def save(inp: SaveIn):
    return {"word": store.save_word(inp.model_dump())}


@app.get("/api/vocab")
def vocab(status: str = "todas"):
    return {"words": store.list_words(status), "stats": store.stats()}


class StatusIn(BaseModel):
    lemma: str
    status: str


@app.post("/api/vocab/status")
def status(inp: StatusIn):
    return {"word": store.set_status(inp.lemma, inp.status)}


@app.delete("/api/vocab/{lemma}")
def remove(lemma: str):
    store.delete_word(lemma)
    return {"ok": True}


# ---------- saved articles ----------

class SaveArtIn(BaseModel):
    url: str
    title: str = ""
    source: str = ""
    topic: str = ""
    text: str = ""
    tenses: list[str] = []


@app.post("/api/saved")
def save_art(inp: SaveArtIn):
    d = inp.model_dump()
    if not d["text"]:                      # guardar desde el listado, sin abrir
        art = news.extract(d["url"])
        if art:
            d["text"] = art["text"]
            d["title"] = d["title"] or art["title"]
            d["tenses"] = german.tense_profile(art["text"])
    return {"article": store.save_article(d)}


@app.get("/api/saved")
def list_saved():
    return {"articles": store.list_articles()}


@app.delete("/api/saved")
def unsave(url: str):
    store.unsave_article(url)
    return {"ok": True}


# ---------- review ----------

@app.get("/api/study")
def study(limit: int = 20):
    return {"words": store.due_words(limit), "stats": store.stats()}


class ReviewIn(BaseModel):
    lemma: str
    ok: bool


@app.post("/api/study/review")
def do_review(inp: ReviewIn):
    return {"word": store.review(inp.lemma, inp.ok)}


# ---------- preferences ----------

class PrefsIn(BaseModel):
    topics: list[str] = []
    interests: list[str] = []


@app.get("/api/prefs")
def get_prefs():
    return store.get_setting("prefs", {"topics": [], "interests": []})


@app.post("/api/prefs")
def set_prefs(inp: PrefsIn):
    store.set_setting("prefs", inp.model_dump())
    return inp.model_dump()


@app.get("/api/health")
def health():
    return {"spacy": True, "ollama": llm.available(), "stats": store.stats()}


# ---------- static files ----------

def _assets_version() -> str:
    """Fingerprint of the static files, to bust the cache when they change."""
    stamp = 0.0
    for f in ("app.js", "styles.css"):
        try:
            stamp = max(stamp, (WEB / f).stat().st_mtime)
        except OSError:
            pass
    return str(int(stamp))


@app.get("/")
def index():
    """
    The HTML is served uncached, with the static files' version pinned onto
    every <link>/<script>.

    Without this, Safari would hold on to the old index.html and fetch the new
    app.js. The mix broke the whole app (a button the script expected wasn't in
    the cached HTML) and from the phone it looked like the server had died.
    """
    html = (WEB / "index.html").read_text(encoding="utf-8")
    v = _assets_version()
    html = html.replace("/styles.css", f"/styles.css?v={v}")
    html = html.replace("/app.js", f"/app.js?v={v}")
    return HTMLResponse(html, headers={
        "Cache-Control": "no-cache, must-revalidate",
    })


app.mount("/", StaticFiles(directory=WEB), name="web")
