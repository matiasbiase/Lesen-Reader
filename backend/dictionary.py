"""
German Wiktionary -> Spanish meanings, split sense by sense.

de.wiktionary groups its translations by sense number ({{Ü-Tabelle|1|G=...}}),
so what comes back can be "sense 1 = levantarse, sense 2 = estar de pie" rather
than one flat list. That grouping is exactly what the model is handed later, so
it picks which sense applies instead of being free to invent one.

⚠️ The glosses are Spanish because the reader is: see the note in the README.
"""
import logging
import re
import httpx
from functools import lru_cache

log = logging.getLogger("lesen.dict")

API = "https://de.wiktionary.org/w/api.php"
# Wikimedia returns 403 if the User-Agent isn't descriptive and doesn't carry a
# contact link (their bot policy). It also has to be pure ASCII: HTTP headers
# don't take accented characters.
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
        # No failing quietly: a 403 or a malformed header has to show up in the
        # console, not disguise itself as "word with no entry".
        log.warning("Wiktionary '%s' falló: %s: %s", title, type(e).__name__, e)
        return None


def _clean(s: str) -> str:
    """Strips the wiki markup and leaves readable text."""
    s = re.sub(r"\{\{K\|([^}]*)\}\}", lambda m: m.group(1).split("|")[0] + ":", s)
    s = re.sub(r"\[\[([^\]|]*)\|([^\]]*)\]\]", r"\2", s)
    s = re.sub(r"\[\[([^\]]*)\]\]", r"\1", s)
    s = re.sub(r"\{\{[^}]*\}\}", "", s)
    s = s.replace("'''", "").replace("''", "")
    s = re.sub(r"<[^>]+>", "", s)
    return re.sub(r"\s+", " ", s).strip(" :;,")


def _numbered(block: str) -> dict[str, list[str]]:
    """Parses lines shaped ':[1] text' -> {'1': [text, ...]}"""
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
    """Returns the block after {{Name}} up to the next {{...}} at that level."""
    m = re.search(r"\{\{" + name + r"\}\}(.*?)(?=\n\{\{[A-ZÄÖÜ][^}]*\}\}|\n==|\Z)",
                  wikitext, re.S)
    return m.group(1) if m else ""


def _spanish_by_sense(wikitext: str) -> dict[str, list[str]]:
    """Pulls the Spanish translations out of each {{Ü-Tabelle|N|...}}."""
    out: dict[str, list[str]] = {}
    for m in re.finditer(r"\{\{Ü-Tabelle\|([^|]*)\|(.*?)(?=\n\{\{Ü-Tabelle|\n==|\Z)",
                         wikitext, re.S):
        nums, body = m.group(1), m.group(2)
        words: list[str] = []
        for line in body.split("\n"):
            if not re.match(r"\*+\s*\{\{es\}\}", line.strip()):
                continue
            # {{Ü|es|word}} and {{Üt|es|word|translit}}
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
    Looks a lemma up and returns its senses with their Spanish glosses.

    {"lemma", "pos", "senses":[{"n","de","es":[...],"examples":[...]}], "extra"}
    """
    wt = _fetch_wikitext(lemma)
    if not wt:
        return None

    # Keep only the German part of the page
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
    """Does it exist as a verb? Used to avoid inventing separable verbs."""
    e = lookup(lemma)
    return bool(e and "Verb" in (e.get("pos") or ""))


def confirm_separable(sep: dict) -> bool:
    """
    Checks a separable-verb detection before it gets shown.

    Needed because both detection paths throw false positives:
      - Splitting the lemma by prefix matches too eagerly: 'einigen' ->
        'ein'+'igen', but 'igen' isn't a verb, so 'einigen' is NOT separable.
      - spaCy sometimes marks svp on a predicative: in 'die Zahl liegt hoch' it
        tags 'hoch' as a particle and invents 'hochliegen', which doesn't exist.

    The rule: if the particle is detached, the rebuilt verb has to exist; if
    it's attached, what has to exist is the stem without the prefix.
    """
    if not sep or not sep.get("is_separable"):
        return False
    prefix, stem = sep.get("prefix", ""), sep.get("stem", "")
    if not prefix or not stem:
        return False
    if sep.get("split"):
        return is_verb(prefix + stem)
    return is_verb(stem)
