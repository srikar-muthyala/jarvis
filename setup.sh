#!/usr/bin/env bash
set -e

# Change to script directory
cd "$(dirname "$0")"

echo "=== Jarvis AI Assistant Setup (Linux / POSIX) ==="

# Check Python 3
if ! command -v python3 &> /dev/null; then
    echo "[!] Error: python3 is not installed. Please install Python 3.10+ (e.g. sudo apt install python3 python3-venv python3-pip)"
    exit 1
fi

echo "Creating virtual environment..."
python3 -m venv .venv
source .venv/bin/activate

echo "Upgrading pip and installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

if [ ! -f .env ]; then
    echo "Copying .env.example to .env..."
    cp .env.example .env
fi

echo ""
echo "========================================================================"
echo "Setup complete! Open .env to configure your LLM API key and tools."
echo "Then launch Jarvis with: ./run.sh or ./widget.sh"
echo "========================================================================"
