#!/usr/bin/env bash
# Thin wrapper that forwards arguments to the Python automation script
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY_SCRIPT="$SCRIPT_DIR/odoo_project_workflow.py"

if [[ ! -x "$PY_SCRIPT" ]]; then
  echo "[ERROR] Python workflow script not found or not executable: $PY_SCRIPT" >&2
  exit 1
fi

exec "$PY_SCRIPT" "$@"
