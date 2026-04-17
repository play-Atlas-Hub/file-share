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
import os
from datetime import datetime, timedelta
from enum import Enum
from collections import defaultdict
import threading

# ==================== CONFIG LOADING ====================
def load_config():
    try:
        config_path = os.path.join(os.path.dirname(__file__), 'configs.json')
        with open(config_path, 'r') as f:
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
MAX_PLAYERS_PER_TEAM = CONFIG['server']['max_players_per_team']

# World
WIDTH = CONFIG['world']['width']
HEIGHT = CONFIG['world']['height']
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
MAX_BLOB_DENSITY = CONFIG['blobs']['max_density']
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

# Server utility config
AUTO_SAVE_INTERVAL = CONFIG['server'].get('auto_save_interval_minutes', 2) * 60
VERIFIED_SERVER_IPS = CONFIG['server'].get('verified_server_ip_list', [])
RESOURCE_TO_CURRENCY_RATIO = CONFIG['server'].get('Resource_To_Currency_Conversion_Ratio', '5:3')

# Debug
DEBUG_CONFIG = CONFIG.get('debug', {})
DEBUG_ENABLED = DEBUG_CONFIG.get('enabled', False)
DEBUG_NETWORK = DEBUG_CONFIG.get('network', False)

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
# Anti-cheat logic is disabled in this build. The server relies on game rules
# and client honesty for movement/shooting state, while still keeping the config
# available for future implementation.
ANTI_CHEAT = None

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
        
        self.tank = self._get_tank_by_name(DEFAULT_TANK)
        self.upgrades = {}
        self.last_shot_time = 0
        self.stats = self._calculate_stats()
        self.health = self.stats.get('health', PLAYER_MAX_HEALTH)
        self.max_health = self.stats.get('health', PLAYER_MAX_HEALTH)
        self.radius = self.stats.get('size', PLAYER_RADIUS)
        self.is_admin = False
        self.score = 0
        self.money = 0
        self.kills = 0
        self.assists = 0
        self.deaths = 0
        self.rank = 1
        self.resources = 0
        
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
                spawn_x = team.get('spawn_x', WORLD_W // 2)
                spawn_y = team.get('spawn_y', WORLD_H // 2)
                margin_x = team.get('spawn_margin_x', 120)
                margin_y = team.get('spawn_margin_y', 120)
                x_min = max(PLAYER_RADIUS, spawn_x - margin_x)
                x_max = min(WORLD_W - PLAYER_RADIUS, spawn_x + margin_x)
                y_min = max(PLAYER_RADIUS, spawn_y - margin_y)
                y_max = min(WORLD_H - PLAYER_RADIUS, spawn_y + margin_y)
                return (random.randint(x_min, x_max), random.randint(y_min, y_max))
        return (
            random.randint(PLAYER_RADIUS, WORLD_W - PLAYER_RADIUS),
            random.randint(PLAYER_RADIUS, WORLD_H - PLAYER_RADIUS)
        )
    
    def _get_tank_by_name(self, name):
        for tank in TANKS_CONFIG:
            if tank['name'] == name:
                return tank
        return TANKS_CONFIG[0]
    
    def _calculate_stats(self):
        stats = self.tank.get('stats', {}).copy()
        stats.setdefault('health_regen', HEALTH_REGEN)
        stats.setdefault('bullet_speed', BULLET_SPEED)
        stats.setdefault('bullet_radius', BULLET_RADIUS)
        stats.setdefault('bullet_health', 1)
        stats.setdefault('bullet_range', 200)
        stats.setdefault('fire_rate', stats.get('fire_rate', 0.1))
        stats.setdefault('damage', stats.get('damage', 1))
        stats.setdefault('speed', stats.get('speed', PLAYER_SPEED))
        stats.setdefault('body_damage', stats.get('body_damage', 10))
        stats.setdefault('size', PLAYER_RADIUS)

        for upgrade_name, level in self.upgrades.items():
            upgrade = next((u for u in UPGRADES_CONFIG if u['name'] == upgrade_name), None)
            if not upgrade:
                continue
            multiplier = upgrade.get('multiplier', 1.0) ** level
            slot = upgrade.get('slot', '')

            if slot == 'weapon_1':
                stats['bullet_health'] = stats.get('bullet_health', 1) * multiplier
                stats['bullet_range'] = stats.get('bullet_range', 200) * multiplier
            elif slot == 'weapon_2':
                stats['bullet_speed'] = stats.get('bullet_speed', BULLET_SPEED) * multiplier
            elif slot == 'weapon_3':
                stats['fire_rate'] = max(0.02, stats.get('fire_rate', 0.1) / multiplier)
            elif slot == 'weapon_4':
                stats['damage'] = stats.get('damage', 1) * multiplier
            elif slot == 'health_1':
                stats['health'] = int(stats.get('health', PLAYER_MAX_HEALTH) * multiplier)
            elif slot == 'health_2':
                stats['health_regen'] = stats.get('health_regen', HEALTH_REGEN) * multiplier
            elif slot == 'tank_1':
                stats['speed'] = stats.get('speed', PLAYER_SPEED) * multiplier
            elif slot == 'tank_2':
                stats['body_damage'] = stats.get('body_damage', 10) * multiplier

        return stats

    def recalculate_stats(self):
        self.stats = self._calculate_stats()
        self.max_health = self.stats.get('health', PLAYER_MAX_HEALTH)
        self.radius = max(5, self.stats.get('size', PLAYER_RADIUS))
        if self.health > self.max_health:
            self.health = self.max_health

    def update_rank(self):
        new_rank = self.rank
        for threshold in sorted(RANK_THRESHOLDS, key=lambda x: x.get('rank', 0)):
            if (self.resources >= threshold.get('required_money', 0) and
                self.kills >= threshold.get('required_kills', 0) and
                self.assists >= threshold.get('required_assists', 0)):
                new_rank = threshold.get('rank', new_rank)
        self.rank = new_rank
    
    def sync_resources(self):
        self.score = self.resources

    def to_dict(self):
        self.sync_resources()
        return {
            "id": self.id,
            "username": self.username,
            "x": self.x,
            "y": self.y,
            "angle": self.angle,
            "health": self.health,
            "max_health": self.max_health,
            "score": self.score,
            "resources": self.resources,
            "money": self.money,
            "kills": self.kills,
            "assists": self.assists,
            "team": self.team,
            "tank": self.tank['name'],
            "rank": self.rank,
            "alive": self.alive,
            "state": self.state.value,
            "lobby_id": self.lobby_id,
            "radius": self.radius,
            "is_admin": self.is_admin
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
                attacker.resources += 25
                attacker.sync_resources()
                attacker.update_rank()

                ratio_source, ratio_target = parse_resource_ratio(RESOURCE_TO_CURRENCY_RATIO)
                resource_transfer = max(1, self.resources // 4)
                money_transfer = max(1, int(resource_transfer * ratio_target / ratio_source))
                rank_transfer = max(1, self.rank // 4)
                
                attacker.resources += resource_transfer
                attacker.money += money_transfer
                attacker.rank += rank_transfer
                attacker.sync_resources()
                attacker.update_rank()
                
                self.rank = max(1, self.rank - rank_transfer)
                self.resources = max(0, self.resources - resource_transfer)
                self.money = max(0, self.money - money_transfer)
                self.sync_resources()
                self.update_rank()
            
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
    def __init__(self, bullet_id, x, y, vx, vy, owner_id, owner_team, health=1, radius=BULLET_RADIUS, max_range=200):
        self.id = bullet_id
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.owner_id = owner_id
        self.owner_team = owner_team
        self.health = int(max(1, health))
        self.radius = max(2, int(radius))
        self.max_range = max(50, int(max_range))
        self.created_at = time.time()
        self.distance_traveled = 0.0
    
    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.distance_traveled += math.sqrt(self.vx**2 + self.vy**2)
        return (self.x < 0 or self.x > WORLD_W or 
                self.y < 0 or self.y > WORLD_H or
                self.distance_traveled > self.max_range or
                time.time() - self.created_at > BULLET_MAX_LIFETIME or
                self.health <= 0)
    
    def to_dict(self):
        return {
            "id": self.id,
            "x": self.x,
            "y": self.y,
            "owner_id": self.owner_id,
            "owner_team": self.owner_team,
            "radius": self.radius,
            "health": self.health,
            "max_range": self.max_range
        }

# ==================== LOBBY CLASS ====================
class Lobby:
    def __init__(self, lobby_id, game_mode, max_players=64):
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
        team_id = player_obj.team
        if team_id in self.teams and player_id not in self.teams[team_id]:
            self.teams[team_id].append(player_id)
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

def parse_resource_ratio(ratio):
    try:
        left, right = ratio.split(':')
        left_val = float(left)
        right_val = float(right)
        return left_val, right_val
    except Exception:
        return 5.0, 3.0

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
        },
        "lobbies": [lobby.get_status() for lobby in lobbies.values()]
    }
    await broadcast(state)

def is_ip_allowed(websocket):
    '''
    addr = websocket.remote_address[0] if websocket.remote_address else ''
    if addr in ('127.0.0.1', '::1'):
        return True
    if '0.0.0.0' in VERIFIED_SERVER_IPS:
        return True
    return addr in VERIFIED_SERVER_IPS
    '''
    return True

def find_or_create_lobby():
    global next_lobby_id
    for lobby in lobbies.values():
        if lobby.state == LobbyState.WAITING and len(lobby.players) < lobby.max_players:
            return lobby
    lobby = Lobby(next_lobby_id, INITIAL_GAME_MODE, max_players=MAX_PLAYERS_PER_LOBBY)
    lobbies[next_lobby_id] = lobby
    next_lobby_id += 1
    return lobby


def broadcast_lobby_update(lobby):
    payload = {
        "type": "lobby_update",
        "lobby": lobby.get_status()
    }
    return broadcast(payload)

# ==================== MESSAGE HANDLERS ====================
async def handle_move(player_id, data):
    if player_id not in players:
        return
    
    player = players[player_id]
    if not player.alive:
        return
    
    vx = data.get('vx', 0)
    vy = data.get('vy', 0)
    
    speed = math.sqrt(vx**2 + vy**2)
    movement_speed = player.stats.get('speed', PLAYER_SPEED)
    if speed > 0:
        vx = (vx / speed) * movement_speed
        vy = (vy / speed) * movement_speed
    
    player.vx = vx
    player.vy = vy
    player.angle = data.get('angle', player.angle)
    
    new_x = player.x + vx
    new_y = player.y + vy
    
    if player.radius <= new_x <= WORLD_W - player.radius:
        player.x = new_x
    if player.radius <= new_y <= WORLD_H - player.radius:
        player.y = new_y

async def handle_shoot(player_id, data):
    global next_bullet_id
    
    if player_id not in players:
        return
    
    player = players[player_id]
    if not player.alive:
        return
    
    current_time = time.time()
    fire_rate = player.stats.get('fire_rate', 0.1)
    
    if current_time - player.last_shot_time < fire_rate:
        return
    
    player.last_shot_time = current_time
    
    angle = data.get('angle', 0)
    vx, vy = calculate_direction_vector(angle)
    bullet_speed = player.stats.get('bullet_speed', BULLET_SPEED)
    bullet_radius = player.stats.get('bullet_radius', BULLET_RADIUS)
    bullet_health = player.stats.get('bullet_health', 1)
    bullet_range = player.stats.get('bullet_range', 200)
    
    bullet = Bullet(
        next_bullet_id,
        player.x,
        player.y,
        vx * bullet_speed,
        vy * bullet_speed,
        player_id,
        player.team,
        health=bullet_health,
        radius=bullet_radius,
        max_range=bullet_range
    )
    
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
    player.recalculate_stats()
    player.update_rank()
    
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
    
    applicable = upgrade.get('applicable_tanks', [])
    current_tank_type = player.tank.get('type')
    if applicable and 'all' not in applicable and current_tank_type not in applicable:
        await clients[player_id].send(json.dumps({
            "type": "error",
            "message": "Upgrade not available for current tank"
        }))
        return
    
    slot = upgrade.get('slot')
    max_per_slot = CONFIG['upgrades'].get('max_per_slot', 10)
    current_level = player.upgrades.get(upgrade_name, 0)
    if current_level >= max_per_slot:
        await clients[player_id].send(json.dumps({
            "type": "error",
            "message": "Upgrade slot already at maximum"
        }))
        return
    
    cost = UPGRADE_COST
    if player.money < cost:
        await clients[player_id].send(json.dumps({
            "type": "error",
            "message": "Not enough money"
        }))
        return
    
    player.money -= cost
    player.upgrades[upgrade_name] = current_level + 1
    player.recalculate_stats()
    player.update_rank()
    
    await broadcast({
        "type": "upgrade_bought",
        "player_id": player_id,
        "upgrade": upgrade_name,
        "level": player.upgrades[upgrade_name]
    })

async def handle_admin_login(player_id, data):
    player = players.get(player_id)
    if not player:
        return

    username = data.get('username', '')
    password = data.get('password', '')
    expected = ADMIN_CREDENTIALS.get(username)

    success = expected is not None and expected == password
    player.is_admin = success

    await clients[player_id].send(json.dumps({
        "type": "admin_login_response",
        "success": success,
        "message": "Admin login successful" if success else "Invalid admin credentials",
        "is_admin": success
    }))

async def handle_admin_command(player_id, data):
    player = players.get(player_id)
    if not player or not player.is_admin:
        if player_id in clients:
            await clients[player_id].send(json.dumps({
                "type": "admin_command_response",
                "success": False,
                "message": "Admin privileges required"
            }))
        return

    command = data.get('command', '')
    payload = data.get('payload', {})
    response = {"type": "admin_command_response", "command": command, "success": False}

    if command == 'kick_player':
        target_id = payload.get('player_id')
        if target_id in players:
            await disconnect_player(target_id)
            response.update({"success": True, "message": f"Kicked player {target_id}"})
        else:
            response.update({"message": "Player not found"})

    elif command == 'broadcast':
        message = payload.get('message', 'Server message')
        await broadcast({"type": "chat", "username": "SERVER", "message": message, "team": 0, "timestamp": time.time()})
        response.update({"success": True, "message": "Broadcast sent"})

    elif command == 'spawn_blob':
        blob_type = payload.get('type', None)
        if blob_type not in BLOB_TYPES:
            response.update({"message": "Invalid blob type"})
        else:
            global next_blob_id
            x = random.randint(BULLET_RADIUS * 2, WORLD_W - BULLET_RADIUS * 2)
            y = random.randint(BULLET_RADIUS * 2, WORLD_H - BULLET_RADIUS * 2)
            blobs.append(Blob(next_blob_id, x, y, blob_type))
            next_blob_id += 1
            response.update({"success": True, "message": f"Spawned blob {blob_type}"})

    elif command == 'give_money':
        target_id = payload.get('player_id')
        amount = int(payload.get('amount', 0))
        if target_id in players:
            players[target_id].money += amount
            response.update({"success": True, "message": f"Added {amount} money"})
        else:
            response.update({"message": "Player not found"})

    elif command == 'give_resources':
        target_id = payload.get('player_id')
        amount = int(payload.get('amount', 0))
        if target_id in players:
            players[target_id].resources += amount
            players[target_id].sync_resources()
            players[target_id].update_rank()
            response.update({"success": True, "message": f"Added {amount} resources"})
        else:
            response.update({"message": "Player not found"})

    elif command == 'set_game_mode':
        new_mode = payload.get('mode')
        if new_mode and any(m['name'] == new_mode for m in GAME_MODES):
            lobby = lobbies.get(players[player_id].lobby_id)
            if lobby:
                lobby.game_mode = new_mode
                await broadcast_lobby_update(lobby)
                response.update({"success": True, "message": f"Lobby mode set to {new_mode}"})
            else:
                response.update({"message": "No lobby found"})
        else:
            response.update({"message": "Invalid game mode"})

    elif command == 'toggle_debug':
        DEBUG_CONFIG['enabled'] = not DEBUG_CONFIG.get('enabled', False)
        response.update({"success": True, "message": f"Debug enabled = {DEBUG_CONFIG['enabled']}"})

    elif command == 'set_player_health':
        target_id = payload.get('player_id')
        health = int(payload.get('health', 100))
        if target_id in players:
            players[target_id].health = min(health, players[target_id].max_health)
            response.update({"success": True, "message": f"Set player {target_id} health to {health}"})
        else:
            response.update({"message": "Player not found"})

    elif command == 'teleport_player':
        target_id = payload.get('player_id')
        x = int(payload.get('x', 0))
        y = int(payload.get('y', 0))
        if target_id in players:
            players[target_id].x = x
            players[target_id].y = y
            response.update({"success": True, "message": f"Teleported player {target_id} to ({x}, {y})"})
        else:
            response.update({"message": "Player not found"})

    elif command == 'spawn_blob_at':
        blob_type = payload.get('type')
        x = int(payload.get('x', WORLD_W // 2))
        y = int(payload.get('y', WORLD_H // 2))
        if blob_type not in BLOB_TYPES:
            response.update({"message": "Invalid blob type"})
        else:
            # global next_blob_id
            blobs.append(Blob(next_blob_id, x, y, blob_type))
            next_blob_id += 1
            response.update({"success": True, "message": f"Spawned {blob_type} at ({x}, {y})"})

    elif command == 'clear_blobs':
        blobs.clear()
        response.update({"success": True, "message": "Cleared all blobs"})

    elif command == 'set_day_night':
        is_day = payload.get('is_day', True)
        global day_night_cycle_start
        day_night_cycle_start = time.time() - (DAY_DURATION if is_day else DAY_DURATION + NIGHT_DURATION)
        response.update({"success": True, "message": f"Set time to {'day' if is_day else 'night'}"})

    elif command == 'kill_player':
        target_id = payload.get('player_id')
        if target_id in players:
            players[target_id].health = 0
            players[target_id].alive = False
            players[target_id].state = PlayerState.DEAD
            response.update({"success": True, "message": f"Killed player {target_id}"})
        else:
            response.update({"message": "Player not found"})

    elif command == 'give_upgrade':
        target_id = payload.get('player_id')
        upgrade_name = payload.get('upgrade')
        level = int(payload.get('level', 1))
        if target_id in players and upgrade_name in [u['Name'] for u in UPGRADES_CONFIG]:
            players[target_id].upgrades[upgrade_name] = level
            players[target_id].recalculate_stats()
            response.update({"success": True, "message": f"Gave {upgrade_name} level {level} to player {target_id}"})
        else:
            response.update({"message": "Player or upgrade not found"})

    elif command == 'reset_player':
        target_id = payload.get('player_id')
        if target_id in players:
            player = players[target_id]
            player.health = player.max_health
            player.money = 0
            player.resources = 0
            player.kills = 0
            player.deaths = 0
            player.assists = 0
            player.rank = 1
            player.upgrades = {}
            player.recalculate_stats()
            response.update({"success": True, "message": f"Reset player {target_id}"})
        else:
            response.update({"message": "Player not found"})

    elif command == 'server_stats':
        stats = {
            "players": len(players),
            "blobs": len(blobs),
            "bullets": len(bullets),
            "lobbies": len(lobbies),
            "uptime": time.time() - day_night_cycle_start
        }
        response.update({"success": True, "message": "Server stats", "stats": stats})

    else:
        response.update({"message": "Unknown admin command"})

    if player_id in clients:
        await clients[player_id].send(json.dumps(response))

async def handle_message(player_id, raw_message):  # need to add commands and debug/admin tools/msg types
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
        elif msg_type == 'admin_login':
            await handle_admin_login(player_id, data)
        elif msg_type == 'admin_command':
            await handle_admin_command(player_id, data)
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
            lobby = lobbies[player.lobby_id]
            lobby.remove_player(player_id)
            if not lobby.players and not lobby.spectators:
                del lobbies[player.lobby_id]
            else:
                await broadcast_lobby_update(lobby)
        
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
            """
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
            """
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
        
        if not is_ip_allowed(websocket):
            await websocket.send(json.dumps({"type": "error", "message": "IP not allowed"}))
            await websocket.close()
            return

        # Create player
        player = Player(player_id, username, payload['user_id'], team_id)
        lobby = find_or_create_lobby()
        lobby.add_player(player_id, player)
        player.lobby_id = lobby.id
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
                "bullet_speed": BULLET_SPEED,  # needs to be based on tank stats and upgrades
                "player_speed": PLAYER_SPEED,  # needs to be based on tank stats and upgrades
                "teams": NUM_TEAMS,
                "game_modes": [m['name'] for m in GAME_MODES]
            }
        }))

        await websocket.send(json.dumps({
            "type": "server_config",
            "tanks": {"list": TANKS_CONFIG},
            "tanks_paths": CONFIG.get('tank').get('paths'),
            "upgrades": {"list": UPGRADES_CONFIG, "cost_per_upgrade": UPGRADE_COST},
            "ranks": {"thresholds": RANK_THRESHOLDS},
            "player": {"radius": PLAYER_RADIUS, "barrel_length": 25, "shot_cooldown": 0.1},
            "world": {"width": WIDTH, "height": HEIGHT, "screens_x": WORLD_SCREENS_X, "screens_y": WORLD_SCREENS_Y},
            "display": CONFIG.get('display', {})
        }))

        await websocket.send(json.dumps({
            "type": "lobby_update",
            "lobby": lobby.get_status()
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
            
            world_area = (WORLD_W) * (WORLD_H)
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
    last_time = time.time()

    while True:
        try:
            await asyncio.sleep(1 / 60)
            current_time = time.time()
            delta = current_time - last_time
            last_time = current_time

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
                        bullet.health -= 1
                        if bullet.health <= 0 and bullet in bullets:
                            bullets.remove(bullet)

                        if blob.hp <= 0:
                            blobs_to_remove.append(blob)
                            if bullet.owner_id in players:
                                owner = players[bullet.owner_id]
                                owner.money += blob.reward
                                owner.resources += blob.reward
                                owner.sync_resources()
                                owner.update_rank()

            for blob in blobs_to_remove:
                if blob in blobs:
                    blobs.remove(blob)

            # Player-blob collisions
            for blob in list(blobs):
                for player in list(players.values()):
                    if not player.alive:
                        continue
                    if distance(blob.x, blob.y, player.x, player.y) < blob.radius + player.radius:
                        player.take_damage(1)  # Should damage be adjusted based on blob type?
                        blob.hp -= 1
                        if blob.hp <= 0:
                            if blob in blobs:
                                blobs.remove(blob)
                            player.money += blob.reward
                            player.resources += blob.reward
                            player.sync_resources()
                            player.update_rank()
                        break  # Only one player collects per blob per tick

            # Player-bullet collisions
            bullets_to_remove = []
            for bullet in list(bullets):
                if bullet.owner_id not in players:
                    continue
                owner = players[bullet.owner_id]
                lobby = lobbies.get(owner.lobby_id)
                team_match = lobby and any(
                    mode.get('name') == lobby.game_mode and mode.get('teams', 0) > 0
                    for mode in GAME_MODES
                )
                for player in list(players.values()):
                    if not player.alive or player.id == bullet.owner_id:
                        continue
                    if distance(player.x, player.y, bullet.x, bullet.y) < player.radius + bullet.radius:
                        if team_match and player.team == bullet.owner_team:
                            continue
                        damage = owner.stats.get('damage', 1)
                        killed = player.take_damage(damage, bullet.owner_id)
                        bullet.health -= 1
                        if killed and lobby and lobby.game_mode != 'Free For All':
                            lobby.team_scores.setdefault(owner.team, 0)
                            lobby.team_scores[owner.team] += 1
                            await broadcast_lobby_update(lobby)
                        if bullet.health <= 0 and bullet in bullets:
                            bullets_to_remove.append(bullet)
                        break

            for bullet in bullets_to_remove:
                if bullet in bullets:
                    bullets.remove(bullet)

            # Player-player collisions, add player to blob collisions... are we missing player-bullet/bullet-player collisions?
            player_list = list(players.values())
            for i, p1 in enumerate(player_list):
                if not p1.alive:
                    continue
                for p2 in player_list[i+1:]:
                    if not p2.alive:
                        continue
                    if distance(p1.x, p1.y, p2.x, p2.y) < p1.radius + p2.radius:
                        damage = max(1, int((p1.stats.get('body_damage', 10) + p2.stats.get('body_damage', 10)) / 2))
                        p1.take_damage(damage, p2.id)
                        p2.take_damage(damage, p1.id)

            # Health regen
            for player in players.values():
                if player.alive and player.health < player.max_health:
                    player.regen_timer += delta
                    if player.regen_timer >= player.regen_cooldown:
                        player.regen_timer = 0.0
                        player.health = min(player.max_health, player.health + player.regen)

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
