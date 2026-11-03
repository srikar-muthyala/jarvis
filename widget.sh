#!/usr/bin/env bash
cd "$(dirname "$0")"

export HF_HUB_DISABLE_XET=1
export HF_HUB_DISABLE_SYMLINKS_WARNING=1

if [ -f .venv/bin/activate ]; then
    source .venv/bin/activate
fi

python3 widget.py "$@"
