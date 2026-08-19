# Pruebas

Las mediciones que respaldan el análisis. Se corren con el venv del proyecto:

```bash
./.venv/bin/python pruebas/test_enum.py
```

| Archivo | Qué mide | Resultado obtenido |
|---|---|---|
| `test_ollama.py` | Primera evaluación de gemma con separables, sin acotar la salida | Acierta el sentido, falla la gramática |
| `test_modelos_chicos.py` | Modelos de 1B y 3B con salida libre | El 3B entiende pero erra el formato (0/8) |
| `test_enum.py` | Los mismos modelos con salida restringida a acepciones válidas | 12B 8/8 · 3B 6/8 · 1B 5/8 · qwen1.7B 4/8 |
| `test_sin_spacy.py` | Detectar separables sin parser de dependencias | 10/10 contra spaCy |

`test_enum.py` y `test_modelos_chicos.py` necesitan los modelos bajados:

```bash
ollama pull llama3.2:3b && ollama pull llama3.2:1b && ollama pull qwen3:1.7b
```
