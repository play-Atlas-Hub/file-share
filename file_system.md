tank-battle-arena/
│
├── 📄 README.md                          # Main documentation
├── 📄 SETUP.md                           # Setup instructions
├── 📄 requirements.txt                   # Python dependencies (server)
├── 📄 client_requirements.txt            # Python dependencies (client)
│
├── 🔧 SERVER FILES
│   ├── server_complete.py                # All-in-one server (login + game)
│   ├── lobby_system.py
│   ├── spectator_system.py
│   ├── login_server.py
│   ├── 📄 requirements.txt               # Python dependencies (server)
│   ├── start_all.sh                      # Linux/macOS startup script
│   ├── configs.json                      # Server configuration
│   ├── msg.json                          # Server messages/localization
│   ├── login_data.db                     # SQLite database (auto-created)
│   ├── game_data.db                      # SQLite database (auto-created)
│   └── website.py                        # Flask web dashboard
│
├── 🎮 CLIENT FILES
│   ├── start_client.bat
│   ├── start_client.sh
│   ├── 📄 client_requirements.txt        # Python dependencies (client)
│   ├── client_complete.py                # Complete Pygame client
│   ├── client_configs.json               # Client configuration
│   ├── generate_grid.py                  # Grid texture generator
│   ├── grid.png                          # Grid texture (auto-generated)
│   └── tank_images/                      # Tank sprite images
│       ├── basic_tank.png
│       ├── freeze_tank.png
│       ├── flame_tank.png
│       ├── ray_tank.png
│       ├── grinder_tank.png
│       ├── block_tank.png
│       ├── sniper_tank.png
│       └── spammer_tank.png
│
├── 🌐 WEB DASHBOARD (templates/ & static/)
│   ├── templates/
│   │   ├── index.html                   # Home page
│   │   ├── login.html                   # Login page
│   │   ├── register.html                # Registration page
│   │   ├── dashboard.html               # User dashboard
│   │   └── admin.html                   # Admin panel
│   │
│   ├── static/
│   │   ├── css/
│   │   │   └── style.css                # Main stylesheet
│   │   └── js/
│   │       └── main.js                  # Frontend JavaScript
│
├── 📚 STARTUP SCRIPTS
│   ├── start_all.sh                     # Linux/macOS startup script
│   └── start_all.bat                    # Windows startup script
│
└── 📁 DATA DIRECTORIES (auto-created)
    ├── venv/                            # Virtual environment
    ├── __pycache__/                     # Python cache
    └── logs/                            # Server logs (optional)