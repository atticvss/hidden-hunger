#!/bin/bash
# Validate project health: imports, service tests, and API startup smoke-check.

set -euo pipefail

cd "$(dirname "$0")"

if [ -x ".venv/bin/python3" ]; then
  PYTHON_BIN=".venv/bin/python3"
elif [ -x ".venv/bin/python" ]; then
  PYTHON_BIN=".venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
else
  echo "Error: Python 3 was not found."
  exit 1
fi

echo "Using Python: $PYTHON_BIN"

echo "[1/4] Checking key imports..."
"$PYTHON_BIN" -c "import fastapi, uvicorn, sqlalchemy, numpy, sklearn, joblib; print('Imports OK')"

echo "[2/4] Running storage tests..."
"$PYTHON_BIN" test_storage.py

echo "[3/4] Running services tests..."
"$PYTHON_BIN" test_services.py

HOST="127.0.0.1"
PORT="${VALIDATE_PORT:-8011}"

if command -v lsof >/dev/null 2>&1 && lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Error: validation port $PORT is already in use. Set VALIDATE_PORT to another value."
  exit 1
fi

echo "[4/4] API startup smoke test on $HOST:$PORT ..."
"$PYTHON_BIN" -m uvicorn app.main:app --host "$HOST" --port "$PORT" >/tmp/hidden_hunger_validate_uvicorn.log 2>&1 &
UVICORN_PID=$!
cleanup() {
  kill "$UVICORN_PID" >/dev/null 2>&1 || true
}
trap cleanup EXIT

READY=0
for _ in $(seq 1 20); do
  if "$PYTHON_BIN" -c "import socket; s=socket.socket(); s.settimeout(0.5); ok=(s.connect_ex(('127.0.0.1',$PORT))==0); s.close(); raise SystemExit(0 if ok else 1)"; then
    READY=1
    break
  fi
  sleep 0.5
done

if [ "$READY" -ne 1 ]; then
  echo "Uvicorn did not become ready. See /tmp/hidden_hunger_validate_uvicorn.log"
  exit 1
fi

echo "Validation passed: project is runnable and core checks succeeded."
