import asyncio
import json
import uuid
from enum import Enum
from datetime import datetime

# ==================== LOBBY STATES ====================
class LobbyState(Enum):
    WAITING = "waiting"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    FINISHED = "finished"

# ==================== LOBBY CLASS ====================
class Lobby:
    def __init__(self, lobby_id, game_mode, max_players=32):
        self.id = lobby_id
        self.game_mode = game_mode
        self.max_players = max_players
        self.players = {}  # {player_id: player_obj}
        self.state = LobbyState.WAITING
        self.created_at = datetime.now()
        self.started_at = None
        self.teams = {i: [] for i in range(1, 5)}
        self.team_scores = {i: 0 for i in range(1, 5)}
        self.spectators = set()
        self.is_voting = False
        self.votes = {}
        self.chat_history = []
    
    def add_player(self, player_id, player_obj):
        """Add player to lobby"""
        if len(self.players) >= self.max_players:
            return False
        self.players[player_id] = player_obj
        return True
    
    def remove_player(self, player_id):
        """Remove player from lobby"""
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
    
    def auto_balance_teams(self):
        """Auto-balance teams based on player count"""
        player_list = list(self.players.values())
        random_players = sorted(player_list, key=lambda x: x.kills)
        
        # Reset teams
        for team in self.teams:
            self.teams[team] = []
        
        # Distribute players evenly
        for i, player in enumerate(player_list):
            team = (i % len(self.teams)) + 1
            self.teams[team].append(player.id)
            player.team = team
    
    def start_game(self):
        """Start the game"""
        self.state = LobbyState.IN_PROGRESS
        self.started_at = datetime.now()
        return True
    
    def end_game(self):
        """End the game"""
        self.state = LobbyState.FINISHED
    
    def add_spectator(self, player_id):
        """Add player as spectator"""
        self.spectators.add(player_id)
    
    def get_status(self):
        return {
            "lobby_id": self.id,
            "game_mode": self.game_mode,
            "state": self.state.value,
            "players_count": len(self.players),
            "max_players": self.max_players,
            "players": {pid: p.to_dict() for pid, p in self.players.items()},
            "spectators": list(self.spectators),
            "teams": self.teams,
            "team_scores": self.team_scores,
            "created_at": str(self.created_at)
        }

# ==================== MATCHMAKING QUEUE ====================
class MatchmakingQueue:
    def __init__(self):
        self.queue = []
        self.waiting_players = {}  # {player_id: (player_obj, timestamp)}
    
    def add_player(self, player_id, player_obj):
        """Add player to matchmaking queue"""
        self.queue.append(player_id)
        self.waiting_players[player_id] = (player_obj, datetime.now())
    
    def remove_player(self, player_id):
        """Remove player from queue"""
        if player_id in self.queue:
            self.queue.remove(player_id)
        if player_id in self.waiting_players:
            del self.waiting_players[player_id]
    
    async def process_queue(self, lobbies, config):
        """Process matchmaking queue and create games"""
        min_players = config.get('tournament', {}).get('min_players', 4)
        
        while len(self.queue) >= min_players:
            # Get next batch of players
            batch = self.queue[:min_players]
            self.queue = self.queue[min_players:]
            
            # Create lobby
            lobby_id = str(uuid.uuid4())
            lobby = Lobby(lobby_id, "Ranked Match", min_players)
            
            for player_id in batch:
                player_obj, _ = self.waiting_players[player_id]
                lobby.add_player(player_id, player_obj)
                del self.waiting_players[player_id]
            
            # Auto-balance teams
            lobby.auto_balance_teams()
            lobbies[lobby_id] = lobby
            
            # Notify players
            yield lobby

# ==================== GAME MODE VOTING ====================
class GameModeVoting:
    def __init__(self, modes, timeout_seconds=30):
        self.available_modes = modes
        self.votes = {mode['name']: 0 for mode in modes}
        self.voted_players = set()
        self.timeout = timeout_seconds
        self.started_at = datetime.now()
    
    def vote(self, player_id, mode_name):
        """Vote for game mode"""
        if player_id in self.voted_players:
            return False
        if mode_name not in self.votes:
            return False
        
        self.votes[mode_name] += 1
        self.voted_players.add(player_id)
        return True
    
    def is_expired(self):
        """Check if voting time expired"""
        elapsed = (datetime.now() - self.started_at).total_seconds()
        return elapsed > self.timeout
    
    def get_winner(self):
        """Get winning game mode"""
        if not self.votes:
            return self.available_modes[0]['name']
        return max(self.votes, key=self.votes.get)
    
    def get_status(self):
        return {
            "votes": self.votes,
            "voted_players": len(self.voted_players),
            "time_remaining": max(0, self.timeout - (datetime.now() - self.started_at).total_seconds())
        }

# ==================== TOURNAMENT BRACKET ====================
class TournamentBracket:
    def __init__(self, tournament_id, players, bracket_type="single_elimination"):
        self.id = tournament_id
        self.players = players
        self.bracket_type = bracket_type
        self.rounds = []
        self.generate_bracket()
    
    def generate_bracket(self):
        """Generate bracket structure"""
        import math
        
        players = self.players[:]
        round_num = 0
        
        while len(players) > 1:
            round_num += 1
            matches = []
            
            # Pair players for matches
            for i in range(0, len(players), 2):
                if i + 1 < len(players):
                    match = {
                        "match_id": f"{self.id}_R{round_num}_M{i//2}",
                        "player1": players[i],
                        "player2": players[i + 1],
                        "winner": None,
                        "score1": 0,
                        "score2": 0
                    }
                    matches.append(match)
                else:
                    # Bye
                    matches.append({
                        "match_id": f"{self.id}_R{round_num}_BYE{i//2}",
                        "player1": players[i],
                        "player2": None,
                        "winner": players[i],
                        "score1": 1,
                        "score2": 0
                    })
            
            self.rounds.append(matches)
            
            # Advance winners to next round
            players = [m["winner"] for m in matches if m["winner"]]
    
    def record_match_result(self, round_num, match_num, winner_id):
        """Record match result"""
        if round_num < len(self.rounds):
            match = self.rounds[round_num][match_num]
            match["winner"] = winner_id
    
    def get_status(self):
        return {
            "tournament_id": self.id,
            "bracket_type": self.bracket_type,
            "rounds": self.rounds
        }

# ==================== INTEGRATION WITH SERVER ====================
class GameManager:
    def __init__(self, config):
        self.config = config
        self.lobbies = {}
        self.matchmaking = MatchmakingQueue()
        self.active_voting = {}  # {lobby_id: GameModeVoting}
        self.tournaments = {}
    
    async def create_lobby(self, game_mode, max_players=32):
        """Create new lobby"""
        lobby_id = str(uuid.uuid4())
        lobby = Lobby(lobby_id, game_mode, max_players)
        self.lobbies[lobby_id] = lobby
        return lobby
    
    async def join_lobby(self, player_id, player_obj, lobby_id=None):
        """Join or create lobby"""
        if lobby_id and lobby_id in self.lobbies:
            lobby = self.lobbies[lobby_id]
            if lobby.add_player(player_id, player_obj):
                return lobby
        
        # Create new lobby if none available
        game_mode = self.config['game_modes']['initial']
        lobby = await self.create_lobby(game_mode)
        lobby.add_player(player_id, player_obj)
        return lobby
    
    async def create_tournament(self, tournament_id, players):
        """Create tournament bracket"""
        bracket = TournamentBracket(tournament_id, players)
        self.tournaments[tournament_id] = bracket
        return bracket
    
    def get_lobbies_status(self):
        """Get all lobbies status"""
        return {lid: lobby.get_status() for lid, lobby in self.lobbies.items()}