#!/bin/bash
# Startet Modellserver + Web-App und öffnet den Browser. Fenster schließt sich danach selbst.
source "$(dirname "$0")/scripts/common.sh"
cd "$ROOT" || exit 1
lade_conf
mkdir -p "$DATA"

if [ ! -x "$ENGINE/build/ace-server" ]; then
  echo "Noch nicht installiert. Bitte zuerst 'Install' starten."
  read -n 1 -s -r -p "Beliebige Taste drücken zum Schließen..."
  exit 1
fi

fehler() {
  echo "$1 Log-Datei ($2):"
  tail -n 30 "$2"
  echo ""
  read -n 1 -s -r -p "Beliebige Taste drücken zum Schließen..."
  exit 1
}

# Zeitstempel der neusten Quelldatei — daran erkennt man veralteten Code.
neuste_quelle() {
  find app static -type f \( -name '*.py' -o -name '*.js' -o -name '*.html' -o -name '*.css' \) \
    -exec stat -f '%m' {} \; 2>/dev/null | sort -rn | head -1
}

# --- Modellserver -----------------------------------------------------------
if [ "$MODE" = "split" ]; then
  if laeuft "$LM_PORT"; then
    echo "Sprachmodell-Server läuft bereits (Port $LM_PORT)."
  else
    echo "Starte Sprachmodell-Server (CPU)..."
    GGML_BACKEND=CPU nohup "$ENGINE/build/ace-server" --host 127.0.0.1 --port "$LM_PORT" \
      --models "$MODELS" --max-batch 1 > "$DATA/ace-lm.log" 2>&1 &
    disown
  fi
fi

if laeuft "$SYNTH_PORT"; then
  echo "Synthese-Server läuft bereits (Port $SYNTH_PORT)."
else
  echo "Starte Synthese-Server (Metal)..."
  nohup "$ENGINE/build/ace-server" --host 127.0.0.1 --port "$SYNTH_PORT" \
    --models "$MODELS" --max-batch 1 > "$DATA/ace-server.log" 2>&1 &
  disown
fi

# --- Web-App ----------------------------------------------------------------
PID=$(lsof -i :"$PORT" -sTCP:LISTEN -t 2>/dev/null | head -1)
if [ -n "$PID" ]; then
  START=$(date -j -f "%a %b %e %T %Y" "$(ps -p "$PID" -o lstart=)" +%s 2>/dev/null)
  NEUSTE=$(neuste_quelle)
  if [ -n "$START" ] && [ -n "$NEUSTE" ] && [ "$NEUSTE" -gt "$START" ]; then
    echo "Der Code ist neuer als die laufende Web-App — Neustart."
    kill $(lsof -i :"$PORT" -sTCP:LISTEN -t) 2>/dev/null
    for _ in $(seq 1 20); do laeuft "$PORT" || break; sleep 0.5; done
    PID=""
  else
    echo "Web-App läuft bereits auf Port $PORT."
  fi
fi
if [ -z "$PID" ]; then
  echo "Starte Web-App..."
  nohup uv run uvicorn app.main:app --host 127.0.0.1 --port "$PORT" > "$DATA/server.log" 2>&1 &
  disown
fi

# --- Warten, bis alles antwortet --------------------------------------------
for _ in $(seq 1 60); do
  laeuft "$PORT" && laeuft "$SYNTH_PORT" && { [ "$MODE" != "split" ] || laeuft "$LM_PORT"; } && break
  sleep 0.5
done
laeuft "$PORT"       || fehler "Web-App ist nicht rechtzeitig gestartet." "$DATA/server.log"
laeuft "$SYNTH_PORT" || fehler "Synthese-Server ist nicht rechtzeitig gestartet." "$DATA/ace-server.log"
if [ "$MODE" = "split" ]; then
  laeuft "$LM_PORT" || fehler "Sprachmodell-Server ist nicht rechtzeitig gestartet." "$DATA/ace-lm.log"
fi
echo "Alle Server laufen."

open "http://localhost:$PORT"
echo ""
echo "Music Generator ist offen unter http://localhost:$PORT"
echo "Zum Beenden: 'Music Generator OFF' verwenden."
fenster_schliessen
exit 0
