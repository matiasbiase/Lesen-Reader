"""
Capa gramatical determinista.

Todo lo que se pueda resolver con reglas se resuelve acá, sin LLM: lema,
categoría, y sobre todo la reconstrucción de verbos separables. Esta capa
tiene que ser siempre correcta, porque es la que el usuario ve al instante
cuando toca una palabra.
"""
from dataclasses import dataclass, asdict, field
from functools import lru_cache
import re

import spacy

# Prefijos que SIEMPRE se separan. Llevan el acento y se van al final del campo verbal.
SEPARABLE = {
    "ab", "an", "auf", "aus", "bei", "da", "dar", "davon", "dazu", "ein", "empor",
    "entgegen", "entlang", "fern", "fest", "fort", "gegenüber", "gleich", "her",
    "herab", "heran", "herauf", "heraus", "herbei", "herein", "herum", "herunter",
    "hervor", "hin", "hinab", "hinauf", "hinaus", "hinein", "hinter", "hinunter",
    "hinzu", "los", "mit", "nach", "nieder", "statt", "teil", "vor", "voran",
    "voraus", "vorbei", "vorüber", "weg", "weiter", "wieder", "zu", "zurecht",
    "zurück", "zusammen",
}

# Prefijos que NUNCA se separan. Además, su Partizip II no lleva "ge-".
INSEPARABLE = {"be", "emp", "ent", "er", "ge", "miss", "ver", "zer"}

# Prefijos ambiguos: separan o no según el significado, y cambia el acento.
# Es la trampa clásica del alemán, así que los marco aparte para poder avisar.
DUAL = {
    "durch": ("durchqueren (insep.) vs. durchfahren (sep.)"),
    "über": ("übersetzen = traducir (insep.) vs. übersetzen = cruzar en barca (sep.)"),
    "um": ("umfahren = esquivar (insep.) vs. umfahren = atropellar (sep.)"),
    "unter": ("unterschreiben = firmar (insep.) vs. untergehen = hundirse (sep.)"),
    "voll": ("vollenden = completar (insep.) vs. vollmachen = llenar (sep.)"),
    "wider": ("widersprechen = contradecir (insep.) vs. widerspiegeln = reflejar (sep.)"),
}

# Reglas de posición. Se arman con el verbo que el usuario tocó, no con un
# ejemplo enlatado: leer una regla sobre 'aufstehen' cuando tocaste 'abhängen'
# obliga a traducir mentalmente y estorba más de lo que ayuda.
def position_rule(kind: str, prefix: str, stem: str) -> str:
    p, s = f"**{prefix}**", stem
    if kind == "hauptsatz":
        return (f"En oración principal (presente o Präteritum) la partícula se va al FINAL "
                f"de la oración, lejos del verbo. Por eso ves el verbo conjugado por un lado "
                f"y {p} por el otro.")
    if kind == "partizip":
        return (f"Es el Partizip II: la partícula {p} queda pegada adelante y el «ge-» se "
                f"mete en el medio ({p}ge{s[:-2] if s.endswith('en') else s}…).")
    if kind == "nebensatz":
        return (f"Acá la partícula está pegada: en subordinada el verbo se va al final y "
                f"{p} vuelve a unirse ({p}{s}).")
    if kind == "modal":
        return (f"En infinitivo va entero: {p}{s}. Con «zu», el «zu» se mete en el medio "
                f"({p}zu{s}).")
    return ""

_NLP = None


def nlp():
    global _NLP
    if _NLP is None:
        _NLP = spacy.load("de_core_news_sm")
    return _NLP


@dataclass
class Separable:
    is_separable: bool = False
    prefix: str = ""
    stem: str = ""
    split: bool = False          # ¿está partido en ESTA oración?
    particle_text: str = ""      # la partícula tal como aparece
    particle_i: int = -1         # índice del token de la partícula
    dual: str = ""               # aviso si el prefijo es ambiguo
    rule: str = ""               # regla de posición que aplica acá
    display: str = ""            # "auf|stehen"


def _split_prefix(lemma: str):
    """Parte un lema en (prefijo, raíz) si arranca con prefijo separable."""
    low = lemma.lower()
    # el más largo primero, para que "zurück" gane sobre "zu"
    for p in sorted(SEPARABLE, key=len, reverse=True):
        if low.startswith(p) and len(low) > len(p) + 2:
            return p, low[len(p):]
    return "", ""


def analyze_separable(tok, doc) -> Separable:
    """
    Decide si el token es un verbo separable y, si está partido, lo reconstruye.

    Dos caminos:
      1. La partícula está suelta en la oración -> spaCy la marca con dep_="svp"
         y apunta al verbo. Es el caso de "steht ... auf".
      2. La partícula está pegada (infinitivo, Partizip II, subordinada) -> el
         lema de spaCy ya viene entero y solo hay que separarlo para mostrarlo.
    """
    if tok.pos_ not in ("VERB", "AUX"):
        return Separable()

    # Camino 1: partícula suelta apuntando a este verbo
    for child in tok.children:
        if child.dep_ == "svp":
            prefix = child.text.lower()
            stem = tok.lemma_.lower()
            full = prefix + stem
            return Separable(
                is_separable=True, prefix=prefix, stem=stem, split=True,
                particle_text=child.text, particle_i=child.i,
                dual=DUAL.get(prefix, ""),
                rule=position_rule("hauptsatz", prefix, stem),
                display=f"{prefix}|{stem}",
            )

    # Camino 2: lema ya unido; ver si empieza con prefijo separable
    prefix, stem = _split_prefix(tok.lemma_)
    if not prefix:
        return Separable()

    morph = tok.morph.to_dict()
    kind = {"Part": "partizip", "Inf": "modal"}.get(morph.get("VerbForm"), "nebensatz")
    rule = position_rule(kind, prefix, stem)

    return Separable(
        is_separable=True, prefix=prefix, stem=stem, split=False,
        dual=DUAL.get(prefix, ""), rule=rule, display=f"{prefix}|{stem}",
    )


def lemma_of(tok, doc) -> str:
    """Lema de búsqueda: para separables partidos, el verbo reconstruido."""
    sep = analyze_separable(tok, doc)
    if sep.is_separable and sep.split:
        return sep.prefix + sep.stem
    return tok.lemma_


# Categorías que vale la pena poder tocar. El resto (puntuación, números,
# nombres propios) no aporta nada al vocabulario y ensucia el texto.
CONTENT_POS = {"NOUN", "VERB", "ADJ", "ADV", "PROPN", "ADP", "AUX"}

POS_ES = {
    "NOUN": "sustantivo", "VERB": "verbo", "ADJ": "adjetivo", "ADV": "adverbio",
    "PROPN": "nombre propio", "ADP": "preposición", "AUX": "verbo auxiliar",
    "PRON": "pronombre", "DET": "artículo", "CCONJ": "conjunción",
    "SCONJ": "conjunción", "NUM": "número", "PART": "partícula",
}

# Género a partir de la morfología, para mostrar der/die/das con el sustantivo.
ARTICLE = {"Masc": "der", "Fem": "die", "Neut": "das"}


def analyze(text: str) -> dict:
    """
    Convierte un texto alemán en tokens listos para renderizar y tocar.

    Devuelve todos los tokens (incluida puntuación y espacios) para poder
    reconstruir el texto exacto, pero solo marca `tappable` en los que valen.
    """
    doc = nlp()(text)
    tokens = []
    for tok in doc:
        is_word = tok.is_alpha and not tok.is_stop or (tok.is_alpha and tok.pos_ in CONTENT_POS)
        sep = analyze_separable(tok, doc)
        item = {
            "i": tok.i,
            "text": tok.text,
            "ws": tok.whitespace_,
            "sent": tok.sent.text.strip(),
            "tappable": bool(tok.is_alpha and tok.pos_ in CONTENT_POS),
            "pos": tok.pos_,
            "pos_es": POS_ES.get(tok.pos_, tok.pos_.lower()),
            "lemma": lemma_of(tok, doc),
        }
        if tok.pos_ == "NOUN":
            g = tok.morph.to_dict().get("Gender")
            item["article"] = ARTICLE.get(g, "")
        if sep.is_separable:
            item["separable"] = asdict(sep)
            # La partícula suelta se marca también, para poder resaltar el par
            if sep.split:
                item["pair_i"] = sep.particle_i
        tokens.append(item)

    # Marcar las partículas sueltas para que el frontend pueda iluminar el par
    by_i = {t["i"]: t for t in tokens}
    for t in tokens:
        if t.get("separable", {}).get("split"):
            p = by_i.get(t["separable"]["particle_i"])
            if p:
                p["is_particle_of"] = t["i"]
                p["tappable"] = True
                p["lemma"] = t["lemma"]

    return {"tokens": tokens, "n_sentences": len(list(doc.sents))}


# Tiempos y modos que se pueden reconocer con la morfología de spaCy.
# El orden es el que se muestra en la interfaz.
TENSES = {
    "praesens":     "Presente",
    "perfekt":      "Perfekt",
    "praeteritum":  "Präteritum",
    "plusquam":     "Plusquamperfekt",
    "futur":        "Futur",
    "passiv":       "Pasiva",
    "konjunktiv1":  "Konjunktiv I",
    "konjunktiv2":  "Konjunktiv II",
}

# Las noticias viven en presente, Perfekt y Präteritum. Konjunktiv I aparece
# en la cita indirecta ("der Minister sagte, die Lage sei ernst"), que es muy
# de prensa y casi no se practica; el resto es directamente raro.
COMMON_TENSES = {"praesens", "perfekt", "praeteritum"}


def tense_profile(text: str) -> list[str]:
    """Qué tiempos y modos aparecen en un texto."""
    return _profile(nlp()(text))


def tense_profiles(texts: list[str]) -> list[list[str]]:
    """Versión en lote, para perfilar los titulares del feed de una pasada."""
    return [_profile(d) for d in nlp().pipe(texts, batch_size=32)]


def _profile(doc) -> list[str]:
    """
    Los tiempos compuestos se arman con auxiliar + forma no finita, así que
    primero se resuelven esos y el auxiliar se marca como consumido: si no, un
    Perfekt contaría además como presente por culpa del "hat".
    """
    found: set[str] = set()
    consumed: set[int] = set()

    for tok in doc:
        if tok.pos_ not in ("VERB", "AUX") or tok.morph.to_dict().get("VerbForm") != "Fin":
            continue
        m = tok.morph.to_dict()
        tense, mood = m.get("Tense"), m.get("Mood")

        # forma no finita que depende de este verbo
        nonfin = next((c for c in tok.children
                       if c.morph.to_dict().get("VerbForm") in ("Part", "Inf")), None)
        if nonfin is None:
            continue
        vf = nonfin.morph.to_dict().get("VerbForm")
        lem = tok.lemma_.lower()

        if lem == "werden" and vf == "Part":
            found.add("passiv"); consumed.add(tok.i)
        elif lem == "werden" and vf == "Inf":
            found.add("konjunktiv2" if mood == "Sub" else "futur"); consumed.add(tok.i)
        elif lem in ("haben", "sein") and vf == "Part":
            if mood == "Sub":
                found.add("konjunktiv2")
            else:
                found.add("plusquam" if tense == "Past" else "perfekt")
            consumed.add(tok.i)

    for tok in doc:
        if tok.i in consumed or tok.pos_ not in ("VERB", "AUX"):
            continue
        m = tok.morph.to_dict()
        if m.get("VerbForm") != "Fin":
            continue
        tense, mood = m.get("Tense"), m.get("Mood")
        if mood == "Sub":
            found.add("konjunktiv2" if tense == "Past" else "konjunktiv1")
        elif tense == "Past":
            found.add("praeteritum")
        elif tense == "Pres":
            found.add("praesens")

    return [k for k in TENSES if k in found]


def rare_tenses(profile: list[str]) -> list[str]:
    """Los que valen la pena señalar: lo que no es el pan de cada día."""
    return [t for t in profile if t not in COMMON_TENSES]


def check_example(sentence: str, lemma: str) -> bool:
    """
    ¿La oración de ejemplo usa bien el verbo separable?

    El modelo local comete un error muy concreto y muy repetido: conjuga la
    raíz y además deja el infinitivo entero colgado al final, tipo
    «Der Erfolg hängt von dem Wetter abhängen» en vez de «… hängt vom Wetter ab».
    Como el ejemplo es material de estudio, se descarta si tiene esa forma.

    Devuelve True si el uso es válido (o si no hay nada que objetar).
    """
    prefix, stem = _split_prefix(lemma)
    if not prefix:
        return True

    doc = nlp()(sentence)

    # Caso correcto y más común: partícula suelta (Satzklammer).
    if any(t.dep_ == "svp" and t.text.lower() == prefix for t in doc):
        return True

    enteros = [t for t in doc if t.lemma_.lower() == lemma.lower()]
    if not enteros:
        return True                      # el verbo no aparece: nada que objetar

    for t in enteros:
        # Regido por auxiliar o modal: «wird … abhängen», «muss … aufstehen».
        # Ojo: spaCy cuelga el modal como HIJO del infinitivo, no como head,
        # así que hay que mirar para los dos lados.
        if t.head.pos_ == "AUX" or any(c.pos_ == "AUX" for c in t.children):
            return True
        if t.morph.to_dict().get("VerbForm") == "Part":
            return True                  # Partizip II: «abgehangen»
        if any(c.text.lower() == "zu" for c in t.children):
            return True                  # «abzuhängen»

    # Queda el verbo entero sin nada que lo rija. Si además hay un verbo
    # conjugado con la raíz sola, es el error del modelo: conjugó la raíz Y
    # dejó el infinitivo colgado. No se puede confiar como material de estudio.
    #
    # No se mira VerbForm porque spaCy etiqueta «abhängen» como finito en la
    # oración mal formada — el infinitivo y la 3ª del plural son idénticos.
    if any(t.pos_ in ("VERB", "AUX") and t.lemma_.lower() == stem.lower() for t in doc):
        return False

    return True                          # verbo entero al final de subordinada


@lru_cache(maxsize=4096)
def quick_lemma(word: str) -> str:
    """Lema de una palabra suelta, sin contexto. Para la vista de estudio."""
    doc = nlp()(word)
    return doc[0].lemma_ if len(doc) else word
