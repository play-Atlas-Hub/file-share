#!/bin/bash

# Install requirements
echo "Installing client requirements..."
pip3 install -r client_requirements.txt

# Generate grid if it doesn't exist
if [ ! -f "grid.png" ]; then
    echo "Generating grid texture..."
    python3 generate_grid.py
fi

# Start client
echo "Starting Tank Battle Arena client..."
python3 client_complete.py