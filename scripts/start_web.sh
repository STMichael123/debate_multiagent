#!/usr/bin/env bash
set -euo pipefail

PORT="${WEB_PORT:-8000}"
HOST="${WEB_HOST:-127.0.0.1}"

echo "Starting Debate Project on ${HOST}:${PORT}..."

exec python -m uvicorn debate_agent.app.web:app \
    --host "$HOST" \
    --port "$PORT" \
    --timeout-graceful-shutdown 10
