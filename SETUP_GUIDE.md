# Tank Battle Arena - Multiplayer Game

A real-time multiplayer tank battle game built with Python, Pygame, and WebSockets.

## Features

- **Real-time Multiplayer**: Up to 256 players on a single server
- **Team-based Gameplay**: 4-team battle system with quadrant-based spawning
- **Tank Customization**: Multiple tank types with unique abilities
- **Progression System**: Ranks, money, and resources
- **Upgrades**: Skill-based upgrades with progression
- **Dynamic World**: Day/night cycle, collectible blobs
- **Admin Tools**: Server interactive admin panel for management

## Project Structure

```
TANK_GAME/
├── client/
│   ├── client_final.py       # Main client application
│   ├── client_configs.json   # Client configuration
│   ├── client_requirements.txt # Client dependencies
│   └── tank_images/          # Tank sprite assets
├── server/
│   ├── server_complete.py    # Main server application
│   ├── configs.json          # Server configuration
│   ├── requirements.txt       # Server dependencies
│   ├── login_server.py       # Authentication server
│   └── website.py            # Web dashboard
├── utils/
│   ├── __init__.py
│   ├── logging_config.py     # Logging setup
│   └── config_validator.py   # Config validation
├── .env.example              # Environment variables template
├── requirements.txt          # Project dependencies
└── README.md                 # This file
```

## Installation

### Prerequisites

- Python 3.9 or higher
- pip (Python package manager)

### Setup Instructions

1. **Clone/Download the repository**
   ```bash
   cd TANK_GAME
   ```

2. **Create virtual environment** (recommended)
   ```bash
   python -m venv venv
   
   # Activate virtual environment
   # On macOS/Linux:
   source venv/bin/activate
   # On Windows:
   venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Create environment file**
   ```bash
   cp .env.example .env
   ```

5. **Edit .env file with your settings**
   ```
   # Generate a strong JWT secret
   # On macOS/Linux:
   openssl rand -hex 32
   
   # Then paste the output into .env as:
   JWT_SECRET=<your_generated_hex_string>
   ```

## Running the Game

### Start the Server

```bash
# Terminal 1 - Login Server
python server/login_server.py

# Terminal 2 - Game Server
python server/server_complete.py
```

### Start the Client

```bash
# Terminal 3 - Client
python client/client_final.py
```

### Admin Panel (Optional)

```bash
# Terminal 4 - Admin Tool
python server_interactive.py
```

## Configuration

### Client Configuration (`client/client_configs.json`)

- **Display**: Resolution, FPS, fullscreen mode
- **Keyboard**: Keybindings for all actions
- **Gameplay**: Auto-shoot, camera smoothing, particle effects
- **Network**: Server URLs, reconnection settings
- **Colors**: UI and team colors

### Server Configuration (`server/configs.json`)

- **Server**: Port, max players, maintenance mode
- **World**: Dimensions, screen layout, day/night cycle
- **Game Balance**: Player speeds, bullet properties, blob spawning
- **Progression**: Costs, upgrades, rank thresholds
- **Game Modes**: Available modes and voting

### Environment Variables (`.env`)

```env
# CRITICAL - Generate with: openssl rand -hex 32
JWT_SECRET=your_secret_here

# Logging
LOG_LEVEL=INFO
DEBUG_MODE=false

# Database
DATABASE_PATH=login_data.db
```

## Game Controls

### Client Controls

```
WASD         - Move
Mouse/G      - Rotate turret
Left Click   - Shoot
F            - Toggle auto-shoot
R            - Toggle auto-spin
T            - Open chat
Z            - Open menu
Q            - Tank upgrades
E            - Skill upgrades
B            - Buy (in menu)
ESC          - Close menu
```

### Menu Navigation

```
UP/DOWN      - Navigate menu items
ENTER        - Select item / Purchase
TAB          - Switch input fields (auth)
```

## Architecture

### Client (`client_final.py`)

**Key Classes:**
- `Game`: Main game loop and state management
- `GameClient`: WebSocket connection and message handling
- `Renderer`: Rendering game world, HUD, minimap
- `Menu`: In-game menu system
- `InputManager`: Input handling and key mapping
- `RemotePlayer`, `Blob`, `Bullet`: Game objects

**Game States:**
- Server Selection → Login/Register → Team Selection → Playing → Menu/Dead/Spectating

### Server (`server_complete.py`)

**Key Classes:**
- `GameDatabase`: SQLite database management
- `Player`: Player state and statistics
- `Lobby`: Game lobby management
- `Blob`: Collectible entities
- `Bullet`: Projectile tracking

**Server Components:**
- **Login Server** (port 8766): Authentication via JWT
- **Game Server** (port 8765): Real-time game state
- **Message Handlers**: Process client actions
- **Game Loops**: Blob spawning, state broadcasting

## Security Considerations

### Implemented

✅ JWT token-based authentication
✅ Password hashing with salt (PBKDF2)
✅ Environment variable secrets management
✅ Admin credential protection
✅ IP whitelisting for admin access

### Recommendations for Production

- [ ] Use HTTPS/WSS (WebSocket Secure)
- [ ] Implement rate limiting on login attempts
- [ ] Add CORS headers and request validation
- [ ] Use stronger password hashing (Argon2)
- [ ] Implement request signing/verification
- [ ] Add database encryption
- [ ] Set up firewall rules and DDoS protection
- [ ] Regular security audits
- [ ] Monitor for suspicious activity
- [ ] Keep dependencies updated

## Troubleshooting

### Connection Issues

**"Connection timeout"**
- Verify server is running on correct port
- Check firewall settings
- Ensure client server URL matches server binding

**"Login failed"**
- Check username and password
- Verify login server is running (port 8766)
- Check database for user account

### Performance Issues

**Low FPS**
- Reduce draw distance in renderer
- Lower texture quality
- Disable particle effects
- Reduce player/blob limits

**Network lag**
- Decrease send_rate_ms in client config
- Reduce player count
- Check network connection
- Enable UDP optimization if available

### Database Issues

**"Database locked"**
- Ensure only one server instance is running
- Delete `login_data.db` and restart (loses progress)
- Check for orphaned processes

## Development

### Code Style

```bash
# Format code
black server/ client/ utils/

# Check linting
flake8 server/ client/ utils/

# Type checking
mypy server/ client/ utils/
```

### Testing

```bash
# Run tests
pytest tests/

# Run specific test file
pytest tests/test_auth.py -v
```

### Adding Features

1. Create feature branch
2. Make changes with proper docstrings
3. Test thoroughly
4. Update documentation
5. Submit pull request

## Performance Metrics

### Current Limits

- **Max Players**: 256 per server
- **Max Players Per Lobby**: 64
- **Network Update Rate**: 16ms (60 updates/sec)
- **Message Send Rate**: 50ms (20 updates/sec)
- **World Size**: 9280×6240 pixels (10×8 screens)

### Optimization Tips

1. Use spatial partitioning for collision detection
2. Implement object pooling for bullets/particles
3. Stream LOD (level of detail) based on distance
4. Batch network messages
5. Use delta compression for state updates
6. Implement client-side prediction

## Known Issues & Limitations

- [ ] Client honesty-based anti-cheat (needs server-side validation)
- [ ] No persistent world between server restarts
- [ ] Limited spectator functionality
- [ ] No voice chat
- [ ] No mobile client

## Future Roadmap

- [ ] In-game friends system
- [ ] Clan/guild support
- [ ] Battle pass progression
- [ ] Custom game modes
- [ ] Replay system
- [ ] Mobile client (React Native)
- [ ] Trading/marketplace
- [ ] PvE dungeons
- [ ] Ranked ladder
- [ ] Seasonal resets

## Contributing

See CONTRIBUTING.md for guidelines

## License

[Add your license here]

## Support

For issues, questions, or suggestions:
- Open a GitHub issue
- Contact: [your-email]
- Discord: [invite link]

## Credits

- Game Design: [Names]
- Development: [Names]
- Art: [Names]

---

**Last Updated**: April 2026
**Version**: 1.0.0
