#!/bin/bash
# ==============================================================================
# Local Development Startup Script
# ==============================================================================
# This script automates the startup of both backend (Python/FastAPI) and 
# frontend (React/Vite) development servers for local development.
#
# Prerequisites:
#   - Python 3.8+ installed
#   - Node.js 16+ and npm installed
#   - PostgreSQL database running (connection string in .env)
#
# Usage:
#   ./local-auto-start.sh              # Start both backend and frontend
#   ./local-auto-start.sh --backend-only   # Start only backend
#   ./local-auto-start.sh --frontend-only  # Start only frontend
#   ./local-auto-start.sh --no-open        # Don't open browser automatically
#   ./local-auto-start.sh --skip-install   # Skip dependency installation
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

NO_OPEN=0
SKIP_INSTALL=0
SKIP_PRISMA=0
BACKEND_ONLY=0
FRONTEND_ONLY=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-open) NO_OPEN=1; shift ;;
    --skip-install) SKIP_INSTALL=1; shift ;;
    --skip-prisma) SKIP_PRISMA=1; shift ;;
    --backend-only) BACKEND_ONLY=1; shift ;;
    --frontend-only) FRONTEND_ONLY=1; shift ;;
    *) echo "Unknown option: $1" ; exit 1 ;;
  esac
done

if [[ $BACKEND_ONLY -eq 1 && $FRONTEND_ONLY -eq 1 ]]; then
  echo "Cannot use --backend-only and --frontend-only together"
  exit 1
fi

ensure_backend_deps() {
  # Check if Python 3 is available
  if ! command -v python3 &> /dev/null; then
    echo "❌ Error: python3 not found. Please install Python 3.8 or higher."
    exit 1
  fi
  
  # Create virtual environment if it doesn't exist
  if [[ $SKIP_INSTALL -eq 0 && ! -d ai-core/.venv ]]; then
    echo "📦 Creating Python virtual environment and installing backend dependencies..."
    (cd ai-core && python3 -m venv .venv && .venv/bin/pip install --upgrade pip && .venv/bin/pip install -e .)
  fi
  
  # Generate Prisma client for Python
  if [[ $SKIP_PRISMA -eq 0 && -d prisma ]]; then
    echo "🔧 Generating Prisma client for Python..."
    (cd ai-core && .venv/bin/prisma generate)
  fi
}

ensure_frontend_deps() {
  # Check if Node.js and npm are available
  if ! command -v node &> /dev/null; then
    echo "❌ Error: node not found. Please install Node.js 16 or higher."
    exit 1
  fi
  
  if ! command -v npm &> /dev/null; then
    echo "❌ Error: npm not found. Please install npm."
    exit 1
  fi
  
  # Install frontend dependencies
  if [[ $SKIP_INSTALL -eq 0 && ! -d client/node_modules ]]; then
    echo "📦 Installing frontend dependencies..."
    (cd client && npm install)
  fi
}

BACK_PID=""
FRONT_PID=""

kill_existing_processes() {
  echo "Checking for existing processes on ports 8000 and 5173..."
  
  # Kill processes on port 8000 (backend)
  PIDS_8000=$(lsof -ti:8000 2>/dev/null || true)
  if [[ -n "$PIDS_8000" ]]; then
    echo "Killing existing backend process(es) on port 8000: $PIDS_8000"
    echo "$PIDS_8000" | xargs kill -9 2>/dev/null || true
    sleep 1
  fi
  
  # Kill processes on port 5173 (frontend)
  PIDS_5173=$(lsof -ti:5173 2>/dev/null || true)
  if [[ -n "$PIDS_5173" ]]; then
    echo "Killing existing frontend process(es) on port 5173: $PIDS_5173"
    echo "$PIDS_5173" | xargs kill -9 2>/dev/null || true
    sleep 1
  fi
  
  if [[ -z "$PIDS_8000" && -z "$PIDS_5173" ]]; then
    echo "No existing processes found on ports 8000 or 5173."
  fi
}

start_backend() {
  echo "🚀 Starting Python backend (Uvicorn) on http://localhost:8000..."
  (cd ai-core && .venv/bin/uvicorn src.main:app_sio --host 0.0.0.0 --port 8000 --reload) &
  BACK_PID=$!
  echo "   Backend PID: $BACK_PID"
}

start_frontend() {
  echo "🚀 Starting frontend (Vite) on http://localhost:5173..."
  (cd client && npm run start) &
  FRONT_PID=$!
  echo "   Frontend PID: $FRONT_PID"
}

cleanup() {
  echo ""
  echo "🛑 Shutting down servers..."
  if [[ -n "$BACK_PID" ]] && kill -0 "$BACK_PID" 2>/dev/null; then
    echo "   Stopping backend (PID: $BACK_PID)..."
    kill -TERM "$BACK_PID" 2>/dev/null || true
  fi
  if [[ -n "$FRONT_PID" ]] && kill -0 "$FRONT_PID" 2>/dev/null; then
    echo "   Stopping frontend (PID: $FRONT_PID)..."
    kill -TERM "$FRONT_PID" 2>/dev/null || true
  fi
  wait 2>/dev/null || true
  echo "✅ Shutdown complete"
}

trap cleanup EXIT INT TERM

if [[ $FRONTEND_ONLY -eq 0 ]]; then
  ensure_backend_deps
fi
if [[ $BACKEND_ONLY -eq 0 ]]; then
  ensure_frontend_deps
fi

# Kill any existing processes before starting
kill_existing_processes

if [[ $BACKEND_ONLY -eq 1 ]]; then
  start_backend
  wait "$BACK_PID"
  exit $?
fi

if [[ $FRONTEND_ONLY -eq 1 ]]; then
  start_frontend
  if [[ $NO_OPEN -eq 0 ]]; then
    (sleep 5 && open "http://localhost:5173") >/dev/null 2>&1 &
  fi
  wait "$FRONT_PID"
  exit $?
fi

start_backend
echo "⏳ Waiting for backend readiness at http://localhost:8000/readiness ..."
ATTEMPTS=0
until curl -fsS http://localhost:8000/readiness >/dev/null 2>&1; do
  ATTEMPTS=$((ATTEMPTS+1))
  if [[ $ATTEMPTS -ge 120 ]]; then
    echo "⚠️  Backend readiness not ready after 120s; proceeding to start frontend."
    break
  fi
  sleep 1
done
echo "✅ Backend is ready!"
start_frontend

if [[ -f .env ]]; then
  FRONTENV=$(grep -E '^FRONTEND_URL=' .env | head -n1 | cut -d '=' -f2- | tr -d '"')
  if [[ -n "$FRONTENV" && "$FRONTENV" != *"localhost:5173"* ]]; then
    echo "Warning: .env FRONTEND_URL=$FRONTENV (for local dev, usually http://localhost:5173)"
  fi
fi

if [[ $NO_OPEN -eq 0 ]]; then
  (sleep 6 && open "http://localhost:5173") >/dev/null 2>&1 &
fi

echo ""
echo "=========================================="
echo "✨ Development servers are running!"
echo "=========================================="
echo "Backend:  http://localhost:8000"
echo "Frontend: http://localhost:5173"
echo "=========================================="
echo "Press Ctrl+C to stop both servers"
echo ""

while true; do
  BACK_ALIVE=1
  FRONT_ALIVE=1
  if [[ -n "$BACK_PID" ]] && ! kill -0 "$BACK_PID" 2>/dev/null; then
    BACK_ALIVE=0
  fi
  if [[ -n "$FRONT_PID" ]] && ! kill -0 "$FRONT_PID" 2>/dev/null; then
    FRONT_ALIVE=0
  fi

  if [[ $BACK_ALIVE -eq 0 ]]; then
    echo "Backend process exited. Stopping frontend..."
    wait "$BACK_PID" 2>/dev/null || true
    if [[ -n "$FRONT_PID" ]] && kill -0 "$FRONT_PID" 2>/dev/null; then
      kill -TERM "$FRONT_PID" 2>/dev/null || true
      wait "$FRONT_PID" 2>/dev/null || true
    fi
    break
  fi
  if [[ $FRONT_ALIVE -eq 0 ]]; then
    echo "Frontend process exited. Stopping backend..."
    wait "$FRONT_PID" 2>/dev/null || true
    if [[ -n "$BACK_PID" ]] && kill -0 "$BACK_PID" 2>/dev/null; then
      kill -TERM "$BACK_PID" 2>/dev/null || true
      wait "$BACK_PID" 2>/dev/null || true
    fi
    break
  fi
  sleep 2
done

echo "Stopped."
