import asyncio
import json

class Spectator:
    def __init__(self, player_id, watched_player_id=None):
        self.player_id = player_id
        self.watched_player_id = watched_player_id
        self.is_spectating = True
        self.view_mode = "follow"  # follow, free_cam, minimap
    
    def switch_target(self, player_id):
        """Switch spectated player"""
        self.watched_player_id = player_id
    
    def set_view_mode(self, mode):
        """Change view mode"""
        if mode in ["follow", "free_cam", "minimap"]:
            self.view_mode = mode
    
    def to_dict(self):
        return {
            "player_id": self.player_id,
            "watched_player_id": self.watched_player_id,
            "view_mode": self.view_mode
        }

class SpectatorManager:
    def __init__(self):
        self.spectators = {}  # {spectator_id: Spectator}
    
    def add_spectator(self, player_id, watched_player_id=None):
        """Add spectator"""
        spectator = Spectator(player_id, watched_player_id)
        self.spectators[player_id] = spectator
        return spectator
    
    def remove_spectator(self, player_id):
        """Remove spectator"""
        if player_id in self.spectators:
            del self.spectators[player_id]
    
    async def broadcast_spectator_view(self, players, blobs, bullets):
        """Broadcast game state for spectators"""
        for spectator in self.spectators.values():
            if spectator.view_mode == "follow" and spectator.watched_player_id:
                player = players.get(spectator.watched_player_id)
                if player:
                    yield {
                        "type": "spectator_view",
                        "spectator_id": spectator.player_id,
                        "camera_x": player.x,
                        "camera_y": player.y,
                        "players": [p.to_dict() for p in players.values()],
                        "blobs": [b.to_dict() for b in blobs],
                        "bullets": [b.to_dict() for b in bullets]
                    }
            elif spectator.view_mode == "minimap":
                yield {
                    "type": "minimap_view",
                    "spectator_id": spectator.player_id,
                    "players": [p.to_dict() for p in players.values()],
                    "blobs": [b.to_dict() for b in blobs]
                }
    
    def get_spectators_for_player(self, player_id):
        """Get list of spectators watching specific player"""
        return [s for s in self.spectators.values() 
                if s.watched_player_id == player_id]