#!/bin/bash
# Run the FastAPI application

set -e

cd "$(dirname "$0")"

# Runtime settings (override with env vars when needed).
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"

# Select python from project venv when available.
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

# Fail early with a clear message when target port is already in use.
if command -v lsof >/dev/null 2>&1 && lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
	echo "Error: port $PORT is already in use."
	echo "Stop the running process or start with another port, e.g. PORT=8001 bash run.sh"
	exit 1
fi

echo "Starting server on http://localhost:$PORT"
exec "$PYTHON_BIN" -m uvicorn app.main:app --reload --host "$HOST" --port "$PORT"
