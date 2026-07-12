#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

BACKEND_PORT="${BACKEND_PORT:-8790}"
FRONTEND_PORT="${FRONTEND_PORT:-3790}"
MODE="${1:-dev}"

PY="$SCRIPT_DIR/miniapp_demo/.venv/bin/python"
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

if [[ "$MODE" == "prod" ]]; then
    # ---- Production: build frontend, backend serves everything ----
    DIST_DIR="$SCRIPT_DIR/miniapp_demo/frontend/dist"
    if [[ ! -f "$DIST_DIR/index.html" ]]; then
        echo "[run] building frontend..."
        cd "$SCRIPT_DIR/miniapp_demo/frontend"
        npx vite build
    fi

    echo "[run] starting server on :$BACKEND_PORT (production)"
    cd "$SCRIPT_DIR"
    "$PY" -m uvicorn miniapp_demo.backend.main:app \
        --host 0.0.0.0 --port "$BACKEND_PORT" &
    BACK_PID=$!

    echo ""
    echo "=========================================="
    echo "  MiniApp Demo is running! (production)"
    echo ""
    echo "  URL:  http://localhost:$BACKEND_PORT"
    echo ""
    echo "  Press Ctrl+C to stop"
    echo "=========================================="
    wait
else
    # ---- Dev: backend + Vite dev server ----
    echo "[run] starting backend on :$BACKEND_PORT"
    cd "$SCRIPT_DIR"
    "$PY" -m uvicorn miniapp_demo.backend.main:app \
        --host 0.0.0.0 --port "$BACKEND_PORT" &
    BACK_PID=$!

    echo "[run] starting frontend on :$FRONTEND_PORT"
    cd "$SCRIPT_DIR/miniapp_demo/frontend"
    export FRONTEND_PORT
    npx vite &
    FRONT_PID=$!

    echo ""
    echo "=========================================="
    echo "  MiniApp Demo is running! (dev)"
    echo ""
    echo "  Frontend:  http://localhost:$FRONTEND_PORT"
    echo "  Backend:   http://localhost:$BACKEND_PORT"
    echo ""
    echo "  Press Ctrl+C to stop"
    echo "=========================================="
    wait
fi
