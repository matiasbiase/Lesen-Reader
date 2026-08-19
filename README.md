# lesen

Read German news by tapping the words you don't know. They save themselves into
a deck, and later you review them.

*[Léeme en español](README.es.md)*

```bash
./run.sh
```

- On the Mac: <http://localhost:8777>
- On your phone: over [Tailscale](https://tailscale.com), inside your tailnet
  only. Put your address (`https://YOUR-MACHINE.YOUR-TAILNET.ts.net:8443`) in a
  `direccion.txt` file next to `run.sh` and you'll see it printed on startup.

Needs Ollama running with `gemma4:12b`. Without Ollama the app still works, but
without the in-context analysis: it shows you every sense and you pick.

> **A note on language.** The interface and the code are in Spanish, and that is
> a product decision rather than an oversight: this is a German reader *for
> Spanish speakers*. The dictionary layer pulls the **Spanish** glosses out of
> the German Wiktionary, sense by sense. An English interface would be
> promising something the app doesn't do.

## The idea

The real problem with reading German isn't not knowing a word: it's not knowing
**which** of its meanings applies, and having the verb split into two pieces
half a sentence apart. This app goes after those two things.

## What's in it

Five screens: **news** (filtered by your topics and keywords), **reading**,
**saved**, **words** and **review**.

- Words you save stay **highlighted like with a marker** in everything you read
  afterwards. The ones you already know lose the color and leave only a trace.
- You can **save articles** with the bookmark at the top right. The whole text
  is stored, so reopening is instant (0.14s against several seconds to fetch it
  again) and the article stays even after the newspaper takes it down.
- **Filter by tense**: news lives in present, Perfekt and Präteritum. The filter
  finds the pieces carrying Konjunktiv, Passiv, Futur or Plusquamperfekt, the
  ones you almost never get to practise. An article is tagged only when it
  brings one of those; marking the everyday three would say nothing.

The interface talks in icons and uses words only where they're needed. Nothing
is set in all caps.

**Light/dark theme** from the switch at the top right. Your choice is remembered
and beats the system; if you never chose, it follows the system.

## Installing it on an iPhone

Open it in **Safari** (not Chrome: no other browser on iOS offers this) →
share button → **Add to Home Screen**.

It behaves like an app: its own icon, the name "lesen", full screen, no browser
chrome. After that you get in by tapping the icon instead of typing an address.

For it to work, the Mac has to be awake with `run.sh` running.

## When it looks dead from the phone

Almost always **the server didn't crash: the Mac went to sleep**. On battery
this Mac suspends after a minute idle (`pmset -g custom` → `sleep 1`); plugged
in it never sleeps (`sleep 0`). Asleep, Tailscale can't reach it and the app
looks dead from the phone even though everything is fine on the Mac.

Before touching anything, check whether the server is alive:

```bash
lsof -nP -iTCP:8777 -sTCP:LISTEN && curl -s localhost:8777/api/health
```

Three ways to stop it happening again, from least to most:

1. **Keep the Mac plugged in** when you plan to read from the phone. Simplest.
2. **`./run.sh --despierta`** — keeps it awake while the app runs, and only
   while it runs. Costs battery.
3. **Install it as a service**, so it starts at login and comes back on its own
   if it falls over:

   ```bash
   cp "com.lesen.server.plist" ~/Library/LaunchAgents/
   launchctl load ~/Library/LaunchAgents/com.lesen.server.plist
   ```

   The plist ships as a template — replace `/RUTA/A/lesen` with wherever the
   folder actually lives before copying it. To remove:
   `launchctl unload ~/Library/LaunchAgents/com.lesen.server.plist` and delete
   the file. This covers reboots and crashes, but **not** the Mac sleeping:
   asleep, nothing runs.

## How it's put together

Three layers, each doing what it's actually good at:

| Layer | Tool | What it handles |
|---|---|---|
| Grammar | spaCy `de_core_news_sm` | lemma, part of speech, gender, and rebuilding separables |
| Dictionary | German Wiktionary | senses with Spanish glosses, verb forms, real examples |
| Meaning | Ollama · gemma4:12b | which sense applies **in this sentence** |

The split isn't arbitrary, it came out of measuring. Testing gemma on separable
verbs: it gets the contextual meaning right (it tells *"hat die Produktion
eingestellt"* = halted from *"hat Mitarbeiter eingestellt"* = hired), but it
gets the grammar wrong — it went as far as claiming `einstellen` isn't separable
and inventing an `in-` prefix. spaCy gets 100% of those same cases right.

So **the model is never asked about grammar**, and when there's a dictionary
entry it's asked to *choose* among the existing senses rather than write a new
one.

### Separable verbs

Two detection paths:

1. **Detached particle** — `steht … auf`. spaCy marks it with the `svp` relation
   and points at the verb; `aufstehen` gets rebuilt.
2. **Attached particle** — `eingestellt`, `aufzustehen`, or the verb at the end
   of a subordinate clause. The lemma already arrives whole and is only split
   for display.

Both paths produce **false positives**, so everything is checked against the
dictionary before it's shown:

- `geeinigt` → splitting by prefix gives `ein` + `igen`, but `igen` isn't a verb.
  `einigen` is **not** separable. Discarded.
- `liegt … hoch` → spaCy marks `hoch` as a particle and invents `hochliegen`,
  which doesn't exist. Discarded, and it falls back to `liegen`.

The rule: if the particle is detached, the rebuilt verb has to exist; if it's
attached, what has to exist is the stem without the prefix.

### Generated examples get validated

The model writes things like *"Der Erfolg hängt von dem Wetter **abhängen**"* —
it conjugates the stem and then leaves the infinitive dangling at the end. In an
app that teaches separables that is poison. `german.check_example()` parses every
generated example and throws it out if it has that shape. Wiktionary examples go
first because they're correct by definition.

### Tenses

`german.tense_profile()` reads them off spaCy's morphology. Compound tenses are
built from auxiliary + non-finite form, so those get resolved first and the
auxiliary is marked as consumed: otherwise a Perfekt would also count as present
because of the "hat". It tells Futur (`werden` + infinitive) from passive
(`werden` + participle), and Konjunktiv I from II by the verb's tense.

In the list the profile is computed over headline + standfirst, not the whole
article: it's a sample, but it costs half a second for 40 articles. Opening the
article recomputes it over the full text.

## Files

```
backend/
  german.py      spaCy, separable prefixes, position rules, tenses,
                 example validator
  dictionary.py  German Wiktionary -> Spanish, sense by sense; separable check
  llm.py         Ollama; sense choice constrained to the dictionary
  news.py        feeds (all verified) + extraction with trafilatura
  store.py       SQLite: vocabulary, saved articles, spaced review (Leitner)
  app.py         FastAPI
web/             frontend with no dependencies
data/lesen.db    your words — not in this repo
```

## Things that cost time if you don't know them

- **Wikimedia returns 403** if the `User-Agent` isn't descriptive and doesn't
  carry a contact link. On top of that HTTP headers don't take accents: a
  `User-Agent` containing the word "alemán" throws `UnicodeEncodeError`.
- **Wiktionary only understands lemmas.** `aufstehen` yes, `steht` no. Which is
  why lemmatization has to happen before any lookup.
- **DWDS doesn't lemmatize either** — inflected forms (`steht`, `Häuser`,
  `wurde`) come back empty, so it can't replace spaCy.
- DW's per-topic feeds and the nachrichtenleicht ones I tried return 404. The
  nine left in `news.py` are all verified.
- Inline SVGs inherit the container's font size. Inside the reader, which uses
  large type, an icon without a fixed `width` blows up to hundreds of pixels.
  Every context showing icons needs its own size rule.

## Review

Plain Leitner: 0 → 1 → 3 → 7 → 16 → 35 → 90 days. A hit moves the word up a
step, a miss sends it back to the start. At the top it becomes "known".

## Privacy

Everything runs on your machine: the model is your local Ollama, and your words
and saved articles live in a SQLite file (`data/`) that is **not** in this repo.
The server has no login of its own, so keep it on localhost and your tailnet —
don't expose port 8777 to the open internet.
