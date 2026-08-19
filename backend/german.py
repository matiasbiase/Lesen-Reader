"""
The deterministic grammar layer.

Anything rules can settle is settled here, with no LLM in the loop: lemma, part
of speech, and above all rebuilding separable verbs. This layer has to be right
every time, because it's what the reader sees the instant a word is tapped.

⚠️ The strings this module returns to the interface (the position rules) are in
Spanish on purpose — they are what the reader reads. See the README.
"""
from dataclasses import dataclass, asdict, field
from functools import lru_cache
import re

import spacy

# Prefixes that ALWAYS separate. They carry the stress and move to the end of the clause.
SEPARABLE = {
    "ab", "an", "auf", "aus", "bei", "da", "dar", "davon", "dazu", "ein", "empor",
    "entgegen", "entlang", "fern", "fest", "fort", "gegenüber", "gleich", "her",
    "herab", "heran", "herauf", "heraus", "herbei", "herein", "herum", "herunter",
    "hervor", "hin", "hinab", "hinauf", "hinaus", "hinein", "hinter", "hinunter",
    "hinzu", "los", "mit", "nach", "nieder", "statt", "teil", "vor", "voran",
    "voraus", "vorbei", "vorüber", "weg", "weiter", "wieder", "zu", "zurecht",
    "zurück", "zusammen",
}

# Prefixes that NEVER separate. Their Partizip II also drops the "ge-".
INSEPARABLE = {"be", "emp", "ent", "er", "ge", "miss", "ver", "zer"}

# Ambiguous prefixes: they separate or not depending on the meaning, and the
# stress moves with it. The classic German trap, kept apart so it can be flagged.
DUAL = {
    "durch": ("durchqueren (insep.) vs. durchfahren (sep.)"),
    "über": ("übersetzen = traducir (insep.) vs. übersetzen = cruzar en barca (sep.)"),
    "um": ("umfahren = esquivar (insep.) vs. umfahren = atropellar (sep.)"),
    "unter": ("unterschreiben = firmar (insep.) vs. untergehen = hundirse (sep.)"),
    "voll": ("vollenden = completar (insep.) vs. vollmachen = llenar (sep.)"),
    "wider": ("widersprechen = contradecir (insep.) vs. widerspiegeln = reflejar (sep.)"),
}

# Position rules. Built around the verb that was actually tapped, never a canned
# example: reading a rule about 'aufstehen' when you tapped 'abhängen' forces a
# mental substitution and gets in the way more than it helps.
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
    """Splits a lemma into (prefix, stem) if it starts with a separable prefix."""
    low = lemma.lower()
    # longest first, so "zurück" wins over "zu"
    for p in sorted(SEPARABLE, key=len, reverse=True):
        if low.startswith(p) and len(low) > len(p) + 2:
            return p, low[len(p):]
    return "", ""


def analyze_separable(tok, doc) -> Separable:
    """
    Decides whether the token is a separable verb and, if it's split, rebuilds it.

    Two paths:
      1. The particle stands loose in the sentence -> spaCy marks it dep_="svp"
         and points at the verb. That's the "steht ... auf" case.
      2. The particle is attached (infinitive, Partizip II, subordinate clause)
         -> spaCy's lemma already arrives whole and is only split for display.
    """
    if tok.pos_ not in ("VERB", "AUX"):
        return Separable()

    # Path 1: a loose particle pointing at this verb
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

    # Path 2: lemma already joined; check whether it starts with a separable prefix
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
    """The lemma to look up: for split separables, the rebuilt verb."""
    sep = analyze_separable(tok, doc)
    if sep.is_separable and sep.split:
        return sep.prefix + sep.stem
    return tok.lemma_


# The parts of speech worth making tappable. The rest (punctuation, numbers,
# proper nouns) adds nothing to a vocabulary and only clutters the text.
CONTENT_POS = {"NOUN", "VERB", "ADJ", "ADV", "PROPN", "ADP", "AUX"}

POS_ES = {
    "NOUN": "sustantivo", "VERB": "verbo", "ADJ": "adjetivo", "ADV": "adverbio",
    "PROPN": "nombre propio", "ADP": "preposición", "AUX": "verbo auxiliar",
    "PRON": "pronombre", "DET": "artículo", "CCONJ": "conjunción",
    "SCONJ": "conjunción", "NUM": "número", "PART": "partícula",
}

# Gender off the morphology, so der/die/das shows next to the noun.
ARTICLE = {"Masc": "der", "Fem": "die", "Neut": "das"}


def analyze(text: str) -> dict:
    """
    Turns a German text into tokens ready to render and tap.

    Returns every token (punctuation and whitespace included) so the exact text
    can be rebuilt, but only marks `tappable` on the ones worth tapping.
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
            # The loose particle is tagged too, so the pair can be highlighted
            if sep.split:
                item["pair_i"] = sep.particle_i
        tokens.append(item)

    # Tag the loose particles so the frontend can light up both halves
    by_i = {t["i"]: t for t in tokens}
    for t in tokens:
        if t.get("separable", {}).get("split"):
            p = by_i.get(t["separable"]["particle_i"])
            if p:
                p["is_particle_of"] = t["i"]
                p["tappable"] = True
                p["lemma"] = t["lemma"]

    return {"tokens": tokens, "n_sentences": len(list(doc.sents))}


# The tenses and moods spaCy's morphology can recognise.
# The order here is the order the interface shows them in.
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

# News lives in present, Perfekt and Präteritum. Konjunktiv I turns up in
# reported speech ("der Minister sagte, die Lage sei ernst"), which is very much
# a press thing and almost never drilled; the rest is plainly rare.
COMMON_TENSES = {"praesens", "perfekt", "praeteritum"}


def tense_profile(text: str) -> list[str]:
    """Which tenses and moods show up in a text."""
    return _profile(nlp()(text))


def tense_profiles(texts: list[str]) -> list[list[str]]:
    """Batched version, to profile a feed's headlines in one pass."""
    return [_profile(d) for d in nlp().pipe(texts, batch_size=32)]


def _profile(doc) -> list[str]:
    """
    Compound tenses are built from auxiliary + non-finite form, so those get
    resolved first and the auxiliary is marked as consumed: otherwise a Perfekt
    would also count as present, on account of the "hat".
    """
    found: set[str] = set()
    consumed: set[int] = set()

    for tok in doc:
        if tok.pos_ not in ("VERB", "AUX") or tok.morph.to_dict().get("VerbForm") != "Fin":
            continue
        m = tok.morph.to_dict()
        tense, mood = m.get("Tense"), m.get("Mood")

        # the non-finite form hanging off this verb
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

    # The correct and commonest case: a loose particle (Satzklammer).
    if any(t.dep_ == "svp" and t.text.lower() == prefix for t in doc):
        return True

    whole = [t for t in doc if t.lemma_.lower() == lemma.lower()]
    if not whole:
        return True                      # the verb isn't there: nothing to object to

    for t in whole:
        # Governed by an auxiliary or modal: «wird … abhängen», «muss … aufstehen».
        # Careful: spaCy hangs the modal as a CHILD of the infinitive, not as its
        # head, so both directions have to be checked.
        if t.head.pos_ == "AUX" or any(c.pos_ == "AUX" for c in t.children):
            return True
        if t.morph.to_dict().get("VerbForm") == "Part":
            return True                  # Partizip II: «abgehangen»
        if any(c.text.lower() == "zu" for c in t.children):
            return True                  # «abzuhängen»

    # What's left is the whole verb with nothing governing it. If there's also a
    # conjugated verb built on the bare stem, that's the model's mistake: it
    # conjugated the stem AND left the infinitive dangling. Not something to
    # trust as study material.
    #
    # VerbForm isn't consulted because spaCy tags «abhängen» as finite in the
    # malformed sentence — the infinitive and the 3rd person plural are identical.
    if any(t.pos_ in ("VERB", "AUX") and t.lemma_.lower() == stem.lower() for t in doc):
        return False

    return True                          # whole verb at the end of a subordinate clause


@lru_cache(maxsize=4096)
def quick_lemma(word: str) -> str:
    """Lemma of a word on its own, with no context. For the study view."""
    doc = nlp()(word)
    return doc[0].lemma_ if len(doc) else word
