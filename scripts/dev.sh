#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKEND_DIR="${ROOT_DIR}/backend"

PYTHON_VERSION="${BACKEND_PYTHON_VERSION:-3.13}"
HOST="${BACKEND_HOST:-127.0.0.1}"
PORT="${BACKEND_PORT:-8000}"

if [[ ! -d "${BACKEND_DIR}" ]]; then
  echo "backend directory not found: ${BACKEND_DIR}" >&2
  exit 1
fi

if [[ ! -f "${BACKEND_DIR}/.env" && -f "${BACKEND_DIR}/.env.example" ]]; then
  cp "${BACKEND_DIR}/.env.example" "${BACKEND_DIR}/.env"
  echo "created ${BACKEND_DIR}/.env from .env.example"
fi

cd "${BACKEND_DIR}"

echo "syncing backend dependencies with Python ${PYTHON_VERSION}"
uv sync --python "${PYTHON_VERSION}"

echo "starting backend server on http://${HOST}:${PORT}"
exec uv run uvicorn main:app --reload --host "${HOST}" --port "${PORT}" "$@"
