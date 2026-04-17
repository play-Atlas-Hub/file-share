# TANK GAME - Quick Start & Setup

## ✅ All Issues Fixed!

Two critical bugs have been fixed and setup scripts created.

---

## 🚀 Quick Start (5 Minutes)

### 1. Install Project
```bash
cd /Users/nelson.nolan16/Desktop/TANK_GAME
./install.sh
```

### 2. Configure Environment
```bash
nano .env
```
Change these values to random strings (32+ characters):
- `JWT_SECRET_KEY`
- `PASSWORD_HASH_SECRET`

Save and exit (Ctrl+X, Y, Enter in nano)

### 3. Start Servers (Terminal 1)
```bash
./start_servers.sh
```
Wait for the message: "Server running..."

### 4. Start Client (Terminal 2)  
```bash
./start_client.sh
```
The game window will open!

---

## 📋 What Was Fixed

### Bug #1: Server Logger Error ❌→✅
**Error was:** `NameError: name 'logger' is not defined`
- **Fixed in:** [server/server_complete.py](server/server_complete.py#L32-L39)
- **Change:** Moved logging initialization to line 32 (before any logger use)

### Bug #2: Client Websocket Error ❌→✅
**Error was:** `AttributeError: 'GameClient' object has no attribute 'game_client'`
- **Fixed in:** [client/client_final.py](client/client_final.py#L1985)
- **Change:** Changed `self.game_client.websocket` to `self.game_client.game_ws` with connection check

---

## 📦 Scripts Created

| Script | Purpose | Usage |
|--------|---------|-------|
| [install.sh](install.sh) | First-time project setup | `./install.sh` |
| [start_servers.sh](start_servers.sh) | Launch game servers | `./start_servers.sh` |
| [start_client.sh](start_client.sh) | Launch game client | `./start_client.sh` |

All scripts are executable and handle:
- Virtual environment activation
- Dependency checking
- Config file validation
- Clear error messages

---

## 🔧 Manual Setup (If Not Using Scripts)

### Setup Virtual Environment
```bash
cd /Users/nelson.nolan16/Desktop/TANK_GAME
python3 -m venv venv
source venv/bin/activate
```

### Install Dependencies
```bash
pip install -r server/requirements.txt
pip install -r client/client_requirements.txt
```

### Configure Environment
```bash
cp .env.example .env
# Edit .env and set JWT_SECRET_KEY and PASSWORD_HASH_SECRET
```

### Run Servers
```bash
cd server
python server_complete.py
```

### Run Client (in new terminal)
```bash
source venv/bin/activate
cd client
python client_final.py
```

---

## 🐛 Troubleshooting

### Server won't start
1. Check `.env` file exists: `ls -la .env`
2. Verify Python: `python --version` (should be 3.9+)
3. Check configs: `ls -la server/configs.json server/msg.json`
4. Check dependencies: `pip list | grep -E "websockets|pyjwt"`

### Client won't connect
1. Verify server is running first
2. Check client config: `cat client/client_configs.json`
3. Check server URL in config matches server host/port
4. Check firewall isn't blocking ports 8765-8766

### Admin login fails
1. Verify WebSocket connection is established (check server logs)
2. Check admin credentials in admin_login_async() match server

---

## 📊 Project Structure

```
TANK_GAME/
├── install.sh              ← Run this first!
├── start_servers.sh        ← Start servers
├── start_client.sh         ← Start client
├── .env                    ← Environment config (auto-created)
├── venv/                   ← Virtual environment (auto-created)
│
├── server/
│   ├── server_complete.py  ← Main server (FIXED ✅)
│   ├── configs.json        ← Server config
│   ├── msg.json            ← Server messages
│   └── requirements.txt
│
├── client/
│   ├── client_final.py     ← Main client (FIXED ✅)
│   ├── client_configs.json ← Client config
│   ├── client_requirements.txt
│   └── tank_images/        ← Game assets
│
└── docs/
    ├── SETUP_GUIDE.md      ← Detailed setup
    ├── DEVELOPMENT_GUIDE.md
    ├── CODE_IMPROVEMENTS.md
    └── FIXES_AND_SCRIPTS.md ← Details of fixes
```

---

## ✨ Verification

Both files have been syntax-checked:
- ✅ [server/server_complete.py](server/server_complete.py) - Valid Python
- ✅ [client/client_final.py](client/client_final.py) - Valid Python

Logger will now initialize before use, and WebSocket will access the correct attribute.

---

## 📞 Support

If you encounter issues:
1. Check the [FIXES_AND_SCRIPTS.md](FIXES_AND_SCRIPTS.md) for detailed fix information
2. Review [SETUP_GUIDE.md](docs/SETUP_GUIDE.md) for comprehensive setup steps
3. Check server logs for error messages: `tail -f logs/server.log`

---

**Last Updated:** April 17, 2024
**Status:** ✅ Ready to Run
