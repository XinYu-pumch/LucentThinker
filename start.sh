#!/bin/zsh
set -e
cd -P -- "$(dirname "$0")"
export UV_CACHE_DIR="$PWD/.cache/uv"
export UV_PYTHON_INSTALL_DIR="$PWD/.runtime/python"
export PYTHONPYCACHEPREFIX="$PWD/.cache/pycache"
export TIKTOKEN_CACHE_DIR="$PWD/.cache/tiktoken"
export TMPDIR="$PWD/.cache/tmp"
mkdir -p "$TMPDIR"
if [[ ! -x .venv/bin/python ]]; then
  echo '首次启动：安装项目内 Python 和依赖…'
  uv python install 3.12
  uv sync --frozen --python 3.12
fi
PORT_VALUE=$(.venv/bin/python -c 'from dotenv import dotenv_values; print(dotenv_values(".env").get("PORT") or "8765")')
exec "$PWD/.venv/bin/python" "$PWD/scripts/launch.py" --port "$PORT_VALUE" "$@"
