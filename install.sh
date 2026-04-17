#!/bin/bash
set -e

# TANK GAME - Installation Script
# This script sets up the development environment for the Tank Game project

echo "=========================================="
echo "Tank Game - Installation Script"
echo "=========================================="
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 is not installed. Please install Python 3.9 or higher."
    exit 1
fi

PYTHON_VERSION=$(python3 --version | awk '{print $2}')
echo "✓ Python $PYTHON_VERSION found"
echo ""

# Create virtual environment
echo "Creating virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "✓ Virtual environment created"
else
    echo "✓ Virtual environment already exists"
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate
echo "✓ Virtual environment activated"
echo ""

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip setuptools wheel > /dev/null 2>&1
echo "✓ pip upgraded"
echo ""

# Install server dependencies
echo "Installing server dependencies..."
if [ -f "server/requirements.txt" ]; then
    pip install -r server/requirements.txt > /dev/null 2>&1
    echo "✓ Server dependencies installed"
else
    echo "⚠ server/requirements.txt not found, skipping server dependencies"
fi
echo ""

# Install client dependencies
echo "Installing client dependencies..."
if [ -f "client/client_requirements.txt" ]; then
    pip install -r client/client_requirements.txt > /dev/null 2>&1
    echo "✓ Client dependencies installed"
else
    echo "⚠ client/client_requirements.txt not found, skipping client dependencies"
fi
echo ""

# Setup environment file
echo "Setting up environment file..."
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo "✓ .env file created from template"
        echo "  ⚠ Please edit .env and add your secret keys:"
        echo "    - JWT_SECRET_KEY"
        echo "    - PASSWORD_HASH_SECRET"
    else
        # Create basic .env file
        cat > .env << 'EOF'
# Environment Configuration
LOG_LEVEL=INFO
JWT_SECRET_KEY=change-this-to-a-random-secret-key-min-32-chars
PASSWORD_HASH_SECRET=change-this-to-a-random-secret-min-32-chars
ENV=development
EOF
        echo "✓ .env file created"
        echo "  ⚠ Please edit .env and set secure values for:"
        echo "    - JWT_SECRET_KEY"
        echo "    - PASSWORD_HASH_SECRET"
    fi
else
    echo "✓ .env file already exists"
fi
echo ""

# Create necessary directories
echo "Creating necessary directories..."
mkdir -p server/data
mkdir -p client/data
mkdir -p logs
echo "✓ Directories created"
echo ""

# Make scripts executable
echo "Making scripts executable..."
chmod +x install.sh 2>/dev/null || true
chmod +x start_servers.sh 2>/dev/null || true
chmod +x start_client.sh 2>/dev/null || true
chmod +x server/start_all.sh 2>/dev/null || true
chmod +x client/start_client.sh 2>/dev/null || true
echo "✓ Scripts are now executable"
echo ""

echo "=========================================="
echo "Installation Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Edit .env and set secure values for JWT_SECRET_KEY and PASSWORD_HASH_SECRET"
echo "2. Configure server/configs.json and client/client_configs.json if needed"
echo "3. Run './start_servers.sh' in one terminal to start the servers"
echo "4. Run './start_client.sh' in another terminal to start the client"
echo ""
echo "For more information, see README.md"
echo ""
