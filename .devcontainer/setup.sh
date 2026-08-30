#!/usr/bin/env bash
# Выполняется один раз при создании Codespace: ставит зависимости бэкенда
# и готовит .env, если его ещё нет.
set -e
cd "$(dirname "$0")/.."

cd backend
python -m pip install --upgrade pip
pip install -r requirements.txt

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Создан backend/.env из .env.example (AI_STUB_MODE=true — рапорты оформляются без реального ключа Anthropic)."
fi
