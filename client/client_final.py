import os
import pygame
import websockets
import json
import asyncio
import math
import sys
import time
import hashlib
from enum import Enum
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta

# Try to get team input, default to 1 if problem, need to add debug server change, and or to enable debug/admin login screen(not yet implemented to server?)
try:
    start_team = int(input("Enter team number (1-4): ") or "1")
except (ValueError, EOFError):
    start_team = 1

# ==================== PYGAME SETUP ====================
pygame.init()
pygame.mixer.init()

# Lock cursor
pygame.event.set_grab(True)
pygame.mouse.set_visible(True)

# Load client config relative to this script
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CLIENT_CONFIG_PATH = os.path.join(SCRIPT_DIR, 'client_configs.json')
try:
    with open(CLIENT_CONFIG_PATH, 'r') as f:
        CLIENT_CONFIG = json.load(f)
except FileNotFoundError:
    print(f"ERROR: {CLIENT_CONFIG_PATH} not found!")
    sys.exit(1)

# Load server index metadata
SERVER_INDEX_DATA = {}

TANK_INDEX = SERVER_INDEX_DATA.get('tanks', {}).get('list', [])
UPGRADE_COST = SERVER_INDEX_DATA.get('upgrades', {}).get('cost_per_upgrade', 20)
SKILL_INDEX = SERVER_INDEX_DATA.get('upgrades', {}).get('list', [])
RANK_INDEX = SERVER_INDEX_DATA.get('ranks', {}).get('thresholds', [])

SCREEN_WIDTH = CLIENT_CONFIG.get('display', {}).get('width', 1280)
SCREEN_HEIGHT = CLIENT_CONFIG.get('display', {}).get('height', 720)
FPS = CLIENT_CONFIG.get('display', {}).get('fps', 60)
FULLSCREEN = CLIENT_CONFIG.get('display', {}).get('fullscreen', False)

flags = pygame.FULLSCREEN if FULLSCREEN else 0
screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), flags)
pygame.display.set_caption("Tank Battle Arena - Client")
clock = pygame.time.Clock()

# Utility helpers

def get_team_color(team_id: int, dark: bool = False):
    teams = CLIENT_CONFIG.get('teams', {}).get('list', [])
    if 1 <= team_id <= len(teams):
        team = teams[team_id - 1]
        color = team.get('dark_color' if dark else 'color')
        if isinstance(color, (list, tuple)) and len(color) == 3:
            return tuple(color)
    return (200, 200, 200)


def get_player_attr(player, key, default=None):
    if isinstance(player, dict):
        return player.get(key, default)
    if hasattr(player, key):
        return getattr(player, key, default)
    return default

# Fonts
font_large = pygame.font.Font(None, 48)
font_medium = pygame.font.Font(None, 32)
font_small = pygame.font.Font(None, 24)
font_tiny = pygame.font.Font(None, 16)

# ==================== ENUMS ====================
class GameState(Enum):
    SERVER_SELECTION = "server_selection"
    CONNECTING = "connecting"
    LOGIN = "login"
    REGISTER = "register"
    TEAM_SELECTION = "team_selection"
    CONNECTING_TO_GAME = "connecting_to_game"
    PLAYING = "playing"
    DEAD = "dead"
    SPECTATING = "spectating"
    MENU = "menu"
    ERROR = "error"

class PlayerState(Enum):
    ALIVE = "alive"
    DEAD = "dead"
    SPECTATING = "spectating"

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

# ==================== VECTOR CLASS ====================
class Vector2:
    """2D Vector math"""
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
    """Manage keyboard and mouse input"""
    def __init__(self, config):
        self.config = config['keyboard']
        self.keys = {}
        self.mouse_pos = (0, 0)
        self.mouse_buttons = {}
        self.key_map = self._create_key_map()
        self.key_pressed_last_frame = set()
    
    def _create_key_map(self):
        """Create mapping from config strings to pygame constants"""
        key_map = {
            'W': pygame.K_w, 'S': pygame.K_s, 'A': pygame.K_a, 'D': pygame.K_d,
            'Q': pygame.K_q, 'E': pygame.K_e, 'R': pygame.K_r, 'T': pygame.K_t,
            'Z': pygame.K_z, 'F': pygame.K_f, 'TAB': pygame.K_TAB,
            'SHIFT': pygame.K_LSHIFT, 'SPACE': pygame.K_SPACE,
            'RETURN': pygame.K_RETURN, 'ESCAPE': pygame.K_ESCAPE
        }
        return key_map
    
    def update(self):
        """Update input state"""
        self.keys = pygame.key.get_pressed()
        self.mouse_pos = pygame.mouse.get_pos()
        self.mouse_buttons = pygame.mouse.get_pressed()
    
    def is_pressed(self, action):
        """Check if action key is pressed"""
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
        """Get movement direction from WASD"""
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
        """Get angle from screen center to mouse"""
        return math.atan2(self.mouse_pos[1] - SCREEN_HEIGHT/2, 
                         self.mouse_pos[0] - SCREEN_WIDTH/2)

# ==================== GAME OBJECTS ====================
class RemotePlayer:
    """Represents another player in the game"""
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
        """Update from server data"""
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
        """Draw player on screen"""
        if not self.is_alive:
            return
        
        screen_x = self.x - camera_pos[0] + SCREEN_WIDTH/2
        screen_y = self.y - camera_pos[1] + SCREEN_HEIGHT/2
        
        if screen_x < -100 or screen_x > SCREEN_WIDTH + 100 or \
           screen_y < -100 or screen_y > SCREEN_HEIGHT + 100:
            return
        
        # Determine color based on team
        color = get_team_color(self.team)
        
        # Draw tank body
        radius = SERVER_INDEX_DATA.get('player', {}).get('radius', 15)
        pygame.draw.circle(surface, color, (int(screen_x), int(screen_y)), radius)
        pygame.draw.circle(surface, (255, 255, 255), (int(screen_x), int(screen_y)), radius, 2)
        
        # Draw barrel/turret
        barrel_length = SERVER_INDEX_DATA.get('player', {}).get('barrel_length', 25)
        barrel_x = screen_x + math.cos(self.angle) * barrel_length
        barrel_y = screen_y + math.sin(self.angle) * barrel_length
        pygame.draw.line(surface, color, (screen_x, screen_y), 
                        (barrel_x, barrel_y), 4)
        
        # Draw username
        if CLIENT_CONFIG.get('gameplay', {}).get('show_names', True):
            name_text = text_cache.get(self.username, font_tiny, color)
            surface.blit(name_text, (int(screen_x - name_text.get_width()/2), int(screen_y - 35)))
        
        # Draw health bar above name
        if CLIENT_CONFIG.get('gameplay', {}).get('show_health_bars', True):
            health_width = 40
            health_height = 5
            health_ratio = max(0, self.health / self.max_health)
            pygame.draw.rect(surface, (100, 255, 100), 
                           (int(screen_x - health_width/2), int(screen_y - 50), 
                            int(health_width * health_ratio), health_height))
            pygame.draw.rect(surface, (255, 255, 255), 
                           (int(screen_x - health_width/2), int(screen_y - 50), 
                            health_width, health_height), 1)

class Blob:
    """Collectible blob in the game"""
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
        """Update from server data"""
        self.x = data.get('x', self.x)
        self.y = data.get('y', self.y)
        self.hp = data.get('hp', self.hp)
    
    def draw(self, surface, camera_pos):
        """Draw blob on screen"""
        screen_x = self.x - camera_pos[0] + SCREEN_WIDTH/2
        screen_y = self.y - camera_pos[1] + SCREEN_HEIGHT/2
        
        if screen_x < -50 or screen_x > SCREEN_WIDTH + 50 or \
           screen_y < -50 or screen_y > SCREEN_HEIGHT + 50:
            return
        
        # Get color for blob type
        color_key = f'blob_{self.type}'
        color = tuple(CLIENT_CONFIG['colors'].get(color_key, [200, 200, 200]))
        
        # Draw blob based on type
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
        elif self.type == 'pentagon':
            points = []
            for i in range(5):
                angle = math.pi * 2 * i / 5
                px = screen_x + math.cos(angle) * self.radius
                py = screen_y + math.sin(angle) * self.radius
                points.append((px, py))
            pygame.draw.polygon(surface, color, points)
        elif self.type == 'hexagon':
            points = []
            for i in range(6):
                angle = math.pi * 2 * i / 6
                px = screen_x + math.cos(angle) * self.radius
                py = screen_y + math.sin(angle) * self.radius
                points.append((px, py))
            pygame.draw.polygon(surface, color, points)
        elif self.type == 'heptagon':
            points = []
            for i in range(7):
                angle = math.pi * 2 * i / 7
                px = screen_x + math.cos(angle) * self.radius
                py = screen_y + math.sin(angle) * self.radius
                points.append((px, py))
            pygame.draw.polygon(surface, color, points)
        elif self.type == 'octagon':
            points = []
            for i in range(8):
                angle = math.pi * 2 * i / 8
                px = screen_x + math.cos(angle) * self.radius
                py = screen_y + math.sin(angle) * self.radius
                points.append((px, py))
            pygame.draw.polygon(surface, color, points)
        elif self.type == 'nonagon':
            points = []
            for i in range(9):
                angle = math.pi * 2 * i / 9
                px = screen_x + math.cos(angle) * self.radius
                py = screen_y + math.sin(angle) * self.radius
                points.append((px, py))
            pygame.draw.polygon(surface, color, points)
        elif self.type == 'decagon':
            points = []
            for i in range(10):
                angle = math.pi * 2 * i / 10
                px = screen_x + math.cos(angle) * self.radius
                py = screen_y + math.sin(angle) * self.radius
                points.append((px, py))
            pygame.draw.polygon(surface, color, points)
        
        # Draw health bar above blob
        health_width = 30
        health_height = 4
        health_ratio = max(0, self.hp / self.max_hp)
        pygame.draw.rect(surface, (100, 255, 100), 
                       (int(screen_x - health_width/2), int(screen_y - self.radius - 10), 
                        int(health_width * health_ratio), health_height))
        pygame.draw.rect(surface, (255, 255, 255), 
                       (int(screen_x - health_width/2), int(screen_y - self.radius - 10), 
                        health_width, health_height), 1)

class Bullet:
    """Projectile in the game"""
    def __init__(self, bullet_id, x, y, owner_id, owner_team):
        self.id = bullet_id
        self.x = x
        self.y = y
        self.owner_id = owner_id
        self.owner_team = owner_team
        self.radius = 3
        self.creation_time = time.time()
    
    def draw(self, surface, camera_pos):
        """Draw bullet on screen"""
        screen_x = self.x - camera_pos[0] + SCREEN_WIDTH/2
        screen_y = self.y - camera_pos[1] + SCREEN_HEIGHT/2
        
        if -50 < screen_x < SCREEN_WIDTH + 50 and -50 < screen_y < SCREEN_HEIGHT + 50:
            color = get_team_color(self.owner_team)
            pygame.draw.circle(surface, color, (int(screen_x), int(screen_y)), self.radius)

# ==================== MENU SYSTEM ====================
class MenuItem:
    """Single menu item"""
    def __init__(self, title, action=None, meta=None):
        self.title = title
        self.action = action
        self.meta = meta

class Menu:
    """Main menu system"""
    def __init__(self, game):
        self.game = game
        self.active = False
        self.current_menu = 'main'
        self.selected_option = 0
        self.previewed_tank = None
        self.previewed_skill = None
        self.previewed_rank = None
        self.menus = {}
        self.last_nav_time = 0.0
        self.nav_delay = 0.18
        self.init_menus()
        
        # Set previewed_tank to the first available tank
        self.previewed_tank = None
        if self.menus.get('tank_index'):
            for item in self.menus['tank_index']:
                if hasattr(item, 'meta') and item.meta and 'tank' in item.meta:
                    self.previewed_tank = item.meta['tank']
                    break
    
    def init_menus(self):
        """Initialize all menu structures"""
        self.menus = {
            'main': [
                MenuItem("Resume Game", self.resume_game),
                MenuItem("Tank Upgrades (Q)", self.show_tank_upgrades),
                MenuItem("Skill Upgrades (E)", self.show_skill_upgrades),
                MenuItem("Tank Index", self.show_tank_index),
                MenuItem("Tank Menu", self.show_tank_menu),
                MenuItem("Skill Menu", self.show_skill_menu),
                MenuItem("Rank Index", self.show_rank_index),
                MenuItem("Profile", self.show_profile),
                MenuItem("Settings", self.show_settings),
                MenuItem("Tutorial", self.show_tutorial),
                MenuItem("Admin Login", self.show_admin_login),
                MenuItem("Disconnect", self.disconnect),
                MenuItem("Quit to Desktop", self.quit_game)
            ],
            'settings': [
                MenuItem(f"Auto Shoot: {'On' if getattr(self.game, 'auto_shoot', False) else 'Off'}", self.toggle_auto_shoot),
                MenuItem(f"Auto Spin: {'On' if getattr(self.game, 'auto_spin', False) else 'Off'}", self.toggle_auto_spin),
                MenuItem(f"Mouse Control Angle: {'On' if getattr(self.game, 'mouse_control_angle', True) else 'Off'}", self.toggle_mouse_angle),
                MenuItem(f"Show Names: {'On' if CLIENT_CONFIG.get('gameplay', {}).get('show_names', True) else 'Off'}", self.toggle_show_names),
                MenuItem(f"Show Health Bars: {'On' if CLIENT_CONFIG.get('gameplay', {}).get('show_health_bars', True) else 'Off'}", self.toggle_show_health),
                MenuItem("Back", self.back_to_main)
            ],
            'tank_index': self.build_tank_INDEX_menu(),
            'tank_menu': self.build_tank_BUY_menu(),
            'skill_menu': self.build_skill_menu(),
            'rank_index': self.build_rank_menu(),
            'profile': self.build_profile_menu(),
            'tutorial': self.build_tutorial_menu(),
            'admin_login': self.build_admin_login_menu()
        }
    
    def build_tank_INDEX_menu(self):
        items = [
            MenuItem("=== TANK INDEX ===", None),
            MenuItem("-" * 40, None)
        ]
        for tank in TANK_INDEX:
            tank_name = tank.get('name', 'Unknown')
            path_to_tank = tank.get('path', 'Unknown')
            cost = tank.get('cost', 0)
            min_rank = tank.get('min_rank', 1)
            label = f"{tank_name} | Rank {min_rank} | Cost {cost}"
            items.append(MenuItem(label, lambda t=tank: self.preview_tank(t), {'type': 'tank', 'tank': tank}))
        items.extend([
            MenuItem("-" * 40, None),
            MenuItem("Back", self.back_to_main)
        ])
        return items
    
    def build_tank_BUY_menu(self):
        items = [
            MenuItem("=== TANK UPGRADES ===", None),
            MenuItem("-" * 40, None)
        ]
        for tank in TANK_INDEX:
            tank_name = tank.get('name', 'Unknown')
            cost = tank.get('cost', 0)
            min_rank = tank.get('min_rank', 1)
            label = f"{tank_name} | Rank {min_rank} | Cost {cost}"
            items.append(MenuItem(label, lambda t=tank: self.preview_tank(t), {'type': 'tank', 'tank': tank}))
        items.extend([
            MenuItem("-" * 40, None),
            MenuItem("Buy Selected Tank (B)", self.buy_current_selection),
            MenuItem("Back", self.back_to_main)
        ])
        return items

    def build_skill_menu(self):
        items = [
            MenuItem("=== SKILL UPGRADES ===", None),
            MenuItem("-" * 40, None)
        ]
        for upgrade in SKILL_INDEX:
            upgrade_name = upgrade.get('name', 'Unknown')
            slot = upgrade.get('slot', 'Unknown')
            cost = upgrade.get('cost', UPGRADE_COST)
            label = f"{upgrade_name} | Slot: {slot} | Cost: {cost}"
            items.append(MenuItem(label, lambda u=upgrade: self.preview_skill(u), {'type': 'upgrade', 'upgrade': upgrade}))
        items.extend([
            MenuItem("-" * 40, None),
            MenuItem("Buy Selected Upgrade (B)", self.buy_current_selection),
            MenuItem("Back", self.back_to_main)
        ])
        return items

    def build_rank_menu(self):
        items = [
            MenuItem("=== RANK INDEX ===", None),
            MenuItem("-" * 40, None)
        ]
        for rank in RANK_INDEX:
            rank_num = rank.get('rank', 1)
            money = rank.get('required_money', 0)
            kills = rank.get('required_kills', 0)
            assists = rank.get('required_assists', 0)
            label = f"Rank {rank_num} | Money {money} | Kills {kills} | Assists {assists}"
            items.append(MenuItem(label, lambda r=rank: self.preview_rank(r), {'type': 'rank', 'rank': rank}))
        items.append(MenuItem("Back", self.back_to_main))
        return items

    def build_profile_menu(self):
        items = [
            MenuItem("=== PROFILE ===", None),
            MenuItem("-" * 40, None)
        ]
        for line in self.get_profile_info():
            items.append(MenuItem(line, None))
        items.append(MenuItem("Back", self.back_to_main))
        return items

    def build_tutorial_menu(self):
        tutorial_lines = [
            "=== TUTORIAL ===",
            "- Use WASD to move.",
            "- Aim with mouse or keyboard.",
            "- Press F to toggle auto-shoot.",
            "- Press R to toggle auto-spin.",
            "- Use Q/E to open tank/skill menus.",
            "- Press T to chat.",
            "- Press Z to open the menu.",
            "- Press B to buy selected tank/upgrade.",
            "- Press ESC to close menus."
        ]
        items = [MenuItem(line, None) for line in tutorial_lines]
        items.append(MenuItem("Back", self.back_to_main))
        return items
    
    def build_admin_login_menu(self):
        items = [
            MenuItem("=== ADMIN LOGIN ===", None),
            MenuItem("Note: Admin login requires server credentials.", None),
            MenuItem("Attempt Login (uses hardcoded credentials for demo)", self.game.attempt_admin_login),
            MenuItem("Back", self.back_to_main)
        ]
        return items
    
    def toggle(self):
        """Toggle menu open/closed"""
        self.active = not self.active
        self.selected_option = 0
        pygame.mouse.set_visible(self.active)
        pygame.event.set_grab(not self.active)
    
    def handle_input(self, input_manager):
        """Handle menu input"""
        if not self.active:
            return
        
        now = time.time()
        keys = pygame.key.get_pressed()
        if now - self.last_nav_time >= self.nav_delay:
            if keys[pygame.K_UP]:
                self.selected_option = (self.selected_option - 1) % len(self.menus[self.current_menu])
                self.last_nav_time = now
            elif keys[pygame.K_DOWN]:
                self.selected_option = (self.selected_option + 1) % len(self.menus[self.current_menu])
                self.last_nav_time = now
            elif keys[pygame.K_ESCAPE] and self.current_menu != 'main':
                self.back_to_main()
                self.last_nav_time = now
        if keys[pygame.K_RETURN]:
            item = self.get_selected_item()
            if item and item.action:
                item.action()
    
    def draw(self, surface):
        """Draw menu on screen"""
        if not self.active:
            return
        
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
        overlay.set_alpha(220)
        overlay.fill((0, 0, 0))
        surface.blit(overlay, (0, 0))
        
        title_text = text_cache.get(f"MENU - {self.current_menu.upper()}", font_large, (100, 255, 100))
        surface.blit(title_text, (SCREEN_WIDTH//2 - title_text.get_width()//2, 50))
        
        menu_items = self.menus.get(self.current_menu, [])
        start_index = max(0, self.selected_option - 5)
        end_index = min(len(menu_items), start_index + 12)
        y_offset = 150
        for i in range(start_index, end_index):
            item = menu_items[i]
            color = (100, 255, 100) if i == self.selected_option else (200, 200, 200)
            text = text_cache.get(item.title, font_medium, color)
            surface.blit(text, (60, y_offset + (i - start_index) * 40))
        
        if self.current_menu in ('tank_index', 'tank_menu', 'skill_menu', 'rank_index', 'profile', 'tutorial'):
            self.draw_detail_panel(surface)

        instructions_text = "UP/DOWN Navigate | ENTER Select/Preview | ESC Close"
        if self.current_menu in ('tank_index', 'tank_menu', 'skill_menu'):
            instructions_text = "UP/DOWN Navigate | ENTER Preview | B Buy | ESC Back"
        instructions = text_cache.get(instructions_text, font_tiny, (150, 150, 150))
        surface.blit(instructions, (SCREEN_WIDTH//2 - instructions.get_width()//2, SCREEN_HEIGHT - 50))
    
    def draw_detail_panel(self, surface):
        panel_x = SCREEN_WIDTH - 420
        panel_y = 120
        panel_width = 360
        panel_height = SCREEN_HEIGHT - 180
        panel = pygame.Surface((panel_width, panel_height))
        panel.set_alpha(220)
        panel.fill((20, 20, 20))
        surface.blit(panel, (panel_x, panel_y))

        y = panel_y + 20
        title = text_cache.get("DETAILS", font_medium, (180, 255, 180))
        surface.blit(title, (panel_x + 20, y))
        y += 40

        details = []
        if self.current_menu == 'tank_index' and self.previewed_tank or self.selected_option:
            tank = self.previewed_tank
            details.append(f"Name: {tank.get('name', 'Unknown')}")
            details.append(f"Type: {tank.get('type', 'N/A')}")
            details.append(f"Cost: {tank.get('cost', 0)}")
            details.append(f"Min Rank: {tank.get('min_rank', 1)}")
            stats = tank.get('stats', {})
            for stat_name, stat_value in stats.items():
                details.append(f"{stat_name.replace('_', ' ').title()}: {stat_value}")
            abilities = ', '.join(tank.get('abilities', []))
            details.append(f"Abilities: {abilities}")
            details.append("")
        elif self.current_menu == 'tank_menu' and self.previewed_tank or self.selected_option:
            tank = self.previewed_tank
            details.append(f"Name: {tank.get('name', 'Unknown')}")
            details.append(f"Type: {tank.get('type', 'N/A')}")
            details.append(f"Cost: {tank.get('cost', 0)}")
            details.append(f"Min Rank: {tank.get('min_rank', 1)}")
            stats = tank.get('stats', {})
            for stat_name, stat_value in stats.items():
                details.append(f"{stat_name.replace('_', ' ').title()}: {stat_value}")
            abilities = ', '.join(tank.get('abilities', []))
            details.append(f"Abilities: {abilities}")
            details.append("")
            details.append("Press B to buy this tank.")
        elif self.current_menu == 'skill_menu' and self.previewed_skill or self.selected_option:
            upgrade = self.previewed_skill
            details.append(f"Name: {upgrade.get('name', 'Unknown')}")
            details.append(f"Slot: {upgrade.get('slot', 'Unknown')}")
            details.append(f"Cost: {upgrade.get('cost', UPGRADE_COST)}")
            details.append(f"Multiplier: {upgrade.get('multiplier', 1.0)}x")
            details.append(f"Applies To: {', '.join(upgrade.get('applicable_tanks', []))}")
            details.append("")
            details.append("Press B to buy this upgrade.")
        elif self.current_menu == 'rank_index' and self.previewed_rank or self.selected_option:
            rank = self.previewed_rank
            details.append(f"Rank: {rank.get('rank', 1)}")
            details.append(f"Money: {rank.get('required_money', 0)}")
            details.append(f"Kills: {rank.get('required_kills', 0)}")
            details.append(f"Assists: {rank.get('required_assists', 0)}")
            details.append("")
            details.append("Ranks scale automatically beyond the defined thresholds.")
        elif self.current_menu == 'profile':
            for line in self.get_profile_info():
                details.append(line)
        elif self.current_menu == 'tutorial':
            details.append("Use the arrow keys to move the cursor.")
            details.append("Choose an item and press ENTER to preview.")
            details.append("Press B to purchase the selected item.")
            details.append("Press ESC to return to the main menu.")

        for line in details:
            text = text_cache.get(line, font_small, (220, 220, 220))
            surface.blit(text, (panel_x + 20, y))
            y += 28
    
    def get_selected_item(self):
        items = self.menus.get(self.current_menu, [])
        if 0 <= self.selected_option < len(items):
            return items[self.selected_option]
        return None

    def get_profile_info(self):
        info = []
        local = self.game.player_local
        if local and hasattr(local, 'username'):
            info.append(f"Username: {local.username}")
            info.append(f"Team: {local.team}")
            info.append(f"Tank: {local.tank_name}")
            info.append(f"Rank: {local.rank}")
            info.append(f"Money: {local.money}")
            info.append(f"Resources: {local.resource}")
        else:
            info.append("Not connected to a player yet.")
            info.append("Login and join a game to see stats.")
        return info

    def resume_game(self):
        self.active = False

    def show_tank_upgrades(self):
        self.show_tank_index()

    def show_skill_upgrades(self):
        self.show_skill_index()

    def show_tank_index(self):
        self.current_menu = 'tank_index'
        self.selected_option = 2 if len(self.menus.get('tank_index', [])) > 2 else 0
        self.previewed_tank = TANK_INDEX[0] if TANK_INDEX else None
        
    def show_tank_menu(self):
        self.current_menu = 'tank_menu'
        self.selected_option = 2 if len(self.menus.get('tank_menu', [])) > 2 else 0
        self.previewed_tank = TANK_INDEX[0] if TANK_INDEX else None

    def show_skill_menu(self):
        self.current_menu = 'skill_menu'
        self.selected_option = 2 if len(self.menus.get('skill_index', [])) > 2 else 0
        self.previewed_skill = SKILL_INDEX[0] if SKILL_INDEX else None

    def show_rank_index(self):
        self.current_menu = 'rank_index'
        self.selected_option = 2 if len(self.menus.get('rank_index', [])) > 2 else 0
        self.previewed_rank = RANK_INDEX[0] if RANK_INDEX else None

    def show_profile(self):
        self.current_menu = 'profile'
        self.selected_option = 0
        self.init_menus()

    def show_settings(self):
        self.current_menu = 'settings'
        self.selected_option = 0
        self.init_menus()

    def toggle_auto_shoot(self):
        self.game.auto_shoot = not self.game.auto_shoot
        self.init_menus()

    def toggle_auto_spin(self):
        self.game.auto_spin = not self.game.auto_spin
        self.init_menus()

    def toggle_mouse_angle(self):
        self.game.mouse_control_angle = not self.game.mouse_control_angle
        self.init_menus()

    def toggle_show_names(self):
        gameplay = CLIENT_CONFIG.setdefault('gameplay', {})
        gameplay['show_names'] = not gameplay.get('show_names', True)
        self.init_menus()

    def toggle_show_health(self):
        gameplay = CLIENT_CONFIG.setdefault('gameplay', {})
        gameplay['show_health_bars'] = not gameplay.get('show_health_bars', True)
        self.init_menus()

    def buy_current_selection(self):
        selected = self.get_selected_item()
        if selected and selected.meta:
            meta = selected.meta
            if meta.get('type') == 'tank':
                self.buy_tank(meta['tank'])
                return
            if meta.get('type') == 'upgrade':
                self.buy_upgrade(meta['upgrade'])
                return
        if self.current_menu == 'tank_menu' and self.previewed_tank:
            self.buy_tank(self.previewed_tank)
        elif self.current_menu == 'skill_menu' and self.previewed_skill:
            self.buy_upgrade(self.previewed_skill)

    def preview_tank(self, tank):
        self.previewed_tank = tank

    def preview_skill(self, upgrade):
        self.previewed_skill = upgrade

    def preview_rank(self, rank):
        self.previewed_rank = rank

    def buy_tank(self, tank):
        if not tank:
            return
        if self.game.game_client.connected:
            asyncio.create_task(self.game.game_client.send_buy_tank(tank.get('name')))

    def buy_upgrade(self, upgrade):
        if not upgrade:
            return
        if self.game.game_client.connected:
            asyncio.create_task(self.game.game_client.send_buy_upgrade(upgrade.get('name')))

    def back_to_main(self):
        self.current_menu = 'main'
        self.selected_option = 0

    def show_tutorial(self):
        self.current_menu = 'tutorial'
    
    def show_admin_login(self):
        self.current_menu = 'admin_login'
        self.selected_option = 0

    def disconnect(self):
        self.game.game_state = GameState.LOGIN
        self.game.game_client.disconnect()

    def quit_game(self):
        self.game.running = False

# ==================== RENDERER ====================
class Renderer:
    """Game world renderer"""
    def __init__(self, screen_width, screen_height):
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.grid_surface = self.create_grid()
    
    def create_grid(self):
        """Create grid texture"""
        grid_surface = pygame.Surface((self.screen_width, self.screen_height))
        grid_surface.fill((20, 20, 20))
        grid_size = CLIENT_CONFIG.get('display', {}).get('grid_size', 50)
        
        for x in range(0, self.screen_width, grid_size):
            pygame.draw.line(grid_surface, (60, 60, 60), (x, 0), (x, self.screen_height), 1)
        for y in range(0, self.screen_height, grid_size):
            pygame.draw.line(grid_surface, (60, 60, 60), (0, y), (self.screen_width, y), 1)
        
        return grid_surface
    
    def draw_world(self, surface, players, blobs, bullets, camera_pos, brightness, local_player=None, player_team=1):
        """Draw the game world"""
        surface.fill((20, 20, 20))
        
        # Apply day/night coloring
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
        
        # Draw grid with quadrant colors
        if CLIENT_CONFIG.get('display', {}).get('grid_visible', True):
            self._draw_quadrant_grid(surface, camera_pos)
        
        # Draw all game objects
        for blob in blobs:
            blob.draw(surface, camera_pos)
        
        for bullet in bullets:
            bullet.draw(surface, camera_pos)
        
        for player in players:
            player.draw(surface, camera_pos, player_team)
        
        # Draw local player
        if local_player:
            self._draw_player(surface, local_player, camera_pos, player_team)
    
    def _draw_quadrant_grid(self, surface, camera_pos):
        """Draw grid with team-based quadrant colors"""
        grid_size = CLIENT_CONFIG.get('display', {}).get('grid_size', 50)
        world_width = (SERVER_INDEX_DATA.get('world', {}).get('width', 928) *
                       SERVER_INDEX_DATA.get('world', {}).get('screens_x', 10))
        world_height = (SERVER_INDEX_DATA.get('world', {}).get('height', 522) *
                        SERVER_INDEX_DATA.get('world', {}).get('screens_y', 8))
        teams = CLIENT_CONFIG.get('teams', {}).get('list', [])

        quad_colors = {
            'Q1': get_team_color(1),
            'Q2': get_team_color(2),
            'Q3': get_team_color(3),
            'Q4': get_team_color(4)
        }
        if len(teams) >= 4:
            quad_colors = {
                'Q1': tuple(teams[0].get('color', quad_colors['Q1'])),
                'Q2': tuple(teams[1].get('color', quad_colors['Q2'])),
                'Q3': tuple(teams[2].get('color', quad_colors['Q3'])),
                'Q4': tuple(teams[3].get('color', quad_colors['Q4']))
            }

        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        half_w = world_width / 2
        half_h = world_height / 2
        quad_rects = [
            (0, 0, half_w, half_h, quad_colors['Q1']),
            (half_w, 0, half_w, half_h, quad_colors['Q2']),
            (0, half_h, half_w, half_h, quad_colors['Q3']),
            (half_w, half_h, half_w, half_h, quad_colors['Q4'])
        ]

        for qx, qy, qw, qh, color in quad_rects:
            screen_x = qx - camera_pos[0] + SCREEN_WIDTH / 2
            screen_y = qy - camera_pos[1] + SCREEN_HEIGHT / 2
            rect = pygame.Rect(int(screen_x), int(screen_y), int(qw), int(qh))
            if rect.colliderect(pygame.Rect(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT)):
                pygame.draw.rect(overlay, (*color, 28), rect)
        surface.blit(overlay, (0, 0))

        grid_color = tuple(CLIENT_CONFIG.get('colors', {}).get('grid_color', [60, 60, 60]))
        for x in range(0, world_width + grid_size, grid_size):
            screen_x = x - camera_pos[0] + SCREEN_WIDTH / 2
            if -grid_size < screen_x < SCREEN_WIDTH + grid_size:
                pygame.draw.line(surface, grid_color, (screen_x, 0), (screen_x, SCREEN_HEIGHT), 1)
        for y in range(0, world_height + grid_size, grid_size):
            screen_y = y - camera_pos[1] + SCREEN_HEIGHT / 2
            if -grid_size < screen_y < SCREEN_HEIGHT + grid_size:
                pygame.draw.line(surface, grid_color, (0, screen_y), (SCREEN_WIDTH, screen_y), 1)
    
    def _draw_player(self, surface, player, camera_pos, player_team, rotation):
        """Draw a player dict or object (for local player)"""
        alive = get_player_attr(player, 'alive', True)
        if not alive:
            return
        
        x = get_player_attr(player, 'x', 0)
        y = get_player_attr(player, 'y', 0)
        screen_x = x - camera_pos[0] + SCREEN_WIDTH/2
        screen_y = y - camera_pos[1] + SCREEN_HEIGHT/2
        
        if screen_x < -100 or screen_x > SCREEN_WIDTH + 100 or \
           screen_y < -100 or screen_y > SCREEN_HEIGHT + 100:
            return
        
        player_team_id = get_player_attr(player, 'team', 1)
        if player_team_id == player_team:
            color = get_team_color(player_team_id, dark=True)
        else:
            color = get_team_color(player_team_id)
        
        radius = 15
        pygame.draw.circle(surface, color, (int(screen_x), int(screen_y)), radius)
        pygame.draw.circle(surface, (255, 255, 255), (int(screen_x), int(screen_y)), radius, 2)
        
        # Draw barrel/turret
        angle = get_player_attr(player, 'angle', 0)
        barrel_length = 25
        barrel_x = screen_x + math.cos(angle) * barrel_length
        barrel_y = screen_y + math.sin(angle) * barrel_length
        pygame.draw.line(surface, color, (screen_x, screen_y), 
                        (barrel_x, barrel_y), 4)
        
        # Draw username
        if CLIENT_CONFIG.get('gameplay', {}).get('show_names', True):
            username = get_player_attr(player, 'username', 'Player')
            name_text = text_cache.get(username, font_small, color)
            surface.blit(name_text, (screen_x - name_text.get_width()/2, screen_y - radius - 25))
        
        # Draw health bar above name
        if CLIENT_CONFIG.get('gameplay', {}).get('show_health_bars', True):
            health = get_player_attr(player, 'health', 100)
            max_health = get_player_attr(player, 'max_health', 100)
            health_width = 30
            health_height = 4
            health_ratio = max(0, health / max_health)
            pygame.draw.rect(surface, (100, 255, 100), 
                           (int(screen_x - health_width/2), int(screen_y - radius - 35), 
                            int(health_width * health_ratio), health_height))
            pygame.draw.rect(surface, (255, 255, 255), 
                           (int(screen_x - health_width/2), int(screen_y - radius - 35), 
                            health_width, health_height), 1)
    
    def draw_hud(self, surface, player, all_players):
        """Draw heads-up display"""
        if not player:
            return
        
        # Health bar
        health_width = 200
        health_x = 20
        health_y = 20
        health_ratio = player.get('health', 100) / max(1, player.get('max_health', 100))
        
        pygame.draw.rect(surface, (100, 255, 100), 
                        (health_x, health_y, int(health_width * health_ratio), 20))
        pygame.draw.rect(surface, (255, 255, 255), 
                        (health_x, health_y, health_width, 20), 2)
        
        health_text = text_cache.get(
            f"Health: {player.get('health', 100):.0f}/{player.get('max_health', 100):.0f}",
            font_small, (255, 255, 255)
        )
        surface.blit(health_text, (health_x + 5, health_y + 25))
        
        # Stats on left side
        y = SCREEN_HEIGHT - 120
        score_text = text_cache.get(f"Resources: {player.get('score', 0)}", font_small, (100, 255, 100))
        surface.blit(score_text, (20, y - 40))
        
        money_text = text_cache.get(f"Money: {player.get('money', 0)}", font_small, (100, 255, 100))
        surface.blit(money_text, (20, y))
        
        rank_text = text_cache.get(f"Rank: {player.get('rank', 1)}", font_small, (100, 255, 100))
        surface.blit(rank_text, (20, y + 40))
        
        tank_text = text_cache.get(f"Tank: {player.get('tank', 'Basic')}", font_small, (100, 100, 255))
        surface.blit(tank_text, (20, y + 80))
        
        # Draw minimap, need to add color for in game quadrents put to minimap
        self.draw_minimap(surface, player, all_players)
    
    def draw_minimap(self, surface, player, all_players):
        """Draw minimap in corner"""
        minimap_size = CLIENT_CONFIG.get('display').get('minimap_size', 150)
        minimap_x = SCREEN_WIDTH - minimap_size - 10
        minimap_y = 10
        
        # Background
        pygame.draw.rect(surface, (0, 0, 0), 
                        (minimap_x, minimap_y, minimap_size, minimap_size))
        pygame.draw.rect(surface, (100, 100, 100), 
                        (minimap_x, minimap_y, minimap_size, minimap_size), 2)
        
        # Draw quadrants
        half = minimap_size // 2
        for team in SERVER_INDEX_DATA.get('teams', {}).get('list', []):
            quadrant = team.get('quadrant')
            color = team.get('color', [100, 100, 100])
            if quadrant == 'Q1':
                pygame.draw.rect(surface, color, (minimap_x, minimap_y, half, half))
            elif quadrant == 'Q2':
                pygame.draw.rect(surface, color, (minimap_x + half, minimap_y, half, half))
            elif quadrant == 'Q3':
                pygame.draw.rect(surface, color, (minimap_x, minimap_y + half, half, half))
            elif quadrant == 'Q4':
                pygame.draw.rect(surface, color, (minimap_x + half, minimap_y + half, half, half))
        
        # Draw players
        scale = minimap_size / 9280
        for p in all_players:
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
    """WebSocket game client"""
    def __init__(self):
        self.game_ws = None
        self.token = None
        self.player_id = None
        self.player_data = None
        self.connected = False
        self.server_config = {}
        
        # Configurable server URLs
        self.game_server_url = CLIENT_CONFIG.get('network', {}).get('game_server', 'ws://127.0.0.1:8765')
        self.login_server_url = CLIENT_CONFIG.get('network', {}).get('login_server', 'ws://127.0.0.1:8766')
        
        # Game data
        self.players = {}
        self.blobs = {}
        self.bullets = {}
        self.chat_messages = []
        self.day_night_info = {'is_day': True, 'brightness': 1.0}
        
        # Async
        self.server_messages = asyncio.Queue()
        self.connection_error = None
    
    async def connect_to_game(self, username: str, team: int = 1) -> bool:
        """Connect to game server"""
        game_url = self.game_server_url
        
        try:
            print(f"[DEBUG] Connecting to game server at {game_url}")
            self.game_ws = await asyncio.wait_for(
                websockets.connect(game_url, ping_interval=20, ping_timeout=10),
                timeout=5.0
            )
            print("[DEBUG] WebSocket connected, sending auth...")
            
            # Send authentication
            await self.game_ws.send(json.dumps({
                'type': 'auth',
                'token': self.token,
                'username': username,
                'team': team
            }))
            
            print("[DEBUG] Auth sent, waiting for welcome...")
            
            # Receive welcome
            response = json.loads(await asyncio.wait_for(self.game_ws.recv(), timeout=5.0))
            print(f"[DEBUG] Received response: {response.get('type')}")
            
            if response['type'] == 'welcome':
                self.player_id = response['player_id']
                self.server_config = response.get('config', {})
                self.connected = True
                
                # Add local player to players dict
                player_data = response.get('player', {})
                self.players[self.player_id] = RemotePlayer(
                    player_data.get('id', self.player_id),
                    player_data.get('username', 'You'),
                    player_data.get('x', 0),
                    player_data.get('y', 0),
                    player_data.get('team', 1),
                    player_data.get('tank', 'Basic Tank'),
                    player_data.get('rank', 1)
                )

                print("[DEBUG] Successfully connected to game server!")
                
                # Start message receiver
                asyncio.create_task(self._receive_messages())
                return True
            elif response['type'] == 'server_config':
                server_config_message = (response)
            else:
                self.connection_error = "Invalid server response"
                return False
        
        except asyncio.TimeoutError:
            self.connection_error = "Connection timeout - Server not responding"
            print("[ERROR] Connection timeout")
            return False
        except Exception as e:
            self.connection_error = f"Connection error: {str(e)}"
            print(f"[ERROR] {self.connection_error}")
            return False
        
    async def login(self, username: str, password: str) -> bool:
        """Authenticate with the login server"""
        login_url = self.login_server_url

        try:
            async with websockets.connect(login_url, ping_interval=20, ping_timeout=12) as ws:
                password_hash = hashlib.sha256(password.encode()).hexdigest()
                await ws.send(json.dumps({
                    'action': 'login',
                    'username': username,
                    'password': password_hash
                }))

                response = json.loads(await asyncio.wait_for(ws.recv(), timeout=5.0))
                if response.get('success'):
                    self.token = response['token']
                    print("[DEBUG] Login successful, token received")
                    return True
                self.connection_error = response.get('error', 'Login failed')
                print(f"[DEBUG] Login failed: {self.connection_error}")
                return False
        except asyncio.TimeoutError:
            self.connection_error = "Login timeout"
            print("[ERROR] Login timeout")
            return False
        except Exception as e:
            self.connection_error = f"Login error: {str(e)}"
            print(f"[ERROR] {self.connection_error}")
            return False

    async def register(self, username: str, email: str, password: str) -> bool:
        """Register a new account with the login server"""
        login_url = CLIENT_CONFIG.get('network', {}).get('login_server', 'ws://127.0.0.1:8766')

        try:
            async with websockets.connect(login_url, ping_interval=20, ping_timeout=12) as ws:
                password_hash = hashlib.sha256(password.encode()).hexdigest()
                await ws.send(json.dumps({
                    'action': 'register',
                    'username': username,
                    'email': email,
                    'password': password_hash
                }))

                response = json.loads(await asyncio.wait_for(ws.recv(), timeout=5.0))
                if response.get('success'):
                    print("[DEBUG] Registration successful")
                    return True
                self.connection_error = response.get('error', 'Registration failed')
                print(f"[DEBUG] Registration failed: {self.connection_error}")
                return False
        except asyncio.TimeoutError:
            self.connection_error = "Register timeout"
            print("[ERROR] Register timeout")
            return False
        except Exception as e:
            self.connection_error = f"Register error: {str(e)}"
            print(f"[ERROR] {self.connection_error}")
            return False

    async def _receive_messages(self):
        """Receive messages from server"""
        try:
            async for message in self.game_ws:
                data = json.loads(message)
                await self.server_messages.put(data)
        except websockets.exceptions.ConnectionClosed:
            self.connected = False
            self.connection_error = "Disconnected from server"
        except Exception as e:
            self.connected = False
            self.connection_error = f"Receive error: {str(e)}"
    
    def process_messages(self):
        """Process queued messages (non-async)"""
        while not self.server_messages.empty():
            try:
                data = self.server_messages.get_nowait()
                self._handle_message(data)
            except asyncio.QueueEmpty:
                break
    
    def _handle_message(self, data: dict):
        """Handle server message"""
        global SERVER_INDEX_DATA
        msg_type = data.get('type')
        
        if msg_type == 'server_config':
            SERVER_INDEX_DATA = data
        
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
                    # Remove dead blobs
                    if self.blobs[blob_id].hp <= 0:
                        del self.blobs[blob_id]
            
            # Update bullets
            self.bullets.clear()
            for bullet_data in data.get('bullets', []):
                bullet_id = bullet_data['id']
                self.bullets[bullet_id] = Bullet(
                    bullet_id, bullet_data['x'], bullet_data['y'],
                    bullet_data['owner_id'], bullet_data.get('owner_team', 1)
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
                    player_data.get('rank')
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
    
    async def send_move(self, vx: float, vy: float, angle: float):
        """Send movement to server"""
        if self.game_ws and self.connected:
            try:
                await self.game_ws.send(json.dumps({
                    'type': 'move',
                    'vx': vx,
                    'vy': vy,
                    'angle': angle
                }))
            except:
                pass
    
    async def send_shoot(self, angle: float):
        """Send shoot to server"""
        if self.game_ws and self.connected:
            try:
                await self.game_ws.send(json.dumps({
                    'type': 'shoot',
                    'angle': angle
                }))
            except:
                pass
    
    async def send_chat(self, message: str):
        """Send chat message"""
        if self.game_ws and self.connected:
            try:
                await self.game_ws.send(json.dumps({
                    'type': 'chat',
                    'message': message
                }))
            except:
                pass

    async def send_command(self, command: str): # need to add: replace("/", "")
        """Send chat message"""
        if self.game_ws and self.connected:
            try:
                await self.game_ws.send(json.dumps({
                    'type': 'command',
                    'command': command
                }))
            except:
                pass

    async def send_buy_tank(self, tank_name: str):
        """Request a tank purchase from the server"""
        if self.game_ws and self.connected:
            try:
                await self.game_ws.send(json.dumps({
                    'type': 'buy_tank',
                    'tank_name': tank_name
                }))
            except:
                pass

    async def send_buy_upgrade(self, upgrade_name: str):
        """Request an upgrade purchase from the server"""
        if self.game_ws and self.connected:
            try:
                await self.game_ws.send(json.dumps({
                    'type': 'buy_upgrade',
                    'upgrade_name': upgrade_name
                }))
            except:
                pass

    def disconnect(self):
        """Disconnect from server"""
        self.connected = False
        if self.game_ws:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop is not None:
                asyncio.create_task(self.game_ws.close())
            elif hasattr(self, 'loop') and self.loop and not self.loop.is_closed():
                self.loop.create_task(self.game_ws.close())
            else:
                try:
                    asyncio.run(self.game_ws.close())
                except Exception:
                    pass
            self.game_ws = None

# ==================== SERVER SELECTION SCREEN ====================
class ServerSelectionScreen:
    def __init__(self, game_client):
        self.game_client = game_client
        #for i in available_servers: make menu with "custom" ip's
        self.servers = [
            {"name": "Localhost Server", "game_url": "ws://localhost:8765", "login_url": "ws://localhost:8766"},
            {"name": "0.0.0.0 Server", "game_url": "ws://0.0.0.0:8765", "login_url": "ws://0.0.0.0:8766"},
            # Add more servers as needed
        ]
        self.selected_server = 0
        self.connecting = False
        self.error_message = ""
    
    def handle_input(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_UP:
                self.selected_server = (self.selected_server - 1) % len(self.servers)
            elif event.key == pygame.K_DOWN:
                self.selected_server = (self.selected_server + 1) % len(self.servers)
            elif event.key == pygame.K_RETURN:
                self.connecting = True
                server = self.servers[self.selected_server]
                self.game_client.game_server_url = server["game_url"]
                self.game_client.login_server_url = server["login_url"]
                # Return to main game to proceed to auth
                return "auth"
        return None
    
    def draw(self, surface):
        surface.fill((20, 20, 20))
        
        title = text_cache.get("Select Server", font_large, (100, 255, 100))
        surface.blit(title, (SCREEN_WIDTH//2 - title.get_width()//2, 100))
        
        y_offset = 200
        for i, server in enumerate(self.servers):
            color = (255, 255, 100) if i == self.selected_server else (200, 200, 200)
            server_text = text_cache.get(server["name"], font_medium, color)
            surface.blit(server_text, (SCREEN_WIDTH//2 - server_text.get_width()//2, y_offset))
            y_offset += 50
        
        if self.connecting:
            connecting_text = text_cache.get("Connecting...", font_medium, (255, 255, 255))
            surface.blit(connecting_text, (SCREEN_WIDTH//2 - connecting_text.get_width()//2, y_offset + 50))
        
        if self.error_message:
            error_text = text_cache.get(self.error_message, font_small, (255, 100, 100))
            surface.blit(error_text, (SCREEN_WIDTH//2 - error_text.get_width()//2, y_offset + 100))

# ==================== TEAM SELECTION SCREEN ====================
class TeamSelectionScreen:
    def __init__(self, game_client):
        self.game_client = game_client
        self.teams = [
            {"id": 1, "name": "Team 1", "color": (255, 0, 0)},
            {"id": 2, "name": "Team 2", "color": (0, 0, 255)},
            {"id": 3, "name": "Team 3", "color": (0, 255, 0)},
            {"id": 4, "name": "Team 4", "color": (128, 0, 128)}
        ]
        self.selected_team = 0
        self.connecting = False
        self.error_message = ""
    
    def handle_input(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_LEFT:
                self.selected_team = (self.selected_team - 1) % len(self.teams)
            elif event.key == pygame.K_RIGHT:
                self.selected_team = (self.selected_team + 1) % len(self.teams)
            elif event.key == pygame.K_RETURN:
                self.connecting = True
                team = self.teams[self.selected_team]
                # Proceed to connect with selected team
                return team["id"]
        return None
    
    def draw(self, surface):
        surface.fill((20, 20, 20))
        
        title = text_cache.get("Select Team", font_large, (100, 255, 100))
        surface.blit(title, (SCREEN_WIDTH//2 - title.get_width()//2, 100))
        
        x_offset = 200
        for i, team in enumerate(self.teams):
            color = team["color"] if i == self.selected_team else (100, 100, 100)
            team_text = text_cache.get(team["name"], font_medium, color)
            surface.blit(team_text, (x_offset, 300))
            x_offset += 250
        
        if self.connecting:
            connecting_text = text_cache.get("Connecting...", font_medium, (255, 255, 255))
            surface.blit(connecting_text, (SCREEN_WIDTH//2 - connecting_text.get_width()//2, 500))
        
        if self.error_message:
            error_text = text_cache.get(self.error_message, font_small, (255, 100, 100))
            surface.blit(error_text, (SCREEN_WIDTH//2 - error_text.get_width()//2, 550))

# ==================== AUTH SCREEN ====================
class AuthScreen:
    """Login / register interface"""
    def __init__(self, game_client, game, is_register=False):
        self.game_client = game_client
        self.game = game
        self.is_register = is_register
        self.username_input = ""
        self.password_input = ""
        self.email_input = ""
        self.active_field = 0
        self.error_message = ""
        self.connecting = False
        self.auth_successful = False

    def set_mode(self, is_register: bool):
        self.is_register = is_register
        self.username_input = ""
        self.password_input = ""
        self.email_input = ""
        self.active_field = 0
        self.error_message = ""
        self.connecting = False
        self.auth_successful = False

    def handle_input(self, event):
        """Handle auth input"""
        if event.type != pygame.KEYDOWN:
            return

        if event.key == pygame.K_TAB:
            self.active_field = (self.active_field + 1) % (3 if self.is_register else 2)
            return

        if event.key == pygame.K_BACKSPACE:
            if self.active_field == 0:
                self.username_input = self.username_input[:-1]
            elif self.active_field == 1:
                if self.is_register:
                    self.email_input = self.email_input[:-1]
                else:
                    self.password_input = self.password_input[:-1]
            elif self.active_field == 2:
                self.password_input = self.password_input[:-1]
            return

        if event.key == pygame.K_RETURN:
            asyncio.create_task(self._try_auth())
            return

        char = event.unicode
        if not char or not char.isprintable() or len(char) != 1:
            return

        if self.active_field == 0:
            self.username_input += char
        elif self.active_field == 1:
            if self.is_register:
                self.email_input += char
            else:
                self.password_input += char
        elif self.active_field == 2:
            self.password_input += char

    async def _try_auth(self):
        """Attempt login or registration"""
        self.connecting = True
        self.error_message = ""
        self.auth_successful = False

        username = self.username_input.strip()
        password = self.password_input
        email = self.email_input.strip()

        if not username or not password or (self.is_register and not email):
            self.error_message = "Please fill in all fields."
            self.connecting = False
            return False

        try:
            if self.is_register:
                registered = await self.game_client.register(username, email, password)
                if not registered:
                    self.error_message = "Registration failed."
                    self.connecting = False
                    return False

            logged_in = await self.game_client.login(username, password)
            if logged_in:
                self.auth_successful = True
                return True

            self.error_message = "Login failed."
        except Exception as e:
            self.error_message = f"Error: {e}"

        self.connecting = False
        return False

    def draw(self, surface):
        """Draw auth screen"""
        surface.fill((20, 20, 20))

        title = text_cache.get("TANK BATTLE ARENA", font_large, (100, 255, 100))
        surface.blit(title, (SCREEN_WIDTH // 2 - title.get_width() // 2, 50))

        screen_title = "REGISTER" if self.is_register else "LOGIN"
        title_text = text_cache.get(screen_title, font_medium, (100, 200, 100))
        surface.blit(title_text, (SCREEN_WIDTH // 2 - title_text.get_width() // 2, 120))

        y = 200
        label = text_cache.get("Username:", font_small, (200, 200, 200))
        surface.blit(label, (SCREEN_WIDTH // 2 - 200, y))

        color = (100, 255, 100) if self.active_field == 0 else (100, 100, 100)
        pygame.draw.rect(surface, color, (SCREEN_WIDTH // 2 - 200, y + 40, 300, 40), 2)
        text = text_cache.get(self.username_input or "Enter username", font_small, color)
        surface.blit(text, (SCREEN_WIDTH // 2 - 190, y + 45))

        y += 100
        if self.is_register:
            label = text_cache.get("Email:", font_small, (200, 200, 200))
            surface.blit(label, (SCREEN_WIDTH // 2 - 200, y))

            color = (100, 255, 100) if self.active_field == 1 else (100, 100, 100)
            pygame.draw.rect(surface, color, (SCREEN_WIDTH // 2 - 200, y + 40, 300, 40), 2)
            text = text_cache.get(self.email_input or "Enter email", font_small, color)
            surface.blit(text, (SCREEN_WIDTH // 2 - 190, y + 45))

            y += 100

        label = text_cache.get("Password:", font_small, (200, 200, 200))
        surface.blit(label, (SCREEN_WIDTH // 2 - 200, y))

        field_index = 2 if self.is_register else 1
        color = (100, 255, 100) if self.active_field == field_index else (100, 100, 100)
        pygame.draw.rect(surface, color, (SCREEN_WIDTH // 2 - 200, y + 40, 300, 40), 2)
        password_display = "*" * len(self.password_input) if self.password_input else "Enter password"
        text = text_cache.get(password_display, font_small, color)
        surface.blit(text, (SCREEN_WIDTH // 2 - 190, y + 45))

        if self.error_message:
            error_text = text_cache.get(self.error_message, font_small, (255, 100, 100))
            surface.blit(error_text, (SCREEN_WIDTH // 2 - error_text.get_width() // 2, SCREEN_HEIGHT - 150))

        if self.connecting:
            connecting_text = text_cache.get("Connecting...", font_small, (100, 100, 255))
            surface.blit(connecting_text, (SCREEN_WIDTH // 2 - connecting_text.get_width() // 2, SCREEN_HEIGHT - 110))

        instructions = text_cache.get(
            "TAB: Switch field | ENTER: Submit | F2: Toggle Login/Register | F3: Guest(!COMMING SOON!)",
            font_tiny, (150, 150, 150)
        )
        surface.blit(instructions, (SCREEN_WIDTH // 2 - instructions.get_width() // 2, SCREEN_HEIGHT - 50))

# ==================== CONNECTING SCREEN ====================
class ConnectingScreen:
    """Connecting to game server screen"""
    def __init__(self, game_client):
        self.game_client = game_client
        self.start_time = time.time()
    
    def draw(self, surface):
        """Draw connecting screen"""
        surface.fill((20, 20, 20))
        
        title = text_cache.get("CONNECTING TO GAME SERVER", font_large, (100, 200, 100))
        surface.blit(title, (SCREEN_WIDTH//2 - title.get_width()//2, SCREEN_HEIGHT//2 - 100))
        
        elapsed = time.time() - self.start_time
        dots = "." * (int(elapsed) % 4)
        status = text_cache.get(f"Connecting{dots}", font_medium, (100, 255, 100))
        surface.blit(status, (SCREEN_WIDTH//2 - status.get_width()//2, SCREEN_HEIGHT//2))
        
        if self.game_client.connection_error:
            error = text_cache.get(self.game_client.connection_error, font_small, (255, 100, 100))
            surface.blit(error, (SCREEN_WIDTH//2 - error.get_width()//2, SCREEN_HEIGHT//2 + 100))
            
            retry = text_cache.get("Press R to retry or ENTER to login again", font_tiny, (150, 150, 150))
            surface.blit(retry, (SCREEN_WIDTH//2 - retry.get_width()//2, SCREEN_HEIGHT - 50))

# ==================== ERROR SCREEN ====================
class ErrorScreen:
    """Error display screen"""
    def __init__(self, message):
        self.message = message
    
    def draw(self, surface):
        """Draw error screen"""
        surface.fill((40, 20, 20))
        
        title = text_cache.get("CONNECTION ERROR", font_large, (255, 100, 100))
        surface.blit(title, (SCREEN_WIDTH//2 - title.get_width()//2, 100))
        
        # Split message into lines
        lines = self.message.split('\n')
        y_offset = 250
        for line in lines:
            error_text = text_cache.get(line, font_small, (255, 150, 150))
            surface.blit(error_text, (SCREEN_WIDTH//2 - error_text.get_width()//2, y_offset))
            y_offset += 40
        
        instructions = text_cache.get("Press R to retry or Q to quit", font_small, (150, 150, 150))
        surface.blit(instructions, (SCREEN_WIDTH//2 - instructions.get_width()//2, SCREEN_HEIGHT - 50))

# ==================== MAIN GAME CLASS ====================
class Game:
    """Main game application"""
    def __init__(self):
        self.game_client = GameClient()
        self.input_manager = InputManager(CLIENT_CONFIG)
        self.renderer = Renderer(SCREEN_WIDTH, SCREEN_HEIGHT)
        self.server_selection_screen = ServerSelectionScreen(self.game_client)
        self.auth_screen = AuthScreen(self.game_client, self)
        self.team_selection_screen = TeamSelectionScreen(self.game_client)
        self.connecting_screen = None
        self.error_screen = None
        
        self.game_state = GameState.SERVER_SELECTION
        self.camera_pos = Vector2(0, 0)
        self.player_local = None
        self.player_local_id = None
        self.running = True
        gameplay_config = CLIENT_CONFIG.get('gameplay', {})
        self.auto_shoot = gameplay_config.get('auto_shoot', False)
        self.auto_spin = gameplay_config.get('auto_spin', False)
        self.mouse_control_angle = gameplay_config.get('mouse_control_angle', True)
        self.manual_angle = 0
        self.last_send_time = 0
        self.send_rate = CLIENT_CONFIG.get('network', {}).get('send_rate_ms', 50) / 1000
        self.chat_input = ""
        self.chat_mode = False
        self.start_team = start_team
        
        # Initialize menu AFTER setting game attributes
        self.menu = Menu(self)
        
        # Event loop
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
    
    def handle_events(self):
        """Handle pygame events"""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_F12:
                    self.game_client.disconnect()
                    self.running = False
                
                elif self.game_state in (GameState.LOGIN, GameState.REGISTER):
                    if event.key == pygame.K_F2:
                        self.auth_screen.set_mode(not self.auth_screen.is_register)
                    else:
                        self.auth_screen.handle_input(event)
                
                # Server selection input
                elif self.game_state == GameState.SERVER_SELECTION:
                    result = self.server_selection_screen.handle_input(event)
                    if result == "auth":
                        self.game_state = GameState.LOGIN
                
                # Team selection input
                elif self.game_state == GameState.TEAM_SELECTION:
                    result = self.team_selection_screen.handle_input(event)
                    if result:
                        # Connect with selected team
                        asyncio.create_task(self._connect_with_team(result))
                
                elif event.key == pygame.K_r and self.game_state == GameState.CONNECTING_TO_GAME or self.game_state == GameState.ERROR:
                    if self.game_state == GameState.CONNECTING_TO_GAME and self.game_client.connection_error:
                        # Retry connection
                        self.attempt_game_connection(self.auth_screen.username_input)
                    elif self.game_state == GameState.ERROR:
                        # Go back to login
                        self.game_state = GameState.LOGIN
                        self.error_screen = None
                
                elif self.game_state == GameState.PLAYING:
                    if self.chat_mode:
                        # Chat input mode
                        if event.key == pygame.K_RETURN:
                            if self.chat_input.strip():
                                asyncio.create_task(self.game_client.send_chat(self.chat_input))
                                self.chat_input = ""
                            self.chat_mode = False
                        elif event.key == pygame.K_BACKSPACE:
                            self.chat_input = self.chat_input[:-1]
                        elif event.key == pygame.K_ESCAPE:
                            self.chat_mode = False
                            self.chat_input = ""
                        elif event.unicode.isprintable() and len(self.chat_input) < 100:
                            self.chat_input += event.unicode
                    else:
                        # Game controls
                        if event.key == pygame.K_z:
                            self.menu.toggle()
                        elif event.key == pygame.K_f:
                            self.auto_shoot = not self.auto_shoot
                        elif event.key == pygame.K_r:
                            self.auto_spin = not self.auto_spin
                        elif event.key == pygame.K_g:
                            self.mouse_control_angle = not self.mouse_control_angle
                        elif event.key == pygame.K_q:
                            if self.menu.active:
                                self.menu.show_tank_upgrades()
                            else:
                                self.menu.active = True
                                self.menu.show_tank_upgrades()
                        elif event.key == pygame.K_e:
                            if self.menu.active:
                                self.menu.show_skill_upgrades()
                            else:
                                self.menu.active = True
                                self.menu.show_skill_upgrades()
                        elif event.key == pygame.K_LEFT:
                            pass  # Continuous in update
                        elif event.key == pygame.K_RIGHT:
                            pass  # Continuous in update
                        elif event.key == pygame.K_t:
                            self.chat_mode = True
                        elif event.key == pygame.K_b and self.menu.active and self.menu.current_menu in ('tank_menu', 'skill_menu'):
                            self.menu.buy_current_selection()
                        elif event.key == pygame.K_ESCAPE:
                            if self.menu.active:
                                if self.menu.current_menu != 'main':
                                    self.menu.back_to_main()
                                else:
                                    self.menu.active = False
    
    async def _connect_with_team(self, team_id):
        username = self.auth_screen.username_input
        if await self.game_client.connect_to_game(username, team_id):
            self.game_state = GameState.CONNECTING_TO_GAME
        else:
            self.team_selection_screen.error_message = "Failed to connect to game server"
            self.team_selection_screen.connecting = False
    
    def update(self):
        """Update game logic"""
        self.input_manager.update()
        if self.menu.active:
            self.menu.handle_input(self.input_manager)

        if self.menu.active or self.chat_mode:
            pygame.mouse.set_visible(True)
            pygame.event.set_grab(False)
        else:
            pygame.mouse.set_visible(False)
            pygame.event.set_grab(True)

        if self.game_state in (GameState.LOGIN, GameState.REGISTER) and self.auth_screen.auth_successful:
            self.auth_screen.auth_successful = False
            self.attempt_game_connection(self.auth_screen.username_input)
        
        if self.game_state == GameState.PLAYING:
            self._update_gameplay()
    
    def _update_gameplay(self):
        """Update gameplay"""
        if self.player_local_id not in self.game_client.players:
            return
        
        self.player_local = self.game_client.players[self.player_local_id]
        self.game_client.process_messages()
        
        # Update camera
        self.camera_pos.x = get_player_attr(self.player_local, 'x', 0)
        self.camera_pos.y = get_player_attr(self.player_local, 'y', 0)
        
        # Get input
        direction = self.input_manager.get_direction()
        if self.auto_spin:
            angle = math.sin(time.time() * 2) * math.pi
        elif self.mouse_control_angle:
            angle = self.input_manager.get_mouse_angle()
        else:
            if self.input_manager.is_pressed('left'):
                self.manual_angle -= 0.05
            if self.input_manager.is_pressed('right'):
                self.manual_angle += 0.05
            angle = self.manual_angle
        
        # Send movement with angle if not in chat mode
        if not self.chat_mode:
            current_time = time.time()
            if current_time - self.last_send_time > self.send_rate:
                asyncio.create_task(
                    self.game_client.send_move(direction.x, direction.y, angle)
                )
                self.last_send_time = current_time
        
        # Handle shooting
        if not self.chat_mode and not self.menu.active:
            if self.auto_shoot or self.input_manager.is_pressed('shoot'):
                asyncio.create_task(self.game_client.send_shoot(angle))
            
            if self.auto_spin:
                spin_angle = math.sin(time.time() * 2) * math.pi
                asyncio.create_task(self.game_client.send_shoot(spin_angle))
        
        # Update camera
        if self.player_local:
            target_x = self.player_local.x
            target_y = self.player_local.y
            
            smoothing = CLIENT_CONFIG.get('gameplay', {}).get('camera_smoothing', 0.1)
            self.camera_pos.x += (target_x - self.camera_pos.x) * smoothing
            self.camera_pos.y += (target_y - self.camera_pos.y) * smoothing
    
    def attempt_game_connection(self, username):
        """Attempt to connect to game server"""
        print("[DEBUG] Attempting to connect to game server...")
        self.game_state = GameState.CONNECTING_TO_GAME
        self.connecting_screen = ConnectingScreen(self.game_client)
        asyncio.create_task(self._connect_to_game_async(username, self.start_team))
    
    async def _connect_to_game_async(self, username, team):
        """Async connection to game server"""
        try:
            result = await self.game_client.connect_to_game(username, team)
            if result:
                self.game_state = GameState.PLAYING
                self.player_local_id = self.game_client.player_id
                print("[DEBUG] Successfully connected to game!")
            else:
                if not self.game_client.connection_error:
                    self.game_client.connection_error = "Failed to connect to game server"
                self.game_state = GameState.ERROR
                self.error_screen = ErrorScreen(self.game_client.connection_error)
        except Exception as e:
            print(f"[ERROR] Connection failed: {e}")
            self.game_client.connection_error = str(e)
            self.game_state = GameState.ERROR
            self.error_screen = ErrorScreen(str(e))
    
    def attempt_admin_login(self):
        """Attempt admin login with hardcoded credentials"""
        # For demo, use first admin credential
        admin_creds = SERVER_INDEX_DATA.get('admin', {}).get('credentials', {})
        if admin_creds:
            username = list(admin_creds.keys())[0]
            password = admin_creds[username]
            asyncio.create_task(self._admin_login_async(username, password))
    
    async def _admin_login_async(self, username, password):
        """Async admin login"""
        try:
            # Send admin login message
            await self.game_client.websocket.send(json.dumps({
                "type": "admin_login",
                "username": username,
                "password": password
            }))
            print(f"[DEBUG] Attempted admin login for {username}")
            # Note: Response handling would need to be added in _handle_message
        except Exception as e:
            print(f"[ERROR] Admin login failed: {e}")
    def draw(self):
        """Draw game screen"""
        if self.game_state == GameState.SERVER_SELECTION:
            self.server_selection_screen.draw(screen)
        
        elif self.game_state == GameState.TEAM_SELECTION:
            self.team_selection_screen.draw(screen)
        
        elif self.game_state in (GameState.LOGIN, GameState.REGISTER):
            self.auth_screen.draw(screen)
        
        elif self.game_state == GameState.CONNECTING_TO_GAME:
            self.connecting_screen.draw(screen)
            
            if self.game_client.connection_error:
                time.sleep(2)
                self.game_state = GameState.ERROR
                self.error_screen = ErrorScreen(self.game_client.connection_error)
        
        elif self.game_state == GameState.ERROR:
            if self.error_screen:
                self.error_screen.draw(screen)
        
        elif self.game_state == GameState.PLAYING:
            # Draw world
            player_list = list(self.game_client.players.values())
            blob_list = list(self.game_client.blobs.values())
            bullet_list = list(self.game_client.bullets.values())
            
            brightness = self.game_client.day_night_info.get('brightness', 1.0)
            self.renderer.draw_world(screen, player_list, blob_list, bullet_list,
                                    (self.camera_pos.x, self.camera_pos.y), brightness,
                                    self.player_local, self.start_team)
            
            # Draw HUD
            if self.player_local:
                player_dict = {
                    'id': self.player_local.id,
                    'health': self.player_local.health,
                    'max_health': self.player_local.max_health,
                    'resources': self.player_local.resources,
                    'money': self.player_local.money,
                    'rank': self.player_local.rank,
                    'tank': self.player_local.tank_name,
                    'team': self.player_local.team
                }
                self.renderer.draw_hud(screen, player_dict, player_list)
            
            # Draw chat
            self._draw_chat()
            
            # Draw status
            y_offset = SCREEN_HEIGHT - 100
            mouse_control_status = "MOUSE" if self.mouse_control_angle else "KEYS"
            mouse_control_color = (100, 255, 100) if self.mouse_control_angle else (150, 150, 150)
            mouse_control_text = text_cache.get(f"ANGLE CONTROL: {mouse_control_status} (G)", font_tiny, mouse_control_color)
            screen.blit(mouse_control_text, (SCREEN_WIDTH - 250, y_offset))
            y_offset -= 30

            auto_shoot_status = "ON" if self.auto_shoot else "OFF"
            auto_shoot_color = (100, 255, 100) if self.auto_shoot else (150, 150, 150)
            auto_shoot_text = text_cache.get(f"AUTO-SHOOT: {auto_shoot_status} (F)", font_tiny, auto_shoot_color)
            screen.blit(auto_shoot_text, (SCREEN_WIDTH - 250, y_offset))
            y_offset -= 30

            auto_spin_status = "ON" if self.auto_spin else "OFF"
            auto_spin_color = (100, 255, 100) if self.auto_spin else (150, 150, 150)
            auto_spin_text = text_cache.get(f"AUTO-SPIN: {auto_spin_status} (R)", font_tiny, auto_spin_color)
            screen.blit(auto_spin_text, (SCREEN_WIDTH - 250, y_offset))

            if self.chat_mode:
                chat_input_text = text_cache.get(f"Chat: {self.chat_input}_", font_small, (200, 255, 200))
                screen.blit(chat_input_text, (20, SCREEN_HEIGHT - 50))

        # Draw menu
        self.menu.draw(screen)
        pygame.display.flip()

    def _draw_chat(self):
        """Draw chat messages"""
        y_offset = SCREEN_HEIGHT - 180
        current_time = time.time()

        for msg in self.game_client.chat_messages[-8:]:
            if current_time - msg.get('timestamp', 0) > 10:
                continue

            username = msg['username']
            message = msg['message']
            if username == 'SYSTEM':
                color = (255, 255, 100)
            else:
                color = (200, 200, 200)

            chat_text = text_cache.get(f"{username}: {message}", font_tiny, color)
            screen.blit(chat_text, (20, y_offset))
            y_offset -= 20

    async def run_async(self):
        """Async main loop"""
        while self.running:
            self.handle_events()
            self.update()
            self.draw()
            clock.tick(FPS)
            await asyncio.sleep(0)

    def run(self):
        """Main game loop"""
        try:
            self.loop.run_until_complete(self.run_async())
        except KeyboardInterrupt:
            pass
        finally:
            self.game_client.disconnect()
            pygame.quit()
            self.loop.close()

# ==================== MAIN ====================
def main():
    game = Game()
    game.run()

if __name__ == "__main__":
    main()
            
