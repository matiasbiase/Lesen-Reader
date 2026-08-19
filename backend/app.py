"""
Servidor de lesen.

Separa a propósito dos rutas para el toque de una palabra:
  /api/word    -> rápido (spaCy + Wiktionary). Es lo que ves al instante.
  /api/context -> lento (Ollama, ~4s). Llega después y completa la ficha.

Esa división existe porque el LLM local tarda demasiado para bloquear un toque.
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

# ── SIN CORS, Y ESO ES EL ARREGLO ────────────────────────────────────────────
#
# Acá había `CORSMiddleware(allow_origins=["*"])`, que le decía al navegador
# "cualquier página del mundo puede hacerme pedidos". Como el server no tiene
# login, eso significaba que **cualquier sitio que abrieras en otra pestaña
# podía leer tus palabras y tus notas** pidiéndoselas a localhost:8777 mientras
# lesen estuviera corriendo.
#
# 👉 Y no habilitaba nada: la web la sirve este mismo server y `app.js` pide
# siempre `/api/...` en relativo, así que los pedidos son del mismo origen y el
# navegador ni consulta CORS. Estaba abierto sin que nadie lo usara.
#
# ⚠️ Si algún día servís la web desde otro lado, esto vuelve — pero con la
# lista de orígenes escrita, nunca con `*`.


@app.on_event("startup")
def _startup():
    store.init()
    german.nlp()  # cargar spaCy ya, para que el primer artículo no espere
    log.info("spaCy listo · Ollama %s", "OK" if llm.available() else "NO DISPONIBLE")


# ---------- noticias ----------

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

    # Perfil de tiempos verbales del titular + copete. Es una muestra, no el
    # artículo entero, pero alcanza para encontrar las notas que se salen del
    # presente/Perfekt de siempre.
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
    # Si ya está guardada, se lee de la base: instantáneo y sigue disponible
    # aunque el diario la haya bajado.
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
    """Para pegar un texto propio: un mail del laburo, una carta del Amt."""
    an = german.analyze(inp.text)
    return {"url": "", "title": inp.title, "text": inp.text,
            "n_chars": len(inp.text), **an, "statuses": store.statuses()}


# ---------- toque de palabra ----------

class WordIn(BaseModel):
    word: str
    lemma: str
    sentence: str = ""
    pos: str = ""
    separable: dict | None = None


@app.post("/api/word")
def word(inp: WordIn):
    """Camino rápido: diccionario, sin LLM. Responde en el acto."""
    entry = dictionary.lookup(inp.lemma)
    if not entry and inp.lemma != inp.word:
        entry = dictionary.lookup(inp.word)
    # La detección de separables se confirma contra el diccionario antes de
    # mostrarla: spaCy y el corte por prefijo dan falsos positivos ('einigen',
    # 'hochliegen') y no quiero enseñarle al usuario una regla que no existe.
    sep_ok = dictionary.confirm_separable(inp.separable) if inp.separable else False

    # Si era falso positivo, el lema reconstruido tampoco sirve para buscar
    # ('hochliegen' no está en ningún lado): hay que caer a la raíz real.
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
    """Camino lento: el LLM elige la acepción que aplica y arma un ejemplo."""
    if not llm.available():
        return {"error": "Ollama no responde. Levantalo con: ollama serve"}
    entry = dictionary.lookup(inp.lemma)
    if entry and entry["senses"]:
        out = llm.pick_sense(inp.word, inp.sentence, inp.lemma, entry["senses"])
        if out:
            sense = next((s for s in entry["senses"] if s["n"] == out["sense"]), None)
            # El ejemplo generado se valida antes de mostrarlo: con verbos
            # separables el modelo escribe cosas como «hängt vom Wetter
            # abhängen», y un ejemplo mal escrito es peor que ninguno.
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
                    # Ejemplos reales del diccionario para la acepción elegida:
                    # están bien escritos por definición.
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


# ---------- vocabulario ----------

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


# ---------- noticias guardadas ----------

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


# ---------- repaso ----------

@app.get("/api/study")
def study(limit: int = 20):
    return {"words": store.due_words(limit), "stats": store.stats()}


class ReviewIn(BaseModel):
    lemma: str
    ok: bool


@app.post("/api/study/review")
def do_review(inp: ReviewIn):
    return {"word": store.review(inp.lemma, inp.ok)}


# ---------- preferencias ----------

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


# ---------- estáticos ----------

def _assets_version() -> str:
    """Huella de los estáticos, para invalidar la caché cuando cambian."""
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
    El HTML se sirve sin cachear y con la versión de los estáticos pegada a
    cada <link>/<script>.

    Sin esto, Safari se quedaba con el index.html viejo y bajaba el app.js
    nuevo. La mezcla rompía la app entera (un botón que el script esperaba no
    existía en el HTML cacheado) y desde el teléfono se veía como si el
    servidor se hubiera caído.
    """
    html = (WEB / "index.html").read_text(encoding="utf-8")
    v = _assets_version()
    html = html.replace("/styles.css", f"/styles.css?v={v}")
    html = html.replace("/app.js", f"/app.js?v={v}")
    return HTMLResponse(html, headers={
        "Cache-Control": "no-cache, must-revalidate",
    })


app.mount("/", StaticFiles(directory=WEB), name="web")
