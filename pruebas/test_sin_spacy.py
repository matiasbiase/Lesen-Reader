"""
¿Se puede detectar verbos separables SIN el parser de dependencias de spaCy?

Importa para saber si la app puede correr sola en el teléfono: en iOS,
NLTagger da lema y categoría pero no árbol de dependencias, y para los
separables devuelve la raíz sin prefijo ('stehen' en vez de 'aufstehen').

La hipótesis: alcanza con reglas de posición + verificar contra diccionario.
Se compara contra spaCy, que acá hace de patrón de referencia.
"""
import pathlib
import sys, re
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "backend"))
from german import nlp, SEPARABLE, _split_prefix
from dictionary import is_verb

# Signos que cierran una cláusula: la partícula suele quedar justo antes.
CIERRE = {".", ",", ";", ":", "!", "?", "–", "—", ")", '"', "“", "”",
          # una coordinada también cierra la cláusula: "…nimmt teil UND bringt…"
          "und", "oder", "aber", "sondern", "denn", "sowie"}


def detectar_sin_dependencias(doc):
    """
    Solo con lema + categoría + posición, que es lo que da NLTagger.

    Regla: una partícula separable suelta aparece al final de su cláusula.
    Se busca hacia atrás el verbo conjugado más cercano y se verifica que el
    verbo reconstruido exista de verdad.
    """
    encontrados = {}
    for tok in doc:
        if tok.text.lower() not in SEPARABLE:
            continue
        # ¿está al final de la cláusula? (le sigue puntuación o el final)
        sig = doc[tok.i + 1] if tok.i + 1 < len(doc) else None
        if sig is not None and sig.text.lower() not in CIERRE:
            continue
        # verbo conjugado más cercano hacia atrás, dentro de la misma oración
        limite = tok.sent.start          # .sent devuelve un Span nuevo cada vez:
        for j in range(tok.i - 1, max(tok.i - 25, -1), -1):   # comparar con `is` no sirve
            v = doc[j]
            if j < limite:
                break
            if v.pos_ in ("VERB", "AUX") and v.morph.to_dict().get("VerbForm") == "Fin":
                cand = tok.text.lower() + v.lemma_.lower()
                if is_verb(cand):                      # la verificación decide
                    encontrados[v.i] = cand
                break
    return encontrados


def detectar_con_spacy(doc):
    out = {}
    for tok in doc:
        if tok.dep_ == "svp" and tok.head.pos_ in ("VERB", "AUX"):
            cand = tok.text.lower() + tok.head.lemma_.lower()
            if is_verb(cand):
                out[tok.head.i] = cand
    return out


TEXTOS = [
    "Die Regierung schlägt neue Maßnahmen gegen die Inflation vor.",
    "Er steht jeden Morgen um sechs Uhr auf.",
    "Ich stehe vor dem Haus und warte auf dich.",
    "Ob das so bleiben kann, hängt auch davon ab, wieviel Personal rekrutiert wird.",
    "Wenn er morgen früh aufsteht, ruft er dich an.",
    "Die Zahl der Anträge liegt hoch.",
    "Das Unternehmen stellte die Produktion vergangene Woche ein.",
    "Der Minister kündigte an, dass die Regelung im Januar in Kraft tritt.",
    "Sie nimmt an der Konferenz teil und bringt ihre Unterlagen mit.",
    "Die Parteien haben sich auf einen Kompromiss geeinigt.",
]

ok = fallos = 0
print(f"{'oración':<62} {'spaCy':<26} {'sin dependencias'}")
print("-" * 118)
for t in TEXTOS:
    doc = nlp()(t)
    a = detectar_con_spacy(doc)
    b = detectar_sin_dependencias(doc)
    igual = a == b
    ok += igual
    fallos += (not igual)
    va = ", ".join(sorted(a.values())) or "—"
    vb = ", ".join(sorted(b.values())) or "—"
    print(f"{'OK ' if igual else 'DIF'} {t[:58]:<58} {va:<26} {vb}")

print(f"\ncoincide en {ok}/{len(TEXTOS)}")
