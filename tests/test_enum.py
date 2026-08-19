"""
Round two: the small model understood fine and only got the format wrong.

Here it's given an ENUM SCHEMA: the answer can only be one of the valid sense
numbers. It's the same thing Apple's guided generation does (@Generable with a
Swift enum): the format stops being possible to get wrong, and what's left
measured is comprehension on its own.
"""
import json, sys, time, urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "backend"))
from dictionary import lookup

MODELOS = ["gemma4:12b", "llama3.2:3b", "qwen3:1.7b", "llama3.2:1b"]

CASOS = [
    ("Das Unternehmen hat die Produktion vergangene Woche eingestellt.", "eingestellt", "einstellen", "4", "suspender"),
    ("Die Firma hat letzte Woche drei neue Mitarbeiter eingestellt.", "eingestellt", "einstellen", "1", "contratar"),
    ("Er muss die Kamera noch richtig einstellen, bevor er filmt.", "einstellen", "einstellen", "2", "ajustar"),
    ("Er steht jeden Morgen um sechs Uhr auf.", "steht", "aufstehen", "1", "levantarse de la cama"),
    ("Nach dem Vortrag stand das Publikum auf und applaudierte.", "stand", "aufstehen", "2", "levantarse del asiento"),
    ("Ob das gelingt, hängt vom Wetter ab.", "hängt", "abhängen", "1", "depender"),
    ("Die Regierung schlägt neue Maßnahmen vor.", "schlägt", "vorschlagen", "1", "proponer"),
    ("Der Zug fährt um acht Uhr ab.", "fährt", "abfahren", "1", "partir"),
]

entradas = {l: lookup(l) for _, _, l, _, _ in CASOS}


def preguntar(modelo, word, sentence, lemma, senses):
    validos = [s["n"] for s in senses]
    listado = "\n".join(
        f"  [{s['n']}] {s['de']}" + (f"  -> es: {', '.join(s['es'])}" if s["es"] else "")
        for s in senses)
    prompt = (f"Oración alemana: «{sentence}»\n"
              f"Palabra tocada: «{word}» (lema: {lemma})\n\n"
              f"Acepciones del diccionario:\n{listado}\n\n"
              f"¿Cuál acepción aplica en ESTA oración? Respondé solo con su número.")
    # the enum is the whole point: the model cannot return anything else
    schema = {"type": "object",
              "properties": {"sense": {"type": "string", "enum": validos}},
              "required": ["sense"]}
    body = json.dumps({"model": modelo, "prompt": prompt, "stream": False,
                       "format": schema,
                       "options": {"temperature": 0, "num_predict": 30}}).encode()
    t0 = time.time()
    with urllib.request.urlopen(urllib.request.Request(
            "http://localhost:11434/api/generate", body,
            {"Content-Type": "application/json"}), timeout=300) as r:
        out = json.load(r)
    return json.loads(out["response"]), time.time() - t0


print(f"{'modelo':<16} {'aciertos':<10} {'tiempo medio':<14} detalle")
print("-" * 74)
for modelo in MODELOS:
    ac, tt, det = 0, 0.0, []
    for sent, word, lemma, esperado, desc in CASOS:
        try:
            out, dt = preguntar(modelo, word, sent, lemma, entradas[lemma]["senses"])
        except Exception as e:
            det.append("ERR"); continue
        tt += dt
        bien = out.get("sense") == esperado
        ac += bien
        det.append("·" if bien else f"✗{desc[:9]}")
    print(f"{modelo:<16} {ac}/{len(CASOS):<8} {tt/max(len(CASOS),1):>6.1f}s        {' '.join(det)}")
