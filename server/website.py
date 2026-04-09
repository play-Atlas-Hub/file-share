from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import os
import json

# Get the directory where this script is located
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, 'templates')
STATIC_DIR = os.path.join(BASE_DIR, 'static')

# Create Flask app
app = Flask(__name__, template_folder=TEMPLATE_DIR, static_folder=STATIC_DIR)
CORS(app)

# ==================== ROUTES ====================

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login')
def login_page():
    return render_template('login.html')

@app.route('/register')
def register_page():
    return render_template('register.html')

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

@app.route('/admin')
def admin_panel():
    return render_template('admin.html')

# ==================== API ROUTES ====================

@app.route('/api/leaderboard', methods=['GET'])
def get_leaderboard():
    return jsonify([
        {"username": "Player1", "total_kills": 100, "total_money": 5000, "current_rank": 5},
        {"username": "Player2", "total_kills": 85, "total_money": 4200, "current_rank": 6},
        {"username": "Player3", "total_kills": 72, "total_money": 3800, "current_rank": 7},
    ])

@app.route('/api/stats', methods=['GET'])
def get_stats():
    return jsonify({
        'total_kills': 0,
        'total_deaths': 0,
        'total_assists': 0,
        'total_money': 0,
        'total_games_played': 0,
        'current_rank': 1,
        'best_rank': 1,
        'playtime_hours': 0,
        'win_rate': 0.0
    })

@app.route('/api/tanks', methods=['GET'])
def get_tanks():
    return jsonify([
        {"name": "Basic", "cost": 0, "min_rank": 1},
        {"name": "Fire", "cost": 100, "min_rank": 2},
        {"name": "Ice", "cost": 100, "min_rank": 2},
    ])

@app.route('/api/upgrades', methods=['GET'])
def get_upgrades():
    return jsonify([
        {"name": "Speed Boost", "slot": "engine", "cost": 50},
        {"name": "Shield", "slot": "armor", "cost": 75},
        {"name": "Damage+", "slot": "weapon", "cost": 100},
    ])

@app.route('/api/game-modes', methods=['GET'])
def get_game_modes():
    return jsonify([
        {"name": "Free For All", "max_players": 32},
        {"name": "Team Battle", "max_players": 64},
        {"name": "Capture Flag", "max_players": 16},
    ])

@app.route('/api/server-status', methods=['GET'])
def server_status():
    return jsonify({"status": "online", "players_online": 0})

@app.route('/api/admin/users', methods=['GET'])
def admin_get_users():
    return jsonify([
        {"user_id": "1", "username": "Admin", "email": "admin@game.com", "is_banned": 0},
        {"user_id": "2", "username": "Player1", "email": "player1@game.com", "is_banned": 0},
    ])

@app.errorhandler(404)
def not_found(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def server_error(error):
    return render_template('500.html'), 500

if __name__ == '__main__':
    print("="*60)
    print("Tank Battle Arena - Website")
    print("="*60)
    print("\nStarting website on http://localhost:5000")
    print("\nPress Ctrl+C to stop\n")
    
    app.run(host='0.0.0.0', port=5001, debug=False)