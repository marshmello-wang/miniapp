#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================="
echo "  MiniApp Demo - Install"
echo "=========================================="

# ---- check Python ----
if ! command -v python3 &>/dev/null; then
    echo "[ERROR] python3 not found. Please install Python 3.10+"
    exit 1
fi
PY_VER=$(python3 -c 'import sys; v=sys.version_info; print(f"{v.major}.{v.minor}")')
PY_MINOR=$(python3 -c 'import sys; print(sys.version_info.minor)')
if [ "$PY_MINOR" -lt 10 ]; then
    echo "[ERROR] Python 3.10+ required, got 3.$PY_MINOR"
    exit 1
fi
echo "[ok] Python $PY_VER"

# ---- check Node.js ----
if ! command -v node &>/dev/null; then
    echo "[ERROR] node not found. Please install Node.js 18+"
    exit 1
fi
echo "[ok] Node.js $(node --version)"

# ---- Python venv + deps ----
echo ""
echo "[1/2] Creating Python virtual environment..."
cd "$SCRIPT_DIR/miniapp_demo"
python3 -m venv .venv
source .venv/bin/activate

echo "  Installing Python dependencies..."
pip install --upgrade pip -q
pip install -r backend/requirements.txt -q
pip install httpx jinja2 -q
echo "  done ($(pip list --format=freeze | wc -l | tr -d ' ') packages)"

# ---- Frontend deps ----
echo "[2/2] Installing frontend dependencies..."
cd "$SCRIPT_DIR/miniapp_demo/frontend"
npm install --no-fund --no-audit 2>&1 | tail -1
cd "$SCRIPT_DIR"

echo ""
echo "=========================================="
echo "  Install complete!"
echo ""
echo "  Next steps:"
echo "    1. Edit config:  ~/.miniapp/config.json"
echo "       (set your LLM provider / api_key)"
echo "    2. Start:        ./run.sh"
echo "    3. Open:         http://localhost:3790"
echo "=========================================="
