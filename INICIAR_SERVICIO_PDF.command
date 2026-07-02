#!/bin/zsh
cd '/Users/omarconde/Documents/New project/fp2026_publicacion'
PID_FILE="/tmp/fp2026_pdf_service.pid"
LOG_FILE="/tmp/fp2026_pdf_service.log"
PYTHON_BIN='/Users/omarconde/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3'
SERVICE='/Users/omarconde/Documents/New project/fp2026_publicacion/pdf_report_service.py'

if [ -f "$PID_FILE" ]; then
  OLD_PID=$(cat "$PID_FILE" 2>/dev/null)
  if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
    echo "Servicio PDF ya activo en http://127.0.0.1:8765"
    echo "PID: $OLD_PID"
    exit 0
  fi
fi

nohup "$PYTHON_BIN" "$SERVICE" >> "$LOG_FILE" 2>&1 &
NEW_PID=$!
echo "$NEW_PID" > "$PID_FILE"
sleep 1

if kill -0 "$NEW_PID" 2>/dev/null; then
  echo "Servicio PDF iniciado en http://127.0.0.1:8765"
  echo "PID: $NEW_PID"
  echo "Log: $LOG_FILE"
  exit 0
fi

echo "No se pudo iniciar el servicio PDF. Revisá: $LOG_FILE"
exit 1
