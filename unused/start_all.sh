#!/bin/bash

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Tank Battle Arena - Server Suite${NC}"
echo "================================="

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Python 3 is not installed${NC}"
    exit 1
fi

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}Creating virtual environment...${NC}"
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install requirements
echo -e "${YELLOW}Installing server requirements...${NC}"
pip3 install -q -r requirements.txt

# Generate grid if it doesn't exist
if [ ! -f "grid.png" ]; then
    echo -e "${YELLOW}Generating grid texture...${NC}"
    python3 generate_grid.py
fi

# Start servers in separate tmux windows
if ! command -v tmux &> /dev/null; then
    echo -e "${YELLOW}tmux not found. Starting servers sequentially...${NC}"
    echo -e "${GREEN}Starting Login Server on port 8766...${NC}"
    python3 login_server.py &
    LOGIN_PID=$!
    sleep 2
    
    echo -e "${GREEN}Starting Game Server on port 8765...${NC}"
    python3 server_v2.py &
    SERVER_PID=$!
    sleep 2
    
    echo -e "${GREEN}Starting Website on port 5000...${NC}"
    python3 website.py &
    WEBSITE_PID=$!
    
    echo -e "${GREEN}All servers started!${NC}"
    echo -e "${YELLOW}Login Server PID: $LOGIN_PID${NC}"
    echo -e "${YELLOW}Game Server PID: $SERVER_PID${NC}"
    echo -e "${YELLOW}Website PID: $WEBSITE_PID${NC}"
    echo -e "${YELLOW}Press Ctrl+C to stop all servers${NC}"
    
    wait
else
    echo -e "${GREEN}Starting servers with tmux...${NC}"
    
    tmux new-session -d -s tba -x 120 -y 30
    
    tmux new-window -t tba -n "login"
    tmux send-keys -t tba:login "cd $(pwd) && python3 login_server.py" Enter
    
    tmux new-window -t tba -n "game"
    tmux send-keys -t tba:game "cd $(pwd) && python3 server_complete.py" Enter
    
    tmux new-window -t tba -n "website"
    tmux send-keys -t tba:website "cd $(pwd) && python3 website.py" Enter
    
    tmux new-window -t tba -n "client"
    tmux send-keys -t tba:client "cd $(pwd) && python3 client_complete.py" Enter
    
    echo -e "${GREEN}All servers started in tmux session 'tba'${NC}"
    echo -e "${YELLOW}Use 'tmux attach -t tba' to view${NC}"
    echo -e "${YELLOW}Use 'tmux kill-session -t tba' to stop all${NC}"
fi