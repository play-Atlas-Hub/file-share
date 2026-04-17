#!/bin/bash

# TANK GAME - Client Startup Script
# Starts the Pygame client

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "ERROR: Virtual environment not found. Please run ./install.sh first."
    exit 1
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

echo ""
echo "=========================================="
echo "Tank Game - Client Startup"
echo "=========================================="
echo ""

# Check required config files
if [ ! -f "client/client_configs.json" ]; then
    echo "ERROR: client/client_configs.json not found!"
    exit 1
fi

echo "Starting Tank Game Client..."
echo ""
echo "Client Configuration:"
echo "  - Config file: client/client_configs.json"
echo ""
echo "Press Ctrl+C or close the window to exit"
echo ""
echo "=========================================="
echo ""

# Start the client
cd "$PROJECT_DIR/client"
python client_final.py
