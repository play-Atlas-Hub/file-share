import asyncio
import json
import random
import sys
import websockets
import time
import math
import sqlite3
import hashlib
import uuid
import jwt
from datetime import datetime, timedelta
from enum import Enum
from collections import defaultdict
import threading

# ==================== CONFIG LOADING ====================
def load_config():
    try:
        with open('configs.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print("ERROR: configs.json not found!")
        sys.exit(1)
    except json.JSONDecodeError:
        print("ERROR: configs.json is not valid JSON!")
        sys.exit(1)

def load_messages():
    try:
        with open('msg.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

CONFIG = load_config()
MESSAGES = load_messages()

# ==================== CONSTANTS ====================
# Server
SERVER_HOST = CONFIG['server']['host']
GAME_SERVER_PORT = CONFIG['server']['port']
LOGIN_SERVER_PORT = CONFIG['server']['login_port']
SERVER_MAINTENANCE_MODE = CONFIG['server']['maintenance_mode']
SERVER_CLOSED = CONFIG['server']['closed']
MAX_PLAYERS = CONFIG['server']['max_players']
MAX_PLAYERS_PER_LOBBY = CONFIG['server']['max_players_per_lobby']

# World
WIDTH = CONFIG['world']['width']
HEIGHT = CONFIG['world']['height']
TILE_SIZE = CONFIG['world']['tile_size']
WORLD_SCREENS_X = CONFIG['world']['screens_x']
WORLD_SCREENS_Y = CONFIG['world']['screens_y']
WORLD_W = WIDTH * WORLD_SCREENS_X
WORLD_H = HEIGHT * WORLD_SCREENS_Y

# Day/Night
DAY_NIGHT_ENABLED = CONFIG['world']['day_night_cycle']['enabled']
DAY_DURATION = CONFIG['world']['day_night_cycle']['day_duration_seconds']
NIGHT_DURATION = CONFIG['world']['day_night_cycle']['night_duration_seconds']

# Player
PLAYER_SPEED = CONFIG['player']['speed']
PLAYER_RADIUS = CONFIG['player']['radius']
RESPAWN_TIME = CONFIG['player']['respawn_time_seconds']
RESPAWN_INVINCIBILITY = CONFIG['player']['respawn_invincibility_seconds']
NEW_PLAYER_INVINCIBILITY = CONFIG['player']['new_player_invincibility_seconds']
PLAYER_MAX_HEALTH = CONFIG['player']['max_health']
HEALTH_REGEN = CONFIG['player']['health_regen_per_second']

# Bullet
BULLET_SPEED = CONFIG['bullet']['speed']
BULLET_RADIUS = CONFIG['bullet']['radius']
BULLET_MAX_LIFETIME = CONFIG['bullet']['max_lifetime_seconds']

# Blobs
BLOB_SPAWN_TIME = CONFIG['blobs']['spawn_time_seconds']
MAX_BLOB_DENSITY = CONFIG['blobs']['max_density_per_tile']
BLOB_TYPES = CONFIG['blobs']['types']

# Teams
TEAMS_CONFIG = CONFIG['teams']['list']
NUM_TEAMS = CONFIG['teams']['count']

# Tanks
TANKS_CONFIG = CONFIG['tanks']['list']
DEFAULT_TANK = CONFIG['tanks']['default']

# Upgrades
UPGRADES_CONFIG = CONFIG['upgrades']['list']
UPGRADE_COST = CONFIG['upgrades']['cost_per_upgrade']

# Ranks
RANK_THRESHOLDS = CONFIG['ranks']['thresholds']

# Game Modes
GAME_MODES = CONFIG['game_modes']['modes']
INITIAL_GAME_MODE = CONFIG['game_modes']['initial']
VOTING_ENABLED = CONFIG['game_modes']['voting_enabled']
VOTING_TIMEOUT = CONFIG['game_modes']['voting_timeout_seconds']

# Chat
CHAT_ENABLED = CONFIG['chat']['enabled']
CHAT_LIMIT = CONFIG['chat']['message_limit_per_second']
CHAT_MAX_LENGTH = CONFIG['chat']['max_message_length']

# Daily Rewards
DAILY_REWARDS_ENABLED = CONFIG['daily_rewards']['enabled']
DAILY_REWARD_BASE = CONFIG['daily_rewards']['base_reward']

# Anti-Cheat
ANTI_CHEAT_ENABLED = CONFIG['anti_cheat']['enabled']

# Admin
ADMIN_CREDENTIALS = CONFIG['admin']['credentials']
ADMIN_IPS = CONFIG['admin']['allowed_ips']

# JWT
JWT_SECRET = "q1w2e3r4t5y6-secret-key-@#$!"
JWT_ALGORITHM = "HS256"
TOKEN_EXPIRY_MINUTES = 60

# ==================== ENUMS ====================
class GameState(Enum):
    LOBBY = "LOBBY"
    VOTING = "VOTING"
    PLAYING = "PLAYING"
    ENDED = "ENDED"

class PlayerState(Enum):
    ALIVE = "ALIVE"
    DEAD = "DEAD"
    SPECTATING = "SPECTATING"

class LobbyState(Enum):
    WAITING = "WAITING"
    READY = "READY"
    IN_PROGRESS = "IN_PROGRESS"
    FINISHED = "FINISHED"

# ==================== DATABASE ====================
class GameDatabase:
    def __init__(self, db_path='login_data.db'):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        # Accounts table
        c.execute('''CREATE TABLE IF NOT EXISTS accounts (
            user_id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            email TEXT,
            password_hash TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP,
            is_banned INTEGER DEFAULT 0,
            ban_reason TEXT,
            ban_until TIMESTAMP,
            daily_reward_last_claimed TIMESTAMP,
            daily_reward_streak INTEGER DEFAULT 0,
            is_guest INTEGER DEFAULT 0
        )''')
        
        # Sessions table
        c.execute('''CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            token TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL,
            ip_address TEXT,
            FOREIGN KEY(user_id) REFERENCES accounts(user_id)
        )''')
        
        # Player stats table
        c.execute('''CREATE TABLE IF NOT EXISTS player_stats (
            user_id TEXT PRIMARY KEY,
            total_kills INTEGER DEFAULT 0,
            total_deaths INTEGER DEFAULT 0,
            total_assists INTEGER DEFAULT 0,
            total_money INTEGER DEFAULT 0,
            total_games_played INTEGER DEFAULT 0,
            current_rank INTEGER DEFAULT 1,
            best_rank INTEGER DEFAULT 1,
            playtime_hours INTEGER DEFAULT 0,
            win_rate REAL DEFAULT 0.0,
            FOREIGN KEY(user_id) REFERENCES accounts(user_id)
        )''')
        
        # Daily rewards table
        c.execute('''CREATE TABLE IF NOT EXISTS daily_rewards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            reward_date DATE NOT NULL,
            amount INTEGER NOT NULL,
            streak_bonus INTEGER DEFAULT 0,
            claimed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES accounts(user_id),
            UNIQUE(user_id, reward_date)
        )''')
        
        # Suspicious activity log
        c.execute('''CREATE TABLE IF NOT EXISTS suspicious_activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            action TEXT,
            details TEXT,
            timestamp TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES accounts(user_id)
        )''')
        
        # Match history table
        c.execute('''CREATE TABLE IF NOT EXISTS match_history (
            match_id TEXT PRIMARY KEY,
            game_mode TEXT,
            winner_team INTEGER,
            duration_seconds INTEGER,
            created_at TIMESTAMP,
            players_stats TEXT
        )''')
        
        conn.commit()
        conn.close()
    
    def query(self, sql, params=None):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        if params:
            c.execute(sql, params)
        else:
            c.execute(sql)
        result = c.fetchall()
        conn.close()
        return [dict(row) for row in result]
    
    def get_one(self, sql, params=None):
        result = self.query(sql, params)
        return result[0] if result else None
    
    def execute(self, sql, params=None):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        if params:
            c.execute(sql, params)
        else:
            c.execute(sql)
        conn.commit()
        conn.close()

DB = GameDatabase()

# ==================== AUTH HELPERS ====================
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def generate_token(user_id):
    payload = {
        'user_id': user_id,
        'iat': datetime.utcnow(),
        'exp': datetime.utcnow() + timedelta(minutes=TOKEN_EXPIRY_MINUTES)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def verify_token(token):
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

# ==================== ANTI-CHEAT ====================
class AntiCheat:
    def __init__(self):
        self.player_positions = {}
        self.player_last_action_time = {}
    
    def check_speed_hack(self, player_id, new_x, new_y):
        if player_id not in self.player_positions:
            self.player_positions[player_id] = (new_x, new_y)
            return False
        
        old_x, old_y = self.player_positions[player_id]
        dist = math.sqrt((old_x - new_x)**2 + (old_y - new_y)**2)
        max_distance = PLAYER_SPEED * 1.5
        
        if dist > max_distance:
            return True
        
        self.player_positions[player_id] = (new_x, new_y)
        return False
    
    def check_rate_limit(self, player_id, action_type):
        key = (player_id, action_type)
        last_time = self.player_last_action_time.get(key, 0)
        current_time = time.time()
        
        if action_type == 'shoot':
            min_interval = 0.05
        elif action_type == 'move':
            min_interval = 0.01
        else:
            min_interval = 0.1
        
        if current_time - last_time < min_interval:
            return False
        
        self.player_last_action_time[key] = current_time
        return True
    
    def log_suspicious(self, user_id, action, details):
        DB.execute(
            'INSERT INTO suspicious_activity (user_id, action, details, timestamp) VALUES (?, ?, ?, ?)',
            (user_id, action, details, datetime.now())
        )

ANTI_CHEAT = AntiCheat() if ANTI_CHEAT_ENABLED else None

# ==================== PLAYER CLASS ====================
class Player:
    def __init__(self, player_id, username, user_id, team_id=1):
        self.id = player_id
        self.username = username
        self.user_id = user_id
        self.team = team_id
        
        spawn_x, spawn_y = self._get_spawn_location(team_id)
        self.x = spawn_x
        self.y = spawn_y
        self.vx = 0
        self.vy = 0
        self.angle = 0
        
        self.health = PLAYER_MAX_HEALTH
        self.max_health = PLAYER_MAX_HEALTH
        self.score = 0
        self.money = 0
        self.kills = 0
        self.assists = 0
        self.deaths = 0
        self.rank = 1
        
        self.tank = self._get_tank_by_name(DEFAULT_TANK)
        self.upgrades = {}
        self.last_shot_time = 0
        
        self.alive = True
        self.state = PlayerState.ALIVE
        self.invincible_until = time.time() + NEW_PLAYER_INVINCIBILITY
        self.last_damage_time = time.time()
        self.last_killer_id = None
        
        self.joined_at = time.time()
        self.lobby_id = None
    
    def _get_spawn_location(self, team_id):
        for team in TEAMS_CONFIG:
            if team['id'] == team_id:
                return (team['spawn_x'], team['spawn_y'])
        return (
            random.randint(PLAYER_RADIUS, WORLD_W - PLAYER_RADIUS),
            random.randint(PLAYER_RADIUS, WORLD_H - PLAYER_RADIUS)
        )
    
    def _get_tank_by_name(self, name):
        for tank in TANKS_CONFIG:
            if tank['name'] == name:
                return tank
        return TANKS_CONFIG[0]
    
    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "x": self.x,
            "y": self.y,
            "angle": self.angle,
            "health": self.health,
            "max_health": self.max_health,
            "score": self.score,
            "kills": self.kills,
            "team": self.team,
            "tank": self.tank['name'],
            "rank": self.rank,
            "alive": self.alive,
            "state": self.state.value
        }
    
    def take_damage(self, damage, attacker_id=None):
        if not self.alive or time.time() < self.invincible_until:
            return False
        
        self.health -= damage
        self.last_damage_time = time.time()
        self.last_killer_id = attacker_id
        
        if self.health <= 0:
            self.health = 0
            self.alive = False
            self.state = PlayerState.DEAD
            self.deaths += 1
            
            if attacker_id and attacker_id in players:
                attacker = players[attacker_id]
                attacker.kills += 1
                attacker.score += 25
                
                # Kill/Death penalty: transfer 1/4 of resources
                rank_transfer = max(1, self.rank // 4)
                score_transfer = max(1, self.score // 4)
                money_transfer = max(1, self.money // 4)
                
                attacker.rank += rank_transfer
                attacker.score += score_transfer
                attacker.money += money_transfer
                
                self.rank = max(1, self.rank - rank_transfer)
                self.score = max(0, self.score - score_transfer)
                self.money = max(0, self.money - money_transfer)
            
            return True
        return False

# ==================== BLOB CLASS ====================
class Blob:
    def __init__(self, blob_id, x, y, blob_type=None):
        if blob_type is None:
            blob_type = random.choice(list(BLOB_TYPES.keys()))
        
        self.id = blob_id
        self.type = blob_type
        self.x = x
        self.y = y
        
        blob_data = BLOB_TYPES[blob_type]
        self.hp = blob_data['hp']
        self.max_hp = blob_data['hp']
        self.reward = blob_data['reward']
        self.radius = BULLET_RADIUS * 2
        self.created_at = time.time()
    
    def to_dict(self):
        return {
            "id": self.id,
            "type": self.type,
            "x": self.x,
            "y": self.y,
            "hp": self.hp,
            "max_hp": self.max_hp,
            "reward": self.reward
        }

# ==================== BULLET CLASS ====================
class Bullet:
    def __init__(self, bullet_id, x, y, vx, vy, owner_id, owner_team):
        self.id = bullet_id
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.owner_id = owner_id
        self.owner_team = owner_team
        self.radius = BULLET_RADIUS
        self.created_at = time.time()
    
    def update(self):
        self.x += self.vx
        self.y += self.vy
        return (self.x < 0 or self.x > WORLD_W or 
                self.y < 0 or self.y > WORLD_H or
                time.time() - self.created_at > BULLET_MAX_LIFETIME)
    
    def to_dict(self):
        return {
            "id": self.id,
            "x": self.x,
            "y": self.y,
            "owner_id": self.owner_id,
            "radius": self.radius
        }

# ==================== LOBBY CLASS ====================
class Lobby:
    def __init__(self, lobby_id, game_mode, max_players=32):
        self.id = lobby_id
        self.game_mode = game_mode
        self.max_players = max_players
        self.players = {}
        self.state = LobbyState.WAITING
        self.created_at = datetime.now()
        self.started_at = None
        self.teams = {i: [] for i in range(1, NUM_TEAMS + 1)}
        self.team_scores = {i: 0 for i in range(1, NUM_TEAMS + 1)}
        self.spectators = set()
    
    def add_player(self, player_id, player_obj):
        if len(self.players) >= self.max_players:
            return False
        self.players[player_id] = player_obj
        return True
    
    def remove_player(self, player_id):
        if player_id in self.players:
            player = self.players[player_id]
            team = player.team
            if team in self.teams and player_id in self.teams[team]:
                self.teams[team].remove(player_id)
            del self.players[player_id]
            return True
        if player_id in self.spectators:
            self.spectators.remove(player_id)
            return True
        return False
    
    def start_game(self):
        self.state = LobbyState.IN_PROGRESS
        self.started_at = datetime.now()
    
    def get_status(self):
        return {
            "lobby_id": self.id,
            "game_mode": self.game_mode,
            "state": self.state.value,
            "players_count": len(self.players),
            "max_players": self.max_players,
            "players": {pid: p.to_dict() for pid, p in self.players.items()},
            "teams": self.teams,
            "team_scores": self.team_scores,
            "created_at": str(self.created_at)
        }

# ==================== GAME STATE ====================
players = {}
lobbies = {}
blobs = []
bullets = []
chat_messages = []

next_player_id = 1
next_blob_id = 1
next_bullet_id = 1
next_lobby_id = 1

clients = {}
player_chat_cooldown = {}
anti_cheat_flags = defaultdict(int)
day_night_cycle_start = time.time()

# ==================== HELPER FUNCTIONS ====================
def get_msg(key, **kwargs):
    msg = MESSAGES.get(key, key)
    for k, v in kwargs.items():
        msg = msg.replace(f"{{{k}}}", str(v))
    return msg

def distance(x1, y1, x2, y2):
    return math.sqrt((x1 - x2)**2 + (y1 - y2)**2)

def calculate_direction_vector(angle):
    return math.cos(angle), math.sin(angle)

def get_day_night_cycle():
    if not DAY_NIGHT_ENABLED:
        return True, 0, 1.0
    
    cycle_total = DAY_DURATION + NIGHT_DURATION
    elapsed = (time.time() - day_night_cycle_start) % cycle_total
    
    is_day = elapsed < DAY_DURATION
    cycle_progress = elapsed / (DAY_DURATION if is_day else NIGHT_DURATION)
    brightness = 1.0 if is_day else 0.5
    
    return is_day, elapsed, brightness

# ==================== BROADCAST ====================
async def broadcast(message, exclude_id=None, target_ids=None):
    targets = target_ids if target_ids else clients.keys()
    dead_clients = []
    
    for player_id in targets:
        if exclude_id and player_id == exclude_id:
            continue
        if player_id not in clients:
            continue
        
        try:
            await clients[player_id].send(json.dumps(message))
        except:
            dead_clients.append(player_id)
    
    # Handle dead clients without calling disconnect_player to avoid recursion
    for player_id in dead_clients:
        if player_id in players:
            player = players[player_id]
            if player.lobby_id in lobbies:
                lobbies[player.lobby_id].remove_player(player_id)
            del players[player_id]
        if player_id in clients:
            try:
                await clients[player_id].close()
            except:
                pass
            del clients[player_id]

async def broadcast_state():
    is_day, cycle_time, brightness = get_day_night_cycle()
    
    state = {
        "type": "state",
        "timestamp": time.time(),
        "players": [p.to_dict() for p in players.values()],
        "blobs": [b.to_dict() for b in blobs],
        "bullets": [b.to_dict() for b in bullets],
        "day_night": {
            "is_day": is_day,
            "cycle_time": cycle_time,
            "brightness": brightness
        }
    }
    await broadcast(state)

# ==================== MESSAGE HANDLERS ====================
async def handle_move(player_id, data):
    if player_id not in players:
        return
    
    player = players[player_id]
    if not player.alive:
        return
    
    if ANTI_CHEAT and ANTI_CHEAT.check_speed_hack(player_id, data.get('x', player.x), 
                                                   data.get('y', player.y)):
        anti_cheat_flags[player_id] += 1
        return
    
    vx = data.get('vx', 0)
    vy = data.get('vy', 0)
    
    speed = math.sqrt(vx**2 + vy**2)
    if speed > 0:
        vx = (vx / speed) * PLAYER_SPEED
        vy = (vy / speed) * PLAYER_SPEED
    
    player.vx = vx
    player.vy = vy
    player.angle = data.get('angle', player.angle)
    
    new_x = player.x + vx
    new_y = player.y + vy
    
    if PLAYER_RADIUS <= new_x <= WORLD_W - PLAYER_RADIUS:
        player.x = new_x
    if PLAYER_RADIUS <= new_y <= WORLD_H - PLAYER_RADIUS:
        player.y = new_y

async def handle_shoot(player_id, data):
    global next_bullet_id
    
    if player_id not in players:
        return
    
    player = players[player_id]
    if not player.alive:
        return
    
    current_time = time.time()
    fire_rate = player.tank['stats'].get('fire_rate', 0.1)
    
    if current_time - player.last_shot_time < fire_rate:
        return
    
    if ANTI_CHEAT and not ANTI_CHEAT.check_rate_limit(player_id, 'shoot'):
        anti_cheat_flags[player_id] += 1
        return
    
    player.last_shot_time = current_time
    
    angle = data.get('angle', 0)
    vx, vy = calculate_direction_vector(angle)
    
    bullet = Bullet(next_bullet_id, player.x, player.y,
                   vx * BULLET_SPEED, vy * BULLET_SPEED,
                   player_id, player.team)
    
    bullets.append(bullet)
    next_bullet_id += 1

async def handle_chat(player_id, data):
    if player_id not in players or not CHAT_ENABLED:
        return
    
    current_time = time.time()
    cooldown = 1.0 / CHAT_LIMIT
    if current_time - player_chat_cooldown.get(player_id, 0) < cooldown:
        return
    
    player_chat_cooldown[player_id] = current_time
    
    message = data.get('message', '').strip()
    if not message or len(message) > CHAT_MAX_LENGTH:
        return
    
    player = players[player_id]
    chat_msg = {
        "type": "chat",
        "player_id": player_id,
        "username": player.username,
        "team": player.team,
        "message": message,
        "timestamp": current_time
    }
    
    chat_messages.append(chat_msg)
    if len(chat_messages) > 100:
        chat_messages.pop(0)
    
    await broadcast(chat_msg)

async def handle_buy_tank(player_id, data):
    if player_id not in players:
        return
    
    player = players[player_id]
    tank_name = data.get('tank_name')
    
    tank = next((t for t in TANKS_CONFIG if t['name'] == tank_name), None)
    if not tank:
        return
    
    if player.money < tank['cost']:
        await clients[player_id].send(json.dumps({
            "type": "error",
            "message": "Not enough money"
        }))
        return
    
    player.money -= tank['cost']
    player.tank = tank
    
    await broadcast({
        "type": "tank_changed",
        "player_id": player_id,
        "tank": tank['name']
    })

async def handle_buy_upgrade(player_id, data):
    if player_id not in players:
        return
    
    player = players[player_id]
    upgrade_name = data.get('upgrade_name')
    
    upgrade = next((u for u in UPGRADES_CONFIG if u['name'] == upgrade_name), None)
    if not upgrade:
        return
    
    cost = UPGRADE_COST
    if player.money < cost:
        return
    
    player.money -= cost
    player.upgrades[upgrade_name] = player.upgrades.get(upgrade_name, 0) + 1
    
    await broadcast({
        "type": "upgrade_bought",
        "player_id": player_id,
        "upgrade": upgrade_name,
        "level": player.upgrades[upgrade_name]
    })

async def handle_message(player_id, raw_message):
    try:
        data = json.loads(raw_message)
        msg_type = data.get('type')
        
        if msg_type == 'move':
            await handle_move(player_id, data)
        elif msg_type == 'shoot':
            await handle_shoot(player_id, data)
        elif msg_type == 'chat':
            await handle_chat(player_id, data)
        elif msg_type == 'buy_tank':
            await handle_buy_tank(player_id, data)
        elif msg_type == 'buy_upgrade':
            await handle_buy_upgrade(player_id, data)
        elif msg_type == 'ping':
            if player_id in clients:
                await clients[player_id].send(json.dumps({"type": "pong"}))
    except json.JSONDecodeError:
        pass
    except Exception as e:
        print(f"Error: {e}")

async def disconnect_player(player_id):
    if player_id in players:
        player = players[player_id]
        
        if player.lobby_id in lobbies:
            lobbies[player.lobby_id].remove_player(player_id)
        
        await broadcast({
            "type": "player_left",
            "player_id": player_id,
            "username": player.username
        })
        
        del players[player_id]
    
    if player_id in clients:
        try:
            await clients[player_id].close()
        except:
            pass
        del clients[player_id]

# ==================== LOGIN SERVER ====================
async def handle_login_client(websocket, path):
    try:
        message = await websocket.recv()
        data = json.loads(message)
        action = data.get('action')
        
        if action == 'register':
            username = data.get('username', '').strip()
            email = data.get('email', '').strip()
            password = data.get('password', '')
            
            is_guest = username.startswith('guest_')
            
            if not username:
                await websocket.send(json.dumps({"success": False, "error": "Missing username"}))
                return
            
            if not is_guest and (not email or not password):
                await websocket.send(json.dumps({"success": False, "error": "Missing fields"}))
                return
            
            if len(username) < 6 or len(username) > 20:
                await websocket.send(json.dumps({"success": False, "error": "Username must be 6-20 characters"}))
                return
            
            if not is_guest and len(password) < 6:
                await websocket.send(json.dumps({"success": False, "error": "Password must be at least 6 characters"}))
                return
            
            existing = DB.get_one('SELECT * FROM accounts WHERE username = ?',
                                 (username,))
            if existing:
                await websocket.send(json.dumps({"success": False, "error": "Username already exists"}))
                return
            
            if not is_guest and email:
                existing_email = DB.get_one('SELECT * FROM accounts WHERE email = ?',
                                           (email,))
                if existing_email:
                    await websocket.send(json.dumps({"success": False, "error": "Email already exists"}))
                    return
            
            user_id = str(uuid.uuid4())
            password_hash = hash_password(password) if not is_guest else ''
            
            try:
                DB.execute(
                    'INSERT INTO accounts (user_id, username, email, password_hash, is_guest) VALUES (?, ?, ?, ?, ?)',
                    (user_id, username, email or '', password_hash, 1 if is_guest else 0)
                )
                
                DB.execute(
                    'INSERT INTO player_stats (user_id) VALUES (?)',
                    (user_id,)
                )
                
                await websocket.send(json.dumps({
                    "success": True,
                    "message": "Account created successfully",
                    "user_id": user_id,
                    "username": username
                }))
            except Exception as e:
                await websocket.send(json.dumps({"success": False, "error": str(e)}))
        
        elif action == 'login':
            username = data.get('username', '').strip()
            password = data.get('password', '')
            
            is_guest = username.startswith('guest_')
            
            if not username:
                await websocket.send(json.dumps({"success": False, "error": "Missing username"}))
                return
            
            if not is_guest and not password:
                await websocket.send(json.dumps({"success": False, "error": "Missing password"}))
                return
            
            user = DB.get_one('SELECT * FROM accounts WHERE username = ?', (username,))
            
            if not user:
                if is_guest:
                    # Create guest account
                    user_id = str(uuid.uuid4())
                    DB.execute(
                        'INSERT INTO accounts (user_id, username, email, password_hash, is_guest) VALUES (?, ?, ?, ?, ?)',
                        (user_id, username, '', '', 1)
                    )
                    DB.execute(
                        'INSERT INTO player_stats (user_id) VALUES (?)',
                        (user_id,)
                    )
                    user = DB.get_one('SELECT * FROM accounts WHERE user_id = ?', (user_id,))
                else:
                    await websocket.send(json.dumps({"success": False, "error": "Invalid credentials"}))
                    return
            
            if user['is_banned']:
                await websocket.send(json.dumps({
                    "success": False,
                    "error": f"Account banned: {user['ban_reason']}"
                }))
                return
            
            if not is_guest and hash_password(password) != user['password_hash']:
                await websocket.send(json.dumps({"success": False, "error": "Invalid credentials"}))
                return
            
            token = generate_token(user['user_id'])
            session_id = str(uuid.uuid4())
            
            DB.execute(
                'INSERT INTO sessions (session_id, user_id, token, expires_at) VALUES (?, ?, ?, ?)',
                (session_id, user['user_id'], token,
                 datetime.utcnow() + timedelta(minutes=TOKEN_EXPIRY_MINUTES))
            )
            
            DB.execute('UPDATE accounts SET last_login = ? WHERE user_id = ?',
                      (datetime.now(), user['user_id']))
            
            stats = DB.get_one('SELECT * FROM player_stats WHERE user_id = ?',
                              (user['user_id'],))
            
            await websocket.send(json.dumps({
                "success": True,
                "message": "Login successful",
                "user_id": user['user_id'],
                "username": user['username'],
                "token": token,
                "session_id": session_id,
                "stats": dict(stats) if stats else {}
            }))
        
        elif action == 'verify_token':
            token = data.get('token')
            
            if not token:
                await websocket.send(json.dumps({"success": False, "error": "No token provided"}))
                return
            
            payload = verify_token(token)
            
            if not payload:
                await websocket.send(json.dumps({"success": False, "error": "Invalid or expired token"}))
                return
            
            user = DB.get_one('SELECT * FROM accounts WHERE user_id = ?',
                             (payload['user_id'],))
            
            if not user:
                await websocket.send(json.dumps({"success": False, "error": "User not found"}))
                return
            
            await websocket.send(json.dumps({
                "success": True,
                "message": "Token valid",
                "user_id": user['user_id'],
                "username": user['username']
            }))
        
        elif action == 'claim_daily_reward':
            token = data.get('token')
            
            payload = verify_token(token)
            if not payload:
                await websocket.send(json.dumps({"success": False, "error": "Invalid token"}))
                return
            
            user_id = payload['user_id']
            today = datetime.now().date()
            
            claimed = DB.get_one(
                'SELECT * FROM daily_rewards WHERE user_id = ? AND reward_date = ?',
                (user_id, today)
            )
            
            if claimed:
                await websocket.send(json.dumps({"success": False, "error": "Already claimed today"}))
                return
            
            user = DB.get_one('SELECT * FROM accounts WHERE user_id = ?', (user_id,))
            last_claim = user['daily_reward_last_claimed']
            
            streak = user['daily_reward_streak']
            if last_claim:
                days_since = (datetime.now() - datetime.fromisoformat(str(last_claim))).days
                if days_since > 1:
                    streak = 0
            
            streak += 1
            base_reward = DAILY_REWARD_BASE
            streak_bonus = streak * 10 if streak > 1 else 0
            total_reward = base_reward + streak_bonus
            
            DB.execute(
                'INSERT INTO daily_rewards (user_id, reward_date, amount, streak_bonus) VALUES (?, ?, ?, ?)',
                (user_id, today, base_reward, streak_bonus)
            )
            
            DB.execute(
                'UPDATE accounts SET daily_reward_last_claimed = ?, daily_reward_streak = ? WHERE user_id = ?',
                (datetime.now(), streak, user_id)
            )
            
            DB.execute(
                'UPDATE player_stats SET total_money = total_money + ? WHERE user_id = ?',
                (total_reward, user_id)
            )
            
            await websocket.send(json.dumps({
                "success": True,
                "message": "Daily reward claimed",
                "reward": base_reward,
                "streak_bonus": streak_bonus,
                "total": total_reward,
                "streak": streak
            }))
        
        else:
            await websocket.send(json.dumps({"success": False, "error": "Unknown action"}))
    
    except json.JSONDecodeError:
        pass
    except Exception as e:
        print(f"Login client error: {e}")

# ==================== GAME SERVER ====================
async def handle_game_client(websocket, path):
    global next_player_id
    
    if SERVER_CLOSED:
        await websocket.close()
        return
    
    player_id = next_player_id
    next_player_id += 1
    
    try:
        # Authentication
        auth_msg = await asyncio.wait_for(websocket.recv(), timeout=5.0)
        auth_data = json.loads(auth_msg)
        
        token = auth_data.get('token')
        payload = verify_token(token)
        
        if not payload:
            await websocket.close()
            return
        
        username = auth_data.get('username', f'Player_{player_id}')
        team_id = auth_data.get('team', 1)
        
        if team_id not in range(1, NUM_TEAMS + 1):
            team_id = 1
        
        # Create player
        player = Player(player_id, username, payload['user_id'], team_id)
        players[player_id] = player
        clients[player_id] = websocket
        
        # Send welcome
        await websocket.send(json.dumps({
            "type": "welcome",
            "player_id": player_id,
            "player": player.to_dict(),
            "config": {
                "width": WIDTH,
                "height": HEIGHT,
                "world_width": WORLD_W,
                "world_height": WORLD_H,
                "player_radius": PLAYER_RADIUS,
                "bullet_radius": BULLET_RADIUS,
                "bullet_speed": BULLET_SPEED,
                "player_speed": PLAYER_SPEED,
                "tile_size": TILE_SIZE,
                "teams": NUM_TEAMS,
                "game_modes": [m['name'] for m in GAME_MODES]
            }
        }))
        
        # Broadcast player joined
        await broadcast({
            "type": "player_joined",
            "player": player.to_dict()
        }, exclude_id=player_id)
        
        print(f"Player {username} (ID: {player_id}) joined (Team {team_id})")
        
        # Message loop
        async for message in websocket:
            await handle_message(player_id, message)
    
    except asyncio.TimeoutError:
        print(f"Connection timeout: {player_id}")
    except websockets.exceptions.ConnectionClosed:
        pass
    except Exception as e:
        print(f"Game client error: {e}")
    finally:
        await disconnect_player(player_id)

# ==================== GAME LOOPS ====================
async def spawn_blobs_loop():
    global next_blob_id
    
    while True:
        try:
            await asyncio.sleep(BLOB_SPAWN_TIME)
            
            blob_counts = defaultdict(int)
            for blob in blobs:
                blob_counts[blob.type] += 1
            
            world_area = (WORLD_W // TILE_SIZE) * (WORLD_H // TILE_SIZE)
            max_total = int(world_area * MAX_BLOB_DENSITY)
            
            to_spawn = max(0, max_total - len(blobs))
            for _ in range(to_spawn):
                blob_type = random.choice(list(BLOB_TYPES.keys()))
                x = random.randint(BULLET_RADIUS * 2, WORLD_W - BULLET_RADIUS * 2)
                y = random.randint(BULLET_RADIUS * 2, WORLD_H - BULLET_RADIUS * 2)
                
                blobs.append(Blob(next_blob_id, x, y, blob_type))
                next_blob_id += 1
        except Exception as e:
            print(f"Blob spawn error: {e}")

async def update_loop():
    last_state_update = 0
    last_info_print = 0
    
    while True:
        try:
            await asyncio.sleep(1 / 60)
            current_time = time.time()
            
            if current_time - last_info_print > 10:
                print(f"[INFO] Players online: {len(players)}, Blobs: {len(blobs)}, Bullets: {len(bullets)}")
                last_info_print = current_time
            
            # Update bullets
            bullets_to_remove = []
            for bullet in list(bullets):
                if bullet.update():
                    bullets_to_remove.append(bullet)
            
            for bullet in bullets_to_remove:
                if bullet in bullets:
                    bullets.remove(bullet)
            
            # Blob-bullet collisions
            blobs_to_remove = []
            for blob in list(blobs):
                for bullet in list(bullets):
                    if distance(blob.x, blob.y, bullet.x, bullet.y) < blob.radius + bullet.radius:
                        blob.hp -= 1
                        if bullet in bullets:
                            bullets.remove(bullet)
                        
                        if blob.hp <= 0:
                            blobs_to_remove.append(blob)
                            if bullet.owner_id in players:
                                owner = players[bullet.owner_id]
                                owner.money += blob.reward
                                owner.score += blob.reward
                                owner.kills += 1
            
            for blob in blobs_to_remove:
                if blob in blobs:
                    blobs.remove(blob)
            
            # Player-player collisions
            player_list = list(players.values())
            for i, p1 in enumerate(player_list):
                if not p1.alive:
                    continue
                for p2 in player_list[i+1:]:
                    if not p2.alive:
                        continue
                    if distance(p1.x, p1.y, p2.x, p2.y) < PLAYER_RADIUS * 2:
                        damage = 5
                        p1.take_damage(damage, p2.id)
                        p2.take_damage(damage, p1.id)
            
            # Health regen
            for player in players.values():
                if player.alive and player.health < player.max_health:
                    player.health = min(player.max_health, player.health + HEALTH_REGEN)
            
            # Respawn
            for player in players.values():
                if not player.alive and current_time - player.last_damage_time > RESPAWN_TIME:
                    spawn_x, spawn_y = player._get_spawn_location(player.team)
                    player.x = spawn_x
                    player.y = spawn_y
                    player.health = player.max_health
                    player.alive = True
                    player.state = PlayerState.ALIVE
                    player.invincible_until = current_time + RESPAWN_INVINCIBILITY
            
            # Broadcast state
            if current_time - last_state_update > 0.1:
                await broadcast_state()
                last_state_update = current_time
        
        except Exception as e:
            print(f"Update error: {e}")

# ==================== MAIN ====================
async def start_login_server():
    print(f"Login server starting on {SERVER_HOST}:{LOGIN_SERVER_PORT}")
    server = await websockets.serve(handle_login_client, SERVER_HOST, LOGIN_SERVER_PORT, ping_interval=20)
    print("Login server ready!")
    return server

async def start_game_server():
    print(f"Game server starting on {SERVER_HOST}:{GAME_SERVER_PORT}")
    print(f"World size: {WORLD_W}x{WORLD_H}")
    print(f"Max players: {MAX_PLAYERS}")
    
    server = await websockets.serve(handle_game_client, SERVER_HOST, GAME_SERVER_PORT, ping_interval=20)
    print("Game server ready!")
    return server

async def main():
    # Start both servers
    login_server = await start_login_server()
    game_server = await start_game_server()
    
    # Start game loops
    asyncio.create_task(spawn_blobs_loop())
    asyncio.create_task(update_loop())
    
    print("\n✓ All servers running!")
    print("Press Ctrl+C to stop\n")
    
    # Keep running
    await asyncio.Future()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServers shutting down...")
        # Clean up guest accounts
        try:
            DB.execute('DELETE FROM accounts WHERE is_guest = 1')
            print("Guest accounts cleaned up.")
        except Exception as e:
            print(f"Error cleaning up guests: {e}")