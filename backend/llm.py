"""
Capa semántica: Ollama (gemma4:12b) local.

Regla de diseño, sacada de probar el modelo: gemma es bueno decidiendo QUÉ
significa una palabra en una frase concreta, y malo explicando gramática
alemana (llegó a decir que 'einstellen' no es separable y a inventar un
prefijo 'in-'). Así que acá NUNCA se le pregunta gramática — eso ya lo
resolvió spaCy — y cuando hay entrada de Wiktionary se le pide que ELIJA
entre las acepciones existentes en vez de escribir una nueva.
"""
import json
import logging
import httpx

log = logging.getLogger("lesen.llm")

OLLAMA = "http://localhost:11434"
MODEL = "gemma4:12b"

# Elegir acepción: respuesta corta y cerrada, así sale rápido.
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
        log.warning("ollama falló: %s: %s", type(e).__name__, e)
        return None


def available() -> bool:
    try:
        return httpx.get(f"{OLLAMA}/api/tags", timeout=3.0).status_code == 200
    except Exception:
        return False


def pick_sense(word: str, sentence: str, lemma: str, senses: list[dict]) -> dict | None:
    """
    Elige cuál de las acepciones de Wiktionary aplica en esta oración.

    Se le pasan las acepciones numeradas y devuelve el número, no texto libre.
    Así el significado que ve el usuario viene siempre de un diccionario real.
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
    # Validar que el número exista de verdad; si alucinó, caemos a la primera.
    valid = {s["n"] for s in senses}
    if out.get("sense") not in valid:
        log.info("sentido '%s' fuera de rango para %s", out.get("sense"), lemma)
        out["sense"] = senses[0]["n"]
        out["porque"] = out.get("porque", "")
    return out


def explain_free(word: str, sentence: str, lemma: str) -> dict | None:
    """
    Sin entrada de diccionario. Pasa mucho con los compuestos del alemán
    (Inflationsbekämpfung, Fachkräftemangel), que Wiktionary no lista pero
    el modelo descompone bien.
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
    """Traducción de la oración entera, para cuando se pierde el hilo."""
    out = _call(
        f"Traducí esta oración del alemán al español, natural y fiel. "
        f"Devolvé solo la traducción.\n\n«{sentence}»",
        {"type": "object", "properties": {"es": {"type": "string"}}, "required": ["es"]},
        num_predict=300,
    )
    return out.get("es") if out else None
