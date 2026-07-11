#!/usr/bin/env bash
# 启动小程序框架 Demo:后端(8790) + 前端(3790)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"   # 包含 miniapp_demo 的目录

BACKEND_PORT="${BACKEND_PORT:-8790}"
FRONTEND_PORT="${FRONTEND_PORT:-3790}"

# forge_os 根目录(含 common/ = agent_framework + llm)
export FORGE_OS_ROOT="${FORGE_OS_ROOT:-$(cd "$REPO_ROOT/.." && pwd)/forge_os}"
PY="$SCRIPT_DIR/.venv/bin/python"
[[ -x "$PY" ]] || PY="python3"

cleanup() {
  echo "\n[run] shutting down…"
  [[ -n "${BACK_PID:-}" ]] && kill "$BACK_PID" 2>/dev/null || true
  [[ -n "${FRONT_PID:-}" ]] && kill "$FRONT_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "[run] starting backend on :$BACKEND_PORT"
cd "$REPO_ROOT"
"$PY" -m uvicorn miniapp_demo.backend.main:app --host 0.0.0.0 --port "$BACKEND_PORT" --reload &
BACK_PID=$!

echo "[run] starting frontend on :$FRONTEND_PORT"
cd "$SCRIPT_DIR/frontend"
if [[ ! -d node_modules ]]; then
  echo "[run] installing frontend deps…"
  npm install
fi
npm run dev -- --port "$FRONTEND_PORT" --host &
FRONT_PID=$!

echo "[run] backend:  http://localhost:$BACKEND_PORT"
echo "[run] frontend: http://localhost:$FRONTEND_PORT"
wait
