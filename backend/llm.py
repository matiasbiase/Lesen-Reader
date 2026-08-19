"""
The meaning layer: a local Ollama (gemma4:12b).

Design rule, and it came out of testing the model: gemma is good at deciding
WHICH sense a word carries in a concrete sentence, and bad at explaining German
grammar (it went as far as claiming 'einstellen' isn't separable, and inventing
an 'in-' prefix). So grammar is NEVER asked here — spaCy already settled it —
and when there's a Wiktionary entry the model is asked to PICK among the senses
that exist instead of writing a new one.

⚠️ The prompts below stay in Spanish on purpose. They are not comments: they
are the product. What comes back is what the reader reads, and this is a German
reader written for Spanish speakers — see the note in the README.
"""
import json
import logging
import httpx

log = logging.getLogger("lesen.llm")

OLLAMA = "http://localhost:11434"
MODEL = "gemma4:12b"

# Picking a sense: a short, closed answer, so it comes back fast.
# ⚠️ The keys (`porque`, `ejemplo_de`…) are the contract with the frontend:
# renaming them here breaks `web/app.js`.
PICK_SCHEMA = {
    "type": "object",
    "properties": {
        "sense": {"type": "string"},
        "es": {"type": "string"},
        "porque": {"type": "string"},
        "ejemplo_de": {"type": "string"},
        "ejemplo_es": {"type": "string"},
    },
    "required": ["sense", "es", "porque", "ejemplo_de", "ejemplo_es"],
}

FREE_SCHEMA = {
    "type": "object",
    "properties": {
        "es": {"type": "string"},
        "literal": {"type": "string"},
        "porque": {"type": "string"},
        "ejemplo_de": {"type": "string"},
        "ejemplo_es": {"type": "string"},
    },
    "required": ["es", "literal", "porque", "ejemplo_de", "ejemplo_es"],
}


def _call(prompt: str, schema: dict, num_predict: int = 320) -> dict | None:
    try:
        r = httpx.post(f"{OLLAMA}/api/generate", json={
            "model": MODEL, "prompt": prompt, "stream": False,
            "format": schema, "options": {"temperature": 0, "num_predict": num_predict},
        }, timeout=120.0)
        r.raise_for_status()
        return json.loads(r.json()["response"])
    except Exception as e:
        log.warning("ollama failed: %s: %s", type(e).__name__, e)
        return None


def available() -> bool:
    try:
        return httpx.get(f"{OLLAMA}/api/tags", timeout=3.0).status_code == 200
    except Exception:
        return False


def pick_sense(word: str, sentence: str, lemma: str, senses: list[dict]) -> dict | None:
    """
    Picks which of Wiktionary's senses applies in this sentence.

    The senses go in numbered and what comes back is the number, not free text.
    That way the meaning the reader sees always comes from a real dictionary.
    """
    listado = "\n".join(
        f"  [{s['n']}] {s['de']}" + (f"  -> es: {', '.join(s['es'])}" if s["es"] else "")
        for s in senses
    )
    prompt = f"""Sos profesor de alemán para un hispanohablante.

Oración: «{sentence}»
El estudiante tocó: «{word}» (lema: {lemma})

Acepciones que el diccionario da para «{lemma}»:
{listado}

Tu tarea:
1. "sense": el NÚMERO de la acepción que aplica en ESTA oración. Elegí uno de la lista, no inventes.
2. "es": la traducción al español que corresponde acá, 1-4 palabras.
3. "porque": en UNA línea corta y en español, por qué esa y no otra, según el contexto.
4. "ejemplo_de": una oración NUEVA y simple en alemán usando «{lemma}» con ESE mismo sentido.
5. "ejemplo_es": su traducción al español.

No expliques gramática. No inventes acepciones."""
    out = _call(prompt, PICK_SCHEMA)
    if not out:
        return None
    # Check the number actually exists; if it hallucinated, fall back to the first.
    valid = {s["n"] for s in senses}
    if out.get("sense") not in valid:
        log.info("sense '%s' out of range for %s", out.get("sense"), lemma)
        out["sense"] = senses[0]["n"]
        out["porque"] = out.get("porque", "")
    return out


def explain_free(word: str, sentence: str, lemma: str) -> dict | None:
    """
    No dictionary entry. Happens constantly with German compounds
    (Inflationsbekämpfung, Fachkräftemangel), which Wiktionary doesn't list but
    the model takes apart well.
    """
    prompt = f"""Sos profesor de alemán para un hispanohablante.

Oración: «{sentence}»
El estudiante tocó: «{word}» (lema: {lemma})

Esta palabra no está en el diccionario, probablemente es una palabra compuesta.

1. "es": significado en español acá, 1-5 palabras.
2. "literal": si es compuesta, sus partes separadas con + y qué significa cada una
   (ej. "Wirtschaft (economía) + Wachstum (crecimiento)"). Si no es compuesta, "".
3. "porque": UNA línea en español sobre el sentido en esta oración.
4. "ejemplo_de": oración nueva y simple en alemán con esa palabra.
5. "ejemplo_es": su traducción.

No expliques gramática."""
    return _call(prompt, FREE_SCHEMA)


def translate_sentence(sentence: str) -> str | None:
    """The whole sentence translated, for when you lose the thread."""
    out = _call(
        f"Traducí esta oración del alemán al español, natural y fiel. "
        f"Devolvé solo la traducción.\n\n«{sentence}»",
        {"type": "object", "properties": {"es": {"type": "string"}}, "required": ["es"]},
        num_predict=300,
    )
    return out.get("es") if out else None
