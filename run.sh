#!/usr/bin/env bash
set -e

# DepthWizard Quick Launcher
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

echo "=================================================="
echo " Starting DepthWizard (Backend + Frontend)"
echo "=================================================="

# Cleanup background processes on exit
cleanup() {
    echo ""
    echo "Stopping DepthWizard services..."
    if [ -n "$BACKEND_PID" ]; then
        kill "$BACKEND_PID" 2>/dev/null || true
    fi
    if [ -n "$FRONTEND_PID" ]; then
        kill "$FRONTEND_PID" 2>/dev/null || true
    fi
    exit 0
}

trap cleanup SIGINT SIGTERM

# Start Backend API
echo "[1/2] Starting FastAPI Backend on http://127.0.0.1:8000 ..."
source backend/venv/bin/activate
PYTHONPATH=backend uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload &
BACKEND_PID=$!

# Wait briefly for backend to bind port
sleep 2

# Start Frontend Dev Server
echo "[2/2] Starting Vite Frontend on http://localhost:5173 ..."
cd "$ROOT_DIR/frontend"
npm run dev &
FRONTEND_PID=$!

echo ""
echo "=================================================="
echo " DepthWizard is live!"
echo " Web UI:     http://localhost:5173"
echo " API Docs:   http://127.0.0.1:8000/docs"
echo " Health:     http://127.0.0.1:8000/api/health"
echo " Press Ctrl+C to stop all services."
echo "=================================================="

# Wait for processes
wait
