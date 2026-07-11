#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export FORGE_OS_ROOT="$SCRIPT_DIR/forge_os"

BACKEND_PORT="${BACKEND_PORT:-8790}"
FRONTEND_PORT="${FRONTEND_PORT:-3790}"

PY="$SCRIPT_DIR/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
    echo "[ERROR] Virtual environment not found. Run ./install.sh first."
    exit 1
fi

cleanup() {
    echo ""
    echo "[run] shutting down..."
    [[ -n "${BACK_PID:-}" ]] && kill "$BACK_PID" 2>/dev/null || true
    [[ -n "${FRONT_PID:-}" ]] && kill "$FRONT_PID" 2>/dev/null || true
    wait 2>/dev/null
}
trap cleanup EXIT INT TERM

echo "[run] starting backend on :$BACKEND_PORT"
cd "$SCRIPT_DIR"
"$PY" -m uvicorn miniapp_demo.backend.main:app \
    --host 0.0.0.0 --port "$BACKEND_PORT" &
BACK_PID=$!

echo "[run] starting frontend on :$FRONTEND_PORT"
cd "$SCRIPT_DIR/miniapp_demo/frontend"
npm run dev -- --port "$FRONTEND_PORT" --host &
FRONT_PID=$!

echo ""
echo "=========================================="
echo "  MiniApp Demo is running!"
echo ""
echo "  Frontend:  http://localhost:$FRONTEND_PORT"
echo "  Backend:   http://localhost:$BACKEND_PORT"
echo "  Standalone: http://localhost:$FRONTEND_PORT/app/fortune-teller"
echo ""
echo "  Press Ctrl+C to stop"
echo "=========================================="
wait
