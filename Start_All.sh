#!/bin/bash

# Tank Battle Arena - Universal Start Script
# Supports: Linux, macOS
# Features: Interactive menu, multiple start modes, virtual environment management

set -e

echo "What is the path to your TANK_GAME directory? (Press Enter for current directory)"
read REPLY
cd $REPLY/TANK_GAME/

# ==================== COLORS & FORMATTING ====================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
WHITE='\033[1;37m'
NC='\033[0m' # No Color

# ==================== UTILITY FUNCTIONS ====================
print_banner() {
    clear
    echo -e "${CYAN}"
    echo "╔═══════════════════════════════════════════════════════════════╗"
    echo "║                                                               ║"
    echo "║           ⚔️  TANK BATTLE ARENA - SERVER SUITE  ⚔️           ║"
    echo "║                                                               ║"
    echo "╚═══════��═══════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

print_section() {
    echo -e "\n${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${WHITE}$1${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
}

# ==================== SYSTEM CHECKS ====================
check_python() {
    if ! command -v python3 &> /dev/null; then
        print_error "Python 3 is not installed!"
        echo -e "\n${YELLOW}Installation instructions:${NC}"
        echo "  Ubuntu/Debian: sudo apt-get install python3 python3-pip"
        echo "  macOS: brew install python3"
        echo "  CentOS: sudo yum install python3 python3-pip"
        exit 1
    fi
    
    local python_version=$(python3 --version | awk '{print $2}')
    print_success "Python 3 found: $python_version"
}

check_ports() {
    local ports=(8765 8766 5000)
    local in_use=0
    
    for port in "${ports[@]}"; do
        if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
            print_warning "Port $port is already in use"
            ((in_use++))
        fi
    done
    
    if [ $in_use -gt 0 ]; then
        echo -e "${YELLOW}Some ports are already in use. This may cause conflicts.${NC}"
        read -p "Continue anyway? (y/n): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            print_error "Cancelled by user"
            exit 1
        fi
    fi
}

# ==================== ENVIRONMENT SETUP ====================
setup_venv() {
    if [ ! -d "venv" ]; then
        print_section "Setting up Python Virtual Environment"
        python3 -m venv venv
        print_success "Virtual environment created"
    fi
    
    # Activate venv
    source venv/bin/activate
    print_success "Virtual environment activated"
}

install_dependencies() {
    print_section "Installing Dependencies"
    
    if [ -f "server/requirements.txt" ]; then
        print_info "Installing server requirements..."
        pip3 install -q -r server/requirements.txt
        print_success "Server requirements installed"
    fi
    
    if [ -f "client/client_requirements.txt" ]; then
        print_info "Installing client requirements..."
        pip3 install -q -r client/client_requirements.txt
        print_success "Client requirements installed"
    fi
}

generate_grid() {
    if [ ! -f "client/grid.png" ]; then
        print_section "Generating Grid Texture"
        if python3 client/generate_grid.py 2>/dev/null; then
            print_success "Grid texture generated: grid.png"
        else
            print_warning "Could not generate grid texture (grid.png)"
        fi
    else
        print_success "Grid texture already exists"
    fi
}

check_configs() {
    print_section "Checking Configuration Files"
    
    local missing_files=0
    
    if [ ! -f "server/configs.json" ]; then
        print_error "configs.json not found!"
        ((missing_files++))
    else
        print_success "configs.json found"
    fi
    
    if [ ! -f "client/client_configs.json" ]; then
        print_error "client_configs.json not found!"
        ((missing_files++))
    else
        print_success "client_configs.json found"
    fi
    
    if [ ! -f "server/msg.json" ]; then
        print_warning "msg.json not found (using defaults)"
    else
        print_success "msg.json found"
    fi
    
    if [ $missing_files -gt 0 ]; then
        print_error "Missing configuration files!"
        exit 1
    fi
}

# ==================== START FUNCTIONS ====================
start_login_server() {
    print_section "Starting Login Server (Port 8766)"
    source venv/bin/activate
    
    if [ -f "server/login_server.py" ]; then
        python3 server/login_server.py
    elif [ -f "server/server_complete.py" ]; then
        python3 server/server_complete.py &
    else
        print_error "No login server file found!"
        exit 1
    fi
}

start_game_server() {
    print_section "Starting Game Server (Port 8765)"
    source venv/bin/activate
    
    if [ -f "server/server_complete.py" ]; then
        python3 server/server_complete.py
    else
        print_error "No game server file found!"
        exit 1
    fi
}

start_website() {
    print_section "Starting Website (Port 5000)"
    source venv/bin/activate
    
    if [ -f "server/website.py" ]; then
        python3 server/website.py
    else
        print_error "No website file found!"
        exit 1
    fi
}

start_client() {
    print_section "Starting Game Client"
    source venv/bin/activate
    
    if [ -f "client/client_complete.py" ]; then
        python3 client/client_complete.py
    else
        print_error "No client file found!"
        exit 1
    fi
}

# ==================== TMUX FUNCTIONS ====================
start_with_tmux() {
    print_section "Starting with tmux (Multiple Windows)"
    
    local session_name="tba_session"
    
    # Kill existing session
    tmux kill-session -t $session_name 2>/dev/null || true
    
    # Create new session
    tmux new-session -d -s $session_name -x 200 -y 50
    
    print_info "Starting servers in tmux session: $session_name"
    
    # Window 1: Login Server
    tmux new-window -t $session_name -n "login"
    tmux send-keys -t $session_name:login "cd '$PWD' && source venv/bin/activate && python3 server/server_complete.py" Enter
    print_success "Login server window created"
    sleep 2
    
    # Window 2: Game Server (if separate)
    tmux new-window -t $session_name -n "game"
    tmux send-keys -t $session_name:game "cd '$PWD' && source venv/bin/activate && python3 server/server_complete.py" Enter
    print_success "Game server window created"
    sleep 2
    
    # Window 3: Website
    tmux new-window -t $session_name -n "website"
    tmux send-keys -t $session_name:website "cd '$PWD' && source venv/bin/activate && python3 server/website.py" Enter
    print_success "Website window created"
    sleep 2
    
    # Window 4: Client
    tmux new-window -t $session_name -n "client"
    tmux send-keys -t $session_name:client "cd '$PWD' && source venv/bin/activate && python3 client/client_complete.py" Enter
    print_success "Client window created"
    sleep 1
    
    # Window 5: Monitor
    tmux new-window -t $session_name -n "monitor"
    tmux send-keys -t $session_name:monitor "cd '$PWD' && watch -n 1 'echo Tank Battle Arena Monitor; echo; ps aux | grep python3 | grep -v grep'" Enter
    print_success "Monitor window created"
    
    # Attach to session
    echo -e "\n${GREEN}All servers started in tmux session!${NC}"
    echo -e "\n${CYAN}Session: $session_name${NC}"
    echo -e "${CYAN}Available windows:${NC}"
    echo "  • ${YELLOW}login${NC}   - Login server"
    echo "  • ${YELLOW}game${NC}    - Game server"
    echo "  • ${YELLOW}website${NC} - Website dashboard"
    echo "  • ${YELLOW}client${NC}  - Game client"
    echo "  • ${YELLOW}monitor${NC} - Process monitor"
    echo -e "\n${CYAN}Commands:${NC}"
    echo "  Attach:  tmux attach -t $session_name"
    echo "  Kill:    tmux kill-session -t $session_name"
    echo "  Windows: Ctrl+B then press number (0-4) or arrow keys"
    echo ""
    
    tmux attach -t $session_name
}

start_with_screen() {
    print_section "Starting with screen (Legacy Terminal Multiplexer)"
    
    local session_name="tba"
    
    # Kill existing session
    screen -S $session_name -X quit 2>/dev/null || true
    
    print_info "Starting servers in screen session: $session_name"
    
    # Create session and windows
    screen -dmS $session_name
    
    # Window 0: Login Server
    screen -S $session_name -X screen -t "login"
    screen -S $session_name -p login -X stuff "cd '$PWD' && source venv/bin/activate && python3 server/server_complete.py"
    print_success "\n Login server window created"
    sleep 2
    
    # Window 1: Website
    screen -S $session_name -X screen -t "website"
    screen -S $session_name -p website -X stuff "cd '$PWD' && source venv/bin/activate && python3 server/website.py"
    print_success "\n Website window created"
    sleep 2
    
    # Window 2: Client
    screen -S $session_name -X screen -t "client"
    screen -S $session_name -p client -X stuff "cd '$PWD' && source venv/bin/activate && python3 client/client_complete.py"
    print_success "\n Client window created"
    
    echo -e "\n${GREEN}All servers started in screen session!${NC}"
    echo -e "\n${CYAN}Commands:${NC}"
    echo "  Attach:  screen -r $session_name"
    echo "  Detach:  Ctrl+A then D"
    echo "  Kill:    screen -S $session_name -X quit"
    echo "  Windows: Ctrl+A then N (next) or P (previous)"
    echo ""
    
    screen -r $session_name
}

start_foreground() {
    print_section "Starting All Services (Foreground)"
    print_warning "Services will run in sequence. Close each to start the next."
    
    echo -e "\n${YELLOW}Press Enter to start each service...${NC}\n"
    
    read -p "Ready? " -r
    
    print_info "Starting Login Server..."
    start_login_server &
    local login_pid=$!
    sleep 2
    
    read -p "Login server started (PID: $login_pid). Press Enter for next..." -r
    
    print_info "Starting Website..."
    start_website &
    local website_pid=$!
    sleep 2
    
    read -p "Website started (PID: $website_pid). Press Enter for next..." -r
    
    print_info "Starting Game Client..."
    start_client
    
    # Cleanup on exit
    kill $login_pid $website_pid 2>/dev/null || true
}

# ==================== MENU SYSTEM ====================
show_main_menu() {
    print_banner
    
    echo -e "${WHITE}What would you like to do?${NC}\n"
    echo -e "  ${CYAN}1${NC} - Start all services (auto-detect multiplexer)"
    echo -e "  ${CYAN}2${NC} - Start specific service"
    echo -e "  ${CYAN}3${NC} - Start with tmux (recommended)"
    echo -e "  ${CYAN}4${NC} - Start with screen (legacy)"
    echo -e "  ${CYAN}5${NC} - Start in foreground"
    echo -e "  ${CYAN}6${NC} - Development mode (server only)"
    echo -e "  ${CYAN}7${NC} - Check system status"
    echo -e "  ${CYAN}8${NC} - View configuration"
    echo -e "  ${CYAN}9${NC} - Setup/Reinstall"
    echo -e "  ${CYAN}0${NC} - Exit"
    echo ""
}

show_service_menu() {
    print_banner
    
    echo -e "${WHITE}Select a service:${NC}\n"
    echo -e "  ${CYAN}1${NC} - Login Server (Port 8766)"
    echo -e "  ${CYAN}2${NC} - Game Server (Port 8765)"
    echo -e "  ${CYAN}3${NC} - Website (Port 5000)"
    echo -e "  ${CYAN}4${NC} - Game Client"
    echo -e "  ${CYAN}5${NC} - All services"
    echo -e "  ${CYAN}0${NC} - Back"
    echo ""
}

handle_main_menu() {
    read -p "Enter your choice: " -r
    
    case $REPLY in
        1)
            if command -v tmux &> /dev/null; then
                start_with_tmux
            elif command -v screen &> /dev/null; then
                start_with_screen
            else
                print_warning "No terminal multiplexer found. Starting in foreground..."
                start_foreground
            fi
            ;;
        2)
            show_service_menu
            handle_service_menu
            ;;
        3)
            start_with_tmux
            ;;
        4)
            start_with_screen
            ;;
        5)
            start_foreground
            ;;
        6)
            print_section "Development Mode - Server Only"
            source venv/bin/activate
            python3 server/server_complete.py
            ;;
        7)
            show_status
            ;;
        8)
            show_configuration
            ;;
        9)
            setup_environment
            ;;
        0)
            print_info "Goodbye!"
            exit 0
            ;;
        *)
            print_error "Invalid choice"
            sleep 2
            main
            ;;
    esac
}

handle_service_menu() {
    read -p "Enter your choice: " -r
    
    case $REPLY in
        1) start_login_server ;;
        2) start_game_server ;;
        3) start_website ;;
        4) start_client ;;
        5)
            start_with_tmux
            ;;
        0) main ;;
        *) print_error "Invalid choice"; handle_service_menu ;;
    esac
}

show_status() {
    print_section "System Status"
    
    echo -e "${CYAN}Python:${NC}"
    python3 --version
    
    echo -e "\n${CYAN}Port Status:${NC}"
    for port in 8765 8766 5000; do
        if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
            print_success "Port $port is in use"
        else
            print_warning "Port $port is available"
        fi
    done
    
    echo -e "\n${CYAN}Running Processes:${NC}"
    ps aux | grep python3 | grep -v grep || echo "No Python processes running"
    
    echo -e "\n${CYAN}Installed Packages:${NC}"
    source venv/bin/activate
    pip3 list | grep -E "(websocket|pygame|flask|jwt)" || echo "Some packages not installed"
    
    echo -e "\n${CYAN}Configuration Files:${NC}"
    [ -f "server/configs.json" ] && print_success "configs.json" || print_error "configs.json"
    [ -f "client/client_configs.json" ] && print_success "client_configs.json" || print_error "client_configs.json"
    [ -f "server/msg.json" ] && print_success "msg.json" || print_warning "msg.json (optional)"
    
    read -p "\nPress Enter to continue..." -r
    main
}

show_configuration() {
    print_section "Server Configuration Preview"
    
    if [ -f "configs.json" ]; then
        echo -e "${CYAN}configs.json:${NC}"
        head -20 configs.json | sed 's/^/  /'
        echo "  ..."
    fi
    
    read -p "\nPress Enter to continue..." -r
    main
}

setup_environment() {
    print_section "Setup/Reinstall Environment"
    
    check_python
    setup_venv
    install_dependencies
    check_configs
    generate_grid
    
    print_success "Environment setup complete!"
    read -p "\nPress Enter to continue..." -r
    main
}

# ==================== MAIN FUNCTION ====================
main() {
    show_main_menu
    handle_main_menu
    main
}

# ==================== ENTRY POINT ====================
setup_environment
main