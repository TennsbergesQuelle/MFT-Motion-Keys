#!/usr/bin/env bash
set -euo pipefail

app_dir="$(cd -- "$(dirname -- "$0")" && pwd -P)"
cd -- "$app_dir"

if ! command -v python3 >/dev/null 2>&1; then
    echo "Python 3 wurde nicht gefunden. Bitte Python 3 installieren." >&2
    exit 1
fi

if [[ ! -x "$app_dir/.venv/bin/python" ]]; then
    python3 -m venv "$app_dir/.venv"
fi

"$app_dir/.venv/bin/python" -m pip install -r "$app_dir/requirements.txt"
exec "$app_dir/.venv/bin/python" "$app_dir/app.py"
