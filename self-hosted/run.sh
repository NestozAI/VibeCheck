#!/bin/bash

# VibeCheck run script

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Check .env
if [ ! -f ".env" ]; then
    echo "Error: .env file not found."
    echo "Please run ./setup.sh first."
    exit 1
fi

# Activate virtual environment (venv -> conda -> system order)
if [ -d ".venv" ]; then
    source .venv/bin/activate
elif command -v conda &> /dev/null; then
    eval "$(conda shell.bash hook 2>/dev/null)" && conda activate vibecheck 2>/dev/null || true
fi

echo "Starting VibeCheck..."
python main.py
