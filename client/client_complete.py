import pygame
import websockets
import json
import asyncio
import math
import sys
import time
import threading
import hashlib
from enum import Enum
from typing import Dict, List, Tuple, Optional
import numpy as np
from datetime import datetime, timedelta

# ==================== PYGAME SETUP ====================
pygame.init()
pygame.mixer.init()

# Load client config
try:
    with open('client_configs.json', 'r') as f:
        CLIENT_CONFIG = json.load(f)
except FileNotFoundError:
    print("ERROR: client_configs.json not found!")
    sys.exit(1)

SCREEN_WIDTH = CLIENT_CONFIG['display']['width']
SCREEN_HEIGHT = CLIENT_CONFIG['display']['height']
FPS = CLIENT_CONFIG['display']['fps']
GRID_VISIBLE = CLIENT_CONFIG['display']['grid_visible']
FULLSCREEN = CLIENT_CONFIG['display']['fullscreen']

flags = pygame.FULLSCREEN if FULLSCREEN else 0
screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), flags)
pygame.display.set_caption("Tank Battle Arena")
clock = pygame.time.Clock()

# Font cache
font_large = pygame.font.Font(None, 48)
font_medium = pygame.font.Font(None, 32)
font_small = pygame.font.Font(None, 24)
font_tiny = pygame.font.Font(None, 16)

# ==================== TEXT CACHING ====================
class TextCache:
    """Cache rendered text surfaces for performance"""
    def __init__(self):
        self.cache = {}
    
    def get(self, text, font, color):
        key = (text, id(font), color)
        if key not in self.cache:
            self.cache[key] = font.render(text, True, color)
        return self.cache[key]
    
    def clear(self):
        self.cache.clear()

text_cache = TextCache()

# ==================== ENUMS ====================
class GameState(Enum):
    CONNECTING = "connecting"
    LOGIN = "login"
    REGISTER = "register"
    LOBBY = "lobby"
    PLAYING = "playing"
    DEAD = "dead"
    SPECTATING = "spectating"
    MENU = "menu"

class PlayerState(Enum):
    ALIVE = "alive"
    DEAD = "dead"
    SPECTATING = "spectating"

# ==================== VECTOR CLASS ====================
class Vector2:
    def __init__(self, x=0, y=0):
        self.x = x
        self.y = y
    
    def __add__(self, other):
        return Vector2(self.x + other.x, self.y + other.y)
    
    def __sub__(self, other):
        return Vector2(self.x - other.x, self.y - other.y)
    
    def __mul__(self, scalar):
        return Vector2(self.x * scalar, self.y * scalar)
    
    def distance_to(self, other):
        return math.sqrt((self.x - other.x)**2 + (self.y - other.y)**2)
    
    def normalize(self):
        length = math.sqrt(self.x**2 + self.y**2)
        if length > 0:
            return Vector2(self.x / length, self.y / length)
        return Vector2(0, 0)
    
    def angle(self):
        return math.atan2(self.y, self.x)
    
    def to_tuple(self):
        return (int(self.x), int(self.y))

# ==================== INPUT MANAGER ====================
class InputManager:
    def __init__(self, config):
        self.config = config['keyboard']
        self.keys = {}
        self.mouse_pos = (0, 0)
        self.mouse_buttons = {}
        self.key_map = self._create_key_map()
        self.key_pressed_last_frame = set()
    
    def _create_key_map(self):
        key_map = {
            'W': pygame.K_w, 'S': pygame.K_s, 'A': pygame.K_a, 'D': pygame.K_d,
            'Q': pygame.K_q, 'E': pygame.K_e, 'R': pygame.K_r, 'T': pygame.K_t,
            'Z': pygame.K_z, 'F': pygame.K_f, 'TAB': pygame.K_TAB,
            'SHIFT': pygame.K_LSHIFT, 'SPACE': pygame.K_SPACE,
            'RETURN': pygame.K_RETURN, 'ESCAPE': pygame.K_ESCAPE
        }
        return key_map
    
    def update(self):
        self.keys = pygame.key.get_pressed()
        self.mouse_pos = pygame.mouse.get_pos()
        self.mouse_buttons = pygame.mouse.get_pressed()
    
    def is_pressed(self, action):
        key_name = self.config.get(action)
        if not key_name:
            return False
        if key_name == 'MOUSE_LEFT':
            return self.mouse_buttons[0]
        key_const = self.key_map.get(key_name)
        return self.keys[key_const] if key_const else False
    
    def is_pressed_once(self, action):
        """Check if key pressed this frame (not held)"""
        is_pressed_now = self.is_pressed(action)
        was_pressed_last = action in self.key_pressed_last_frame
        
        if is_pressed_now and not was_pressed_last:
            self.key_pressed_last_frame.add(action)
            return True
        elif not is_pressed_now:
            self.key_pressed_last_frame.discard(action)
        
        return False
    
    def get_direction(self):
        direction = Vector2(0, 0)
        if self.is_pressed('right'):
            direction.x += 1
        if self.is_pressed('left'):
            direction.x -= 1
        if self.is_pressed('down'):
            direction.y += 1
        if self.is_pressed('up'):
            direction.y -= 1
        normalized = direction.normalize()
        return normalized if (direction.x or direction.y) else Vector2(0, 0)
    
    def get_mouse_angle(self):
        return math.atan2(self.mouse_pos[1] - SCREEN_HEIGHT/2, 
                         self.mouse_pos[0] - SCREEN_WIDTH/2)

# ==================== GAME OBJECTS ====================
class RemotePlayer:
    def __init__(self, player_id, username, x, y, team, tank_name, rank=1):
        self.id = player_id
        self.username = username
        self.x = x
        self.y = y
        self.angle = 0
        self.team = team
        self.tank_name = tank_name
        self.health = 100
        self.max_health = 100
        self.is_alive = True
        self.score = 0
        self.rank = rank
        self.last_update = time.time()
        self.kill_count = 0
    
    def update(self, data):
        self.x = data.get('x', self.x)
        self.y = data.get('y', self.y)
        self.angle = data.get('angle', self.angle)
        self.health = data.get('health', self.health)
        self.max_health = data.get('max_health', self.max_health)
        self.is_alive = data.get('alive', True)
        self.score = data.get('score', self.score)
        self.rank = data.get('rank', self.rank)
        self.last_update = time.time()
    
    def draw(self, surface, camera_pos, player_team):
        if not self.is_alive:
            return
        
        screen_x = self.x - camera_pos[0] + SCREEN_WIDTH/2
        screen_y = self.y - camera_pos[1] + SCREEN_HEIGHT/2
        
        if screen_x < -100 or screen_x > SCREEN_WIDTH + 100 or \
           screen_y < -100 or screen_y > SCREEN_HEIGHT + 100:
            return
        
        # Determine color
        if self.team == player_team:
            color = tuple(CLIENT_CONFIG['colors']['player_teammate'])
        else:
            color = tuple(CLIENT_CONFIG['colors']['player_enemy'])
        
        # Draw tank body
        radius = 15
        pygame.draw.circle(surface, color, (int(screen_x), int(screen_y)), radius)
        pygame.draw.circle(surface, (255, 255, 255), (int(screen_x), int(screen_y)), radius, 2)
        
        # Draw barrel
        barrel_length = 25
        barrel_x = screen_x + math.cos(self.angle) * barrel_length
        barrel_y = screen_y + math.sin(self.angle) * barrel_length
        pygame.draw.line(surface, color, (screen_x, screen_y), 
                        (barrel_x, barrel_y), 4)
        
        # Draw name
        if CLIENT_CONFIG['gameplay']['show_names']:
            name_text = text_cache.get(self.username, font_tiny, (255, 255, 255))
            surface.blit(name_text, (int(screen_x - name_text.get_width()/2), int(screen_y - 35)))
        
        # Draw health bar
        if CLIENT_CONFIG['gameplay']['show_health_bars']:
            health_width = 40
            health_height = 5
            health_ratio = max(0, self.health / self.max_health)
            pygame.draw.rect(surface, (100, 255, 100), 
                           (int(screen_x - health_width/2), int(screen_y + 25), 
                            int(health_width * health_ratio), health_height))
            pygame.draw.rect(surface, (255, 255, 255), 
                           (int(screen_x - health_width/2), int(screen_y + 25), 
                            health_width, health_height), 1)

class Blob:
    def __init__(self, blob_id, x, y, blob_type, hp, reward):
        self.id = blob_id
        self.x = x
        self.y = y
        self.type = blob_type
        self.hp = hp
        self.max_hp = hp
        self.reward = reward
        self.radius = 8
    
    def update(self, data):
        self.x = data.get('x', self.x)
        self.y = data.get('y', self.y)
        self.hp = data.get('hp', self.hp)
    
    def draw(self, surface, camera_pos):
        screen_x = self.x - camera_pos[0] + SCREEN_WIDTH/2
        screen_y = self.y - camera_pos[1] + SCREEN_HEIGHT/2
        
        if screen_x < -50 or screen_x > SCREEN_WIDTH + 50 or \
           screen_y < -50 or screen_y > SCREEN_HEIGHT + 50:
            return
        
        color_key = f'blob_{self.type}'
        color = tuple(CLIENT_CONFIG['colors'].get(color_key, [200, 200, 200]))
        
        if self.type == 'circle':
            pygame.draw.circle(surface, color, (int(screen_x), int(screen_y)), self.radius)
        elif self.type == 'triangle':
            points = [
                (screen_x, screen_y - self.radius),
                (screen_x + self.radius, screen_y + self.radius),
                (screen_x - self.radius, screen_y + self.radius)
            ]
            pygame.draw.polygon(surface, color, points)
        elif self.type == 'square':
            pygame.draw.rect(surface, color, 
                           (int(screen_x - self.radius), int(screen_y - self.radius), 
                            self.radius*2, self.radius*2))

class Bullet:
    def __init__(self, bullet_id, x, y, owner_id):
        self.id = bullet_id
        self.x = x
        self.y = y
        self.owner_id = owner_id
        self.radius = 3
        self.creation_time = time.time()
    
    def draw(self, surface, camera_pos):
        screen_x = self.x - camera_pos[0] + SCREEN_WIDTH/2
        screen_y = self.y - camera_pos[1] + SCREEN_HEIGHT/2
        
        if -50 < screen_x < SCREEN_WIDTH + 50 and -50 < screen_y < SCREEN_HEIGHT + 50:
            pygame.draw.circle(surface, (255, 255, 100), (int(screen_x), int(screen_y)), self.radius)

# ==================== MENU SYSTEM ====================
class MenuItem:
    def __init__(self, title, action=None):
        self.title = title
        self.action = action
        self.submenu = None
    
    def execute(self, game):
        if self.action:
            self.action(game)
        return True

class Menu:
    def __init__(self, game):
        self.game = game
        self.active = False
        self.current_menu = None
        self.selected_option = 0
        self.menus = {}
        self.visible_text = []
        self.init_menus()
    
    def init_menus(self):
        # Main menu
        self.menus['main'] = [
            MenuItem("Resume Game", self.resume_game),
            MenuItem("Tank Upgrades (Q)", self.show_tank_upgrades),
            MenuItem("Skill Upgrades (E)", self.show_skill_upgrades),
            MenuItem("Tank Index", self.show_tank_index),
            MenuItem("Skill Index", self.show_skill_index),
            MenuItem("Rank Index", self.show_rank_index),
            MenuItem("Profile", self.show_profile),
            MenuItem("Settings", self.show_settings),
            MenuItem("Tutorial", self.show_tutorial),
            MenuItem("Disconnect", self.disconnect),
            MenuItem("Quit to Desktop", self.quit_game)
        ]
        
        # Tank upgrades menu (placeholder)
        self.menus['tank_upgrades'] = [
            MenuItem("Back to Main", self.back_to_main),
        ]
        
        # Skill upgrades menu (placeholder)
        self.menus['skill_upgrades'] = [
            MenuItem("Back to Main", self.back_to_main),
        ]
        
        self.current_menu = 'main'
    
    def toggle(self):
        self.active = not self.active
        self.selected_option = 0
    
    def handle_input(self, input_manager):
        if not self.active:
            return
        
        keys = pygame.key.get_pressed()
        if keys[pygame.K_UP]:
            self.selected_option = (self.selected_option - 1) % len(self.menus[self.current_menu])
        if keys[pygame.K_DOWN]:
            self.selected_option = (self.selected_option + 1) % len(self.menus[self.current_menu])
        if keys[pygame.K_RETURN]:
            item = self.menus[self.current_menu][self.selected_option]
            item.execute(self.game)
    
    def draw(self, surface):
        if not self.active:
            return
        
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
        overlay.set_alpha(200)
        overlay.fill((0, 0, 0))
        surface.blit(overlay, (0, 0))
        
        title_text = text_cache.get(f"MENU - {self.current_menu.upper()}", font_large, (100, 255, 100))
        surface.blit(title_text, (SCREEN_WIDTH//2 - title_text.get_width()//2, 50))
        
        y_offset = 150
        for i, item in enumerate(self.menus[self.current_menu]):
            color = (100, 255, 100) if i == self.selected_option else (200, 200, 200)
            text = text_cache.get(item.title, font_medium, color)
            surface.blit(text, (SCREEN_WIDTH//2 - text.get_width()//2, y_offset + i*50))
        
        instructions = text_cache.get("↑/↓ Navigate | ENTER Select | ESC Close", font_tiny, (150, 150, 150))
        surface.blit(instructions, (SCREEN_WIDTH//2 - instructions.get_width()//2, SCREEN_HEIGHT - 50))
    
    # Menu actions
    def resume_game(self, game):
        self.active = False
    
    def show_tank_upgrades(self, game):
        self.current_menu = 'tank_upgrades'
    
    def show_skill_upgrades(self, game):
        self.current_menu = 'skill_upgrades'
    
    def show_tank_index(self, game):
        pass
    
    def show_skill_index(self, game):
        pass
    
    def show_rank_index(self, game):
        pass
    
    def show_profile(self, game):
        pass
    
    def show_settings(self, game):
        pass
    
    def show_tutorial(self, game):
        pass
    
    def back_to_main(self, game):
        self.current_menu = 'main'
    
    def disconnect(self, game):
        game.game_client.disconnect()
        game.game_state = GameState.LOGIN
    
    def quit_game(self, game):
        game.running = False

# ==================== RENDERER ====================
class Renderer:
    def __init__(self, screen_width, screen_height):
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.grid_surface = self.create_grid()
    
    def create_grid(self):
        grid_surface = pygame.Surface((self.screen_width, self.screen_height))
        grid_surface.fill((20, 20, 20))
        grid_size = 50
        
        for x in range(0, self.screen_width, grid_size):
            pygame.draw.line(grid_surface, (60, 60, 60), (x, 0), (x, self.screen_height), 1)
        for y in range(0, self.screen_height, grid_size):
            pygame.draw.line(grid_surface, (60, 60, 60), (0, y), (self.screen_width, y), 1)
        
        return grid_surface
    
    def draw_world(self, surface, players, blobs, bullets, camera_pos, brightness):
        surface.fill((20, 20, 20))
        
        # Day/night overlay
        day_color = CLIENT_CONFIG['colors']['day_color']
        night_color = CLIENT_CONFIG['colors']['night_color']
        blend_color = tuple(
            int(day_color[i] * brightness + night_color[i] * (1 - brightness))
            for i in range(3)
        )
        
        overlay = pygame.Surface((self.screen_width, self.screen_height))
        overlay.set_alpha(int(50 * (1 - brightness)))
        overlay.fill(blend_color)
        surface.blit(overlay, (0, 0))
        
        # Draw grid
        if GRID_VISIBLE:
            grid_offset_x = -int(camera_pos[0]) % 50
            grid_offset_y = -int(camera_pos[1]) % 50
            surface.blit(self.grid_surface, (grid_offset_x, grid_offset_y))
        
        # Draw game objects
        for blob in blobs:
            blob.draw(surface, camera_pos)
        
        for bullet in bullets:
            bullet.draw(surface, camera_pos)
        
        for player in players:
            player.draw(surface, camera_pos, 1)  # Pass actual player team
    
    def draw_hud(self, surface, player, all_players, config):
        if not player:
            return
        
        # Health bar
        health_width = 200
        health_x = 20
        health_y = 20
        health_ratio = max(0, player.get('health', 0) / max(1, player.get('max_health', 1)))
        
        pygame.draw.rect(surface, (100, 255, 100), 
                        (health_x, health_y, int(health_width * health_ratio), 20))
        pygame.draw.rect(surface, (255, 255, 255), 
                        (health_x, health_y, health_width, 20), 2)
        
        health_text = text_cache.get(
            f"Health: {player.get('health', 0):.0f}/{player.get('max_health', 100):.0f}",
            font_small, (255, 255, 255)
        )
        surface.blit(health_text, (health_x + 5, health_y + 25))
        
        # Score and stats
        y = SCREEN_HEIGHT - 120
        score_text = text_cache.get(f"Score: {player.get('score', 0)}", font_small, (100, 255, 100))
        surface.blit(score_text, (20, y))
        
        rank_text = text_cache.get(f"Rank: {player.get('rank', 1)}", font_small, (100, 255, 100))
        surface.blit(rank_text, (20, y + 40))
        
        tank_text = text_cache.get(f"Tank: {player.get('tank', 'Basic')}", font_small, (100, 100, 255))
        surface.blit(tank_text, (20, y + 80))
        
        # Draw minimap
        self.draw_minimap(surface, player, all_players)
    
    def draw_minimap(self, surface, player, players):
        minimap_size = 150
        minimap_x = SCREEN_WIDTH - minimap_size - 10
        minimap_y = 10
        
        pygame.draw.rect(surface, (0, 0, 0), 
                        (minimap_x, minimap_y, minimap_size, minimap_size))
        pygame.draw.rect(surface, (100, 100, 100), 
                        (minimap_x, minimap_y, minimap_size, minimap_size), 2)
        
        scale = minimap_size / 9280
        for p in players:
            mm_x = minimap_x + p.x * scale
            mm_y = minimap_y + p.y * scale
            
            if p.id == player.get('id'):
                pygame.draw.circle(surface, (100, 255, 100), (int(mm_x), int(mm_y)), 3)
            elif p.team == player.get('team'):
                pygame.draw.circle(surface, (100, 150, 255), (int(mm_x), int(mm_y)), 2)
            else:
                pygame.draw.circle(surface, (255, 100, 100), (int(mm_x), int(mm_y)), 2)

# ==================== WEBSOCKET CLIENT ====================
class GameClient:
    def __init__(self):
        self.game_ws = None
        self.token = None
        self.player_id = None
        self.player_data = None
        self.connected = False
        self.server_config = {}
        
        # Game data
        self.players = {}
        self.blobs = {}
        self.bullets = {}
        self.chat_messages = []
        self.day_night_info = {'is_day': True, 'brightness': 1.0}
        
        # Async
        self.server_messages = asyncio.Queue()
        self.message_lock = asyncio.Lock()
    
    async def login(self, username: str, password: str) -> bool:
        login_url = CLIENT_CONFIG['network']['login_server']
        
        try:
            async with websockets.connect(login_url, ping_interval=20) as ws:
                password_hash = hashlib.sha256(password.encode()).hexdigest()
                
                await ws.send(json.dumps({
                    'action': 'login',
                    'username': username,
                    'password': password_hash
                }))
                
                response = json.loads(await ws.recv())
                
                if response.get('success'):
                    self.token = response['token']
                    self.player_data = {
                        'user_id': response['user_id'],
                        'username': response['username'],
                        'stats': response.get('stats', {})
                    }
                    return True
                return False
        except Exception as e:
            print(f"Login error: {e}")
            return False
    
    async def register(self, username: str, email: str, password: str) -> bool:
        login_url = CLIENT_CONFIG['network']['login_server']
        
        try:
            async with websockets.connect(login_url, ping_interval=20) as ws:
                password_hash = hashlib.sha256(password.encode()).hexdigest()
                
                await ws.send(json.dumps({
                    'action': 'register',
                    'username': username,
                    'email': email,
                    'password': password_hash
                }))
                
                response = json.loads(await ws.recv())
                return response.get('success', False)
        except Exception as e:
            print(f"Register error: {e}")
            return False
    
    async def connect_to_game(self, username: str, team: int = 1) -> bool:
        game_url = CLIENT_CONFIG['network']['game_server']
        
        try:
            self.game_ws = await websockets.connect(game_url, ping_interval=20)
            self.connected = True
            
            await self.game_ws.send(json.dumps({
                'type': 'auth',
                'token': self.token,
                'username': username,
                'team': team
            }))
            
            response = json.loads(await self.game_ws.recv())
            if response['type'] == 'welcome':
                self.player_id = response['player_id']
                self.server_config = response.get('config', {})
                
                asyncio.create_task(self._receive_messages())
                return True
            
            return False
        except Exception as e:
            print(f"Connection error: {e}")
            self.connected = False
            return False
    
    async def _receive_messages(self):
        try:
            async for message in self.game_ws:
                data = json.loads(message)
                await self.server_messages.put(data)
        except websockets.exceptions.ConnectionClosed:
            self.connected = False
        except Exception as e:
            print(f"Receive error: {e}")
            self.connected = False
    
    def process_messages(self):
        while not self.server_messages.empty():
            try:
                data = self.server_messages.get_nowait()
                self._handle_message(data)
            except asyncio.QueueEmpty:
                break
    
    def _handle_message(self, data: dict):
        msg_type = data.get('type')
        
        if msg_type == 'state':
            # Update players
            for player_data in data.get('players', []):
                player_id = player_data['id']
                if player_id not in self.players:
                    self.players[player_id] = RemotePlayer(
                        player_id, player_data['username'],
                        player_data['x'], player_data['y'],
                        player_data['team'], player_data['tank'],
                        player_data.get('rank', 1)
                    )
                else:
                    self.players[player_id].update(player_data)
            
            # Update blobs
            for blob_data in data.get('blobs', []):
                blob_id = blob_data['id']
                if blob_id not in self.blobs:
                    self.blobs[blob_id] = Blob(
                        blob_id, blob_data['x'], blob_data['y'],
                        blob_data['type'], blob_data['hp'], blob_data['reward']
                    )
                else:
                    self.blobs[blob_id].update(blob_data)
            
            # Update bullets
            self.bullets.clear()
            for bullet_data in data.get('bullets', []):
                bullet_id = bullet_data['id']
                self.bullets[bullet_id] = Bullet(
                    bullet_id, bullet_data['x'], bullet_data['y'],
                    bullet_data['owner_id']
                )
            
            # Update day/night
            day_night = data.get('day_night', {})
            self.day_night_info = {
                'is_day': day_night.get('is_day', True),
                'brightness': day_night.get('brightness', 1.0)
            }
        
        elif msg_type == 'player_joined':
            player_data = data['player']
            if player_data['id'] not in self.players:
                self.players[player_data['id']] = RemotePlayer(
                    player_data['id'], player_data['username'],
                    player_data['x'], player_data['y'],
                    player_data['team'], player_data['tank'],
                    player_data.get('rank', 1)
                )
        
        elif msg_type == 'player_left':
            player_id = data['player_id']
            if player_id in self.players:
                del self.players[player_id]
        
        elif msg_type == 'chat':
            self.chat_messages.append({
                'username': data['username'],
                'message': data['message'],
                'team': data['team'],
                'timestamp': time.time()
            })
            if len(self.chat_messages) > 50:
                self.chat_messages.pop(0)
        
        elif msg_type == 'player_died':
            # Handle death logic - kill/death penalties
            killer_id = data.get('killer_id')
            victim_id = data.get('victim_id')
            
            if killer_id == self.player_id and victim_id in self.players:
                victim = self.players[victim_id]
                reward_resources = victim.rank // 4
                reward_money = victim.score // 4
                # Apply rewards (will be handled by server)
                self.chat_messages.append({
                    'username': 'SYSTEM',
                    'message': f"Killed {victim.username}! +{reward_resources} Resources +{reward_money} Money",
                    'team': 0,
                    'timestamp': time.time()
                })
    
    async def send_move(self, vx: float, vy: float):
        if self.game_ws and self.connected:
            try:
                await self.game_ws.send(json.dumps({
                    'type': 'move',
                    'vx': vx,
                    'vy': vy
                }))
            except:
                pass
    
    async def send_shoot(self, angle: float):
        if self.game_ws and self.connected:
            try:
                await self.game_ws.send(json.dumps({
                    'type': 'shoot',
                    'angle': angle
                }))
            except:
                pass
    
    async def send_chat(self, message: str):
        if self.game_ws and self.connected:
            try:
                await self.game_ws.send(json.dumps({
                    'type': 'chat',
                    'message': message
                }))
            except:
                pass
    
    def disconnect(self):
        self.connected = False
        if self.game_ws:
            asyncio.create_task(self.game_ws.close())

# ==================== LOGIN/REGISTER SCREENS ====================
class AuthScreen:
    def __init__(self, game_client, is_register=False):
        self.game_client = game_client
        self.is_register = is_register
        self.username_input = ""
        self.password_input = ""
        self.email_input = ""
        self.active_field = 0
        self.error_message = ""
        self.connecting = False
        self.max_field = 3 if is_register else 2
    
    def handle_input(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_TAB:
                self.active_field = (self.active_field + 1) % self.max_field
            elif event.key == pygame.K_BACKSPACE:
                if self.active_field == 0:
                    self.username_input = self.username_input[:-1]
                elif self.active_field == 1:
                    self.email_input = self.email_input[:-1] if self.is_register else self.password_input[:-1]
                elif self.active_field == 2 and self.is_register:
                    self.password_input = self.password_input[:-1]
            elif event.key == pygame.K_RETURN:
                asyncio.create_task(self._try_auth())
            else:
                char = event.unicode
                if char.isprintable() and len(char) == 1:
                    if self.active_field == 0:
                        self.username_input += char
                    elif self.active_field == 1:
                        if self.is_register:
                            self.email_input += char
                        else:
                            self.password_input += char
                    elif self.active_field == 2 and self.is_register:
                        self.password_input += char
    
    async def _try_auth(self):
        self.connecting = True
        self.error_message = ""
        
        try:
            if self.is_register:
                success = await self.game_client.register(
                    self.username_input, self.email_input, self.password_input
                )
                if success:
                    self.error_message = "Registration successful! Logging in..."
                    await asyncio.sleep(1)
                    success = await self.game_client.login(
                        self.username_input, self.password_input
                    )
            else:
                success = await self.game_client.login(
                    self.username_input, self.password_input
                )
            
            if success:
                if await self.game_client.connect_to_game(self.username_input):
                    return True
                else:
                    self.error_message = "Failed to connect to game server"
            else:
                self.error_message = "Authentication failed"
        except Exception as e:
            self.error_message = f"Error: {str(e)}"
        
        self.connecting = False
        return False
    
    def draw(self, surface):
        surface.fill((20, 20, 20))
        
        title = text_cache.get("TANK BATTLE ARENA", font_large, (100, 255, 100))
        surface.blit(title, (SCREEN_WIDTH//2 - title.get_width()//2, 50))
        
        screen_title = text_cache.get(
            "REGISTER" if self.is_register else "LOGIN",
            font_medium, (100, 200, 100)
        )
        surface.blit(screen_title, (SCREEN_WIDTH//2 - screen_title.get_width()//2, 120))
        
        y_pos = 200
        
        # Username
        label = text_cache.get("Username:", font_small, (200, 200, 200))
        surface.blit(label, (SCREEN_WIDTH//2 - 200, y_pos))
        
        color = (100, 255, 100) if self.active_field == 0 else (100, 100, 100)
        pygame.draw.rect(surface, color, (SCREEN_WIDTH//2 - 200, y_pos + 40, 300, 40), 2)
        text = text_cache.get(self.username_input or "Enter username", font_small, color)
        surface.blit(text, (SCREEN_WIDTH//2 - 190, y_pos + 45))
        
        y_pos += 100
        
        # Email (if register)
        if self.is_register:
            label = text_cache.get("Email:", font_small, (200, 200, 200))
            surface.blit(label, (SCREEN_WIDTH//2 - 200, y_pos))
            
            color = (100, 255, 100) if self.active_field == 1 else (100, 100, 100)
            pygame.draw.rect(surface, color, (SCREEN_WIDTH//2 - 200, y_pos + 40, 300, 40), 2)
            text = text_cache.get(self.email_input or "Enter email", font_small, color)
            surface.blit(text, (SCREEN_WIDTH//2 - 190, y_pos + 45))
            
            y_pos += 100
        
        # Password
        label = text_cache.get("Password:", font_small, (200, 200, 200))
        surface.blit(label, (SCREEN_WIDTH//2 - 200, y_pos))
        
        field_index = 2 if self.is_register else 1
        color = (100, 255, 100) if self.active_field == field_index else (100, 100, 100)
        pygame.draw.rect(surface, color, (SCREEN_WIDTH//2 - 200, y_pos + 40, 300, 40), 2)
        password_display = "*" * len(self.password_input) if self.password_input else "Enter password"
        text = text_cache.get(password_display, font_small, color)
        surface.blit(text, (SCREEN_WIDTH//2 - 190, y_pos + 45))
        
        # Error message
        if self.error_message:
            error = text_cache.get(self.error_message, font_small, (255, 100, 100))
            surface.blit(error, (SCREEN_WIDTH//2 - error.get_width()//2, SCREEN_HEIGHT - 150))
        
        # Connecting status
        if self.connecting:
            connecting = text_cache.get("Connecting...", font_small, (100, 100, 255))
            surface.blit(connecting, (SCREEN_WIDTH//2 - connecting.get_width()//2, SCREEN_HEIGHT - 100))
        
        instructions = text_cache.get(
            "TAB: Switch | ENTER: Submit | Press Alt+R to switch to Register" if not self.is_register else "TAB: Switch | ENTER: Submit | Press Alt+L to switch to Login",
            font_tiny, (150, 150, 150)
        )
        surface.blit(instructions, (SCREEN_WIDTH//2 - instructions.get_width()//2, SCREEN_HEIGHT - 50))

# ==================== MAIN GAME CLASS ====================
class Game:
    def __init__(self):
        self.game_client = GameClient()
        self.input_manager = InputManager(CLIENT_CONFIG)
        self.renderer = Renderer(SCREEN_WIDTH, SCREEN_HEIGHT)
        self.menu = Menu(self)
        self.auth_screen = AuthScreen(self.game_client, is_register=False)
        self.game_state = GameState.LOGIN
        self.camera_pos = Vector2(0, 0)
        self.player_local = None
        self.player_local_id = None
        self.running = True
        self.auto_shoot = CLIENT_CONFIG['gameplay']['auto_shoot_enabled']
        self.auto_spin = CLIENT_CONFIG['gameplay']['auto_spin_enabled']
        self.last_send_time = 0
        self.send_rate = CLIENT_CONFIG['network']['send_rate_ms'] / 1000
        self.chat_input = ""
        self.chat_mode = False
    
    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            
            elif event.type == pygame.KEYDOWN:
                # Toggle register/login
                if event.key == pygame.K_r and pygame.key.get_mods() & pygame.KMOD_ALT:
                    if self.game_state == GameState.LOGIN:
                        self.auth_screen = AuthScreen(self.game_client, is_register=True)
                        self.game_state = GameState.REGISTER
                
                elif event.key == pygame.K_l and pygame.key.get_mods() & pygame.KMOD_ALT:
                    if self.game_state == GameState.REGISTER:
                        self.auth_screen = AuthScreen(self.game_client, is_register=False)
                        self.game_state = GameState.LOGIN
                
                # Chat input
                elif self.game_state == GameState.PLAYING:
                    if event.key == pygame.K_t:
                        self.chat_mode = not self.chat_mode
                    
                    elif self.chat_mode and event.key == pygame.K_RETURN:
                        if self.chat_input.strip():
                            asyncio.create_task(self.game_client.send_chat(self.chat_input))
                            self.chat_input = ""
                        self.chat_mode = False
                    
                    elif self.chat_mode and event.key == pygame.K_BACKSPACE:
                        self.chat_input = self.chat_input[:-1]
                    
                    elif self.chat_mode and event.unicode.isprintable():
                        if len(self.chat_input) < 100:
                            self.chat_input += event.unicode
                    
                    # Menu toggle
                    elif event.key == pygame.K_z:
                        self.menu.toggle()
                    
                    # Auto-shoot toggle
                    elif event.key == pygame.K_f:
                        self.auto_shoot = not self.auto_shoot
                    
                    # Auto-spin toggle
                    elif event.key == pygame.K_r:
                        self.auto_spin = not self.auto_spin
                    
                    # Close menu
                    elif event.key == pygame.K_ESCAPE:
                        if self.menu.active:
                            self.menu.active = False
                
                # Auth screen input
                elif self.game_state in [GameState.LOGIN, GameState.REGISTER]:
                    self.auth_screen.handle_input(event)
            
            # Menu navigation
            if self.game_state == GameState.PLAYING and self.menu.active:
                self.menu.handle_input(self.input_manager)
    
    def update(self):
        self.input_manager.update()
        self.game_client.process_messages()
        
        if self.game_state == GameState.PLAYING:
            self._update_gameplay()
    
    def _update_gameplay(self):
        """Update gameplay logic"""
        if self.player_local_id not in self.game_client.players:
            return
        
        self.player_local = self.game_client.players[self.player_local_id]
        
        # Get movement input
        direction = self.input_manager.get_direction()
        angle = self.input_manager.get_mouse_angle()
        
        # Send movement
        current_time = time.time()
        if current_time - self.last_send_time > self.send_rate:
            asyncio.create_task(
                self.game_client.send_move(direction.x, direction.y)
            )
            self.last_send_time = current_time
        
        # Handle shooting
        if not self.chat_mode and not self.menu.active:
            if self.auto_shoot or self.input_manager.is_pressed('shoot'):
                asyncio.create_task(self.game_client.send_shoot(angle))
            
            # Auto-spin
            if self.auto_spin:
                spin_angle = math.sin(time.time() * 2) * math.pi
                asyncio.create_task(self.game_client.send_shoot(spin_angle))
        
        # Update camera
        if self.player_local:
            target_x = self.player_local.x
            target_y = self.player_local.y
            
            smoothing = CLIENT_CONFIG['gameplay']['camera_smoothing']
            self.camera_pos.x += (target_x - self.camera_pos.x) * smoothing
            self.camera_pos.y += (target_y - self.camera_pos.y) * smoothing
    
    def draw(self):
        if self.game_state in [GameState.LOGIN, GameState.REGISTER]:
            self.auth_screen.draw(screen)
        
        elif self.game_state == GameState.PLAYING:
            # Draw world
            player_list = list(self.game_client.players.values())
            blob_list = list(self.game_client.blobs.values())
            bullet_list = list(self.game_client.bullets.values())
            
            brightness = self.game_client.day_night_info.get('brightness', 1.0)
            self.renderer.draw_world(screen, player_list, blob_list, bullet_list,
                                    (self.camera_pos.x, self.camera_pos.y), brightness)
            
            # Draw HUD
            if self.player_local:
                player_dict = {
                    'id': self.player_local.id,
                    'health': self.player_local.health,
                    'max_health': self.player_local.max_health,
                    'score': self.player_local.score,
                    'rank': self.player_local.rank,
                    'tank': self.player_local.tank_name,
                    'team': self.player_local.team
                }
                self.renderer.draw_hud(screen, player_dict, player_list, CLIENT_CONFIG)
            
            # Draw chat
            self._draw_chat()
            
            # Draw auto-shoot/spin status
            y_offset = SCREEN_HEIGHT - 100
            if self.auto_shoot:
                auto_shoot_text = text_cache.get("AUTO-SHOOT: ON (F)", font_tiny, (100, 255, 100))
                screen.blit(auto_shoot_text, (SCREEN_WIDTH - 250, y_offset))
                y_offset -= 30
            
            if self.auto_spin:
                auto_spin_text = text_cache.get("AUTO-SPIN: ON (R)", font_tiny, (100, 255, 100))
                screen.blit(auto_spin_text, (SCREEN_WIDTH - 250, y_offset))
            
            # Draw chat input mode
            if self.chat_mode:
                chat_input_text = text_cache.get(f"Chat: {self.chat_input}_", font_small, (200, 255, 200))
                screen.blit(chat_input_text, (20, SCREEN_HEIGHT - 50))
        
        # Draw menu
        self.menu.draw(screen)
        
        pygame.display.flip()
    
    def _draw_chat(self):
        """Draw last chat messages"""
        y_offset = SCREEN_HEIGHT - 180
        current_time = time.time()
        
        for msg in self.game_client.chat_messages[-8:]:
            # Skip old messages
            if current_time - msg.get('timestamp', 0) > 10:
                continue
            
            username = msg['username']
            message = msg['message']
            
            # Color based on sender
            if username == 'SYSTEM':
                color = (255, 255, 100)
            else:
                color = (200, 200, 200)
            
            chat_text = text_cache.get(f"{username}: {message}", font_tiny, color)
            screen.blit(chat_text, (20, y_offset))
            y_offset -= 20
    
    async def run(self):
        """Main game loop"""
        while self.running:
            self.handle_events()
            self.update()
            self.draw()
            clock.tick(FPS)
            
            # Allow asyncio to process
            await asyncio.sleep(0)
        
        pygame.quit()

# ==================== ASYNC WRAPPER ====================
async def main():
    game = Game()
    
    # Welcome screen
    connecting_text = text_cache.get("TANK BATTLE ARENA", font_large, (100, 255, 100))
    init_text = text_cache.get("Initializing...", font_medium, (200, 200, 200))
    
    screen.fill((20, 20, 20))
    screen.blit(connecting_text, (SCREEN_WIDTH//2 - connecting_text.get_width()//2, SCREEN_HEIGHT//2 - 100))
    screen.blit(init_text, (SCREEN_WIDTH//2 - init_text.get_width()//2, SCREEN_HEIGHT//2 + 50))
    pygame.display.flip()
    
    await asyncio.sleep(1)
    
    await game.run()

# ==================== ENTRY POINT ====================
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nGame closed")
        pygame.quit()
        sys.exit(0)