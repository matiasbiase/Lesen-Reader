"""
Is a small model — the size of the one that runs on an iPhone — enough for
lesen's semantic task?

Apple's on-device model is ~3B. This compares 1.7B and 3B against the 12B that
runs on the Mac today, on the real task: picking which dictionary sense applies
in a concrete sentence.

It's multiple choice, not free generation. The hypothesis is that this is
exactly why a small model can be enough.

⚠️ The prompt below stays in Spanish: it's the real one, and changing it would
stop measuring the real thing.
"""
import json, sys, time, urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "backend"))
from dictionary import lookup

MODELOS = ["gemma4:12b", "llama3.2:3b", "qwen3:1.7b"]

SCHEMA = {
    "type": "object",
    "properties": {"sense": {"type": "string"}, "es": {"type": "string"}},
    "required": ["sense", "es"],
}

# (sentence, word, lemma, correct sense according to the dictionary)
CASOS = [
    ("Das Unternehmen hat die Produktion vergangene Woche eingestellt.",
     "eingestellt", "einstellen", "4", "suspender"),
    ("Die Firma hat letzte Woche drei neue Mitarbeiter eingestellt.",
     "eingestellt", "einstellen", "1", "contratar"),
    ("Er muss die Kamera noch richtig einstellen, bevor er filmt.",
     "einstellen", "einstellen", "2", "ajustar"),
    ("Er steht jeden Morgen um sechs Uhr auf.",
     "steht", "aufstehen", "1", "levantarse de la cama"),
    ("Nach dem Vortrag stand das Publikum auf und applaudierte.",
     "stand", "aufstehen", "2", "levantarse del asiento"),
    ("Ob das gelingt, hängt vom Wetter ab.",
     "hängt", "abhängen", "1", "depender"),
    ("Die Regierung schlägt neue Maßnahmen vor.",
     "schlägt", "vorschlagen", "1", "proponer"),
    ("Der Zug fährt um acht Uhr ab.",
     "fährt", "abfahren", "1", "partir"),
]


def preguntar(modelo, word, sentence, lemma, senses):
    listado = "\n".join(
        f"  [{s['n']}] {s['de']}" + (f"  -> es: {', '.join(s['es'])}" if s["es"] else "")
        for s in senses)
    prompt = f"""Sos profesor de alemán para un hispanohablante.

Oración: «{sentence}»
El estudiante tocó: «{word}» (lema: {lemma})

Acepciones del diccionario para «{lemma}»:
{listado}

Devolvé:
1. "sense": el NÚMERO de la acepción que aplica en ESTA oración. Elegí uno de la lista.
2. "es": la traducción al español que corresponde acá, 1-4 palabras.

No inventes acepciones."""
    body = json.dumps({"model": modelo, "prompt": prompt, "stream": False,
                       "format": SCHEMA,
                       "options": {"temperature": 0, "num_predict": 120}}).encode()
    t0 = time.time()
    with urllib.request.urlopen(urllib.request.Request(
            "http://localhost:11434/api/generate", body,
            {"Content-Type": "application/json"}), timeout=300) as r:
        out = json.load(r)
    return json.loads(out["response"]), time.time() - t0


entradas = {lemma: lookup(lemma) for _, _, lemma, _, _ in CASOS}

for modelo in MODELOS:
    print(f"\n{'='*76}\n{modelo}\n{'='*76}")
    aciertos, total_t = 0, 0.0
    for sent, word, lemma, esperado, desc in CASOS:
        senses = entradas[lemma]["senses"]
        try:
            out, dt = preguntar(modelo, word, sent, lemma, senses)
        except Exception as e:
            print(f"  ERROR {type(e).__name__}: {e}")
            continue
        total_t += dt
        bien = out.get("sense") == esperado
        aciertos += bien
        print(f"  {'OK ' if bien else 'MAL'} esperado [{esperado}] {desc:<24} "
              f"-> dio [{out.get('sense')}] {out.get('es','')[:24]:<24} {dt:.1f}s")
    print(f"  >>> {aciertos}/{len(CASOS)} aciertos · {total_t/len(CASOS):.1f}s promedio")
