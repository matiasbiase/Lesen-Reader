#!/bin/bash
# Levanta lesen.
#
#   ./run.sh              normal
#   ./run.sh --despierta  además impide que la Mac se duerma mientras corre
#
# Desde el celu entrás por Tailscale. Tu dirección es tuya y no va al repo:
# ponela en `direccion.txt` (está en .gitignore) y se muestra al arrancar.
#
# OJO: con batería esta Mac se suspende al minuto de inactividad, y dormida
# no hay servidor que valga. Para leer desde el teléfono, tenela enchufada
# (enchufada no se duerme) o usá --despierta.
cd "$(dirname "$0")"

if ! curl -s -m 3 http://localhost:11434/api/tags > /dev/null; then
  echo "⚠️  Ollama no responde. Abrilo o corré:  ollama serve"
  echo "    (la app funciona igual, pero sin el análisis en contexto)"
  echo
fi

# Si el puerto quedó tomado de una corrida anterior, lo libero.
if lsof -ti:8777 > /dev/null 2>&1; then
  echo "· liberando el puerto 8777"
  lsof -ti:8777 | xargs kill 2>/dev/null
  sleep 1
fi

PREFIJO=()
if [ "$1" = "--despierta" ]; then
  # -i impide la suspensión por inactividad; -m que se duerman los discos.
  # Solo mientras el servidor corre: al cortarlo, la Mac vuelve a lo de antes.
  PREFIJO=(caffeinate -i -m)
  echo "· la Mac no se va a dormir mientras esto corra (gasta más batería)"
fi

echo "→ http://localhost:8777"
if [ -f direccion.txt ]; then
  echo "→ $(cat direccion.txt)  (desde el celu, por Tailscale)"
else
  echo "→ (para entrar desde el celu por Tailscale, ver el README)"
fi
echo
exec "${PREFIJO[@]}" ./.venv/bin/python -m uvicorn app:app \
  --app-dir backend --host 0.0.0.0 --port 8777
