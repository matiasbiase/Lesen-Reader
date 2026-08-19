#!/bin/bash
# Starts lesen.
#
#   ./run.sh              normal
#   ./run.sh --despierta  also keeps the Mac awake while it runs
#
# From the phone you get in over Tailscale. Your address is yours and doesn't go
# in the repo: put it in `address.txt` (it's in .gitignore) and it gets printed
# on startup.
#
# CAREFUL: on battery a Mac suspends after a minute idle, and asleep there is no
# server to speak of. To read from the phone, keep it plugged in (plugged in it
# never sleeps) or use --despierta.
cd "$(dirname "$0")"

if ! curl -s -m 3 http://localhost:11434/api/tags > /dev/null; then
  echo "⚠️  Ollama is not answering. Open it, or run:  ollama serve"
  echo "    (the app still works, just without the in-context analysis)"
  echo
fi

# If the port was left taken by an earlier run, free it.
if lsof -ti:8777 > /dev/null 2>&1; then
  echo "· freeing port 8777"
  lsof -ti:8777 | xargs kill 2>/dev/null
  sleep 1
fi

PREFIX=()
if [ "$1" = "--despierta" ]; then
  # -i blocks idle sleep; -m stops the disks spinning down.
  # Only while the server runs: kill it and the Mac goes back to normal.
  PREFIX=(caffeinate -i -m)
  echo "· the Mac will not sleep while this runs (costs battery)"
fi

echo "→ http://localhost:8777"
if [ -f address.txt ]; then
  echo "→ $(cat address.txt)  (from the phone, over Tailscale)"
else
  echo "→ (to get in from the phone over Tailscale, see the README)"
fi
echo
exec "${PREFIX[@]}" ./.venv/bin/python -m uvicorn app:app \
  --app-dir backend --host 0.0.0.0 --port 8777
