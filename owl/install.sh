#!/usr/bin/env bash
# Plug and play: after this, Uino starts by itself every time the board gets power.
#
#   bash owl/install.sh            # on the board, from the repository folder
#   bash owl/install.sh --remove   # undo
#
# Needs a board already set up with steps 0-12 of docs/SETUP_GUIDE.md (llama.cpp, the two model services,
# data/index.db). No sudo: the web page starts from the arduino user's crontab, and the LED eyes are an
# App Lab app set as the board's default app.
set -euo pipefail
cd "$(dirname "$0")/.."
REPO="$(pwd)"
APP=uino-eyes
APP_DIR="$HOME/ArduinoApps/$APP"

if [ "${1:-}" = "--remove" ]; then
  (crontab -l 2>/dev/null | grep -v "owl/start.sh" || true) | crontab -
  arduino-app-cli app stop "user:$APP" >/dev/null 2>&1 || true
  echo "Removed: Uino no longer starts at boot. ($APP_DIR is still there.)"
  exit 0
fi

set -a; . ./config.env; set +a
say() { printf '\n== %s\n' "$*"; }

say "1/4 Checking the board"
for port in "$LLM_PORT" "$EMBED_PORT"; do
  curl -sf "http://127.0.0.1:$port/health" >/dev/null || { echo "No model server on port $port. Do steps 0-12 of docs/SETUP_GUIDE.md first."; exit 1; }
done
MODELS="${MODELS_DIR/#\~/$HOME}"
if [ -f "$MODELS/$MATH_MODEL_FILE" ]; then echo "Maths model: $MATH_MODEL_FILE"
else echo "Maths model not in $MODELS: Reason will answer with the 0.8B model (see machine/NOTES_MATH.md)."; fi
[ -f data/index.db ] || { echo "data/index.db is missing: run python3 build_index.py first."; exit 1; }

say "2/4 The problem bank for Teach"
[ -f data/teach.db ] && echo "data/teach.db is there" || python3 coach/build_bank.py

say "3/4 The eyes (App Lab app '$APP', the board's default app)"
if command -v arduino-app-cli >/dev/null; then
  [ -d "$APP_DIR" ] || arduino-app-cli app new "$APP" -b arduino:web_ui >/dev/null
  cp -r coach/applab/python coach/applab/sketch coach/applab/assets "$APP_DIR/"
  sed "s/^name: .*/name: $APP/" coach/applab/app.yaml > "$APP_DIR/app.yaml"
  arduino-app-cli properties set default "user:$APP"
  arduino-app-cli app start "user:$APP" || echo "The eyes did not start now: see 'arduino-app-cli app logs $APP_DIR'. The page works without them."
else
  echo "arduino-app-cli not found: skipping the eyes."
fi

say "4/4 The web page, at every boot"
chmod +x owl/start.sh
( (crontab -l 2>/dev/null | grep -v "owl/start.sh" || true); echo "@reboot $REPO/owl/start.sh" ) | crontab -
if ! curl -sf "http://127.0.0.1:${OWL_PORT:-8000}/" >/dev/null; then
  nohup setsid "$REPO/owl/start.sh" >/dev/null 2>&1 < /dev/null &
  for _ in $(seq 60); do curl -sf "http://127.0.0.1:${OWL_PORT:-8000}/" >/dev/null && break; sleep 1; done
fi
IP="$(hostname -I | tr ' ' '\n' | grep -v '^172\.' | head -1)"
echo
echo "Done. Uino is at http://${IP:-<board-ip>}:${OWL_PORT:-8000} (same network),"
echo "or over USB: adb forward tcp:8000 tcp:${OWL_PORT:-8000}, then http://127.0.0.1:8000"
echo "Unplug it, plug it in again, and it comes back by itself in about a minute."
