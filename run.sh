#!/usr/bin/env bash
# NOTE: Make this file executable with: chmod +x run.sh

set -e

echo "========================================"
echo "  PDF-to-Obsidian Launcher"
echo "========================================"
echo

# Check if venv exists
if [ ! -d "venv" ] || [ ! -f "venv/bin/activate" ]; then
    echo "[ERROR] Virtual environment not found."
    echo "        Please run 'python setup.py' first to set up the project."
    exit 1
fi

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "[ERROR] .env file not found."
    echo "        Please run 'python setup.py' first to configure your API keys."
    exit 1
fi

# Activate venv and run
echo "Activating virtual environment..."
source venv/bin/activate

echo "Starting application..."
echo
python app.py
