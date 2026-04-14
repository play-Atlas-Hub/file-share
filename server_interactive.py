import asyncio
import json
import math
import sys
import time
import websockets
import pygame
from enum import Enum

# ==================== PYGAME SETUP ====================
pygame.init()
pygame.font.init()

SCREEN_WIDTH = 1400
SCREEN_HEIGHT = 900
FPS = 84

screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption("Server Interactive Admin Tool")
clock = pygame.time.Clock()

# Fonts
font_large = pygame.font.Font(None, 36)
font_medium = pygame.font.Font(None, 28)
font_small = pygame.font.Font(None, 20)
font_tiny = pygame.font.Font(None, 16)

# Colors
COLORS = {
    'background': (20, 20, 20),
    'grid': (40, 40, 40),
    'text': (255, 255, 255),
    'text_highlight': (100, 255, 100),
    'button': (60, 60, 60),
    'button_hover': (80, 80, 80),
    'player_self': (100, 255, 100),
    'player_enemy': (255, 100, 100),
    'blob': (200, 200, 200),
    'bullet': (255, 255, 0),
    'menu_bg': (30, 30, 30),
    'menu_border': (100, 100, 100)
}

# ==================== GAME STATE ====================
class AdminState(Enum):
    CONNECTING = "connecting"
    LOGIN = "login"
    CONNECTED = "connected"
    MENU = "menu"

class ServerInteractive:
    def __init__(self):
        self.state = AdminState.CONNECTING
        self.websocket = None
        self.player_id = None
        self.is_admin = False
        
        # Game data
        self.players = {}
        self.blobs = {}
        self.bullets = {}
        self.lobbies = {}
        self.day_night = {'is_day': True, 'cycle_time': 0, 'brightness': 1.0}
        
        # UI state
        self.menu_open = False
        self.selected_command = None
        self.command_params = {}
        self.selected_player = None
        self.selected_blob = None
        
        # Camera
        self.camera_x = 0
        self.camera_y = 0
        self.zoom = 1.0
        
        # Input
        self.text_input = ""
        self.input_active = False
        
        # Server config
        self.world_width = 9280  # 10 screens
        self.world_height = 6240  # 8 screens
        self.screen_width = 928
        self.screen_height = 522

    async def connect(self, server_url="ws://localhost:8765"):
        try:
            self.websocket = await websockets.connect(server_url)
            self.state = AdminState.LOGIN
            print("Connected to server")
        except Exception as e:
            print(f"Connection failed: {e}")
            self.state = AdminState.CONNECTING

    async def login(self, username, password):
        if not self.websocket:
            return False
        
        try:
            # First login to auth server
            auth_ws = await websockets.connect("ws://localhost:8766")
            await auth_ws.send(json.dumps({
                "action": "login",
                "username": username,
                "password": password
            }))
            
            response = json.loads(await auth_ws.recv())
            if not response.get('success'):
                print("Login failed")
                return False
            
            token = response.get('token')
            await auth_ws.close()
            
            # Now connect to game server
            await self.websocket.send(json.dumps({
                "token": token,
                "username": username,
                "team": 1
            }))
            
            welcome = json.loads(await asyncio.wait_for(self.websocket.recv(), timeout=5.0))
            if welcome.get('type') == 'welcome':
                self.player_id = welcome['player_id']
                self.state = AdminState.CONNECTED
                print("Logged in as admin")
                
                # Login as admin
                await self.websocket.send(json.dumps({
                    "type": "admin_login",
                    "username": username,
                    "password": password
                }))
                
                return True
            else:
                print("Game connection failed")
                return False
                
        except Exception as e:
            print(f"Login error: {e}")
            return False

    async def send_command(self, command, payload=None):
        if not self.websocket or not self.is_admin:
            return
        
        await self.websocket.send(json.dumps({
            "type": "admin_command",
            "command": command,
            "payload": payload or {}
        }))

    async def receive_messages(self):
        try:
            async for message in self.websocket:
                data = json.loads(message)
                self.handle_message(data)
        except Exception as e:
            print(f"Receive error: {e}")
            self.state = AdminState.CONNECTING

    def handle_message(self, data):
        msg_type = data.get('type')
        
        if msg_type == 'admin_login_response':
            self.is_admin = data.get('success', False)
            print(f"Admin login: {'success' if self.is_admin else 'failed'}")
        
        elif msg_type == 'admin_command_response':
            print(f"Command response: {data}")
        
        elif msg_type == 'state':
            self.update_game_state(data)
        
        elif msg_type == 'welcome':
            pass  # Already handled
        
        elif msg_type == 'server_config':
            pass  # Already handled

    def update_game_state(self, data):
        # Update players
        for player_data in data.get('players', []):
            pid = player_data['id']
            if pid not in self.players:
                self.players[pid] = player_data
            else:
                self.players[pid].update(player_data)
        
        # Remove disconnected players
        current_pids = {p['id'] for p in data.get('players', [])}
        self.players = {pid: p for pid, p in self.players.items() if pid in current_pids}
        
        # Update blobs
        for blob_data in data.get('blobs', []):
            bid = blob_data['id']
            self.blobs[bid] = blob_data
        
        # Update bullets
        for bullet_data in data.get('bullets', []):
            bid = bullet_data['id']
            self.bullets[bid] = bullet_data
        
        # Update day/night
        self.day_night = data.get('day_night', self.day_night)

    def draw_world(self, surface):
        # Clear
        surface.fill(COLORS['background'])
        
        # Draw grid
        grid_size = 100
        for x in range(0, self.world_width, grid_size):
            screen_x = (x - self.camera_x) * self.zoom + SCREEN_WIDTH // 2
            if 0 <= screen_x <= SCREEN_WIDTH:
                pygame.draw.line(surface, COLORS['grid'], 
                               (screen_x, 0), (screen_x, SCREEN_HEIGHT))
        
        for y in range(0, self.world_height, grid_size):
            screen_y = (y - self.camera_y) * self.zoom + SCREEN_HEIGHT // 2
            if 0 <= screen_y <= SCREEN_WIDTH:
                pygame.draw.line(surface, COLORS['grid'], 
                               (0, screen_y), (SCREEN_WIDTH, screen_y))
        
        # Draw blobs
        for blob in self.blobs.values():
            x = (blob['x'] - self.camera_x) * self.zoom + SCREEN_WIDTH // 2
            y = (blob['y'] - self.camera_y) * self.zoom + SCREEN_HEIGHT // 2
            
            if 0 <= x <= SCREEN_WIDTH and 0 <= y <= SCREEN_HEIGHT:
                radius = max(2, int(blob.get('radius', 8) * self.zoom))
                color = (200, 200, 200)
                pygame.draw.circle(surface, color, (int(x), int(y)), radius)
                
                # HP bar
                bar_width = radius * 2
                bar_height = 4
                hp_ratio = blob['hp'] / blob['max_hp']
                pygame.draw.rect(surface, (255, 0, 0), 
                               (x - bar_width//2, y - radius - 10, bar_width, bar_height))
                pygame.draw.rect(surface, (0, 255, 0), 
                               (x - bar_width//2, y - radius - 10, bar_width * hp_ratio, bar_height))
        
        # Draw bullets
        for bullet in self.bullets.values():
            x = (bullet['x'] - self.camera_x) * self.zoom + SCREEN_WIDTH // 2
            y = (bullet['y'] - self.camera_y) * self.zoom + SCREEN_HEIGHT // 2
            
            if 0 <= x <= SCREEN_WIDTH and 0 <= y <= SCREEN_HEIGHT:
                radius = max(1, int(bullet.get('radius', 3) * self.zoom))
                pygame.draw.circle(surface, COLORS['bullet'], (int(x), int(y)), radius)
        
        # Draw players
        for player in self.players.values():
            if not player.get('alive', True):
                continue
                
            x = (player['x'] - self.camera_x) * self.zoom + SCREEN_WIDTH // 2
            y = (player['y'] - self.camera_y) * self.zoom + SCREEN_HEIGHT // 2
            
            if 0 <= x <= SCREEN_WIDTH and 0 <= y <= SCREEN_HEIGHT:
                radius = max(5, int(player.get('radius', 15) * self.zoom))
                color = COLORS['player_self'] if player['id'] == self.player_id else COLORS['player_enemy']
                
                # Highlight selected
                if self.selected_player == player['id']:
                    pygame.draw.circle(surface, (255, 255, 255), (int(x), int(y)), radius + 3, 2)
                
                pygame.draw.circle(surface, color, (int(x), int(y)), radius)
                
                # Name
                name_text = font_tiny.render(player['username'], True, COLORS['text'])
                surface.blit(name_text, (x - name_text.get_width()//2, y - radius - 20))
                
                # Health bar
                bar_width = radius * 2
                bar_height = 4
                hp_ratio = player['health'] / player['max_health']
                pygame.draw.rect(surface, (255, 0, 0), 
                               (x - bar_width//2, y - radius - 10, bar_width, bar_height))
                pygame.draw.rect(surface, (0, 255, 0), 
                               (x - bar_width//2, y - radius - 10, bar_width * hp_ratio, bar_height))

    def draw_menu(self, surface):
        if not self.menu_open:
            return
        
        # Menu background
        menu_width = 400
        menu_height = 600
        menu_x = SCREEN_WIDTH - menu_width - 10
        menu_y = 10
        
        pygame.draw.rect(surface, COLORS['menu_bg'], (menu_x, menu_y, menu_width, menu_height))
        pygame.draw.rect(surface, COLORS['menu_border'], (menu_x, menu_y, menu_width, menu_height), 2)
        
        # Title
        title = font_medium.render("Admin Commands", True, COLORS['text_highlight'])
        surface.blit(title, (menu_x + 10, menu_y + 10))
        
        # Commands list
        commands = [
            "kick_player",
            "broadcast",
            "spawn_blob",
            "give_money",
            "give_resources",
            "set_game_mode",
            "set_player_health",
            "teleport_player",
            "spawn_blob_at",
            "clear_blobs",
            "set_day_night",
            "kill_player",
            "give_upgrade",
            "reset_player",
            "server_stats"
        ]
        
        y_offset = menu_y + 50
        for cmd in commands:
            color = COLORS['text_highlight'] if cmd == self.selected_command else COLORS['text']
            cmd_text = font_small.render(cmd, True, color)
            surface.blit(cmd_text, (menu_x + 10, y_offset))
            y_offset += 25
        
        # Parameters input
        if self.selected_command:
            param_text = font_small.render(f"Params: {self.command_params}", True, COLORS['text'])
            surface.blit(param_text, (menu_x + 10, y_offset + 20))

    def draw_ui(self, surface):
        # Status
        status_text = f"Status: {self.state.value} | Admin: {self.is_admin} | Players: {len(self.players)}"
        status_render = font_small.render(status_text, True, COLORS['text'])
        surface.blit(status_render, (10, 10))
        
        # Controls help
        help_text = "M: Menu | Click: Select | WASD: Move Camera | QE: Zoom | Enter: Execute Command"
        help_render = font_tiny.render(help_text, True, COLORS['text'])
        surface.blit(help_render, (10, SCREEN_HEIGHT - 30))

    def handle_click(self, pos):
        # Convert screen to world coordinates
        world_x = (pos[0] - SCREEN_WIDTH // 2) / self.zoom + self.camera_x
        world_y = (pos[1] - SCREEN_HEIGHT // 2) / self.zoom + self.camera_y
        
        # Check players
        for player in self.players.values():
            if not player.get('alive', True):
                continue
            dist = math.sqrt((world_x - player['x'])**2 + (world_y - player['y'])**2)
            if dist <= player.get('radius', 15):
                self.selected_player = player['id']
                self.selected_blob = None
                return
        
        # Check blobs
        for blob in self.blobs.values():
            dist = math.sqrt((world_x - blob['x'])**2 + (world_y - blob['y'])**2)
            if dist <= blob.get('radius', 8):
                self.selected_blob = blob['id']
                self.selected_player = None
                return
        
        self.selected_player = None
        self.selected_blob = None

    def handle_input(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_m:
                self.menu_open = not self.menu_open
            elif event.key == pygame.K_RETURN and self.selected_command:
                # Execute command
                asyncio.create_task(self.send_command(self.selected_command, self.command_params))
                self.selected_command = None
                self.command_params = {}
            elif event.key == pygame.K_BACKSPACE:
                self.text_input = self.text_input[:-1]
            elif event.unicode:
                self.text_input += event.unicode
        
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:  # Left click
                self.handle_click(event.pos)

    def update_camera(self, keys):
        speed = 10 / self.zoom
        if keys[pygame.K_a]:
            self.camera_x -= speed
        if keys[pygame.K_d]:
            self.camera_x += speed
        if keys[pygame.K_w]:
            self.camera_y -= speed
        if keys[pygame.K_s]:
            self.camera_y += speed
        
        if keys[pygame.K_q]:
            self.zoom = max(0.1, self.zoom - 0.01)
        if keys[pygame.K_e]:
            self.zoom = min(5.0, self.zoom + 0.01)

    async def run(self):
        running = True
        
        # Start message receiver
        if self.websocket:
            asyncio.create_task(self.receive_messages())
        
        while running:
            keys = pygame.key.get_pressed()
            
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                else:
                    self.handle_input(event)
            
            self.update_camera(keys)
            
            # Draw
            self.draw_world(screen)
            self.draw_menu(screen)
            self.draw_ui(screen)
            
            pygame.display.flip()
            clock.tick(FPS)
            
            await asyncio.sleep(0)

async def main():
    admin_tool = ServerInteractive()
    
    # Connect and login
    await admin_tool.connect()
    if admin_tool.state == AdminState.LOGIN:
        # For demo, use hardcoded credentials - in real use, prompt for input
        success = await admin_tool.login("AdminUser1", "Admin@U1")
        if success:
            await admin_tool.run()

if __name__ == "__main__":
    asyncio.run(main())