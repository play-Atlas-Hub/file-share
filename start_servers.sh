#!/bin/bash

# TANK GAME - Server Startup Script
# Starts both the login server and game server

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
echo "Tank Game - Server Startup"
echo "=========================================="
echo ""

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "⚠ WARNING: .env file not found!"
    echo "  Please copy .env.example to .env and configure it."
    echo "  The server will run with default settings."
    echo ""
fi

# Check required config files
if [ ! -f "server/configs.json" ]; then
    echo "ERROR: server/configs.json not found!"
    exit 1
fi

if [ ! -f "server/msg.json" ]; then
    echo "ERROR: server/msg.json not found!"
    exit 1
fi

echo "Starting Tank Game Servers..."
echo ""
echo "Server Configuration:"
echo "  - Config file: server/configs.json"
echo "  - Environment: Production (default)"
echo ""
echo "Press Ctrl+C to stop the servers"
echo ""
echo "=========================================="
echo ""

# Start the main server
cd "$PROJECT_DIR/server"
python server_complete.py
