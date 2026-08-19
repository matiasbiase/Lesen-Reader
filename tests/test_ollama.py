import json, time, urllib.request

SCHEMA = {
    "type": "object",
    "properties": {
        "lemma": {"type": "string"},
        "es_contexto": {"type": "string"},
        "separable": {"type": "boolean"},
        "particula": {"type": "string"},
        "nota": {"type": "string"},
    },
    "required": ["lemma", "es_contexto", "separable", "particula", "nota"],
}

PROMPT = """Sos un profesor de alemán. En la oración, el estudiante tocó la palabra marcada con **.

Oración: {sent}
Palabra tocada: {word}

Devolvé JSON:
- lemma: la forma de diccionario. OJO: si es un verbo separable cuya partícula está suelta en otro lugar de la oración, el lemma DEBE incluir la partícula (ej. "steht ... auf" -> "aufstehen").
- es_contexto: el significado en español QUE APLICA EN ESTA ORACIÓN (no todos los sentidos).
- separable: true solo si es un verbo separable.
- particula: la partícula separable, o "" si no hay.
- nota: una línea explicando la gramática al estudiante."""

CASES = [
    ("Die Regierung schlägt neue Maßnahmen gegen die Inflation vor.", "schlägt", "vorschlagen"),
    ("Er steht jeden Morgen um sechs Uhr auf.", "steht", "aufstehen"),
    ("Ich stehe vor dem Haus und warte auf dich.", "stehe", "stehen (CONTROL: NO separable)"),
    ("Das Unternehmen hat die Produktion vergangene Woche eingestellt.", "eingestellt", "einstellen = suspender (NO contratar)"),
]

for sent, word, expected in CASES:
    body = json.dumps({
        "model": "gemma4:12b",
        "prompt": PROMPT.format(sent=sent, word=word),
        "stream": False,
        "format": SCHEMA,
        "options": {"temperature": 0},
    }).encode()
    t0 = time.time()
    try:
        with urllib.request.urlopen(
            urllib.request.Request("http://localhost:11434/api/generate", body,
                                   {"Content-Type": "application/json"}), timeout=180) as r:
            out = json.load(r)
        dt = time.time() - t0
        d = json.loads(out["response"])
        ok = "?"
        print(f"\n{'='*70}\nOración : {sent}\nTocó    : {word}\nEsperado: {expected}\n{'-'*70}")
        print(f"  lemma      : {d.get('lemma')}")
        print(f"  español    : {d.get('es_contexto')}")
        print(f"  separable  : {d.get('separable')}   partícula: '{d.get('particula')}'")
        print(f"  nota       : {d.get('nota')}")
        ev = out.get("eval_count", 0)
        print(f"  >> {dt:.1f}s  ({ev} tokens, {ev/dt:.0f} tok/s)")
    except Exception as e:
        print(f"FALLO en '{word}': {type(e).__name__}: {e}")
