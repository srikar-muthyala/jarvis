#!/usr/bin/env bash
cd "$(dirname "$0")"

if [ -f .venv/bin/activate ]; then
    source .venv/bin/activate
fi

python3 setup_google_tasks.py "$@"
