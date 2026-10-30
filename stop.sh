#!/bin/zsh
set -e
cd -P -- "$(dirname "$0")"
exec "$PWD/.venv/bin/python" "$PWD/scripts/stop_app.py"
