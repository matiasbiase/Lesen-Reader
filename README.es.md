# lesen

Leer noticias en alemán tocando las palabras que no conocés. Se guardan solas
en una carpeta y después las repasás.

*[Read me in English](README.md)*

```bash
./run.sh
```

- En la Mac: <http://localhost:8777>
- En el celu: por [Tailscale](https://tailscale.com), solo dentro de tu tailnet.
  Poné tu dirección (`https://TU-MAQUINA.TU-TAILNET.ts.net:8443`) en un
  archivo `direccion.txt` al lado de `run.sh` y la vas a ver al arrancar.

Necesita Ollama corriendo con `gemma4:12b`. Sin Ollama la app anda igual, pero
sin el análisis en contexto: te muestra todas las acepciones y elegís vos.

## La idea

El problema real de leer alemán no es no saber una palabra: es no saber **cuál**
de sus significados aplica, y que el verbo esté partido en dos pedazos separados
por media oración. Esta app ataca esas dos cosas.

## Qué hay

Cinco pantallas: **Noticias** (filtradas por tus temas y palabras clave),
**Leyendo**, **Guardadas**, **Palabras** y **Repaso**.

- Las palabras que guardás quedan **resaltadas con fibrón** en todo lo que leas
  después. Las que ya sabés pierden el color y queda solo un rastro.
- Podés **guardar notas** con el marcador de arriba a la derecha. Se guarda el
  texto entero, así que volver a abrirlas es instantáneo (0,14s contra varios
  segundos de volver a bajarlas) y siguen estando aunque el diario las baje.
- **Filtro por tiempo verbal**: las noticias viven en presente, Perfekt y
  Präteritum. El filtro te deja buscar las que traen Konjunktiv, Passiv, Futur
  o Plusquamperfekt, que son los que casi no se practican. Cada nota muestra
  una etiqueta solo cuando trae alguno de esos; marcar los tres de siempre no
  aportaría nada.

La interfaz comunica con íconos y usa palabras solo cuando hacen falta. Nada
va en mayúsculas.

**Tema claro/oscuro** con el interruptor de arriba a la derecha. Tu elección
queda guardada y le gana al sistema; si nunca elegiste, sigue al sistema.

## Instalarla en el iPhone

Abrila en **Safari** (no Chrome: el resto de los navegadores en iOS no ofrecen
esta opción) → botón de compartir → **Añadir a pantalla de inicio**.

Queda como app: ícono propio, nombre "lesen", pantalla completa y sin barra de
navegador. Después entrás tocando el ícono y no volvés a escribir la dirección.

Para que ande, la Mac tiene que estar despierta y `run.sh` corriendo.

## Si desde el celu parece que se cayó

Casi siempre **no se cayó el servidor: se durmió la Mac**. Con batería esta Mac
se suspende al minuto de inactividad (`pmset -g custom` → `sleep 1`);
enchufada no se duerme nunca (`sleep 0`). Dormida, Tailscale no llega y la app
se ve muerta desde el teléfono aunque en la Mac esté todo bien.

Antes de tocar nada, mirá si el servidor está vivo:

```bash
lsof -nP -iTCP:8777 -sTCP:LISTEN && curl -s localhost:8777/api/health
```

Tres formas de que no vuelva a pasar, de menos a más:

1. **Tené la Mac enchufada** cuando vayas a leer del celu. Es lo más simple.
2. **`./run.sh --despierta`** — impide que se duerma mientras la app corre, y
   solo mientras corre. Gasta más batería.
3. **Instalarla como servicio**, para que arranque sola al iniciar sesión y se
   levante sola si se cae:

   ```bash
   cp "com.lesen.server.plist" ~/Library/LaunchAgents/
   launchctl load ~/Library/LaunchAgents/com.lesen.server.plist
   ```

   Para sacarlo: `launchctl unload ~/Library/LaunchAgents/com.lesen.server.plist`
   y borrar el archivo. Esto resuelve reinicios y caídas, pero **no** resuelve
   que la Mac se duerma: dormida no corre nada.

## Cómo está armado

Tres capas, cada una haciendo lo que sabe hacer:

| Capa | Herramienta | De qué se ocupa |
|---|---|---|
| Gramática | spaCy `de_core_news_sm` | lema, categoría, género, y reconstruir separables |
| Diccionario | Wiktionary alemán | acepciones con traducción al español, formas del verbo, ejemplos reales |
| Sentido | Ollama · gemma4:12b | cuál acepción aplica **en esta frase** |

El reparto no es arbitrario, salió de medirlo. Probando gemma con verbos
separables: acierta el significado en contexto (distingue *"hat die Produktion
eingestellt"* = suspender de *"hat Mitarbeiter eingestellt"* = contratar), pero
se equivoca en la gramática — llegó a decir que `einstellen` no es separable y a
inventar un prefijo `in-`. spaCy acierta el 100% de esos mismos casos.

Por eso **al modelo nunca se le pregunta gramática**, y cuando hay entrada de
diccionario se le pide que *elija* entre las acepciones existentes en vez de
escribir una nueva.

### Los separables

Dos vías de detección:

1. **Partícula suelta** — `steht … auf`. spaCy la marca con la relación `svp`
   y apunta al verbo; se reconstruye `aufstehen`.
2. **Partícula pegada** — `eingestellt`, `aufzustehen`, o el verbo al final de
   una subordinada. El lema ya viene entero y solo se parte para mostrarlo.

Las dos vías dan **falsos positivos**, así que todo se verifica contra el
diccionario antes de mostrarse:

- `geeinigt` → partir por prefijo da `ein` + `igen`, pero `igen` no es un verbo.
  `einigen` **no** es separable. Descartado.
- `liegt … hoch` → spaCy marca `hoch` como partícula e inventa `hochliegen`,
  que no existe. Descartado, y se cae a `liegen`.

Regla: si la partícula está suelta, el verbo reconstruido tiene que existir; si
está pegada, el que tiene que existir es la raíz sin prefijo.

### Los ejemplos generados se validan

El modelo escribe cosas como *"Der Erfolg hängt von dem Wetter **abhängen**"* —
conjuga la raíz y encima deja el infinitivo colgado al final. En una app que
enseña separables eso es veneno. `german.check_example()` parsea cada ejemplo
generado y lo descarta si tiene esa forma. Los ejemplos de Wiktionary van
primero porque son correctos por definición.

### Los tiempos verbales

`german.tense_profile()` los saca de la morfología de spaCy. Los compuestos se
arman con auxiliar + forma no finita, así que primero se resuelven esos y el
auxiliar se marca como consumido: si no, un Perfekt contaría además como
presente por culpa del "hat". Distingue Futur (`werden` + infinitivo) de pasiva
(`werden` + participio), y Konjunktiv I de II por el tiempo del verbo.

En el listado el perfil se calcula sobre titular + copete, no sobre la nota
entera: es una muestra, pero cuesta medio segundo para 40 notas. Al abrir el
artículo se recalcula sobre el texto completo.

## Archivos

```
backend/
  german.py      spaCy, prefijos separables, reglas de posición, tiempos verbales,
                 validador de ejemplos
  dictionary.py  Wiktionary alemán -> español por acepción, verificación de separables
  llm.py         Ollama; elección de acepción acotada al diccionario
  news.py        feeds (todos verificados) + extracción con trafilatura
  store.py       SQLite: vocabulario, notas guardadas, repaso espaciado (Leitner)
  app.py         FastAPI
web/             frontend sin dependencias
data/lesen.db    tus palabras
```

## Detalles que cuestan tiempo si no se saben

- **Wikimedia devuelve 403** si el `User-Agent` no es descriptivo y no lleva un
  enlace de contacto. Además las cabeceras HTTP no aceptan acentos: un
  `User-Agent` con la palabra "alemán" tira `UnicodeEncodeError`.
- **Wiktionary solo entiende lemas.** `aufstehen` sí, `steht` no. Por eso la
  lematización tiene que pasar antes que cualquier búsqueda.
- **DWDS tampoco lematiza** formas conjugadas (`steht`, `Häuser`, `wurde` →
  vacío), así que no sirve para reemplazar a spaCy.
- Los feeds de DW por tema y los de nachrichtenleicht que probé dan 404. Los
  nueve que quedaron en `news.py` están todos verificados.
- Los SVG inline heredan el tamaño de fuente del contenedor. Dentro del lector,
  que usa cuerpos grandes, un ícono sin `width` fijo se dispara a cientos de
  píxeles. Cada contexto que muestre íconos necesita su propia regla de tamaño.

## Repaso

Leitner simple: 0 → 1 → 3 → 7 → 16 → 35 → 90 días. Acierto sube un escalón,
error vuelve al principio. Al llegar arriba la palabra pasa a "sabida".
