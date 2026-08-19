# Measurements

The measurements the design rests on. Run them with the project's venv:

```bash
./.venv/bin/python tests/test_enum.py
```

These are experiments, not a test suite: each one answers a question that
changed a decision in the app.

| File | What it measures | Result |
|---|---|---|
| `test_ollama.py` | First look at gemma on separables, output unconstrained | Gets the meaning, fails the grammar |
| `test_modelos_chicos.py` | 1B and 3B models with free-form output | The 3B understands but breaks the format (0/8) |
| `test_enum.py` | The same models with output restricted to valid senses | 12B 8/8 · 3B 6/8 · 1B 5/8 · qwen1.7B 4/8 |
| `test_sin_spacy.py` | Detecting separables with no dependency parser | 10/10 against spaCy |

Together they are why the app splits the work the way it does: grammar to
spaCy, meaning to the model, and the model's answer constrained to senses that
already exist in the dictionary.

`test_enum.py` and `test_modelos_chicos.py` need the models pulled:

```bash
ollama pull llama3.2:3b && ollama pull llama3.2:1b && ollama pull qwen3:1.7b
```
