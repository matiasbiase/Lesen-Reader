"""
Wiktionary alemán -> significados en español, separados por acepción.

El de.wiktionary trae las traducciones agrupadas por número de acepción
({{Ü-Tabelle|1|G=...}}), así que se puede devolver "sentido 1 = levantarse,
sentido 2 = estar de pie" en vez de una lista plana. Eso es justo lo que
después le damos al LLM para que elija cuál aplica, en vez de dejarlo inventar.
"""
import logging
import re
import httpx
from functools import lru_cache

log = logging.getLogger("lesen.dict")

API = "https://de.wiktionary.org/w/api.php"
# Wikimedia devuelve 403 si el User-Agent no es descriptivo y no trae un enlace
# de contacto (su política de bots). Además tiene que ser ASCII puro: las
# cabeceras HTTP no admiten acentos.
UA = "lesen/1.0 (personal offline German reader; https://de.wiktionary.org/wiki/Hilfe:API)"


def _fetch_wikitext(title: str) -> str | None:
    try:
        r = httpx.get(API, params={
            "action": "parse", "page": title, "prop": "wikitext",
            "format": "json", "formatversion": "2",
        }, headers={"User-Agent": UA}, timeout=8.0, follow_redirects=True)
        if r.status_code != 200:
            return None
        data = r.json()
        if "error" in data:
            return None
        return data["parse"]["wikitext"]
    except Exception as e:
        # Nada de fallar en silencio: un 403 o una cabecera mal armada tiene que
        # verse en consola, no disfrazarse de "palabra sin entrada".
        log.warning("Wiktionary '%s' falló: %s: %s", title, type(e).__name__, e)
        return None


def _clean(s: str) -> str:
    """Saca el marcado de wiki y deja texto legible."""
    s = re.sub(r"\{\{K\|([^}]*)\}\}", lambda m: m.group(1).split("|")[0] + ":", s)
    s = re.sub(r"\[\[([^\]|]*)\|([^\]]*)\]\]", r"\2", s)
    s = re.sub(r"\[\[([^\]]*)\]\]", r"\1", s)
    s = re.sub(r"\{\{[^}]*\}\}", "", s)
    s = s.replace("'''", "").replace("''", "")
    s = re.sub(r"<[^>]+>", "", s)
    return re.sub(r"\s+", " ", s).strip(" :;,")


def _numbered(block: str) -> dict[str, list[str]]:
    """Parsea líneas del tipo ':[1] texto' -> {'1': [texto, ...]}"""
    out: dict[str, list[str]] = {}
    for line in block.split("\n"):
        line = line.strip()
        if not line.startswith(":"):
            continue
        m = re.match(r":*\[([\d,\s a-z]+)\]\s*(.*)", line.lstrip(":").strip())
        if not m:
            continue
        text = _clean(m.group(2))
        if not text:
            continue
        for num in re.split(r"[,\s]+", m.group(1).strip()):
            num = num.strip()
            if num:
                out.setdefault(num, []).append(text)
    return out


def _section(wikitext: str, name: str) -> str:
    """Devuelve el bloque que sigue a {{Nombre}} hasta el próximo {{...}} de nivel."""
    m = re.search(r"\{\{" + name + r"\}\}(.*?)(?=\n\{\{[A-ZÄÖÜ][^}]*\}\}|\n==|\Z)",
                  wikitext, re.S)
    return m.group(1) if m else ""


def _spanish_by_sense(wikitext: str) -> dict[str, list[str]]:
    """De cada {{Ü-Tabelle|N|...}} extrae las traducciones al español."""
    out: dict[str, list[str]] = {}
    for m in re.finditer(r"\{\{Ü-Tabelle\|([^|]*)\|(.*?)(?=\n\{\{Ü-Tabelle|\n==|\Z)",
                         wikitext, re.S):
        nums, body = m.group(1), m.group(2)
        words: list[str] = []
        for line in body.split("\n"):
            if not re.match(r"\*+\s*\{\{es\}\}", line.strip()):
                continue
            # {{Ü|es|palabra}} y {{Üt|es|palabra|translit}}
            for w in re.findall(r"\{\{Üt?\??\|es\|([^|}]+)", line):
                w = w.strip()
                if w and w not in words:
                    words.append(w)
        if not words:
            continue
        for num in re.split(r"[,\s]+", nums.strip()):
            num = num.strip()
            if num:
                out.setdefault(num, []).extend(w for w in words if w not in out.get(num, []))
    return out


@lru_cache(maxsize=8192)
def lookup(lemma: str) -> dict | None:
    """
    Busca un lema y devuelve sus acepciones con traducción al español.

    {"lemma", "pos", "senses":[{"n","de","es":[...],"examples":[...]}], "extra"}
    """
    wt = _fetch_wikitext(lemma)
    if not wt:
        return None

    # Quedarse solo con la parte alemana de la página
    m = re.search(r"==\s*" + re.escape(lemma) + r"\s*\(\{\{Sprache\|Deutsch\}\}\)\s*==(.*?)(?=\n==\s*\S+\s*\(\{\{Sprache\||\Z)", wt, re.S)
    de = m.group(1) if m else wt

    pos = ""
    mp = re.search(r"\{\{Wortart\|([^|}]+)", de)
    if mp:
        pos = mp.group(1)

    glosses = _numbered(_section(de, "Bedeutungen"))
    examples = _numbered(_section(de, "Beispiele"))
    spanish = _spanish_by_sense(de)

    senses = []
    for n in sorted(set(glosses) | set(spanish), key=lambda x: (len(x), x)):
        senses.append({
            "n": n,
            "de": " / ".join(glosses.get(n, [])),
            "es": spanish.get(n, []),
            "examples": examples.get(n, [])[:2],
        })
    senses = [s for s in senses if s["de"] or s["es"]]
    if not senses:
        return None

    extra = {}
    mw = re.search(r"\{\{Worttrennung\}\}\n:?(.*)", de)
    if mw:
        extra["silabas"] = _clean(mw.group(1))
    mh = re.search(r"Hilfsverb=(\w+)", de)
    if mh:
        extra["hilfsverb"] = mh.group(1)
    mg = re.search(r"\{\{Deutsch (Substantiv|Nachname) Übersicht[^}]*?\|Genus=(\w+)", de, re.S)
    if mg:
        extra["genus"] = mg.group(2)

    return {"lemma": lemma, "pos": pos, "senses": senses[:6], "extra": extra,
            "url": f"https://de.wiktionary.org/wiki/{lemma}"}


@lru_cache(maxsize=8192)
def is_verb(lemma: str) -> bool:
    """¿Existe como verbo? Se usa para no inventar verbos separables."""
    e = lookup(lemma)
    return bool(e and "Verb" in (e.get("pos") or ""))


def confirm_separable(sep: dict) -> bool:
    """
    Verifica una detección de verbo separable antes de mostrarla.

    Hace falta porque las dos vías de detección producen falsos positivos:
      - Partir el lema por prefijo casa de más: 'einigen' -> 'ein'+'igen',
        pero 'igen' no es un verbo, así que 'einigen' NO es separable.
      - spaCy a veces marca svp sobre un predicativo: en 'die Zahl liegt hoch'
        etiqueta 'hoch' como partícula e inventa 'hochliegen', que no existe.

    Regla: si la partícula está suelta, el verbo reconstruido tiene que existir;
    si está pegada, el que tiene que existir es la raíz sin prefijo.
    """
    if not sep or not sep.get("is_separable"):
        return False
    prefix, stem = sep.get("prefix", ""), sep.get("stem", "")
    if not prefix or not stem:
        return False
    if sep.get("split"):
        return is_verb(prefix + stem)
    return is_verb(stem)
