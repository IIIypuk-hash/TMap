#!/usr/bin/env bash
# Выполняется при каждом старте Codespace (включая возобновление после
# паузы): поднимает бэкенд и статику служебного модуля в фоне.
# --host 0.0.0.0 обязателен — иначе Codespaces не сможет пробросить порт.
set -e
cd "$(dirname "$0")/.."

pkill -f "uvicorn app.main:app" 2>/dev/null || true
pkill -f "http.server 8642" 2>/dev/null || true

cd backend
nohup python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > /tmp/tmap-backend.log 2>&1 &
cd ../ops
nohup python -m http.server 8642 --bind 0.0.0.0 > /tmp/tmap-ops.log 2>&1 &

echo "TMap backend (8000) и служебный модуль (8642) запущены в фоне."
echo "Логи: /tmp/tmap-backend.log, /tmp/tmap-ops.log"
